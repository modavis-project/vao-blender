from __future__ import annotations

import io
import os
import shutil
import stat
import subprocess
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from scripts import prepare_native_blender as subject


class PrepareNativeBlenderTests(unittest.TestCase):
    @staticmethod
    def _zip(path: Path, members: list[tuple[str, bytes]]) -> None:
        with zipfile.ZipFile(path, "w") as archive:
            for name, content in members:
                archive.writestr(name, content)

    @staticmethod
    def _tar_file(name: str, content: bytes) -> tuple[tarfile.TarInfo, bytes]:
        member = tarfile.TarInfo(name)
        member.size = len(content)
        return member, content

    @staticmethod
    def _write_tar(path: Path, members: list[tuple[tarfile.TarInfo, bytes | None]]) -> None:
        with tarfile.open(path, "w:xz") as archive:
            for member, content in members:
                archive.addfile(member, io.BytesIO(content) if content is not None else None)

    @staticmethod
    def _remove_mount_contents(mount: Path) -> None:
        for child in mount.iterdir():
            if child.is_symlink() or child.is_file():
                child.unlink()
            else:
                shutil.rmtree(child)

    def _dmg_subprocess(self, mount: Path):
        def run(command, **_kwargs):
            if command[1] == "detach":
                self._remove_mount_contents(mount)
            return subprocess.CompletedProcess(command, 0)

        return run

    def test_zip_extracts_regular_members(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "blender.zip"
            destination = root / "extracted"
            self._zip(archive, [("blender/blender.exe", b"binary")])

            subject.extract_zip(archive, destination)

            self.assertEqual((destination / "blender" / "blender.exe").read_bytes(), b"binary")

    def test_zip_rejects_traversal_special_types_and_nonempty_destinations(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for index, unsafe_name in enumerate(("../escape", "dir\\..\\escape", "/escape")):
                with self.subTest(name=unsafe_name):
                    archive = root / f"unsafe-{index}.zip"
                    destination = root / f"unsafe-{index}"
                    self._zip(archive, [(unsafe_name, b"unsafe")])
                    with self.assertRaisesRegex(RuntimeError, "unsafe member"):
                        subject.extract_zip(archive, destination)

            archive = root / "special.zip"
            special = zipfile.ZipInfo("blender/pipe")
            special.create_system = 3
            special.external_attr = (stat.S_IFIFO | 0o600) << 16
            with zipfile.ZipFile(archive, "w") as output:
                output.writestr(special, b"")
            with self.assertRaisesRegex(RuntimeError, "unsafe member"):
                subject.extract_zip(archive, root / "special")

            archive = root / "regular.zip"
            self._zip(archive, [("blender/file", b"safe")])
            nonempty = root / "nonempty"
            nonempty.mkdir()
            (nonempty / "existing").write_text("do not overwrite", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "empty directory"):
                subject.extract_zip(archive, nonempty)

    def test_zip_rejects_portable_name_collisions(self):
        collisions = (
            ("blender/Module.py", "blender/module.py"),
            (
                "blender/\N{LATIN SMALL LETTER E WITH ACUTE}.txt",
                "blender/e\N{COMBINING ACUTE ACCENT}.txt",
            ),
            ("Blender/one", "blender/two"),
        )
        for first, second in collisions:
            with (
                self.subTest(first=first, second=second),
                tempfile.TemporaryDirectory() as directory,
            ):
                root = Path(directory)
                archive = root / "collision.zip"
                self._zip(archive, [(first, b"one"), (second, b"two")])
                with self.assertRaisesRegex(RuntimeError, "portable-name collision"):
                    subject.extract_zip(archive, root / "extracted")

    def test_zip_enforces_member_and_expanded_size_limits(self):
        cases = (
            ("MAX_ARCHIVE_MEMBERS", 1, [("one", b"1"), ("two", b"2")], "member-count"),
            ("MAX_ARCHIVE_MEMBER_BYTES", 3, [("one", b"1234")], "per-member"),
            (
                "MAX_ARCHIVE_EXPANDED_BYTES",
                7,
                [("one", b"1234"), ("two", b"5678")],
                "aggregate expanded-size",
            ),
        )
        for constant, limit, members, message in cases:
            with self.subTest(constant=constant), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                archive = root / "bounded.zip"
                self._zip(archive, members)
                with (
                    mock.patch.object(subject, constant, limit),
                    self.assertRaisesRegex(RuntimeError, message),
                ):
                    subject.extract_zip(archive, root / "extracted")

    def test_tar_extracts_regular_files_and_contained_links(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "blender.tar.xz"
            target, content = self._tar_file("blender/bin", b"binary")
            link = tarfile.TarInfo("blender/current")
            link.type = tarfile.SYMTYPE
            link.linkname = "bin"
            self._write_tar(archive, [(target, content), (link, None)])

            destination = root / "extracted"
            subject.extract_tar(archive, destination)

            self.assertEqual((destination / "blender" / "current").read_bytes(), b"binary")
            self.assertTrue((destination / "blender" / "current").is_symlink())

    def test_tar_rejects_traversal_escaping_links_and_special_types(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            traversal = root / "traversal.tar.xz"
            member, content = self._tar_file("../escape", b"unsafe")
            self._write_tar(traversal, [(member, content)])
            with self.assertRaisesRegex(RuntimeError, "unsafe member"):
                subject.extract_tar(traversal, root / "traversal")

            escaping = root / "escaping.tar.xz"
            link = tarfile.TarInfo("blender/escape")
            link.type = tarfile.SYMTYPE
            link.linkname = "../../outside"
            self._write_tar(escaping, [(link, None)])
            with self.assertRaisesRegex(RuntimeError, "link outside"):
                subject.extract_tar(escaping, root / "escaping")

            special_archive = root / "special.tar.xz"
            special = tarfile.TarInfo("blender/pipe")
            special.type = tarfile.FIFOTYPE
            self._write_tar(special_archive, [(special, None)])
            with self.assertRaisesRegex(RuntimeError, "unsafe special member"):
                subject.extract_tar(special_archive, root / "special")

            hardlink_archive = root / "hardlink.tar.xz"
            hardlink = tarfile.TarInfo("blender/link")
            hardlink.type = tarfile.LNKTYPE
            hardlink.linkname = "blender/missing"
            self._write_tar(hardlink_archive, [(hardlink, None)])
            with self.assertRaisesRegex(RuntimeError, "unsafe hard-link target"):
                subject.extract_tar(hardlink_archive, root / "hardlink")

    def test_tar_enforces_collisions_and_all_expansion_limits(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            collision = root / "collision.tar.xz"
            first, first_content = self._tar_file("Blender/one", b"one")
            second, second_content = self._tar_file("blender/two", b"two")
            self._write_tar(collision, [(first, first_content), (second, second_content)])
            with self.assertRaisesRegex(RuntimeError, "portable-name collision"):
                subject.extract_tar(collision, root / "collision")

        cases = (
            ("MAX_ARCHIVE_MEMBERS", 1, (b"1", b"2"), "member-count"),
            ("MAX_ARCHIVE_MEMBER_BYTES", 3, (b"1234",), "per-member"),
            ("MAX_ARCHIVE_EXPANDED_BYTES", 7, (b"1234", b"5678"), "aggregate"),
        )
        for constant, limit, contents, message in cases:
            with self.subTest(constant=constant), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                archive = root / "bounded.tar.xz"
                members = [
                    self._tar_file(f"blender/{index}", item) for index, item in enumerate(contents)
                ]
                self._write_tar(archive, members)
                with (
                    mock.patch.object(subject, constant, limit),
                    self.assertRaisesRegex(RuntimeError, message),
                ):
                    subject.extract_tar(archive, root / "extracted")

    def test_dmg_copies_only_a_bounded_contained_app_tree(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            mount = root / "mount"
            executable = mount / "Blender.app" / "Contents" / "MacOS" / "Blender"
            executable.parent.mkdir(parents=True)
            executable.write_bytes(b"binary")
            (mount / "Blender.app" / "Contents" / "Current").symlink_to("MacOS")
            destination = root / "extracted"

            with (
                mock.patch.object(subject.tempfile, "mkdtemp", return_value=str(mount)),
                mock.patch.object(
                    subject.subprocess, "run", side_effect=self._dmg_subprocess(mount)
                ) as run,
            ):
                subject.extract_dmg(root / "Blender.dmg", destination)

            copied = destination / "Blender.app" / "Contents"
            self.assertEqual((copied / "MacOS" / "Blender").read_bytes(), b"binary")
            self.assertTrue((copied / "Current").is_symlink())
            self.assertEqual(run.call_count, 2)

    def test_dmg_rejects_links_outside_the_app_and_special_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            mount = root / "escape-mount"
            contents = mount / "Blender.app" / "Contents"
            contents.mkdir(parents=True)
            (contents / "Escape").symlink_to("../../../outside")
            with (
                mock.patch.object(subject.tempfile, "mkdtemp", return_value=str(mount)),
                mock.patch.object(
                    subject.subprocess, "run", side_effect=self._dmg_subprocess(mount)
                ),
                self.assertRaisesRegex(RuntimeError, "link outside"),
            ):
                subject.extract_dmg(root / "Blender.dmg", root / "escape-output")

            mount = root / "special-mount"
            contents = mount / "Blender.app" / "Contents"
            contents.mkdir(parents=True)
            os.mkfifo(contents / "Pipe")
            with (
                mock.patch.object(subject.tempfile, "mkdtemp", return_value=str(mount)),
                mock.patch.object(
                    subject.subprocess, "run", side_effect=self._dmg_subprocess(mount)
                ),
                self.assertRaisesRegex(RuntimeError, "unsafe special file"),
            ):
                subject.extract_dmg(root / "Blender.dmg", root / "special-output")

    def test_dmg_enforces_tree_limits_and_portable_collisions(self):
        cases = (
            ("MAX_ARCHIVE_MEMBERS", 1, (b"1", b"2"), "member-count"),
            ("MAX_ARCHIVE_MEMBER_BYTES", 3, (b"1234",), "per-member"),
            ("MAX_ARCHIVE_EXPANDED_BYTES", 7, (b"1234", b"5678"), "aggregate"),
        )
        for constant, limit, contents, message in cases:
            with self.subTest(constant=constant), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                mount = root / "mount"
                files = mount / "Blender.app" / "Contents"
                files.mkdir(parents=True)
                for index, content in enumerate(contents):
                    (files / str(index)).write_bytes(content)
                with (
                    mock.patch.object(subject.tempfile, "mkdtemp", return_value=str(mount)),
                    mock.patch.object(
                        subject.subprocess, "run", side_effect=self._dmg_subprocess(mount)
                    ),
                    mock.patch.object(subject, constant, limit),
                    self.assertRaisesRegex(RuntimeError, message),
                ):
                    subject.extract_dmg(root / "Blender.dmg", root / "output")

        with self.assertRaisesRegex(RuntimeError, "portable-name collision"):
            subject._validate_member_inventory(
                [
                    ("Stra\N{LATIN SMALL LETTER SHARP S}e", "file", 3),
                    ("STRASSE", "file", 3),
                ],
                "mounted app fixture",
            )

    def test_probe_binds_output_to_a_stable_executable_digest(self):
        policy = {
            "blender_version": "5.2.1",
            "build_hash": "build",
            "python_version": "3.13.13",
            "system": "Linux",
            "machine": "x86_64",
        }
        actual = {
            "blenderVersion": "5.2.1",
            "blenderBuildHash": "build",
            "pythonVersion": "3.13.13",
            "system": "Linux",
            "machine": "x86_64",
        }
        completed = subprocess.CompletedProcess(
            ("blender",), 0, stdout="VAO_NATIVE_HOST_PROBE=" + subject.json.dumps(actual) + "\n"
        )
        with (
            mock.patch.object(subject.subprocess, "run", return_value=completed),
            mock.patch.object(subject, "sha256", side_effect=("stable", "stable")) as digest,
        ):
            observed = subject.probe(Path("/official/blender"), policy)
        self.assertEqual(observed["blenderExecutableSha256"], "stable")
        self.assertEqual(digest.call_count, 2)

        with (
            mock.patch.object(subject.subprocess, "run", return_value=completed),
            mock.patch.object(subject, "sha256", side_effect=("before", "after")),
            self.assertRaisesRegex(RuntimeError, "changed during"),
        ):
            subject.probe(Path("/official/blender"), policy)


if __name__ == "__main__":
    unittest.main()
