from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from vao_blender.core.archive import (
    MIMETYPE,
    ValidationLimits,
    validate_archive_path,
    validate_package,
)
from vao_blender.core.cache import AssetCache, CacheError
from vao_blender.core.contract import verify_contract
from vao_blender.core.gltf import GLTFError, inject_glb_node_indices
from vao_blender.core.graph import build_graph
from vao_blender.core.interaction_compile import compile_interactions
from vao_blender.core.model import AssetRecord, OutcomeState
from vao_blender.core.strict_json import StrictJSONError, loads

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "fixtures" / "vao-0.2.2"
VAO = "https://w3id.org/modavis/vao/ontology#"
AUDIO = "https://w3id.org/modavis/ontology/audio#"


def cuntz_interaction_manifest() -> dict[str, list[dict]]:
    """Build the tracked declarative equivalent of the Cuntz 5 x 45 voice matrix."""
    keys = [
        36,
        38,
        40,
        41,
        43,
        *range(45, 85),
    ]
    stops = ("ged", "princ4", "princ2", "qui223", "reg8")
    entities: list[dict] = []
    assets: list[dict] = []
    relations: list[dict] = []

    def add_relation(subject: str, predicate: str, obj: str) -> None:
        relations.append(
            {
                "id": f"urn:test:relation:{len(relations):04d}",
                "subjectId": subject,
                "predicate": predicate,
                "objectId": obj,
                "status": "asserted",
            }
        )

    for stop in stops:
        configuration_id = f"urn:test:configuration:{stop}"
        selection_id = f"urn:test:selection:{stop}"
        entities.append(
            {
                "id": selection_id,
                "kind": "interaction",
                "labels": {"en": f"Select {stop}"},
                "properties": {
                    VAO + "controlProtocol": {"binding": "host-toggle"},
                    VAO + "timingPolicy": {
                        "selection": "toggle",
                        "exclusivity": "independent",
                    },
                },
            }
        )
        add_relation(selection_id, VAO + "configuration", configuration_id)

    for key in keys:
        gate_id = f"urn:test:gate:{key}"
        component_id = f"urn:test:component:{key}"
        entities.append(
            {
                "id": gate_id,
                "kind": "interaction",
                "labels": {"en": f"Gate key {key}"},
                "properties": {
                    VAO + "controlDomain": {"keyNumber": key},
                    VAO + "controlProtocol": {"binding": "host-note-gate"},
                    VAO + "timingPolicy": {"release": "on-gate-close"},
                },
            }
        )
        add_relation(gate_id, VAO + "activates", component_id)

        for stop in stops:
            configuration_id = f"urn:test:configuration:{stop}"
            voice_id = f"urn:test:voice:{stop}:{key}"
            asset_id = f"urn:test:asset:{stop}:{key}"
            parameter_id = f"urn:test:parameters:{stop}:{key}"
            entities.extend(
                (
                    {
                        "id": voice_id,
                        "kind": "interaction",
                        "labels": {"en": f"Voice {stop} {key}"},
                        "properties": {
                            VAO + "controlDomain": {
                                "keyNumber": key,
                                "configurationId": configuration_id,
                            },
                            VAO + "controlProtocol": {"binding": "internal-scoped-voice"},
                        },
                    },
                    {
                        "id": parameter_id,
                        "kind": "parameterSet",
                        "labels": {"en": f"Playback parameters {stop} {key}"},
                        "properties": {
                            AUDIO + "channelPolicy": "stereo-preserve",
                            AUDIO + "envelope": {
                                "attackSeconds": 0.0,
                                "curve": "linear",
                                "releaseSeconds": 0.3,
                            },
                            AUDIO + "gainDB": 0.0,
                            AUDIO + "noteOffPolicy": "voice-scoped-fade",
                            AUDIO + "pitchTrackingMode": "preserveRecordedPitch",
                            AUDIO + "status": "reviewed",
                        },
                    },
                )
            )
            assets.append(
                {
                    "id": asset_id,
                    "path": f"payload/audio/{stop}/{key}.wav",
                    "mediaType": "audio/wav",
                    "byteSize": 1,
                    "sha256": hashlib.sha256(asset_id.encode()).hexdigest(),
                }
            )
            add_relation(voice_id, VAO + "triggeredBy", gate_id)
            add_relation(voice_id, VAO + "configuration", configuration_id)
            add_relation(voice_id, VAO + "usesSample", asset_id)
            add_relation(voice_id, VAO + "activates", component_id)
            add_relation(voice_id, AUDIO + "usesPlaybackParameters", parameter_id)

    return {"entities": entities, "assets": assets, "relations": relations}


