from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from vao_blender.core.archive import MIMETYPE, ValidationLimits, validate_package
from vao_blender.core.model import OutcomeState

ROOT = Path(__file__).resolve().parents[2]
FIXTURE_03 = ROOT / "tests" / "fixtures" / "vao-0.3.2" / "acousticrooms-bathrooms-idx-0.vao"
FIXTURE_04 = ROOT / "tests" / "fixtures" / "vao-0.4.0" / "carriers" / "minimal.vao"
FIXTURE_05 = ROOT / "tests" / "fixtures" / "vao-0.5.0" / "carriers" / "minimal.vao"
FIXTURE_02 = ROOT / "tests" / "fixtures" / "vao-0.2.2" / "minimal-string-instrument"


def write_structural_archive(
    destination: Path,
    *,
    mimetype: bytes = MIMETYPE,
    manifest: bytes | None = b"{}",
) -> Path:
    with zipfile.ZipFile(destination, "w", allowZip64=True) as archive:
        archive.writestr("mimetype", mimetype, compress_type=zipfile.ZIP_STORED)
        if manifest is not None:
            archive.writestr("vao-manifest.json", manifest, compress_type=zipfile.ZIP_DEFLATED)
        else:
            archive.writestr("payload/present.bin", b"payload", compress_type=zipfile.ZIP_STORED)
    return destination


def build_02_fixture(destination: Path) -> Path:
    with zipfile.ZipFile(destination, "w", allowZip64=True) as archive:
        archive.writestr("mimetype", MIMETYPE, compress_type=zipfile.ZIP_STORED)
        archive.write(
            FIXTURE_02 / "vao-manifest.json",
            "vao-manifest.json",
            compress_type=zipfile.ZIP_DEFLATED,
        )
        for source in sorted((FIXTURE_02 / "payload").rglob("*")):
            if source.is_file():
                archive.write(
                    source,
                    source.relative_to(FIXTURE_02).as_posix(),
                    compress_type=zipfile.ZIP_STORED,
                )
    return destination


