from __future__ import annotations

import unittest
from pathlib import Path

from vao_blender.core.archive import validate_package
from vao_blender.core.contract import reference_validator_05, verify_contract_05
from vao_blender.core.model import OutcomeState

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests" / "fixtures" / "vao-0.5.0" / "carriers" / "minimal.vao"
EXPECTED_ARCHIVE_SHA256 = "9bc7ff7eb06cd50a66ab5bfeabdecaef68c8b24a15f5b47bc0013811a241403e"
EXPECTED_MANIFEST_SHA256 = "9261db2780dc4cb7530c0283d3c0c3a2b94f82b77432611313c6737a256197da"


class VAO05ContractTests(unittest.TestCase):
    def test_candidate_contract_integrity(self):
        verify_contract_05()
        self.assertEqual(reference_validator_05().FORMAT_VERSION, "0.5.0")

    def test_official_minimal_carrier_matches_reference_validator(self):
        reference = reference_validator_05().validate_archive(FIXTURE)
        outcome = validate_package(FIXTURE)
        self.assertTrue(reference["valid"], reference["errors"])
        self.assertEqual(outcome.state, OutcomeState.VALID)
        self.assertEqual(outcome.contract_line, "0.5.0")
        self.assertEqual(outcome.archive_sha256, EXPECTED_ARCHIVE_SHA256)
        self.assertEqual(outcome.manifest_sha256, EXPECTED_MANIFEST_SHA256)
        self.assertEqual(len(outcome.logical_assets), 1)
        self.assertEqual(len(outcome.realizations), 1)
        self.assertEqual(len(outcome.verified_assets), 1)
        self.assertEqual(outcome.verified_payload_bytes, reference["verifiedBytes"])
        self.assertEqual(outcome.carrier.mode, "bootstrap")
        self.assertEqual(outcome.report()["contract"]["status"], "commit-pinned-standard-candidate")


if __name__ == "__main__":
    unittest.main()
