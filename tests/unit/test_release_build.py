from __future__ import annotations

import hashlib
import json
import stat
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from scripts.build_extension import (
    inspect_output_directory,
    normalize_archive,
    promote_release_directory,
    verify_artifact_contents,
)

EXTENSION_ID = "vao_blender"
VERSION = "0.5.0"
PLATFORMS = {"windows-x64", "macos-arm64", "linux-x64"}
PURE_WHEELS = {
    "wheels/jsonschema-4.26.0-py3-none-any.whl",
    "wheels/rfc8785-0.1.4-py3-none-any.whl",
}
NATIVE_WHEELS = {
    "windows-x64": "wheels/rpds_py-1-cp313-cp313-win_amd64.whl",
    "macos-arm64": "wheels/rpds_py-1-cp313-cp313-macosx_11_0_arm64.whl",
    "linux-x64": ("wheels/rpds_py-1-cp313-cp313-manylinux_2_17_x86_64.manylinux2014_x86_64.whl"),
}
EXPECTED_WHEELS = PURE_WHEELS | set(NATIVE_WHEELS.values())


def _manifest(platforms: set[str], wheels: set[str], *, generated: bool) -> str:
    prefix = (
        f'id = "{EXTENSION_ID}"\n'
        f'version = "{VERSION}"\n'
        'name = "VAO-Blender"\n'
        'schema_version = "1.0.0"\n'
    )
    declared_platforms = PLATFORMS if generated else platforms
    declared_wheels = EXPECTED_WHEELS if generated else wheels
    inventory = (
        f"platforms = {json.dumps(sorted(declared_platforms))}\n"
        f"wheels = {json.dumps(['./' + item for item in sorted(declared_wheels)])}\n"
        '[permissions]\nfiles = "${HOME}/**"\n'
        "[build]\npaths_exclude_pattern = []\n"
    )
    generated_inventory = (
        "[build.generated]\n"
        f"platforms = {json.dumps(sorted(platforms))}\n"
        f"wheels = {json.dumps(['./' + item for item in sorted(wheels)])}\n"
        if generated
        else ""
    )
    return prefix + inventory + generated_inventory


def _artifact(
    path: Path,
    platforms: set[str],
    wheels: set[str],
    *,
    generated: bool,
    extras: tuple[str, ...] = (),
) -> Path:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(
            "blender_manifest.toml",
            _manifest(platforms, wheels, generated=generated),
        )
        for wheel in sorted(wheels):
            archive.writestr(wheel, b"wheel")
        for name in extras:
            archive.writestr(name, b"unsafe")
    return path


