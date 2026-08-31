from __future__ import annotations

import hashlib
import json
import multiprocessing
import os
import queue
import shutil
import tempfile
import unittest
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from vao_blender.core.cache import MARKER, AssetCache, CacheError
from vao_blender.core.cancellation import CancellationToken, CancelledError
from vao_blender.core.model import AssetRecord


def _asset(identifier: str, payload: bytes) -> AssetRecord:
    return AssetRecord(
        identifier,
        f"payload/{identifier}.bin",
        "application/octet-stream",
        len(payload),
        hashlib.sha256(payload).hexdigest(),
    )


def _archive(path: Path, records: list[tuple[AssetRecord, bytes]]) -> Path:
    with zipfile.ZipFile(path, "w") as package:
        for asset, payload in records:
            package.writestr(asset.path, payload)
    return path


def _initialize_owner_during_race(root: str, marker_ready, continue_owner, failures) -> None:
    class PausingOwnerCache(AssetCache):
        def _write_marker_for_empty_root(self, cancellation=None) -> None:
            super()._write_marker_for_empty_root(cancellation)
            marker_ready.set()
            if not continue_owner.wait(timeout=10):
                raise RuntimeError("initializer race test timed out")

    try:
        PausingOwnerCache(root).initialize()
    except BaseException as exc:
        failures.put(f"{type(exc).__name__}: {exc}")


def _hold_cache_protection(root: str, target: str, ready, release, failures) -> None:
    cache = AssetCache(root)
    try:
        cache.register_protected(target)
        ready.set()
        if not release.wait(timeout=10):
            raise RuntimeError("cache protection test timed out")
        cache.unregister_protected(target)
    except BaseException as exc:
        failures.put(f"{type(exc).__name__}: {exc}")


