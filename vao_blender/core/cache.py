"""Managed content-addressed extraction cache with tamper checks."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
import zipfile
from pathlib import Path

from .cancellation import CancellationToken
from .model import AssetRecord

MARKER = ".vao-blender-cache"
CHUNK_SIZE = 4 * 1024 * 1024


class CacheError(RuntimeError):
    pass


def _digest(path: Path, token: CancellationToken | None = None) -> tuple[int, str]:
    checksum = hashlib.sha256()
    count = 0
    with path.open("rb") as stream:
        while chunk := stream.read(CHUNK_SIZE):
            if token:
                token.check()
            count += len(chunk)
            checksum.update(chunk)
    return count, checksum.hexdigest()


class AssetCache:
    def __init__(self, root: str | os.PathLike[str], *, quota_bytes: int = 20 * 1024**3) -> None:
        self.root = Path(root).expanduser().resolve()
        self.quota_bytes = quota_bytes
        self.assets_root = self.root / "assets"
        self.quarantine_root = self.root / "quarantine"

    def initialize(self) -> None:
        if self.root in {Path("/").resolve(), Path.home().resolve(), Path.cwd().resolve()}:
            raise CacheError("refusing an unsafe cache root")
        self.assets_root.mkdir(parents=True, exist_ok=True)
        self.quarantine_root.mkdir(parents=True, exist_ok=True)
        marker = self.root / MARKER
        if marker.exists() and (marker.is_symlink() or not marker.is_file()):
            raise CacheError("cache marker is not a regular file")
        if not marker.exists():
            marker.write_text(
                json.dumps({"owner": "vao_blender", "version": 1}, sort_keys=True) + "\n",
                encoding="utf-8",
            )

    def _require_managed(self) -> None:
        marker = self.root / MARKER
        if not marker.is_file() or marker.is_symlink():
            raise CacheError("directory is not a marked VAO-Blender cache")
        try:
            data = json.loads(marker.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise CacheError("cache marker is unreadable") from exc
        if data != {"owner": "vao_blender", "version": 1}:
            raise CacheError("cache marker does not match this extension")

    @staticmethod
    def _extension(asset: AssetRecord) -> str:
        return {
            "model/gltf-binary": ".glb",
            "model/gltf+json": ".gltf",
            "audio/wav": ".wav",
            "audio/x-wav": ".wav",
            "audio/wave": ".wav",
        }.get(asset.media_type, Path(asset.path).suffix.lower() or ".bin")

    def target_for(self, asset: AssetRecord) -> Path:
        return self.assets_root / asset.sha256[:2] / f"{asset.sha256}{self._extension(asset)}"

    def _check_existing(self, path: Path, asset: AssetRecord) -> bool:
        if not path.exists():
            return False
        if path.is_symlink() or not path.is_file():
            raise CacheError(f"cache target is not a regular file: {path}")
        size, checksum = _digest(path)
        if size == asset.byte_size and checksum == asset.sha256:
            os.utime(path, None)
            return True
        self.quarantine_root.mkdir(parents=True, exist_ok=True)
        destination = self.quarantine_root / f"{path.name}.{time.time_ns()}.tampered"
        os.replace(path, destination)
        return False

    def extract(
        self,
        archive_path: str | os.PathLike[str],
        asset: AssetRecord,
        *,
        cancellation: CancellationToken | None = None,
    ) -> Path:
        self.initialize()
        target = self.target_for(asset)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.parent.is_symlink():
            raise CacheError("cache shard directory is a symlink")
        if self._check_existing(target, asset):
            return target
        partial = target.with_name(f".{target.name}.{os.getpid()}.partial")
        if partial.exists():
            if partial.is_symlink() or not partial.is_file():
                raise CacheError("partial cache target is unsafe")
            partial.unlink()
        checksum = hashlib.sha256()
        count = 0
        try:
            with zipfile.ZipFile(archive_path, "r", allowZip64=True) as zf:
                info = zf.getinfo(asset.path)
                if info.file_size != asset.byte_size:
                    raise CacheError("archive asset size changed after validation")
                with zf.open(info, "r") as source, partial.open("xb") as destination:
                    while chunk := source.read(CHUNK_SIZE):
                        if cancellation:
                            cancellation.check()
                        destination.write(chunk)
                        checksum.update(chunk)
                        count += len(chunk)
                    destination.flush()
                    os.fsync(destination.fileno())
            if count != asset.byte_size or checksum.hexdigest() != asset.sha256:
                raise CacheError("extracted asset failed SHA-256 verification")
            os.replace(partial, target)
            self.enforce_quota(protected={target})
            return target
        finally:
            if partial.exists() and partial.is_file() and not partial.is_symlink():
                partial.unlink()

    def enforce_quota(self, *, protected: set[Path] | None = None) -> None:
        protected = {path.resolve() for path in (protected or set())}
        files = [
            item
            for item in self.assets_root.glob("*/*")
            if item.is_file() and not item.is_symlink() and item.resolve() not in protected
        ]
        total = sum(item.stat().st_size for item in files) + sum(
            item.stat().st_size for item in protected if item.exists()
        )
        for item in sorted(files, key=lambda path: (path.stat().st_atime_ns, path.name)):
            if total <= self.quota_bytes:
                break
            size = item.stat().st_size
            item.unlink()
            total -= size

    def clear(self) -> None:
        self._require_managed()
        if self.root in {Path("/").resolve(), Path.home().resolve(), Path.cwd().resolve()}:
            raise CacheError("refusing to clear an unsafe cache root")
        for child in (self.assets_root, self.quarantine_root):
            if child.exists():
                if child.is_symlink() or not child.is_dir():
                    raise CacheError(f"managed cache child is unsafe: {child}")
                shutil.rmtree(child)
        self.assets_root.mkdir(parents=True)
        self.quarantine_root.mkdir(parents=True)