class ContainerLimitTests(unittest.TestCase):
    def test_missing_manifest_is_invalid_not_resource_limited(self):
        with tempfile.TemporaryDirectory() as directory:
            source = write_structural_archive(Path(directory) / "missing.vao", manifest=None)
            outcome = validate_package(source, hash_archive=False)
        self.assertEqual(outcome.state, OutcomeState.INVALID)
        self.assertEqual(outcome.diagnostics[0].code, "VAO-CNT-011")

    def test_oversized_manifest_is_resource_limited(self):
        with tempfile.TemporaryDirectory() as directory:
            source = write_structural_archive(Path(directory) / "large.vao", manifest=b"{}")
            outcome = validate_package(
                source,
                limits=ValidationLimits(max_manifest_bytes=1),
                hash_archive=False,
            )
        self.assertEqual(outcome.state, OutcomeState.RESOURCE_LIMITED)
        self.assertIn("manifest exceeds", outcome.diagnostics[0].message)

    def test_wrong_mimetype_size_is_rejected_before_read(self):
        with tempfile.TemporaryDirectory() as directory:
            source = write_structural_archive(
                Path(directory) / "mimetype.vao", mimetype=MIMETYPE + b"x"
            )
            original_read = zipfile.ZipFile.read

            def guarded_read(instance, name, *args, **kwargs):
                filename = name.filename if isinstance(name, zipfile.ZipInfo) else name
                if filename == "mimetype":
                    raise AssertionError("oversized mimetype was read")
                return original_read(instance, name, *args, **kwargs)

            with patch.object(zipfile.ZipFile, "read", new=guarded_read):
                outcome = validate_package(source, hash_archive=False)
        self.assertEqual(outcome.state, OutcomeState.INVALID)
        self.assertEqual(outcome.diagnostics[0].code, "VAO-CNT-017")

    def test_optional_archive_byte_limit_runs_before_zip_parsing(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "oversized.vao"
            source.write_bytes(b"not a ZIP")
            outcome = validate_package(
                source,
                limits=ValidationLimits(max_archive_bytes=len(b"not a ZIP") - 1),
                hash_archive=False,
            )
        self.assertEqual(outcome.state, OutcomeState.RESOURCE_LIMITED)
        self.assertIn("configured archive limit", outcome.diagnostics[0].message)

    def test_deep_manifest_is_a_diagnostic_result_not_a_recursion_crash(self):
        with tempfile.TemporaryDirectory() as directory:
            raw = b'{"formatVersion":"0.2.2","value":' + b"[" * 512 + b"0" + b"]" * 512 + b"}"
            source = write_structural_archive(Path(directory) / "deep.vao", manifest=raw)
            outcome = validate_package(source)
        self.assertEqual(outcome.state, OutcomeState.INVALID)
        self.assertTrue(any(item.code == "VAO-CNT-018" for item in outcome.diagnostics))
        self.assertEqual(outcome.manifest_bytes, raw)


class TrustBoundaryTests(unittest.TestCase):
    def test_skipped_fixity_is_explicitly_incomplete_for_every_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture_02 = build_02_fixture(Path(directory) / "minimal-02.vao")
            for source in (fixture_02, FIXTURE_03, FIXTURE_04, FIXTURE_05):
                with self.subTest(source=source):
                    with zipfile.ZipFile(source, "r") as archive:
                        manifest_bytes = archive.read("vao-manifest.json")
                    outcome = validate_package(
                        source,
                        verify_payload=False,
                        hash_archive=False,
                    )
                    self.assertEqual(outcome.state, OutcomeState.INCOMPLETE)
                    self.assertFalse(outcome.is_valid)
                    self.assertFalse(outcome.runtime_ready)
                    self.assertFalse(outcome.payload_verification_complete)
                    self.assertFalse(outcome.archive_hash_complete)
                    self.assertFalse(outcome.verified_assets)
                    self.assertEqual(outcome.manifest_bytes, manifest_bytes)
                    self.assertEqual(
                        outcome.manifest_sha256,
                        hashlib.sha256(manifest_bytes).hexdigest(),
                    )
                    self.assertTrue(any(item.code == "VAO-VER-001" for item in outcome.diagnostics))
                    report = outcome.report()
                    self.assertFalse(report["payloadVerificationComplete"])
                    self.assertFalse(report["archiveHashComplete"])
                    self.assertFalse(report["runtimeReady"])
                    self.assertEqual(report["manifestByteSize"], len(manifest_bytes))

    def test_skipped_archive_hash_alone_is_incomplete(self):
        outcome = validate_package(FIXTURE_04, hash_archive=False)
        self.assertEqual(outcome.state, OutcomeState.INCOMPLETE)
        self.assertFalse(outcome.is_valid)
        self.assertTrue(outcome.payload_verification_complete)
        self.assertFalse(outcome.archive_hash_complete)
        self.assertTrue(outcome.verified_assets)
        self.assertTrue(any(item.code == "VAO-VER-002" for item in outcome.diagnostics))
        self.assertFalse(any(item.code == "VAO-VER-001" for item in outcome.diagnostics))

    def test_source_path_swap_during_validation_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.vao"
            source.write_bytes(FIXTURE_04.read_bytes())
            replacement = Path(directory) / "replacement.vao"
            replacement.write_bytes(b"not the validated package")
            swapped = False
            mutation_blocked = False

            def progress(record) -> None:
                nonlocal mutation_blocked, swapped
                if not swapped and not mutation_blocked and record.stage == "archive-hash":
                    try:
                        os.replace(replacement, source)
                        swapped = True
                    except OSError:
                        if os.name != "nt":
                            raise
                        mutation_blocked = True

            outcome = validate_package(source, progress=progress)
        self.assertTrue(swapped or mutation_blocked)
        if mutation_blocked:
            self.assertTrue(outcome.is_valid)
        else:
            self.assertEqual(outcome.state, OutcomeState.INVALID)
            self.assertTrue(any(item.code == "VAO-CNT-025" for item in outcome.diagnostics))
        self.assertTrue(outcome.manifest_bytes)

    def test_source_growth_during_hashing_is_bounded_and_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.vao"
            source.write_bytes(FIXTURE_04.read_bytes())
            appended = False
            mutation_blocked = False

            def progress(record) -> None:
                nonlocal appended, mutation_blocked
                if not appended and not mutation_blocked and record.stage == "archive-hash":
                    try:
                        with source.open("ab") as stream:
                            stream.write(b"unexpected growth")
                        appended = True
                    except OSError:
                        if os.name != "nt":
                            raise
                        mutation_blocked = True

            outcome = validate_package(source, progress=progress)

        self.assertTrue(appended or mutation_blocked)
        if mutation_blocked:
            self.assertTrue(outcome.is_valid)
        else:
            self.assertEqual(outcome.state, OutcomeState.INVALID)
            self.assertTrue(any(item.code == "VAO-CNT-025" for item in outcome.diagnostics))

    def test_no_payload_cli_never_exits_successfully(self):
        completed = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "validate_vao.py"),
                str(FIXTURE_04),
                "--no-payload",
            ],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(completed.returncode, 0, completed.stderr)
        report = json.loads(completed.stdout)
        self.assertEqual(report["state"], "incomplete")
        self.assertFalse(report["valid"])
        self.assertFalse(report["payloadVerificationComplete"])

    def test_no_archive_hash_cli_never_exits_successfully(self):
        completed = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "validate_vao.py"),
                str(FIXTURE_04),
                "--no-archive-hash",
            ],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(completed.returncode, 0, completed.stderr)
        report = json.loads(completed.stdout)
        self.assertEqual(report["state"], "incomplete")
        self.assertFalse(report["valid"])
        self.assertTrue(report["payloadVerificationComplete"])
        self.assertFalse(report["archiveHashComplete"])


if __name__ == "__main__":
    unittest.main()
