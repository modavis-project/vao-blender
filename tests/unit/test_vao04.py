from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from vao_blender.core.archive import validate_package
from vao_blender.core.contract import reference_validator_04, verify_contract_04
from vao_blender.core.model import OutcomeState

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests" / "fixtures" / "vao-0.4.0" / "carriers" / "minimal.vao"
EXPECTED_ARCHIVE_SHA256 = "1cb8e10c3da1013aacf0e310bfcf60a34959c99ad20e01ece64e3687fa8fe336"
EXPECTED_MANIFEST_SHA256 = "a99c69c8cd6166942adc79eb97a3783a4cebe4bbffcb346f5e09e8cb13ba48fd"
VISUAL_MANIFEST = (
    ROOT
    / "tests"
    / "fixtures"
    / "vao-0.4.0"
    / "descriptors"
    / "cuntz-positiv-acoustic.example.json"
)
VAO03_VISUAL_FIXTURE = (
    ROOT / "tests" / "fixtures" / "vao-0.3.2" / "acousticrooms-bathrooms-idx-0.vao"
)


def rebuild_carrier(
    destination: Path,
    *,
    mutate_manifest=None,
    mutate_carrier=None,
    mutate_payload=None,
    extra_entries: dict[str, bytes] | None = None,
) -> Path:
    with zipfile.ZipFile(FIXTURE, "r", allowZip64=True) as source:
        entries = [(info, source.read(info)) for info in source.infolist() if not info.is_dir()]
    values = {info.filename: data for info, data in entries}
    if mutate_manifest:
        manifest = json.loads(values["vao-manifest.json"])
        mutate_manifest(manifest)
        manifest_data = (
            json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True, allow_nan=False)
            + "\n"
        ).encode("utf-8")
        values["vao-manifest.json"] = manifest_data
        carrier = json.loads(values["META-INF/vao-carrier.json"])
        carrier["manifestSHA256"] = hashlib.sha256(manifest_data).hexdigest()
        carrier["manifestByteSize"] = len(manifest_data)
        values["META-INF/vao-carrier.json"] = (
            json.dumps(carrier, indent=2, ensure_ascii=False, sort_keys=True, allow_nan=False)
            + "\n"
        ).encode("utf-8")
    if mutate_carrier:
        carrier = json.loads(values["META-INF/vao-carrier.json"])
        mutate_carrier(carrier)
        values["META-INF/vao-carrier.json"] = (
            json.dumps(carrier, indent=2, ensure_ascii=False, sort_keys=True, allow_nan=False)
            + "\n"
        ).encode("utf-8")
    if mutate_payload:
        for name in tuple(values):
            if name.startswith("payload/"):
                values[name] = mutate_payload(name, values[name])
    with zipfile.ZipFile(destination, "w", allowZip64=True) as output:
        for original, _data in entries:
            info = zipfile.ZipInfo(original.filename, date_time=original.date_time)
            info.compress_type = original.compress_type
            info.create_system = original.create_system
            info.external_attr = original.external_attr
            info.flag_bits = original.flag_bits
            output.writestr(info, values[original.filename])
        for name, data in sorted((extra_entries or {}).items()):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_STORED
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            output.writestr(info, data)
    return destination


def build_visual_bootstrap(destination: Path) -> Path:
    manifest_data = VISUAL_MANIFEST.read_bytes()
    manifest = json.loads(manifest_data)
    realization_id = "urn:vao:fixture:acousticrooms:realization:geometry:glb"
    payload_path = "payload/geometry/Bathrooms_idx_0.glb"
    with zipfile.ZipFile(VAO03_VISUAL_FIXTURE, "r") as source:
        glb = source.read(payload_path)
    carrier = {
        "$schema": "https://w3id.org/modavis/vao/0.4.0/schema/carrier.json",
        "carrierMode": "bootstrap",
        "completeGroupIds": [],
        "embeddedRealizations": [{"path": payload_path, "realizationId": realization_id}],
        "formatVersion": "0.4.0",
        "manifestByteSize": len(manifest_data),
        "manifestSHA256": hashlib.sha256(manifest_data).hexdigest(),
        "releaseId": manifest["release"]["id"],
        "type": "VAOCarrier",
    }
    carrier_data = (
        json.dumps(carrier, indent=2, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n"
    ).encode("utf-8")
    with zipfile.ZipFile(destination, "w", allowZip64=True) as archive:
        for name, data in (
            ("mimetype", b"application/vnd.modavis.vao+zip"),
            ("vao-manifest.json", manifest_data),
            ("META-INF/vao-carrier.json", carrier_data),
            (payload_path, glb),
        ):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_STORED
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, data)
    return destination


