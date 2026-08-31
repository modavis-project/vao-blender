"""Managed content-addressed extraction cache with tamper checks.

The cache is deliberately conservative about ownership. An unmarked directory
is adopted only when it is empty, and destructive operations are limited to the
two subdirectories named in the ownership marker. Cache mutations are
serialized across threads and processes so extraction, quota enforcement, and
clear cannot observe one another half-complete.
"""

from __future__ import annotations

import errno
import hashlib
import json
import os
import shutil
import stat
import threading
import time
import uuid
import zipfile
from collections import Counter
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from .cancellation import CancellationToken
from .model import AssetRecord

MARKER = ".vao-blender-cache"
MARKER_VERSION = 2
MARKER_MAX_BYTES = 4096
CHUNK_SIZE = 4 * 1024 * 1024
_MANAGED_CHILDREN = ("assets", "quarantine")
_LOCKS_CHILD = ".locks"
_PARTIAL_SUFFIX = ".partial"


class CacheError(RuntimeError):
    pass


def _is_linklike(path: Path) -> bool:
    """Return whether a path redirects traversal (symlink or Windows junction)."""
    return path.is_symlink() or bool(getattr(path, "is_junction", lambda: False)())


def _digest(path: Path, token: CancellationToken | None = None) -> tuple[int, str]:
    checksum = hashlib.sha256()
    count = 0
    if token:
        token.check()
    with path.open("rb") as stream:
        while chunk := stream.read(CHUNK_SIZE):
            if token:
                token.check()
            count += len(chunk)
            checksum.update(chunk)
    return count, checksum.hexdigest()


def _open_private_output(path: Path):
    """Create one non-following, owner-only binary output stream."""
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_BINARY", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags, 0o600)
    try:
        stream = os.fdopen(descriptor, "wb")
    except BaseException:
        os.close(descriptor)
        raise
    return stream


_THREAD_LOCKS_GUARD = threading.Lock()
_THREAD_LOCKS: dict[str, threading.RLock] = {}
_PROTECTION_GUARD = threading.RLock()
_PROTECTED: dict[str, Counter[str]] = {}
_PROTECTION_LEASES: dict[tuple[str, str], "_AssetLease"] = {}


def _thread_lock(path: Path) -> threading.RLock:
    key = os.fspath(path)
    with _THREAD_LOCKS_GUARD:
        return _THREAD_LOCKS.setdefault(key, threading.RLock())


def _lock_contended(exc: OSError) -> bool:
    return (
        exc.errno in {errno.EACCES, errno.EAGAIN, errno.EDEADLK}
        or getattr(exc, "winerror", None) == 33
    )