def package_fixture(name: str, destination: Path, *, mutate=None) -> Path:
    source = FIXTURES / name
    manifest = json.loads((source / "vao-manifest.json").read_text(encoding="utf-8"))
    if mutate:
        mutate(manifest)
    with zipfile.ZipFile(destination, "w", allowZip64=True) as archive:
        archive.writestr("mimetype", MIMETYPE, compress_type=zipfile.ZIP_STORED)
        archive.writestr(
            "vao-manifest.json",
            json.dumps(manifest, ensure_ascii=False, separators=(",", ":")),
            compress_type=zipfile.ZIP_DEFLATED,
        )
        for path in sorted((source / "payload").rglob("*")):
            if path.is_file():
                archive.write(
                    path, path.relative_to(source).as_posix(), compress_type=zipfile.ZIP_STORED
                )
    return destination


class StrictJSONTests(unittest.TestCase):
    def test_duplicate_keys_rejected(self):
        with self.assertRaises(StrictJSONError):
            loads('{"a": 1, "a": 2}')

    def test_non_finite_rejected(self):
        with self.assertRaises(StrictJSONError):
            loads('{"a": NaN}')


class ArchivePathTests(unittest.TestCase):
    def test_safe_path(self):
        self.assertEqual(validate_archive_path("payload/audio/note.wav"), "payload/audio/note.wav")

    def test_traversal_and_platform_paths_rejected(self):
        for value in (
            "payload/../escape",
            "C:/payload/a",
            "payload\\a",
            "/payload/a",
            "payload//a",
        ):
            with self.subTest(value=value), self.assertRaises(RuntimeError):
                validate_archive_path(value)


class ValidationTests(unittest.TestCase):
    def test_default_total_limit_covers_a_50_gb_repository_record(self):
        self.assertGreaterEqual(
            ValidationLimits().max_total_expanded_bytes,
            50_000_000_000,
        )

    def test_vendored_contract_integrity(self):
        verify_contract()

    def test_pinned_positive_fixture(self):
        with tempfile.TemporaryDirectory() as directory:
            path = package_fixture("minimal-string-instrument", Path(directory) / "positive.vao")
            outcome = validate_package(path)
        self.assertTrue(outcome.is_valid)
        self.assertEqual(len(outcome.verified_assets), 1)
        self.assertEqual(outcome.verified_payload_bytes, 63)
        self.assertFalse(outcome.diagnostics)

    def test_payload_tamper_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = package_fixture("minimal-string-instrument", Path(directory) / "tampered.vao")
            with zipfile.ZipFile(path, "a") as archive:
                archive.writestr("payload/extra.bin", b"hidden")
            outcome = validate_package(path)
        self.assertEqual(outcome.state, OutcomeState.INVALID)
        self.assertTrue(
            any(item.code in {"VAO-SEM-016", "VAO-CNT-014"} for item in outcome.diagnostics)
        )

    def test_schema_mutation_rejected(self):
        def mutate(manifest):
            manifest["formatVersion"] = 22

        with tempfile.TemporaryDirectory() as directory:
            path = package_fixture(
                "minimal-string-instrument", Path(directory) / "schema.vao", mutate=mutate
            )
            outcome = validate_package(path)
        self.assertEqual(outcome.state, OutcomeState.INVALID)

    def test_nearby_02_version_is_not_accepted_as_022(self):
        with tempfile.TemporaryDirectory() as directory:
            path = package_fixture(
                "minimal-string-instrument",
                Path(directory) / "nearby-version.vao",
                mutate=lambda manifest: manifest.__setitem__("formatVersion", "0.2.3"),
            )
            outcome = validate_package(path)
        self.assertEqual(outcome.state, OutcomeState.INVALID)
        self.assertIn("exact pinned 0.2.2, 0.3.2, 0.4.0, and 0.5.0", outcome.diagnostics[0].message)

    def test_cuntz_manifest_compiles_exact_matrix(self):
        bundle = compile_interactions(build_graph(cuntz_interaction_manifest()))
        self.assertTrue(bundle.supported)
        self.assertEqual(
            (len(bundle.selections), len(bundle.gates), len(bundle.voices)), (5, 45, 225)
        )
        self.assertEqual([gate.key_number for gate in bundle.gates][:5], [36, 38, 40, 41, 43])
        self.assertTrue({37, 39, 42, 44}.isdisjoint(gate.key_number for gate in bundle.gates))
        self.assertEqual(
            len({(voice.configuration_id, voice.key_number) for voice in bundle.voices}), 225
        )