class VAO04ContractTests(unittest.TestCase):
    def test_published_contract_integrity(self):
        verify_contract_04()
        self.assertEqual(reference_validator_04().FORMAT_VERSION, "0.4.0")

    def test_official_minimal_carrier_matches_reference_validator(self):
        reference = reference_validator_04().validate_archive(FIXTURE)
        outcome = validate_package(FIXTURE)
        self.assertTrue(reference["valid"])
        self.assertEqual(outcome.state, OutcomeState.VALID)
        self.assertEqual(outcome.contract_line, "0.4.0")
        self.assertEqual(outcome.archive_sha256, EXPECTED_ARCHIVE_SHA256)
        self.assertEqual(outcome.manifest_sha256, EXPECTED_MANIFEST_SHA256)
        self.assertEqual(len(outcome.verified_assets), 1)
        self.assertEqual(outcome.verified_payload_bytes, reference["verifiedBytes"])
        self.assertEqual(outcome.carrier.mode, "bootstrap")
        self.assertEqual(outcome.report()["contract"]["status"], "published-standard")

    def test_closed_04_schema_rejects_unknown_root_property(self):
        with tempfile.TemporaryDirectory() as directory:
            path = rebuild_carrier(
                Path(directory) / "unknown-property.vao",
                mutate_manifest=lambda manifest: manifest.__setitem__("unexpected", True),
            )
            outcome = validate_package(path, hash_archive=False)
        self.assertEqual(outcome.state, OutcomeState.INVALID)
        self.assertTrue(any(item.code == "VAO04-SCH-001" for item in outcome.diagnostics))

    def test_missing_04_carrier_uses_version_specific_diagnostic(self):
        with tempfile.TemporaryDirectory() as directory:
            path = rebuild_carrier(Path(directory) / "missing-carrier.vao")
            rewritten = Path(directory) / "without-carrier.vao"
            with zipfile.ZipFile(path, "r") as source, zipfile.ZipFile(rewritten, "w") as target:
                for info in source.infolist():
                    if info.filename != "META-INF/vao-carrier.json":
                        target.writestr(info, source.read(info))
            outcome = validate_package(rewritten, hash_archive=False)
        self.assertEqual(outcome.state, OutcomeState.INVALID)
        self.assertEqual(outcome.diagnostics[0].code, "VAO04-CNT-001")

    def test_exact_payload_fixity_failure_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = rebuild_carrier(
                Path(directory) / "bad-fixity.vao",
                mutate_payload=lambda _name, data: data + b"tampered",
            )
            outcome = validate_package(path, hash_archive=False)
        self.assertEqual(outcome.state, OutcomeState.INVALID)
        self.assertTrue(
            any("exact byte verification" in item.message for item in outcome.diagnostics)
        )

    def test_unindexed_payload_breaks_carrier_closure(self):
        with tempfile.TemporaryDirectory() as directory:
            path = rebuild_carrier(
                Path(directory) / "unindexed.vao",
                extra_entries={"payload/unindexed.bin": b"not declared"},
            )
            outcome = validate_package(path, hash_archive=False)
        self.assertEqual(outcome.state, OutcomeState.INVALID)
        self.assertTrue(any("payload closure" in item.message for item in outcome.diagnostics))

    def test_ascii_control_character_in_archive_path_is_rejected_pre_schema(self):
        with tempfile.TemporaryDirectory() as directory:
            path = rebuild_carrier(
                Path(directory) / "control-path.vao",
                extra_entries={"payload/bad\x1fname.bin": b"hostile"},
            )
            outcome = validate_package(path, hash_archive=False)
        self.assertEqual(outcome.state, OutcomeState.INVALID)
        self.assertEqual(outcome.diagnostics[0].code, "VAO-CNT-002")

    def test_wrong_immutable_context_is_rejected(self):
        def mutate(manifest: dict) -> None:
            manifest["@context"][0] = "https://w3id.org/modavis/vao/0.3/context.jsonld"

        with tempfile.TemporaryDirectory() as directory:
            path = rebuild_carrier(
                Path(directory) / "wrong-context.vao",
                mutate_manifest=mutate,
            )
            outcome = validate_package(path, hash_archive=False)
        self.assertEqual(outcome.state, OutcomeState.INVALID)
        self.assertTrue(any("context" in item.message for item in outcome.diagnostics))

    def test_complex_04_visual_acoustic_records_use_exact_embedded_realization(self):
        with tempfile.TemporaryDirectory() as directory:
            path = build_visual_bootstrap(Path(directory) / "visual-bootstrap.vao")
            reference = reference_validator_04().validate_archive(path)
            outcome = validate_package(path)
        self.assertTrue(reference["valid"], reference["errors"])
        self.assertEqual(outcome.state, OutcomeState.UNSUPPORTED)
        self.assertTrue(outcome.rights_acknowledgement_required)
        self.assertEqual(len(outcome.verified_assets), 1)
        self.assertEqual(len(outcome.logical_assets), 16)
        self.assertEqual(len(outcome.realizations), 17)
        scene = outcome.acoustic_scene
        self.assertIsNotNone(scene)
        self.assertEqual(len(scene.coordinate_frames), 3)
        self.assertEqual(len(scene.poses), 3)
        self.assertEqual(len(scene.measurements), 1)
        self.assertEqual(len(scene.impulse_responses), 1)
        self.assertEqual(
            scene.runtime_visual_realization_id,
            "urn:vao:fixture:acousticrooms:realization:geometry:glb",
        )
        self.assertEqual(
            scene.runtime_visual_binding_id,
            "urn:vao:fixture:acousticrooms:geometry-binding:visual",
        )
        instrument_pose = scene.poses["urn:vao:test:cuntz-positiv:pose:instrument"]
        self.assertEqual(
            instrument_pose.local_frame_id,
            "urn:vao:test:cuntz-positiv:frame:model",
        )


if __name__ == "__main__":
    unittest.main()