class _ProcessFileLock:
    """Cross-thread and cross-process exclusive advisory lock."""

    def __init__(self, path: Path, cancellation: CancellationToken | None = None) -> None:
        self.path = path
        self.cancellation = cancellation
        self._stream = None
        self._thread_lock = _thread_lock(path)

    def __enter__(self) -> _ProcessFileLock:
        if self.cancellation is None:
            self._thread_lock.acquire()
        else:
            while True:
                self.cancellation.check()
                if self._thread_lock.acquire(timeout=0.05):
                    break
        try:
            flags = os.O_CREAT | os.O_RDWR
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            descriptor = os.open(self.path, flags, 0o600)
            try:
                details = os.fstat(descriptor)
                if not stat.S_ISREG(details.st_mode):
                    raise CacheError(f"cache lock is not a regular file: {self.path}")
                if details.st_size == 0:
                    os.write(descriptor, b"\0")
                    os.fsync(descriptor)
                self._stream = os.fdopen(descriptor, "r+b", buffering=0)
                descriptor = -1
                self._acquire_process_lock()
            finally:
                if descriptor >= 0:
                    os.close(descriptor)
            return self
        except Exception:
            if self._stream is not None:
                self._stream.close()
                self._stream = None
            self._thread_lock.release()
            raise

    def _acquire_process_lock(self) -> None:
        assert self._stream is not None
        while True:
            if self.cancellation:
                self.cancellation.check()
            try:
                self._stream.seek(0)
                if os.name == "nt":  # pragma: no cover - native Windows CI
                    import msvcrt

                    msvcrt.locking(self._stream.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(self._stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                return
            except OSError as exc:
                if not _lock_contended(exc):
                    raise
                time.sleep(0.05)

    def __exit__(self, exc_type, exc, traceback) -> None:
        try:
            if self._stream is not None:
                stream = self._stream
                try:
                    if os.name == "nt":  # pragma: no cover - native Windows CI
                        import msvcrt

                        stream.seek(0)
                        msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
                    else:
                        import fcntl

                        fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
                finally:
                    stream.close()
                    self._stream = None
        finally:
            self._thread_lock.release()


class _AssetLease:
    """Exclusive lock on one process-unique active-asset lease file."""

    def __init__(
        self,
        path: Path,
        cancellation: CancellationToken | None = None,
    ) -> None:
        self.path = path
        self.cancellation = cancellation
        self._stream = None

    def acquire(self) -> None:
        self.path.parent.mkdir(mode=0o700, exist_ok=True)
        if _is_linklike(self.path.parent) or not self.path.parent.is_dir():
            raise CacheError("cache asset-lock directory is unsafe")
        flags = os.O_CREAT | os.O_EXCL | os.O_RDWR
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(self.path, flags, 0o600)
        try:
            details = os.fstat(descriptor)
            if not stat.S_ISREG(details.st_mode):
                raise CacheError(f"cache asset lock is not a regular file: {self.path}")
            if details.st_size == 0:
                os.write(descriptor, b"\0")
                os.fsync(descriptor)
            self._stream = os.fdopen(descriptor, "r+b", buffering=0)
            descriptor = -1
            while True:
                if self.cancellation:
                    self.cancellation.check()
                try:
                    self._stream.seek(0)
                    if os.name == "nt":  # pragma: no cover - native Windows CI
                        import msvcrt

                        msvcrt.locking(self._stream.fileno(), msvcrt.LK_NBLCK, 1)
                    else:
                        import fcntl

                        fcntl.flock(
                            self._stream.fileno(),
                            fcntl.LOCK_EX | fcntl.LOCK_NB,
                        )
                    return
                except OSError as exc:
                    if not _lock_contended(exc):
                        raise
                    time.sleep(0.05)
        except Exception:
            if self._stream is not None:
                self._stream.close()
                self._stream = None
            self.path.unlink(missing_ok=True)
            raise
        finally:
            if descriptor >= 0:
                os.close(descriptor)

    def release(self) -> None:
        if self._stream is None:
            return
        stream = self._stream
        try:
            try:
                if os.name == "nt":  # pragma: no cover - native Windows CI
                    import msvcrt

                    stream.seek(0)
                    msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
            finally:
                stream.close()
                self._stream = None
        finally:
            self.path.unlink(missing_ok=True)
            try:
                self.path.parent.rmdir()
            except (FileNotFoundError, OSError):
                # Other processes can hold sibling leases in the same directory.
                pass


class AssetCache:
    def __init__(self, root: str | os.PathLike[str], *, quota_bytes: int = 20 * 1024**3) -> None:
        # Do not resolve the final component: an explicitly selected symlink is
        # not an acceptable ownership boundary.
        self.root = Path(os.path.abspath(Path(root).expanduser()))
        self.quota_bytes = int(quota_bytes)
        if self.quota_bytes < 0:
            raise ValueError("cache quota must be non-negative")
        self.assets_root = self.root / "assets"
        self.quarantine_root = self.root / "quarantine"
        self.locks_root = self.root / _LOCKS_CHILD

    @property
    def _marker(self) -> Path:
        return self.root / MARKER

    @property
    def _mutation_lock(self) -> Path:
        return self.locks_root / "mutation.lock"

    @property
    def _asset_locks_root(self) -> Path:
        return self.locks_root / "assets"

    @property
    def _initialization_thread_lock(self) -> threading.RLock:
        # This key is process-local only and never creates an unowned file in
        # the prospective cache directory.
        return _thread_lock(self.root / f".{MARKER}.initialize")

    def _check_safe_root(self) -> None:
        unsafe = {Path("/").resolve(), Path.home().resolve(), Path.cwd().resolve()}
        if self.root.resolve() in unsafe:
            raise CacheError("refusing an unsafe cache root")
        if _is_linklike(self.root):
            raise CacheError("cache root must not be a symlink or junction")
        if self.root.exists() and not self.root.is_dir():
            raise CacheError("cache root is not a directory")

    @staticmethod
    def _marker_document() -> dict[str, object]:
        return {
            "managedChildren": list(_MANAGED_CHILDREN),
            "owner": "vao_blender",
            "version": MARKER_VERSION,
        }

    def _write_marker_for_empty_root(self, cancellation: CancellationToken | None = None) -> None:
        entries = list(self.root.iterdir())
        if entries:
            if self._marker in entries:
                # A concurrent initializer has already established ownership.
                self._await_managed_marker(cancellation)
                return
            raise CacheError(
                "refusing to adopt a non-empty unmarked directory as a VAO-Blender cache"
            )
        payload = (json.dumps(self._marker_document(), sort_keys=True) + "\n").encode("utf-8")
        # Publish a fully durable marker in one namespace operation. The
        # temporary file lives beside (not inside) the prospective cache root:
        # a crash before the link therefore leaves the root empty and safe to
        # retry, while a crash after the link leaves a complete marker.
        temporary = self.root.parent / (
            f".{self.root.name}.{MARKER}.{os.getpid()}.{uuid.uuid4().hex}.temporary"
        )
        descriptor = -1
        try:
            flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            descriptor = os.open(temporary, flags, 0o600)
            with os.fdopen(descriptor, "wb") as stream:
                descriptor = -1
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            try:
                os.link(temporary, self._marker, follow_symlinks=False)
            except TypeError:  # pragma: no cover - older Windows Python fallback
                os.link(temporary, self._marker)
        except FileExistsError:
            # Another initializer won the marker race. It must still be ours.
            self._await_managed_marker(cancellation)
            return
        except OSError as exc:
            raise CacheError("cache ownership marker could not be published atomically") from exc
        finally:
            if descriptor >= 0:
                os.close(descriptor)
            temporary.unlink(missing_ok=True)

    def _await_managed_marker(self, cancellation: CancellationToken | None = None) -> None:
        """Wait briefly for a concurrent or legacy ownership publisher."""
        deadline = time.monotonic() + 1.0
        while True:
            if cancellation:
                cancellation.check()
            try:
                self._require_managed()
                return
            except CacheError:
                if _is_linklike(self._marker) or time.monotonic() >= deadline:
                    raise
                time.sleep(0.01)

    def _ensure_directory(self, path: Path, description: str) -> None:
        if path.exists() or _is_linklike(path):
            if _is_linklike(path) or not path.is_dir():
                raise CacheError(f"{description} is not a safe directory: {path}")
            return
        # `exist_ok` handles another well-behaved initializer winning the
        # creation race. Re-check afterwards so a raced symlink is not trusted.
        path.mkdir(mode=0o700, exist_ok=True)
        if _is_linklike(path) or not path.is_dir():
            raise CacheError(f"{description} is not a safe directory: {path}")

    def initialize(self, *, cancellation: CancellationToken | None = None) -> None:
        lock = self._initialization_thread_lock
        if cancellation is None:
            lock.acquire()
        else:
            while True:
                cancellation.check()
                if lock.acquire(timeout=0.05):
                    break
        try:
            self._check_safe_root()
            self.root.mkdir(parents=True, exist_ok=True)
            self._check_safe_root()
            if self._marker.exists() or _is_linklike(self._marker):
                self._await_managed_marker(cancellation)
            else:
                self._write_marker_for_empty_root(cancellation)
            self._ensure_directory(self.locks_root, "cache lock directory")
            with _ProcessFileLock(self._mutation_lock, cancellation):
                self._require_managed()
                self._ensure_directory(
                    self._asset_locks_root,
                    "cache asset-lock directory",
                )
                self._ensure_directory(self.assets_root, "cache assets directory")
                self._ensure_directory(self.quarantine_root, "cache quarantine directory")
        finally:
            lock.release()

    def _require_managed(self) -> None:
        marker = self._marker
        if not marker.is_file() or _is_linklike(marker):
            raise CacheError("directory is not a marked VAO-Blender cache")
        descriptor = -1
        try:
            flags = os.O_RDONLY
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            descriptor = os.open(marker, flags)
            details = os.fstat(descriptor)
            if not stat.S_ISREG(details.st_mode):
                raise CacheError("cache marker is not a regular file")
            with os.fdopen(descriptor, "rb") as stream:
                descriptor = -1
                raw = stream.read(MARKER_MAX_BYTES + 1)
            if len(raw) > MARKER_MAX_BYTES:
                raise CacheError("cache marker is unexpectedly large")
            data = json.loads(raw.decode("utf-8"))
        except CacheError:
            raise
        except (OSError, UnicodeError, ValueError) as exc:
            raise CacheError("cache marker is unreadable") from exc
        finally:
            if descriptor >= 0:
                os.close(descriptor)
        legacy = {"owner": "vao_blender", "version": 1}
        if data != legacy and data != self._marker_document():
            raise CacheError("cache marker does not match this extension")

    @staticmethod
    def _validate_asset(asset: AssetRecord) -> None:
        digest = asset.sha256
        if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
            raise CacheError("asset SHA-256 must be 64 lowercase hexadecimal characters")
        if asset.byte_size < 0:
            raise CacheError("asset byte size must be non-negative")

    @staticmethod
    def _extension(asset: AssetRecord) -> str:
        extension = {
            "model/gltf-binary": ".glb",
            "model/gltf+json": ".gltf",
            "audio/wav": ".wav",
            "audio/x-wav": ".wav",
            "audio/wave": ".wav",
        }.get(asset.media_type, Path(asset.path).suffix.lower() or ".bin")
        if (
            len(extension) > 16
            or not extension.startswith(".")
            or not extension[1:].isalnum()
            or not extension.isascii()
        ):
            return ".bin"
        return extension

    def target_for(self, asset: AssetRecord) -> Path:
        self._validate_asset(asset)
        return self.assets_root / asset.sha256[:2] / f"{asset.sha256}{self._extension(asset)}"

    def _check_existing(
        self,
        path: Path,
        asset: AssetRecord,
        cancellation: CancellationToken | None = None,
    ) -> bool:
        if not path.exists() and not _is_linklike(path):
            return False
        if _is_linklike(path) or not path.is_file():
            raise CacheError(f"cache target is not a regular file: {path}")
        size, checksum = _digest(path, cancellation)
        if size == asset.byte_size and checksum == asset.sha256:
            os.utime(path, None)
            return True
        if path.resolve() in self._registered_protected() or self._has_cross_process_lease(
            path,
            cancellation,
        ):
            raise CacheError("refusing to quarantine a cached asset that is actively in use")
        self._ensure_directory(self.quarantine_root, "cache quarantine directory")
        destination = self.quarantine_root / (
            f"{path.name}.{time.time_ns()}.{uuid.uuid4().hex}.tampered"
        )
        os.replace(path, destination)
        # Quarantine is part of the same bounded cache. Enforce immediately so
        # a later archive/read failure cannot leave tampered bytes unbounded.
        self._enforce_quota_locked(cancellation=cancellation)
        return False

    def extract(
        self,
        archive_path: str | os.PathLike[str],
        asset: AssetRecord,
        *,
        cancellation: CancellationToken | None = None,
        protect: bool = False,
    ) -> Path:
        self.initialize(cancellation=cancellation)
        target = self.target_for(asset)
        # A single mutation lock is conservative but makes clear/quota/extract
        # atomic with respect to one another across both threads and processes.
        with _ProcessFileLock(self._mutation_lock, cancellation):
            self._require_managed()
            if asset.byte_size > self.quota_bytes:
                # Also clean any over-quota state left by an earlier, larger
                # configuration before rejecting this impossible extraction.
                self._enforce_quota_locked(cancellation=cancellation)
                raise CacheError(
                    f"asset requires {asset.byte_size} bytes but cache quota is "
                    f"{self.quota_bytes} bytes"
                )
            target.parent.mkdir(parents=True, exist_ok=True)
            if _is_linklike(target.parent) or not target.parent.is_dir():
                raise CacheError("cache shard directory is unsafe")
            if self._check_existing(target, asset, cancellation):
                self._enforce_quota_locked(
                    protected={target.resolve()},
                    cancellation=cancellation,
                )
                if protect:
                    self._register_protected_locked(target, cancellation)
                return target
            remaining = self._enforce_quota_locked(
                reserve_bytes=asset.byte_size,
                cancellation=cancellation,
            )
            if remaining + asset.byte_size > self.quota_bytes:
                raise CacheError(
                    "active cached assets leave insufficient quota for this extraction"
                )
            try:
                free_bytes = shutil.disk_usage(self.root).free
            except OSError as exc:
                raise CacheError("available cache disk space could not be determined") from exc
            if free_bytes < asset.byte_size:
                raise CacheError(
                    f"asset requires {asset.byte_size} free bytes but the cache volume has only "
                    f"{free_bytes}"
                )
            partial = target.with_name(
                f".{target.name}.{os.getpid()}.{threading.get_ident()}.{uuid.uuid4().hex}"
                f"{_PARTIAL_SUFFIX}"
            )
            checksum = hashlib.sha256()
            count = 0
            try:
                with zipfile.ZipFile(archive_path, "r", allowZip64=True) as zf:
                    matches = [info for info in zf.infolist() if info.filename == asset.path]
                    if not matches:
                        raise CacheError("validated archive asset is no longer present")
                    if len(matches) != 1:
                        raise CacheError("validated archive asset path is now duplicated")
                    info = matches[0]
                    if info.is_dir() or info.file_size != asset.byte_size:
                        raise CacheError("archive asset size changed after validation")
                    if info.flag_bits & 0x1:
                        raise CacheError("validated archive asset is now encrypted")
                    if info.compress_type not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}:
                        raise CacheError("validated archive asset compression is now unsupported")
                    with zf.open(info, "r") as source, _open_private_output(partial) as destination:
                        while chunk := source.read(CHUNK_SIZE):
                            if cancellation:
                                cancellation.check()
                            count += len(chunk)
                            if count > asset.byte_size:
                                raise CacheError("archive asset expanded beyond its declared size")
                            destination.write(chunk)
                            checksum.update(chunk)
                        destination.flush()
                        os.fsync(destination.fileno())
                if count != asset.byte_size or checksum.hexdigest() != asset.sha256:
                    raise CacheError("extracted asset failed SHA-256 verification")
                os.replace(partial, target)
                self._enforce_quota_locked(
                    protected={target.resolve()},
                    cancellation=cancellation,
                )
                if protect:
                    self._register_protected_locked(target, cancellation)
                return target
            except (CacheError, zipfile.BadZipFile):
                raise
            except OSError as exc:
                raise CacheError(f"cache extraction failed: {exc}") from exc
            finally:
                if partial.exists() and partial.is_file() and not _is_linklike(partial):
                    partial.unlink()

    def _normalize_owned_asset_path(self, path: str | os.PathLike[str]) -> Path:
        candidate = Path(path).expanduser().resolve()
        try:
            candidate.relative_to(self.assets_root.resolve())
        except ValueError as exc:
            raise CacheError("protected path is outside the managed asset cache") from exc
        if _is_linklike(candidate) or not candidate.is_file():
            raise CacheError("only an existing regular cached asset can be protected")
        return candidate

    def register_protected(self, path: str | os.PathLike[str]) -> Path:
        """Protect an in-use cached asset from quota eviction and cache clearing.

        Registrations are reference counted across local ``AssetCache`` instances
        and backed by process-unique advisory leases so other Blender processes
        also skip the file. Call ``unregister_protected`` when the session no
        longer uses it, or prefer ``protected``.
        """

        self.initialize()
        with _ProcessFileLock(self._mutation_lock):
            self._require_managed()
            return self._register_protected_locked(path)

    def _asset_lock_identifier(self, path: Path) -> str:
        return hashlib.sha256(os.fspath(path.resolve()).encode("utf-8")).hexdigest()

    def _new_asset_lease_path(self, path: Path) -> Path:
        identifier = self._asset_lock_identifier(path)
        return self._asset_locks_root / identifier / (f"{os.getpid()}.{uuid.uuid4().hex}.lease")

    def _register_protected_locked(
        self,
        path: str | os.PathLike[str],
        cancellation: CancellationToken | None = None,
    ) -> Path:
        candidate = self._normalize_owned_asset_path(path)
        root_key = os.fspath(self.root.resolve())
        path_key = os.fspath(candidate)
        lease_key = (root_key, path_key)
        with _PROTECTION_GUARD:
            counter = _PROTECTED.setdefault(root_key, Counter())
            if counter[path_key] == 0:
                lease = _AssetLease(self._new_asset_lease_path(candidate), cancellation)
                lease.acquire()
                _PROTECTION_LEASES[lease_key] = lease
            counter[path_key] += 1
        return candidate

    def unregister_protected(self, path: str | os.PathLike[str]) -> None:
        self.initialize()
        with _ProcessFileLock(self._mutation_lock):
            # Do not resolve the final component here. A non-cooperating writer
            # may have replaced an active file with a symlink, but the original
            # lexical cache path must still be releasable without leaking its
            # local registration or process lease.
            supplied = Path(os.path.abspath(Path(path).expanduser()))
            candidate = supplied.parent.resolve() / supplied.name
            root_key = os.fspath(self.root.resolve())
            key = os.fspath(candidate)
            lease = None
            with _PROTECTION_GUARD:
                counter = _PROTECTED.get(root_key)
                if counter is None or counter[key] <= 0:
                    raise CacheError("cached asset does not have an active protection registration")
                counter[key] -= 1
                if counter[key] == 0:
                    del counter[key]
                    lease = _PROTECTION_LEASES.pop((root_key, key), None)
                if not counter:
                    _PROTECTED.pop(root_key, None)
            if lease is not None:
                lease.release()

    @contextmanager
    def protected(self, *paths: str | os.PathLike[str]) -> Iterator[tuple[Path, ...]]:
        """Context manager for one or more active cached assets."""

        registered: list[Path] = []
        primary_error: BaseException | None = None
        try:
            for path in paths:
                registered.append(self.register_protected(path))
            yield tuple(registered)
        except BaseException as exc:
            primary_error = exc
            raise
        finally:
            cleanup_error: BaseException | None = None
            for path in reversed(registered):
                try:
                    self.unregister_protected(path)
                except BaseException as exc:
                    if primary_error is not None:
                        primary_error.add_note(
                            f"failed to release cache protection for {path}: {exc}"
                        )
                    elif cleanup_error is None:
                        cleanup_error = exc
            if primary_error is None and cleanup_error is not None:
                raise cleanup_error

    def _registered_protected(self) -> set[Path]:
        root_key = os.fspath(self.root.resolve())
        with _PROTECTION_GUARD:
            return {
                Path(path)
                for path, count in _PROTECTED.get(root_key, Counter()).items()
                if count > 0
            }

    def _has_cross_process_lease(
        self,
        path: Path,
        cancellation: CancellationToken | None = None,
    ) -> bool:
        if not self._asset_locks_root.exists():
            return False
        if _is_linklike(self._asset_locks_root) or not self._asset_locks_root.is_dir():
            raise CacheError("cache asset-lock directory is unsafe")
        identifier = self._asset_lock_identifier(path)
        lease_directory = self._asset_locks_root / identifier
        if not lease_directory.exists() and not _is_linklike(lease_directory):
            return False
        if _is_linklike(lease_directory) or not lease_directory.is_dir():
            raise CacheError(f"cache asset lease directory is unsafe: {lease_directory}")
        for lock_path in lease_directory.glob("*.lease"):
            if cancellation:
                cancellation.check()
            if self._lease_file_is_active(lock_path):
                return True
            lock_path.unlink(missing_ok=True)
        try:
            lease_directory.rmdir()
        except (FileNotFoundError, OSError):
            # Another process may be acquiring a lease, or the directory may
            # contain an unfamiliar file. Neither is safe to remove here.
            pass
        return False

    def _lease_file_is_active(self, lock_path: Path) -> bool:
        if _is_linklike(lock_path):
            raise CacheError(f"cache asset lease is unsafe: {lock_path}")
        flags = os.O_RDWR
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            descriptor = os.open(lock_path, flags)
        except FileNotFoundError:
            return False
        stream = None
        acquired = False
        try:
            details = os.fstat(descriptor)
            if not stat.S_ISREG(details.st_mode):
                raise CacheError(f"cache asset lock is not a regular file: {lock_path}")
            if details.st_size == 0:
                os.write(descriptor, b"\0")
                os.fsync(descriptor)
            stream = os.fdopen(descriptor, "r+b", buffering=0)
            descriptor = -1
            try:
                stream.seek(0)
                if os.name == "nt":  # pragma: no cover - native Windows CI
                    import msvcrt

                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                acquired = True
                return False
            except OSError as exc:
                if _lock_contended(exc):
                    return True
                raise
        finally:
            if stream is not None:
                if acquired:
                    try:
                        if os.name == "nt":  # pragma: no cover - native Windows CI
                            import msvcrt

                            stream.seek(0)
                            msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
                        else:
                            import fcntl

                            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
                    finally:
                        stream.close()
                else:
                    stream.close()
            if descriptor >= 0:
                os.close(descriptor)

    def _cache_files(self, cancellation: CancellationToken | None = None) -> list[Path]:
        files: list[Path] = []
        for root in (self.assets_root, self.quarantine_root):
            if cancellation:
                cancellation.check()
            self._ensure_directory(root, "managed cache directory")
            for item in root.rglob("*"):
                if cancellation:
                    cancellation.check()
                if _is_linklike(item):
                    # Never follow or account an externally redirected target.
                    continue
                if item.is_file():
                    files.append(item)
        return files

    def _enforce_quota_locked(
        self,
        *,
        protected: set[Path] | None = None,
        reserve_bytes: int = 0,
        cancellation: CancellationToken | None = None,
    ) -> int:
        """Evict unprotected files and return bytes that remain in the cache."""
        active = {path.resolve() for path in (protected or set())}
        active.update(self._registered_protected())
        snapshots: list[tuple[Path, int, int]] = []
        for item in self._cache_files(cancellation):
            if (
                item.is_relative_to(self.assets_root)
                and item.name.startswith(".")
                and item.name.endswith(_PARTIAL_SUFFIX)
            ):
                # The mutation lock excludes every live extraction. Any unique
                # operation partial that remains here is crash debris.
                item.unlink(missing_ok=True)
                continue
            try:
                details = item.stat()
            except FileNotFoundError:
                continue
            snapshots.append((item, details.st_size, details.st_atime_ns))
            if (
                item.resolve() not in active
                and item.is_relative_to(self.assets_root)
                and self._has_cross_process_lease(item, cancellation)
            ):
                active.add(item.resolve())
        total = sum(size for _, size, _ in snapshots)
        target_total = max(self.quota_bytes - reserve_bytes, 0)
        candidates = [record for record in snapshots if record[0].resolve() not in active]
        for item, size, _ in sorted(candidates, key=lambda row: (row[2], row[0].name)):
            if cancellation:
                cancellation.check()
            if total <= target_total:
                break
            try:
                item.unlink()
            except FileNotFoundError:
                continue
            total -= size
        return total

    def enforce_quota(self, *, protected: set[Path] | None = None) -> None:
        self.initialize()
        with _ProcessFileLock(self._mutation_lock):
            self._require_managed()
            normalized = {self._normalize_owned_asset_path(path) for path in (protected or set())}
            self._enforce_quota_locked(protected=normalized)

    def clear(self) -> None:
        """Clear only plugin-owned cache payloads, preserving the root and marker."""

        self._check_safe_root()
        self._require_managed()
        self._ensure_directory(self.locks_root, "cache lock directory")
        with _ProcessFileLock(self._mutation_lock):
            self._require_managed()
            active = self._registered_protected()
            for item in self._cache_files():
                if item.is_relative_to(self.assets_root) and self._has_cross_process_lease(item):
                    active.add(item.resolve())
            if active:
                raise CacheError(
                    f"refusing to clear {len(active)} cached asset(s) that are actively in use"
                )
            managed: list[Path] = []
            for child in (self.assets_root, self.quarantine_root):
                if child.exists() or _is_linklike(child):
                    if _is_linklike(child) or not child.is_dir():
                        raise CacheError(f"managed cache child is unsafe: {child}")
                    managed.append(child)
            for child in managed:
                shutil.rmtree(child)
            self._ensure_directory(self.assets_root, "cache assets directory")
            self._ensure_directory(self.quarantine_root, "cache quarantine directory")
