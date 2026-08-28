from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import MappingProxyType

from vao_blender.core.archive import validate_package
from vao_blender.core.contract import reference_validator_03, verify_contract_03
from vao_blender.core.model import (
    CoordinateFrameRecord,
    GeometryBindingRecord,
    LogicalAssetRecord,
    OutcomeState,
    PoseRecord,
    RealizationRecord,
)
from vao_blender.core.vao03 import (
    choose_runtime_visual,
    frame_to_root,
    pose_to_root,
    transform_point,
)

ROOT = Path(__file__).resolve().parents[2]
FIXTURE_ROOT = ROOT / "tests" / "fixtures" / "vao-0.3.2"
FIXTURE = FIXTURE_ROOT / "acousticrooms-bathrooms-idx-0.vao"
ORACLE = json.loads((FIXTURE_ROOT / "expected-inspection.json").read_text(encoding="utf-8"))


def rebuild_carrier(
    destination: Path,
    *,
    mutate_entry=None,
    mutate_manifest=None,
    extra_entries: dict[str, bytes] | None = None,
    force_zip64: bool = False,
) -> Path:
    with zipfile.ZipFile(FIXTURE, "r", allowZip64=True) as source:
        entries = [(info, source.read(info)) for info in source.infolist() if not info.is_dir()]
    values = {info.filename: data for info, data in entries}
    if mutate_manifest:
        manifest = json.loads(values["vao-manifest.json"])
        mutate_manifest(manifest)
        manifest_data = json.dumps(
            manifest, ensure_ascii=False, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
        values["vao-manifest.json"] = manifest_data
        carrier = json.loads(values["META-INF/vao-carrier.json"])
        carrier["manifestSHA256"] = hashlib.sha256(manifest_data).hexdigest()
        carrier["manifestByteSize"] = len(manifest_data)
        values["META-INF/vao-carrier.json"] = json.dumps(
            carrier, ensure_ascii=False, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
    with zipfile.ZipFile(destination, "w", allowZip64=True) as output:
        for original, _data in entries:
            data = values[original.filename]
            if mutate_entry:
                data = mutate_entry(original.filename, data)
            info = zipfile.ZipInfo(original.filename, date_time=original.date_time)
            info.compress_type = zipfile.ZIP_STORED
            info.create_system = 3
            info.external_attr = original.external_attr
            if force_zip64:
                with output.open(info, "w", force_zip64=True) as stream:
                    stream.write(data)
            else:
                output.writestr(info, data)
        for name, data in sorted((extra_entries or {}).items()):
            info = zipfile.ZipInfo(name)
            info.compress_type = zipfile.ZIP_STORED
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            output.writestr(info, data)
    return destination


class VAO03ContractTests(unittest.TestCase):
    def test_vendored_contract_integrity(self):
        verify_contract_03()

    def test_exact_dispatch_does_not_decode_draft_versions_as_02(self):
        with tempfile.TemporaryDirectory() as directory:
            path = rebuild_carrier(
                Path(directory) / "draft.vao",
                mutate_manifest=lambda manifest: manifest.__setitem__("formatVersion", "0.3.1"),
            )
            outcome = validate_package(path)
        self.assertEqual(outcome.state, OutcomeState.INVALID)
        self.assertIn("exact pinned 0.2.2, 0.3.2, 0.4.0, and 0.5.0", outcome.diagnostics[0].message)
        self.assertFalse(outcome.graph)

    def test_closed_manifest_rejects_unknown_root_property(self):
        with tempfile.TemporaryDirectory() as directory:
            path = rebuild_carrier(
                Path(directory) / "open.vao",
                mutate_manifest=lambda manifest: manifest.__setitem__("unexpected", True),
            )
            outcome = validate_package(path)
        self.assertEqual(outcome.state, OutcomeState.INVALID)
        self.assertTrue(any(item.code == "VAO03-SCH-001" for item in outcome.diagnostics))

    def test_small_force_zip64_carrier_is_processed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = rebuild_carrier(Path(directory) / "zip64.vao", force_zip64=True)
            outcome = validate_package(path, hash_archive=False)
        self.assertTrue(outcome.is_valid)
        self.assertEqual(len(outcome.verified_assets), 8)

    def test_pinned_orgrec_validator_report_matches_addon_result(self):
        reference = reference_validator_03().validate_archive(FIXTURE)
        outcome = validate_package(FIXTURE)
        self.assertTrue(reference["valid"])
        self.assertTrue(outcome.is_valid)
        self.assertEqual(reference["formatVersion"], outcome.contract_line)
        self.assertEqual(reference["manifestSHA256"], outcome.manifest_sha256)
        self.assertEqual(reference["embeddedRealizationCount"], len(outcome.verified_assets))
        self.assertEqual(reference["verifiedBytes"], outcome.verified_payload_bytes)

    def test_carrier_manifest_fixity_mismatch_is_rejected(self):
        def corrupt_descriptor(name: str, data: bytes) -> bytes:
            if name != "META-INF/vao-carrier.json":
                return data
            carrier = json.loads(data)
            carrier["manifestSHA256"] = "0" * 64
            return json.dumps(carrier, separators=(",", ":")).encode("utf-8")

        with tempfile.TemporaryDirectory() as directory:
            path = rebuild_carrier(
                Path(directory) / "bad-descriptor.vao",
                mutate_entry=corrupt_descriptor,
            )
            outcome = validate_package(path)
        self.assertEqual(outcome.state, OutcomeState.INVALID)
        self.assertTrue(any("manifestSHA256" in item.message for item in outcome.diagnostics))

    def test_unindexed_payload_breaks_carrier_closure(self):
        with tempfile.TemporaryDirectory() as directory:
            path = rebuild_carrier(
                Path(directory) / "unindexed.vao",
                extra_entries={"payload/unindexed.bin": b"not declared"},
            )
            outcome = validate_package(path)
        self.assertEqual(outcome.state, OutcomeState.INVALID)
        self.assertTrue(
            any("unindexed payload" in item.message.casefold() for item in outcome.diagnostics)
        )

    def test_noninvertible_coordinate_transform_is_rejected(self):
        def make_singular(manifest: dict) -> None:
            frame = next(
                item
                for item in manifest["acoustics"]["coordinateFrames"]
                if item.get("parentFrameId")
            )
            frame["transformToParent"] = [0.0] * 16

        with tempfile.TemporaryDirectory() as directory:
            path = rebuild_carrier(
                Path(directory) / "singular-frame.vao",
                mutate_manifest=make_singular,
            )
            outcome = validate_package(path)
        self.assertEqual(outcome.state, OutcomeState.INVALID)
        self.assertTrue(any("invertible" in item.message for item in outcome.diagnostics))


class VAO03InspectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.outcome = validate_package(FIXTURE)

    def test_pinned_carrier_and_payload_oracle(self):
        outcome = self.outcome
        with zipfile.ZipFile(FIXTURE, "r") as archive:
            file_names = [info.filename for info in archive.infolist() if not info.is_dir()]
        self.assertEqual(len(file_names), 11)
        self.assertEqual(len([name for name in file_names if name.startswith("payload/")]), 8)
        self.assertTrue(outcome.is_valid)
        self.assertEqual(outcome.contract_line, "0.3.2")
        self.assertEqual(outcome.archive_sha256, ORACLE["carrierSHA256"])
        self.assertEqual(outcome.manifest_sha256, ORACLE["manifestSHA256"])
        self.assertEqual(outcome.carrier.mode, ORACLE["carrierMode"])
        self.assertEqual(
            len(outcome.carrier.embedded_realizations), ORACLE["embeddedRealizationCount"]
        )
        self.assertEqual(outcome.verified_payload_bytes, ORACLE["verifiedPayloadBytes"])
        self.assertEqual(len(outcome.verified_assets), 8)
        self.assertEqual(len(outcome.logical_assets), 7)
        self.assertEqual(len(outcome.realizations), 8)

    def test_scene_counts_binding_and_exact_realization_selection(self):
        outcome = self.outcome
        scene = outcome.acoustic_scene
        self.assertEqual(len(scene.coordinate_frames), ORACLE["coordinateFrameCount"])
        self.assertEqual(len(scene.poses), ORACLE["poseCount"])
        self.assertEqual(len(scene.measurements), ORACLE["measurementCount"])
        geometry = [
            item
            for item in outcome.realizations.values()
            if item.technical_metadata.get("kind") == "geometry"
        ]
        self.assertEqual(len(geometry), ORACLE["geometryRealizationCount"])
        expected = ORACLE["visualGeometry"]
        self.assertEqual(scene.runtime_visual_realization_id, expected["realizationId"])
        realization = outcome.realizations[scene.runtime_visual_realization_id]
        self.assertEqual(
            realization.logical_asset_id,
            scene.geometry_bindings[scene.runtime_visual_binding_id].logical_asset_id,
        )
        self.assertEqual(realization.embedded_path, expected["path"])
        self.assertEqual(realization.sha256, expected["sha256"])
        self.assertEqual(realization.technical_metadata["coordinateFrameId"], expected["frameId"])

    def test_row_major_frame_graph_and_declared_positions(self):
        scene = self.outcome.acoustic_scene
        geometry = self.outcome.realizations[scene.runtime_visual_realization_id]
        frame_id = geometry.technical_metadata["coordinateFrameId"]
        root_id, matrix = frame_to_root(scene.coordinate_frames, frame_id)
        self.assertEqual(root_id, scene.common_frame_root_id)
        self.assertEqual(
            matrix,
            (
                1.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                -1.0,
                0.0,
                0.0,
                1.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                1.0,
            ),
        )
        self.assertEqual(transform_point(matrix, (1.0, 2.0, 3.0)), (1.0, -3.0, 2.0))
        source = ORACLE["source"]
        receiver = ORACLE["receiver"]
        self.assertEqual(scene.poses[source["poseId"]].position, tuple(source["position"]))
        self.assertEqual(scene.poses[receiver["poseId"]].position, tuple(receiver["position"]))
        measurement = next(iter(scene.measurements.values()))
        self.assertEqual(measurement.source_id, source["entityId"])
        self.assertEqual(measurement.receiver_id, receiver["entityId"])

    def test_pose_orientation_xyzw_is_composed_with_frame_transform(self):
        root = CoordinateFrameRecord(
            "urn:test:root", 3, "http://qudt.org/vocab/unit/M", "right", "+Z", "+Y"
        )
        pose = PoseRecord(
            "urn:test:pose",
            "urn:test:subject",
            root.id,
            (2.0, 3.0, 4.0),
            (0.0, 0.0, 2**-0.5, 2**-0.5),
        )
        root_id, matrix = pose_to_root({root.id: root}, pose)
        self.assertEqual(root_id, root.id)
        transformed = transform_point(matrix, (1.0, 0.0, 0.0))
        for actual, expected in zip(transformed, (2.0, 4.0, 4.0), strict=True):
            self.assertAlmostEqual(actual, expected)

    def test_rir_metadata_fixity_status_and_provenance(self):
        scene = self.outcome.acoustic_scene
        self.assertEqual(len(scene.impulse_responses), ORACLE["impulseResponseRealizationCount"])
        rir = scene.impulse_responses[0]
        expected = ORACLE["impulseResponse"]
        self.assertEqual(rir.realization_id, expected["realizationId"])
        self.assertEqual(rir.embedded_path, expected["path"])
        self.assertEqual(rir.sha256, expected["sha256"])
        self.assertEqual(rir.encoding, expected["encoding"])
        self.assertEqual(rir.sample_rate, expected["sampleRate"])
        self.assertEqual(rir.sample_count, expected["sampleCount"])
        self.assertEqual(rir.channel_count, expected["channelCount"])
        self.assertEqual(rir.channel_indices, (0,))
        self.assertTrue(rir.representation_status.endswith("/hybrid"))
        self.assertEqual(len(rir.provenance_ids), 2)
        response = scene.response_sets[rir.response_set_id]
        self.assertEqual(response.representation_status, "hybrid")
        self.assertEqual(response.measurement_ids, rir.measurement_ids)

    def test_corrupt_payload_fixity_is_rejected_without_touching_fixture(self):
        original_hash = hashlib.sha256(FIXTURE.read_bytes()).hexdigest()

        def corrupt(name: str, data: bytes) -> bytes:
            if name == ORACLE["impulseResponse"]["path"]:
                return data[:-1] + bytes([data[-1] ^ 0x01])
            return data

        with tempfile.TemporaryDirectory() as directory:
            path = rebuild_carrier(Path(directory) / "corrupt.vao", mutate_entry=corrupt)
            outcome = validate_package(path)
        self.assertEqual(outcome.state, OutcomeState.INVALID)
        self.assertTrue(any("SHA-256" in item.message for item in outcome.diagnostics))
        self.assertEqual(hashlib.sha256(FIXTURE.read_bytes()).hexdigest(), original_hash)

    def test_visual_choice_uses_binding_and_media_type_not_filename(self):
        logical = LogicalAssetRecord(
            "urn:test:logical",
            MappingProxyType({"en": "Room"}),
            ("https://w3id.org/modavis/vao/vocab/asset-role/spatial-model",),
            ("urn:test:room",),
            ("urn:test:exact",),
        )
        exact = RealizationRecord(
            "urn:test:exact",
            logical.id,
            "model/gltf-binary",
            4,
            "0" * 64,
            "converted",
            "production-spatial",
            (),
            (),
            MappingProxyType({"kind": "geometry"}),
            "payload/evidence/not-a-model.bin",
        )
        binding = GeometryBindingRecord(
            "urn:test:binding", "urn:test:room", logical.id, "runtime-visual"
        )
        self.assertEqual(
            choose_runtime_visual({logical.id: logical}, {exact.id: exact}, {binding.id: binding}),
            (exact.id, binding.id),
        )


if __name__ == "__main__":
    unittest.main()
