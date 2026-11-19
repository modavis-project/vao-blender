"""Regression checks against the published VAO 0.6.0 Core contract."""

import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

from vao_blender.core.archive import MMIC_PROFILE_BASE, validate_package
from vao_blender.core.model import OutcomeState

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "vao-0.6.0" / "carriers"


class VAO06ContractTests(unittest.TestCase):
    def test_published_generic_core_and_mmic_inspection(self):
        for filename, expected_state, payload_bytes in (
            ("minimal.vao", OutcomeState.VALID, 69),
            ("mmic-design.vao", OutcomeState.UNSUPPORTED, 140001),
        ):
            with self.subTest(filename=filename):
                outcome = validate_package(FIXTURES / filename)
                self.assertEqual(outcome.contract_line, "0.6.0")
                self.assertTrue(outcome.is_valid)
                self.assertEqual(outcome.state, expected_state)
                self.assertTrue(outcome.payload_verification_complete)
                self.assertEqual(outcome.verified_payload_bytes, payload_bytes)
                self.assertEqual(outcome.report()["contract"]["status"], "published-standard")
                if filename == "mmic-design.vao":
                    self.assertTrue(
                        any(
                            result.capability == MMIC_PROFILE_BASE + "1.0.0"
                            and not result.supported
                            for result in outcome.capabilities
                        )
                    )

    def test_same_size_payload_change_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            damaged = Path(directory) / "changed.vao"
            with (
                ZipFile(FIXTURES / "minimal.vao") as source,
                ZipFile(damaged, "w") as target,
            ):
                for entry in source.infolist():
                    data = source.read(entry)
                    if entry.filename.startswith("payload/"):
                        data = bytes([data[0] ^ 1]) + data[1:]
                    target.writestr(entry, data)

            outcome = validate_package(damaged)
        self.assertEqual(outcome.state, OutcomeState.INVALID)
        self.assertTrue(
            any("exact byte verification" in issue.message for issue in outcome.diagnostics)
        )