class CacheOwnershipTests(unittest.TestCase):
    def test_nonempty_unmarked_directory_is_never_adopted(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "selected"
            root.mkdir()
            sentinel = root / "personal-data.txt"
            sentinel.write_text("keep", encoding="utf-8")

            with self.assertRaisesRegex(CacheError, "non-empty unmarked"):
                AssetCache(root).initialize()

            self.assertEqual(sentinel.read_text(encoding="utf-8"), "keep")
            self.assertFalse((root / MARKER).exists())

    def test_explicit_symlink_root_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            real = base / "real"
            real.mkdir()
            linked = base / "linked"
            linked.symlink_to(real, target_is_directory=True)

            with self.assertRaisesRegex(CacheError, "must not be a symlink"):
                AssetCache(linked).initialize()

            self.assertEqual(list(real.iterdir()), [])

    def test_legacy_owned_marker_remains_compatible(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "legacy"
            root.mkdir()
            (root / MARKER).write_text(
                json.dumps({"owner": "vao_blender", "version": 1}), encoding="utf-8"
            )

            cache = AssetCache(root)
            cache.initialize()

            self.assertTrue(cache.assets_root.is_dir())
            self.assertTrue(cache.quarantine_root.is_dir())

    def test_clear_preserves_root_marker_locks_and_unrelated_root_entries(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "cache"
            cache = AssetCache(root)
            cache.initialize()
            (cache.assets_root / "aa").mkdir()
            (cache.assets_root / "aa" / "owned.bin").write_bytes(b"asset")
            (cache.quarantine_root / "owned.tampered").write_bytes(b"quarantine")
            sentinel = root / "added-after-initialization.txt"
            sentinel.write_text("keep", encoding="utf-8")

            cache.clear()

            self.assertEqual(sentinel.read_text(encoding="utf-8"), "keep")
            self.assertTrue((root / MARKER).is_file())
            self.assertTrue(cache.locks_root.is_dir())
            self.assertEqual(list(cache.assets_root.iterdir()), [])
            self.assertEqual(list(cache.quarantine_root.iterdir()), [])

    def test_clear_rejects_managed_child_symlink_without_following_it(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            cache = AssetCache(base / "cache")
            cache.initialize()
            outside = base / "outside"
            outside.mkdir()
            sentinel = outside / "sentinel"
            sentinel.write_text("keep", encoding="utf-8")
            shutil.rmtree(cache.quarantine_root)
            cache.quarantine_root.symlink_to(outside, target_is_directory=True)

            with self.assertRaisesRegex(CacheError, "not a safe|unsafe"):
                cache.clear()

            self.assertEqual(sentinel.read_text(encoding="utf-8"), "keep")

    def test_concurrent_initializer_cannot_make_the_owner_remove_its_marker(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "cache"
            context = multiprocessing.get_context("spawn")
            marker_ready = context.Event()
            continue_owner = context.Event()
            failures = context.Queue()
            owner = context.Process(
                target=_initialize_owner_during_race,
                args=(str(root), marker_ready, continue_owner, failures),
            )
            owner.start()
            self.assertTrue(marker_ready.wait(timeout=10))
            try:
                AssetCache(root).initialize()
            finally:
                continue_owner.set()
            owner.join(timeout=10)

            self.assertFalse(owner.is_alive())
            self.assertEqual(owner.exitcode, 0)
            try:
                failure = failures.get_nowait()
            except queue.Empty:
                failure = ""
            self.assertEqual(failure, "")
            cache = AssetCache(root)
            cache.initialize()
            self.assertTrue((root / MARKER).is_file())
            self.assertTrue(cache.assets_root.is_dir())
            self.assertTrue(cache.quarantine_root.is_dir())

    def test_failed_marker_publication_leaves_an_empty_retryable_root(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "cache"
            cache = AssetCache(root)

            with (
                patch("vao_blender.core.cache.os.link", side_effect=OSError("stop")),
                self.assertRaisesRegex(CacheError, "published atomically"),
            ):
                cache.initialize()

            self.assertTrue(root.is_dir())
            self.assertEqual(list(root.iterdir()), [])
            self.assertEqual(
                list(Path(directory).glob(f".{root.name}.{MARKER}.*.temporary")),
                [],
            )
            cache.initialize()
            self.assertTrue((root / MARKER).is_file())


class CacheMutationTests(unittest.TestCase):
    def test_concurrent_same_asset_extraction_is_atomic_and_reusable(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            payload = b"concurrent verified payload" * 4096
            asset = _asset("shared", payload)
            package = _archive(base / "source.vao", [(asset, payload)])
            cache = AssetCache(base / "cache")

            with ThreadPoolExecutor(max_workers=8) as executor:
                paths = list(executor.map(lambda _: cache.extract(package, asset), range(24)))

            self.assertEqual(len(set(paths)), 1)
            self.assertEqual(paths[0].read_bytes(), payload)
            self.assertEqual(list(cache.assets_root.rglob("*.partial")), [])
            self.assertEqual(list(cache.quarantine_root.iterdir()), [])

    def test_quarantine_consumes_quota_and_is_evicted_by_age(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = AssetCache(Path(directory) / "cache", quota_bytes=4)
            cache.initialize()
            quarantine = cache.quarantine_root / "old.tampered"
            quarantine.write_bytes(b"old!")
            os.utime(quarantine, ns=(1, 1))
            shard = cache.assets_root / "aa"
            shard.mkdir()
            asset = shard / ("a" * 64 + ".bin")
            asset.write_bytes(b"new!")

            cache.enforce_quota(protected={asset})

            self.assertFalse(quarantine.exists())
            self.assertEqual(asset.read_bytes(), b"new!")

    def test_active_asset_is_not_evicted_or_cleared(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            first_payload = b"1111"
            second_payload = b"2222"
            first = _asset("first", first_payload)
            second = _asset("second", second_payload)
            package = _archive(
                base / "source.vao", [(first, first_payload), (second, second_payload)]
            )
            cache = AssetCache(base / "cache", quota_bytes=4)
            first_path = cache.extract(package, first)
            cache.register_protected(first_path)
            try:
                with self.assertRaisesRegex(CacheError, "insufficient quota"):
                    cache.extract(package, second)
                self.assertTrue(first_path.exists())
                cache.enforce_quota()
                self.assertTrue(first_path.exists())
                self.assertFalse(cache.target_for(second).exists())
                with self.assertRaisesRegex(CacheError, "actively in use"):
                    cache.clear()
            finally:
                cache.unregister_protected(first_path)

            cache.quota_bytes = 0
            cache.enforce_quota()
            self.assertFalse(first_path.exists())
            cache.clear()

    def test_protected_context_is_reference_counted_and_exception_safe(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            payload = b"asset"
            asset = _asset("active", payload)
            package = _archive(base / "source.vao", [(asset, payload)])
            cache = AssetCache(base / "cache")
            target = cache.extract(package, asset)

            with self.assertRaisesRegex(RuntimeError, "stop"):
                with cache.protected(target), cache.protected(target):
                    with self.assertRaises(CacheError):
                        cache.clear()
                    raise RuntimeError("stop")

            cache.clear()
            self.assertFalse(target.exists())

    def test_tamper_quarantine_names_are_collision_safe(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            payload = b"verified"
            asset = _asset("asset", payload)
            package = _archive(base / "source.vao", [(asset, payload)])
            cache = AssetCache(base / "cache")
            target = cache.extract(package, asset)
            for value in (b"tampered one", b"tampered two"):
                target.write_bytes(value)
                cache.extract(package, asset)

            quarantined = list(cache.quarantine_root.iterdir())
            self.assertEqual(len(quarantined), 2)
            self.assertEqual(len({item.name for item in quarantined}), 2)

    def test_crash_partials_are_removed_even_when_cache_is_under_quota(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = AssetCache(Path(directory) / "cache")
            cache.initialize()
            shard = cache.assets_root / "aa"
            shard.mkdir()
            stale = shard / ".asset.123.456.unique.partial"
            stale.write_bytes(b"crash debris")

            cache.enforce_quota()

            self.assertFalse(stale.exists())

    def test_invalid_asset_digest_cannot_shape_a_cache_path(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = AssetCache(Path(directory) / "cache")
            asset = AssetRecord(
                "bad", "payload/a.bin", "application/octet-stream", 1, "../not-a-digest"
            )
            with self.assertRaisesRegex(CacheError, "SHA-256"):
                cache.target_for(asset)

    def test_asset_larger_than_quota_is_rejected_without_cache_growth(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            payload = b"four"
            asset = _asset("too-large", payload)
            package = _archive(base / "source.vao", [(asset, payload)])
            cache = AssetCache(base / "cache", quota_bytes=3)

            with self.assertRaisesRegex(CacheError, "cache quota"):
                cache.extract(package, asset)

            self.assertEqual(list(cache.assets_root.rglob("*.*")), [])
            self.assertEqual(list(cache.quarantine_root.rglob("*.*")), [])

    def test_active_assets_cannot_force_a_new_extraction_over_quota(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            first = _asset("first", b"1111")
            second = _asset("second", b"2222")
            package = _archive(base / "source.vao", [(first, b"1111"), (second, b"2222")])
            cache = AssetCache(base / "cache", quota_bytes=4)
            first_path = cache.extract(package, first, protect=True)

            with self.assertRaisesRegex(CacheError, "insufficient quota"):
                cache.extract(package, second, protect=True)

            self.assertTrue(first_path.exists())
            self.assertFalse(cache.target_for(second).exists())
            usage = sum(
                item.stat().st_size for item in cache.assets_root.rglob("*") if item.is_file()
            )
            self.assertLessEqual(usage, cache.quota_bytes)
            cache.unregister_protected(first_path)

    def test_insufficient_free_space_fails_before_creating_a_partial(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            payload = b"payload"
            asset = _asset("disk-space", payload)
            package = _archive(base / "source.vao", [(asset, payload)])
            cache = AssetCache(base / "cache", quota_bytes=len(payload))

            with (
                patch(
                    "vao_blender.core.cache.shutil.disk_usage",
                    return_value=SimpleNamespace(free=len(payload) - 1),
                ),
                self.assertRaisesRegex(CacheError, "free bytes"),
            ):
                cache.extract(package, asset)

            self.assertEqual(list(cache.assets_root.rglob("*.partial")), [])
            self.assertFalse(cache.target_for(asset).exists())

    def test_tamper_quarantine_is_bounded_even_when_reextraction_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            payload = b"good"
            asset = _asset("asset", payload)
            package = _archive(base / "source.vao", [(asset, payload)])
            cache = AssetCache(base / "cache", quota_bytes=8)
            target = cache.extract(package, asset)
            target.write_bytes(b"tampered-and-larger-than-quota")
            with zipfile.ZipFile(package, "w") as changed:
                changed.writestr("payload/other.bin", b"other")

            with self.assertRaisesRegex(CacheError, "no longer present"):
                cache.extract(package, asset)

            usage = sum(
                item.stat().st_size
                for root in (cache.assets_root, cache.quarantine_root)
                for item in root.rglob("*")
                if item.is_file()
            )
            self.assertLessEqual(usage, cache.quota_bytes)

    def test_atomic_extract_protection_closes_clear_and_quota_gap(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            payload = b"active"
            asset = _asset("active", payload)
            package = _archive(base / "source.vao", [(asset, payload)])
            cache = AssetCache(base / "cache", quota_bytes=len(payload))

            target = cache.extract(package, asset, protect=True)
            cache.quota_bytes = 0
            cache.enforce_quota()
            self.assertTrue(target.exists())
            with self.assertRaisesRegex(CacheError, "actively in use"):
                cache.clear()

            cache.unregister_protected(target)
            cache.enforce_quota()
            self.assertFalse(target.exists())

    def test_active_tampered_asset_is_not_moved_or_deleted(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            payload = b"verified"
            asset = _asset("active-tamper", payload)
            package = _archive(base / "source.vao", [(asset, payload)])
            cache = AssetCache(base / "cache")
            target = cache.extract(package, asset, protect=True)
            target.write_bytes(b"tampered while active")

            # The local registry must independently protect the file even on a
            # platform whose byte-lock implementation lets a process probe its
            # own lease as available.
            with (
                patch.object(cache, "_has_cross_process_lease", return_value=False),
                self.assertRaisesRegex(CacheError, "actively in use"),
            ):
                cache.extract(package, asset)

            self.assertEqual(target.read_bytes(), b"tampered while active")
            self.assertEqual(list(cache.quarantine_root.iterdir()), [])
            cache.unregister_protected(target)
            restored = cache.extract(package, asset)
            self.assertEqual(restored.read_bytes(), payload)
            self.assertEqual(len(list(cache.quarantine_root.iterdir())), 1)

    def test_replaced_active_path_can_still_release_its_lease_safely(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            payload = b"active"
            asset = _asset("replaced-active", payload)
            package = _archive(base / "source.vao", [(asset, payload)])
            cache = AssetCache(base / "cache")
            target = cache.extract(package, asset, protect=True)
            outside = base / "outside.bin"
            outside.write_bytes(b"do not remove")
            target.unlink()
            target.symlink_to(outside)

            cache.unregister_protected(target)
            cache.clear()

            self.assertEqual(outside.read_bytes(), b"do not remove")

    def test_asset_leases_are_partitioned_by_asset_identifier(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            payload = b"leased"
            asset = _asset("partitioned", payload)
            package = _archive(base / "source.vao", [(asset, payload)])
            cache = AssetCache(base / "cache")
            target = cache.extract(package, asset, protect=True)

            lease_directories = list(cache._asset_locks_root.iterdir())
            self.assertEqual(len(lease_directories), 1)
            self.assertTrue(lease_directories[0].is_dir())
            self.assertEqual(list(cache._asset_locks_root.glob("*.lease")), [])
            self.assertEqual(len(list(lease_directories[0].glob("*.lease"))), 1)

            cache.unregister_protected(target)
            self.assertEqual(list(cache._asset_locks_root.iterdir()), [])

    def test_other_process_cannot_evict_or_clear_a_leased_asset(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            payload = b"shared"
            asset = _asset("shared", payload)
            package = _archive(base / "source.vao", [(asset, payload)])
            cache = AssetCache(base / "cache", quota_bytes=len(payload))
            target = cache.extract(package, asset)

            context = multiprocessing.get_context("spawn")
            ready = [context.Event(), context.Event()]
            release = context.Event()
            failures = context.Queue()
            holders = [
                context.Process(
                    target=_hold_cache_protection,
                    args=(str(cache.root), str(target), event, release, failures),
                )
                for event in ready
            ]
            for holder in holders:
                holder.start()
            for event in ready:
                self.assertTrue(event.wait(timeout=10))
            try:
                cache.quota_bytes = 0
                cache.enforce_quota()
                self.assertTrue(target.exists())
                with self.assertRaisesRegex(CacheError, "actively in use"):
                    cache.clear()
            finally:
                release.set()
                for holder in holders:
                    holder.join(timeout=10)

            self.assertTrue(all(not holder.is_alive() for holder in holders))
            self.assertTrue(all(holder.exitcode == 0 for holder in holders))
            try:
                failure = failures.get_nowait()
            except queue.Empty:
                failure = ""
            self.assertEqual(failure, "")
            cache.enforce_quota()
            self.assertFalse(target.exists())

    def test_cancelled_extraction_does_not_wait_for_initialization_lock(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            payload = b"payload"
            asset = _asset("cancelled", payload)
            package = _archive(base / "source.vao", [(asset, payload)])
            cache = AssetCache(base / "cache")
            cache.initialize()
            token = CancellationToken()
            token.cancel()

            with self.assertRaises(CancelledError):
                cache.extract(package, asset, cancellation=token)

    def test_existing_target_digest_is_cooperatively_cancellable(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            payload = b"0123456789abcdef"
            asset = _asset("digest", payload)
            package = _archive(base / "source.vao", [(asset, payload)])
            cache = AssetCache(base / "cache")
            target = cache.extract(package, asset)

            class CountingCancellation:
                def __init__(self) -> None:
                    self.checks = 0

                def check(self) -> None:
                    self.checks += 1
                    if self.checks >= 7:
                        raise CancelledError("cancel digest")

            token = CountingCancellation()
            with patch("vao_blender.core.cache.CHUNK_SIZE", 2):
                with self.assertRaises(CancelledError):
                    cache.extract(package, asset, cancellation=token)

            self.assertGreaterEqual(token.checks, 7)
            self.assertEqual(target.read_bytes(), payload)


if __name__ == "__main__":
    unittest.main()
