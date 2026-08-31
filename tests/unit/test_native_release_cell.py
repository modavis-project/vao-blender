from __future__ import annotations

import stat
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from scripts.run_native_release_cell import extract_installed_wheels, verify_installed_tree


class NativeReleaseCellTests(unittest.TestCase):
    def _layout(self, directory: str) -> tuple[Path, Path, Path]:
        root = Path(directory)
        installed = root / "installed"
        wheels = installed / "wheels"
        destination = root / "dependencies"
        wheels.mkdir(parents=True)
        destination.mkdir()
        return installed, wheels / "fixture-1.0-py3-none-any.whl", destination

    def test_dependency_wheel_is_extracted_without_zip_path_traversal(self):
        with tempfile.TemporaryDirectory() as directory:
            installed, wheel, destination = self._layout(directory)
            with zipfile.ZipFile(wheel, "w") as archive:
                archive.writestr("fixture/__init__.py", "VALUE = 1\n")

            extract_installed_wheels(installed, destination)

            self.assertEqual(
                (destination / "fixture" / "__init__.py").read_text(encoding="utf-8"),
                "VALUE = 1\n",
            )

    def test_dependency_wheel_rejects_traversal_and_symbolic_links(self):
        unsafe_members = ("../escape.py", "/absolute.py", "pkg\\..\\escape.py")
        for member in unsafe_members:
            with self.subTest(member=member), tempfile.TemporaryDirectory() as directory:
                installed, wheel, destination = self._layout(directory)
                with zipfile.ZipFile(wheel, "w") as archive:
                    archive.writestr(member, "unsafe\n")
                with self.assertRaisesRegex(RuntimeError, "unsafe member"):
                    extract_installed_wheels(installed, destination)

        with tempfile.TemporaryDirectory() as directory:
            installed, wheel, destination = self._layout(directory)
            link = zipfile.ZipInfo("fixture/link.py")
            link.create_system = 3
            link.external_attr = (stat.S_IFLNK | 0o777) << 16
            with zipfile.ZipFile(wheel, "w") as archive:
                archive.writestr(link, "target.py")
            with self.assertRaisesRegex(RuntimeError, "unsafe member"):
                extract_installed_wheels(installed, destination)

    def test_dependency_wheels_reject_portable_name_collisions(self):
        with tempfile.TemporaryDirectory() as directory:
            installed, wheel, destination = self._layout(directory)
            with zipfile.ZipFile(wheel, "w") as archive:
                archive.writestr("fixture/Module.py", "one\n")
                archive.writestr("fixture/module.py", "two\n")

            with self.assertRaisesRegex(RuntimeError, "portable-name collision"):
                extract_installed_wheels(installed, destination)

    def test_dependency_wheels_enforce_member_and_expanded_byte_limits(self):
        with tempfile.TemporaryDirectory() as directory:
            installed, wheel, destination = self._layout(directory)
            with zipfile.ZipFile(wheel, "w") as archive:
                archive.writestr("fixture/one.py", "one\n")
                archive.writestr("fixture/two.py", "two\n")
            with (
                mock.patch("scripts.run_native_release_cell.MAX_WHEEL_MEMBERS", 1),
                self.assertRaisesRegex(RuntimeError, "member-count limit"),
            ):
                extract_installed_wheels(installed, destination)

        with tempfile.TemporaryDirectory() as directory:
            installed, wheel, destination = self._layout(directory)
            with zipfile.ZipFile(wheel, "w") as archive:
                archive.writestr("fixture/large.py", "12345")
            with (
                mock.patch("scripts.run_native_release_cell.MAX_WHEEL_MEMBER_BYTES", 4),
                self.assertRaisesRegex(RuntimeError, "unsafe member"),
            ):
                extract_installed_wheels(installed, destination)

    def test_installed_tree_is_bound_to_artifact_bytes_and_inventory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact = root / "extension.zip"
            installed = root / "installed"
            (installed / "package").mkdir(parents=True)
            (installed / "blender_manifest.toml").write_text("id = 'fixture'\n")
            (installed / "package" / "module.py").write_text("VALUE = 1\n")
            with zipfile.ZipFile(artifact, "w") as archive:
                archive.write(installed / "blender_manifest.toml", "blender_manifest.toml")
                archive.write(installed / "package" / "module.py", "package/module.py")

            inventory = verify_installed_tree(artifact, installed)
            self.assertEqual(set(inventory), {"blender_manifest.toml", "package/module.py"})

            (installed / "package" / "module.py").write_text("VALUE = 2\n")
            with self.assertRaisesRegex(RuntimeError, "differs from the artifact"):
                verify_installed_tree(artifact, installed)

    def test_installed_tree_allows_only_matching_generated_bytecode_extras(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact = root / "extension.zip"
            installed = root / "installed"
            cache = installed / "package" / "__pycache__"
            cache.mkdir(parents=True)
            (installed / "package" / "module.py").write_text("VALUE = 1\n")
            (cache / "module.cpython-313.pyc").write_bytes(b"derived")
            with zipfile.ZipFile(artifact, "w") as archive:
                archive.write(installed / "package" / "module.py", "package/module.py")

            verify_installed_tree(artifact, installed)
            (cache / "unrelated.cpython-313.pyc").write_bytes(b"unexpected")
            with self.assertRaisesRegex(RuntimeError, "inventory differs"):
                verify_installed_tree(artifact, installed)

    def test_installed_tree_rejects_unexpected_directories_and_portable_collisions(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact = root / "extension.zip"
            installed = root / "installed"
            installed.mkdir()
            (installed / "module.py").write_text("VALUE = 1\n")
            with zipfile.ZipFile(artifact, "w") as archive:
                archive.write(installed / "module.py", "module.py")

            (installed / "unexpected").mkdir()
            with self.assertRaisesRegex(RuntimeError, "unexpected_directories"):
                verify_installed_tree(artifact, installed)
            (installed / "unexpected").rmdir()

            with zipfile.ZipFile(artifact, "w") as archive:
                archive.writestr("Case/module.py", "one\n")
                archive.writestr("case/module.py", "two\n")
            with self.assertRaisesRegex(RuntimeError, "portable-name collision"):
                verify_installed_tree(artifact, installed)


if __name__ == "__main__":
    unittest.main()