class ReproducibleReleaseTests(unittest.TestCase):
    def test_zip_normalization_removes_order_and_timestamp_variance(self):
        with tempfile.TemporaryDirectory() as directory:
            first = Path(directory) / "first.zip"
            second = Path(directory) / "second.zip"
            with zipfile.ZipFile(first, "w") as archive:
                archive.writestr(
                    zipfile.ZipInfo("z.txt", (2026, 8, 27, 12, 30, 0)),
                    b"last",
                    compress_type=zipfile.ZIP_DEFLATED,
                )
                archive.writestr(
                    zipfile.ZipInfo("a.txt", (2026, 8, 27, 12, 31, 0)),
                    b"first",
                    compress_type=zipfile.ZIP_STORED,
                )
            with zipfile.ZipFile(second, "w") as archive:
                archive.writestr(
                    zipfile.ZipInfo("a.txt", (2020, 1, 2, 3, 4, 6)),
                    b"first",
                    compress_type=zipfile.ZIP_STORED,
                )
                archive.writestr(
                    zipfile.ZipInfo("z.txt", (2020, 1, 2, 3, 5, 6)),
                    b"last",
                    compress_type=zipfile.ZIP_DEFLATED,
                )

            normalize_archive(first)
            normalize_archive(second)

            self.assertEqual(
                hashlib.sha256(first.read_bytes()).digest(),
                hashlib.sha256(second.read_bytes()).digest(),
            )
            with zipfile.ZipFile(first) as archive:
                self.assertEqual(archive.namelist(), ["a.txt", "z.txt"])
                self.assertTrue(
                    all(item.date_time == (1980, 1, 1, 0, 0, 0) for item in archive.infolist())
                )
                self.assertEqual(archive.read("a.txt"), b"first")
                self.assertEqual(archive.read("z.txt"), b"last")
                self.assertTrue(
                    all(item.compress_type == zipfile.ZIP_STORED for item in archive.infolist())
                )

    def test_output_replacement_requires_an_exact_owned_release_set(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "release"
            output.mkdir()
            (output / "valuable.txt").write_text("keep", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "not an exact owned release set"):
                inspect_output_directory(
                    output,
                    overwrite=True,
                    allowed_names={"SHA256SUMS", "artifact.zip"},
                )
            self.assertEqual((output / "valuable.txt").read_text(), "keep")

    def test_zip_normalization_preserves_executable_intent(self):
        with tempfile.TemporaryDirectory() as directory:
            archive_path = Path(directory) / "source.zip"
            executable = zipfile.ZipInfo("Tools/validator.py", (2026, 8, 30, 12, 0, 0))
            executable.create_system = 3
            executable.external_attr = (stat.S_IFREG | 0o755) << 16
            regular = zipfile.ZipInfo("README.md", (2026, 8, 30, 12, 0, 0))
            regular.create_system = 3
            regular.external_attr = (stat.S_IFREG | 0o644) << 16
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr(executable, b"#!/usr/bin/env python3\n")
                archive.writestr(regular, b"read me\n")

            normalize_archive(archive_path)

            with zipfile.ZipFile(archive_path) as archive:
                modes = {item.filename: item.external_attr >> 16 for item in archive.infolist()}
            self.assertEqual(modes["Tools/validator.py"] & 0o777, 0o755)
            self.assertEqual(modes["README.md"] & 0o777, 0o644)

    def test_output_replacement_rejects_expected_names_without_valid_ownership(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "release"
            output.mkdir()
            (output / "artifact.zip").mkdir()
            (output / "SHA256SUMS").write_text("0" * 64 + "  artifact.zip\n", encoding="ascii")
            with self.assertRaisesRegex(RuntimeError, "regular file"):
                inspect_output_directory(
                    output,
                    overwrite=True,
                    allowed_names={"SHA256SUMS", "artifact.zip"},
                )
            self.assertTrue((output / "artifact.zip").is_dir())

    def test_transactional_promotion_rolls_back_a_failed_replacement(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            output = base / "release"
            staging = base / ".release.staging"
            output.mkdir()
            staging.mkdir()
            (output / "payload").write_text("old", encoding="utf-8")
            (staging / "payload").write_text("new", encoding="utf-8")
            real_replace = __import__("os").replace
            calls = 0

            def fail_promotion(source, destination):
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise OSError("simulated promotion failure")
                return real_replace(source, destination)

            with mock.patch("scripts.build_extension.os.replace", side_effect=fail_promotion):
                with self.assertRaisesRegex(OSError, "simulated promotion failure"):
                    promote_release_directory(staging, output, overwrite=True)
            self.assertEqual((output / "payload").read_text(), "old")
            self.assertEqual((staging / "payload").read_text(), "new")

    def test_inspection_recovers_a_verified_backup_after_interrupted_replacement(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            output = base / "release"
            backup = base / ".release.previous-123"
            backup.mkdir()
            (backup / "artifact.zip").write_bytes(b"owned")
            (backup / "SHA256SUMS").write_text(
                hashlib.sha256(b"owned").hexdigest() + "  artifact.zip\n",
                encoding="ascii",
            )

            inspect_output_directory(
                output,
                overwrite=True,
                allowed_names={"SHA256SUMS", "artifact.zip"},
            )

            self.assertTrue(output.is_dir())
            self.assertFalse(backup.exists())
            self.assertEqual((output / "artifact.zip").read_bytes(), b"owned")

    def test_inspection_preserves_both_sets_when_cleanup_was_interrupted(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            output = base / "release"
            backup = base / ".release.previous-123"
            output.mkdir()
            backup.mkdir()
            with self.assertRaisesRegex(RuntimeError, "manual recovery"):
                inspect_output_directory(
                    output,
                    overwrite=True,
                    allowed_names={"SHA256SUMS", "artifact.zip"},
                )
            self.assertTrue(output.is_dir())
            self.assertTrue(backup.is_dir())


class ArtifactContentTests(unittest.TestCase):
    def test_valid_split_artifact_has_one_platform_and_matching_native_wheel(self):
        with tempfile.TemporaryDirectory() as directory:
            wheels = PURE_WHEELS | {NATIVE_WHEELS["macos-arm64"]}
            artifact = _artifact(
                Path(directory) / "vao_blender-0.5.0-macos_arm64.zip",
                {"macos-arm64"},
                wheels,
                generated=True,
            )

            platforms = verify_artifact_contents(
                artifact,
                extension_id=EXTENSION_ID,
                version=VERSION,
                expected_platforms=PLATFORMS,
                expected_wheels=EXPECTED_WHEELS,
                split=True,
            )

        self.assertEqual(platforms, ["macos-arm64"])

    def test_artifact_bytes_must_match_the_reviewed_source_inventory(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            source = base / "source"
            (source / "wheels").mkdir(parents=True)
            (source / "blender_manifest.toml").write_text(
                _manifest(PLATFORMS, EXPECTED_WHEELS, generated=False),
                encoding="utf-8",
            )
            (source / "SBOM.spdx.json").write_text("{}\n", encoding="utf-8")
            wheels = PURE_WHEELS | {NATIVE_WHEELS["linux-x64"]}
            for wheel in wheels:
                path = source / wheel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"wheel")
            artifact = _artifact(
                base / "vao_blender-0.5.0-linux_x64.zip",
                {"linux-x64"},
                wheels,
                generated=True,
            )
            self.assertEqual(
                verify_artifact_contents(
                    artifact,
                    extension_id=EXTENSION_ID,
                    version=VERSION,
                    expected_platforms=PLATFORMS,
                    expected_wheels=EXPECTED_WHEELS,
                    split=True,
                    source_root=source,
                ),
                ["linux-x64"],
            )
            with zipfile.ZipFile(artifact) as archive:
                self.assertNotIn("SBOM.spdx.json", archive.namelist())
            (source / next(iter(wheels))).write_bytes(b"changed")
            with self.assertRaisesRegex(RuntimeError, "differs from reviewed source"):
                verify_artifact_contents(
                    artifact,
                    extension_id=EXTENSION_ID,
                    version=VERSION,
                    expected_platforms=PLATFORMS,
                    expected_wheels=EXPECTED_WHEELS,
                    split=True,
                    source_root=source,
                )

    def test_built_manifest_may_only_add_the_generated_inventory(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            source = base / "source"
            (source / "wheels").mkdir(parents=True)
            source_manifest = _manifest(PLATFORMS, EXPECTED_WHEELS, generated=False)
            (source / "blender_manifest.toml").write_text(source_manifest, encoding="utf-8")
            wheels = PURE_WHEELS | {NATIVE_WHEELS["linux-x64"]}
            for wheel in wheels:
                path = source / wheel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"wheel")
            artifact = _artifact(
                base / "vao_blender-0.5.0-linux_x64.zip",
                {"linux-x64"},
                wheels,
                generated=True,
            )
            with zipfile.ZipFile(artifact, "r") as original:
                members = {name: original.read(name) for name in original.namelist()}
            members["blender_manifest.toml"] = members["blender_manifest.toml"].replace(
                b'files = "${HOME}/**"', b'files = "${HOME}/Documents/**"'
            )
            with zipfile.ZipFile(artifact, "w") as rewritten:
                for name, payload in members.items():
                    rewritten.writestr(name, payload)
            with self.assertRaisesRegex(RuntimeError, "differs from reviewed source"):
                verify_artifact_contents(
                    artifact,
                    extension_id=EXTENSION_ID,
                    version=VERSION,
                    expected_platforms=PLATFORMS,
                    expected_wheels=EXPECTED_WHEELS,
                    split=True,
                    source_root=source,
                )

    def test_valid_combined_artifact_covers_every_declared_platform(self):
        with tempfile.TemporaryDirectory() as directory:
            artifact = _artifact(
                Path(directory) / "vao_blender-0.5.0.zip",
                PLATFORMS,
                EXPECTED_WHEELS,
                generated=False,
            )

            platforms = verify_artifact_contents(
                artifact,
                extension_id=EXTENSION_ID,
                version=VERSION,
                expected_platforms=PLATFORMS,
                expected_wheels=EXPECTED_WHEELS,
                split=False,
            )

        self.assertEqual(platforms, sorted(PLATFORMS))

    def test_split_artifact_filename_is_bound_to_declared_platform(self):
        with tempfile.TemporaryDirectory() as directory:
            wheels = PURE_WHEELS | {NATIVE_WHEELS["linux-x64"]}
            artifact = _artifact(
                Path(directory) / "vao_blender-0.5.0-windows_x64.zip",
                {"linux-x64"},
                wheels,
                generated=True,
            )
            with self.assertRaisesRegex(RuntimeError, "filename does not match"):
                verify_artifact_contents(
                    artifact,
                    extension_id=EXTENSION_ID,
                    version=VERSION,
                    expected_platforms=PLATFORMS,
                    expected_wheels=EXPECTED_WHEELS,
                    split=True,
                )

    def test_portable_name_collisions_and_symbolic_links_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            wheels = PURE_WHEELS | {NATIVE_WHEELS["linux-x64"]}
            artifact = _artifact(
                Path(directory) / "vao_blender-0.5.0-linux_x64.zip",
                {"linux-x64"},
                wheels,
                generated=True,
                extras=("vao_blender/Module.py", "vao_blender/module.py"),
            )
            with self.assertRaisesRegex(RuntimeError, "portable-name collision"):
                verify_artifact_contents(
                    artifact,
                    extension_id=EXTENSION_ID,
                    version=VERSION,
                    expected_platforms=PLATFORMS,
                    expected_wheels=EXPECTED_WHEELS,
                    split=True,
                )

            artifact = _artifact(
                Path(directory) / "vao_blender-0.5.0-linux_x64.zip",
                {"linux-x64"},
                wheels,
                generated=True,
            )
            link = zipfile.ZipInfo("vao_blender/linked.py")
            link.create_system = 3
            link.external_attr = (stat.S_IFLNK | 0o777) << 16
            with zipfile.ZipFile(artifact, "a") as archive:
                archive.writestr(link, "target.py")
            with self.assertRaisesRegex(RuntimeError, "symbolic-link"):
                verify_artifact_contents(
                    artifact,
                    extension_id=EXTENSION_ID,
                    version=VERSION,
                    expected_platforms=PLATFORMS,
                    expected_wheels=EXPECTED_WHEELS,
                    split=True,
                )

    def test_development_and_unsafe_members_are_rejected(self):
        unsafe_names = (
            "tests/test_internal.py",
            "scripts/development.py",
            "docs/internal.md",
            "dist/nested.zip",
            "../escape.py",
            "vao_blender/__pycache__/module.pyc",
            "vao_blender\\platform.py",
        )
        with tempfile.TemporaryDirectory() as directory:
            for index, unsafe in enumerate(unsafe_names):
                with self.subTest(member=unsafe):
                    wheels = PURE_WHEELS | {NATIVE_WHEELS["linux-x64"]}
                    artifact = _artifact(
                        Path(directory) / "vao_blender-0.5.0-linux_x64.zip",
                        {"linux-x64"},
                        wheels,
                        generated=True,
                        extras=(unsafe,),
                    )
                    with self.assertRaisesRegex(RuntimeError, "unsafe or development-only"):
                        verify_artifact_contents(
                            artifact,
                            extension_id=EXTENSION_ID,
                            version=VERSION,
                            expected_platforms=PLATFORMS,
                            expected_wheels=EXPECTED_WHEELS,
                            split=True,
                        )

    def test_split_artifact_rejects_native_wheel_for_another_platform(self):
        with tempfile.TemporaryDirectory() as directory:
            wheels = PURE_WHEELS | {NATIVE_WHEELS["windows-x64"]}
            artifact = _artifact(
                Path(directory) / "vao_blender-0.5.0-macos_arm64.zip",
                {"macos-arm64"},
                wheels,
                generated=True,
            )
            with self.assertRaisesRegex(RuntimeError, "platform-specific wheel selection"):
                verify_artifact_contents(
                    artifact,
                    extension_id=EXTENSION_ID,
                    version=VERSION,
                    expected_platforms=PLATFORMS,
                    expected_wheels=EXPECTED_WHEELS,
                    split=True,
                )


if __name__ == "__main__":
    unittest.main()