class CacheTests(unittest.TestCase):
    def test_extract_reuse_and_quarantine_tamper(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            payload = b"verified media"
            digest = hashlib.sha256(payload).hexdigest()
            asset = AssetRecord(
                "urn:test", "payload/media.bin", "application/octet-stream", len(payload), digest
            )
            archive_path = base / "test.vao"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr(asset.path, payload)
            cache = AssetCache(base / "cache")
            target = cache.extract(archive_path, asset)
            self.assertEqual(target.read_bytes(), payload)
            target.write_bytes(b"tampered")
            restored = cache.extract(archive_path, asset)
            self.assertEqual(restored.read_bytes(), payload)
            self.assertEqual(len(list((base / "cache/quarantine").iterdir())), 1)

    def test_clear_requires_marker(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(CacheError):
                AssetCache(Path(directory) / "unmanaged").clear()


class GLBTests(unittest.TestCase):
    def test_node_index_injection(self):
        import struct

        document = json.dumps(
            {"asset": {"version": "2.0"}, "nodes": [{"name": "same"}, {"name": "same"}]},
            separators=(",", ":"),
        ).encode()
        document += b" " * ((-len(document)) % 4)
        blob = bytearray(struct.pack("<4sII", b"glTF", 2, 20 + len(document)))
        blob += struct.pack("<II", len(document), 0x4E4F534A) + document
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.glb"
            destination = Path(directory) / "derived.glb"
            source.write_bytes(blob)
            self.assertEqual(inject_glb_node_indices(source, destination), 2)
            data = destination.read_bytes()
        length = int.from_bytes(data[12:16], "little")
        parsed = json.loads(data[20 : 20 + length].decode())
        self.assertEqual(
            [node["extras"]["vao_blender_node_index"] for node in parsed["nodes"]], [0, 1]
        )

    def test_binary_chunk_is_streamed_byte_identically(self):
        import struct

        document = json.dumps({"asset": {"version": "2.0"}, "nodes": [{}]}).encode()
        document += b" " * ((-len(document)) % 4)
        binary = bytes(range(256)) * 32_768
        blob = bytearray(struct.pack("<4sII", b"glTF", 2, 28 + len(document) + len(binary)))
        blob += struct.pack("<II", len(document), 0x4E4F534A) + document
        blob += struct.pack("<II", len(binary), 0x004E4942) + binary
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.glb"
            destination = Path(directory) / "derived.glb"
            source.write_bytes(blob)
            inject_glb_node_indices(source, destination)
            result = destination.read_bytes()
        json_length = int.from_bytes(result[12:16], "little")
        bin_header = 20 + json_length
        bin_length = int.from_bytes(result[bin_header : bin_header + 4], "little")
        self.assertEqual(result[bin_header + 8 : bin_header + 8 + bin_length], binary)

    def test_failed_rewrite_leaves_no_partial_destination(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.glb"
            destination = Path(directory) / "derived.glb"
            source.write_bytes(b"not a glb")
            with self.assertRaises(GLTFError):
                inject_glb_node_indices(source, destination)
            self.assertFalse(destination.exists())

    def test_external_glb_resource_uri_is_rejected(self):
        import struct

        document = json.dumps(
            {
                "asset": {"version": "2.0"},
                "buffers": [{"uri": "https://example.invalid/payload.bin", "byteLength": 1}],
                "nodes": [],
            },
            separators=(",", ":"),
        ).encode()
        document += b" " * ((-len(document)) % 4)
        blob = bytearray(struct.pack("<4sII", b"glTF", 2, 20 + len(document)))
        blob += struct.pack("<II", len(document), 0x4E4F534A) + document
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "external.glb"
            destination = Path(directory) / "derived.glb"
            source.write_bytes(blob)
            with self.assertRaises(GLTFError):
                inject_glb_node_indices(source, destination)
            self.assertFalse(destination.exists())


if __name__ == "__main__":
    unittest.main()
