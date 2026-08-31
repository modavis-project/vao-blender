from __future__ import annotations

import copy
import hashlib
import unittest

from vao_blender.core.graph import build_graph
from vao_blender.core.interaction_compile import compile_interactions

VAO = "https://w3id.org/modavis/vao/ontology#"
AUDIO = "https://w3id.org/modavis/ontology/audio#"


def playable_manifest() -> dict[str, list[dict]]:
    selection = "urn:test:selection"
    configuration = "urn:test:configuration"
    gate = "urn:test:gate"
    component = "urn:test:component"
    voice = "urn:test:voice"
    parameters = "urn:test:parameters"
    sample = "urn:test:sample"
    entities = [
        {
            "id": selection,
            "kind": "interaction",
            "labels": {"en": "Select"},
            "properties": {
                VAO + "controlProtocol": {"binding": "host-toggle"},
                VAO + "timingPolicy": {"selection": "toggle", "exclusivity": "independent"},
            },
        },
        {
            "id": gate,
            "kind": "interaction",
            "labels": {"en": "Gate"},
            "properties": {
                VAO + "controlProtocol": {"binding": "host-note-gate"},
                VAO + "controlDomain": {"keyNumber": 60},
                VAO + "timingPolicy": {"release": "on-gate-close"},
            },
        },
        {
            "id": voice,
            "kind": "interaction",
            "labels": {"en": "Voice"},
            "properties": {
                VAO + "controlProtocol": {"binding": "internal-scoped-voice"},
                VAO + "controlDomain": {
                    "keyNumber": 60,
                    "configurationId": configuration,
                },
            },
        },
        {
            "id": parameters,
            "kind": "parameterSet",
            "labels": {"en": "Parameters"},
            "properties": {
                AUDIO + "status": "reviewed",
                AUDIO + "gainDB": 0.0,
                AUDIO + "rootKeyNumber": 60,
                AUDIO + "minimumKeyNumber": 60,
                AUDIO + "maximumKeyNumber": 60,
                AUDIO + "minimumVelocity": 1,
                AUDIO + "maximumVelocity": 127,
                AUDIO + "targetFrequencyHz": 261.625565,
                AUDIO + "pitchTrackingMode": "preserveRecordedPitch",
                AUDIO + "noteOffPolicy": "voice-scoped-fade",
                AUDIO + "channelPolicy": "stereo-preserve",
                AUDIO + "envelope": {
                    "attackSeconds": 0.0,
                    "sustainLevel": 1.0,
                    "releaseSeconds": 0.3,
                    "curve": "linear",
                },
            },
        },
    ]
    relations = []

    def relation(subject: str, predicate: str, object_id: str) -> None:
        relations.append(
            {
                "id": f"urn:test:relation:{len(relations)}",
                "subjectId": subject,
                "predicate": predicate,
                "objectId": object_id,
                "status": "asserted",
            }
        )

    relation(selection, VAO + "configuration", configuration)
    relation(gate, VAO + "activates", component)
    relation(voice, VAO + "triggeredBy", gate)
    relation(voice, VAO + "configuration", configuration)
    relation(voice, VAO + "usesSample", sample)
    relation(voice, VAO + "activates", component)
    relation(voice, AUDIO + "usesPlaybackParameters", parameters)
    return {
        "entities": entities,
        "relations": relations,
        "assets": [
            {
                "id": sample,
                "path": "payload/sample.wav",
                "mediaType": "audio/wav",
                "byteSize": 1,
                "sha256": hashlib.sha256(b"sample").hexdigest(),
            }
        ],
    }


def compile_manifest(manifest: dict):
    return compile_interactions(build_graph(manifest))


def add_second_velocity_layer(manifest: dict, *, minimum: int, maximum: int) -> None:
    original_voice = manifest["entities"][2]
    original_parameters = manifest["entities"][3]
    duplicate_voice = copy.deepcopy(original_voice)
    duplicate_voice["id"] = "urn:test:voice:layer-two"
    duplicate_parameters = copy.deepcopy(original_parameters)
    duplicate_parameters["id"] = "urn:test:parameters:layer-two"
    duplicate_parameters["properties"][AUDIO + "minimumVelocity"] = minimum
    duplicate_parameters["properties"][AUDIO + "maximumVelocity"] = maximum
    manifest["entities"].extend((duplicate_voice, duplicate_parameters))
    duplicate_asset = copy.deepcopy(manifest["assets"][0])
    duplicate_asset["id"] = "urn:test:sample:layer-two"
    duplicate_asset["path"] = "payload/sample-layer-two.wav"
    duplicate_asset["sha256"] = hashlib.sha256(b"sample-layer-two").hexdigest()
    manifest["assets"].append(duplicate_asset)
    for relation in tuple(manifest["relations"]):
        if relation["subjectId"] != original_voice["id"]:
            continue
        duplicate_relation = copy.deepcopy(relation)
        duplicate_relation["id"] += ":layer-two"
        duplicate_relation["subjectId"] = duplicate_voice["id"]
        if duplicate_relation["predicate"] == VAO + "usesSample":
            duplicate_relation["objectId"] = duplicate_asset["id"]
        elif duplicate_relation["predicate"] == AUDIO + "usesPlaybackParameters":
            duplicate_relation["objectId"] = duplicate_parameters["id"]
        manifest["relations"].append(duplicate_relation)


class InteractionSupportMatrixTests(unittest.TestCase):
    def test_exact_supported_subset_compiles(self):
        bundle = compile_manifest(playable_manifest())
        self.assertTrue(bundle.supported)
        self.assertEqual((len(bundle.selections), len(bundle.gates), len(bundle.voices)), (1, 1, 1))

    def test_accepted_parameters_and_equal_power_curve_compile(self):
        manifest = playable_manifest()
        properties = manifest["entities"][3]["properties"]
        properties[AUDIO + "status"] = "accepted"
        properties[AUDIO + "envelope"]["curve"] = "equalPower"
        bundle = compile_manifest(manifest)
        self.assertTrue(bundle.supported)
        self.assertEqual(bundle.voices[0].envelope_curve, "equalPower")

    def test_envelope_values_must_be_explicit(self):
        manifest = playable_manifest()
        del manifest["entities"][3]["properties"][AUDIO + "envelope"]["sustainLevel"]
        bundle = compile_manifest(manifest)
        self.assertFalse(bundle.supported)
        self.assertIn("VAO-INT-020", {item.code for item in bundle.diagnostics})

    def test_disjoint_velocity_layers_compile_without_ambiguity(self):
        manifest = playable_manifest()
        manifest["entities"][3]["properties"][AUDIO + "maximumVelocity"] = 63
        add_second_velocity_layer(manifest, minimum=64, maximum=127)
        bundle = compile_manifest(manifest)
        self.assertTrue(bundle.supported)
        self.assertEqual(
            [(item.minimum_velocity, item.maximum_velocity) for item in bundle.voices],
            [(1, 63), (64, 127)],
        )

    def test_overlapping_velocity_layers_are_rejected(self):
        manifest = playable_manifest()
        add_second_velocity_layer(manifest, minimum=64, maximum=127)
        bundle = compile_manifest(manifest)
        self.assertFalse(bundle.supported)
        self.assertIn("VAO-INT-013", {item.code for item in bundle.diagnostics})

    def test_exclusive_selection_is_rejected_until_grouping_is_explicit(self):
        manifest = playable_manifest()
        manifest["entities"][0]["properties"][VAO + "timingPolicy"]["exclusivity"] = "exclusive"
        bundle = compile_manifest(manifest)
        self.assertFalse(bundle.supported)
        self.assertIn("VAO-INT-002", {item.code for item in bundle.diagnostics})

    def test_resample_is_not_claimed_without_a_pitch_ratio(self):
        manifest = playable_manifest()
        manifest["entities"][3]["properties"][AUDIO + "pitchTrackingMode"] = "resample"
        bundle = compile_manifest(manifest)
        self.assertFalse(bundle.supported)
        self.assertIn("VAO-INT-011", {item.code for item in bundle.diagnostics})

    def test_unsupported_channel_policy_is_rejected(self):
        manifest = playable_manifest()
        manifest["entities"][3]["properties"][AUDIO + "channelPolicy"] = "downmix-mono"
        bundle = compile_manifest(manifest)
        self.assertFalse(bundle.supported)
        self.assertIn("VAO-INT-019", {item.code for item in bundle.diagnostics})

    def test_unsafe_numeric_parameters_are_rejected(self):
        manifest = playable_manifest()
        manifest["entities"][3]["properties"][AUDIO + "gainDB"] = 120.0
        bundle = compile_manifest(manifest)
        self.assertFalse(bundle.supported)
        self.assertIn("VAO-INT-021", {item.code for item in bundle.diagnostics})

    def test_duplicate_gate_key_is_rejected(self):
        manifest = playable_manifest()
        duplicate = copy.deepcopy(manifest["entities"][1])
        duplicate["id"] = "urn:test:gate:duplicate"
        manifest["entities"].append(duplicate)
        manifest["relations"].append(
            {
                "id": "urn:test:relation:duplicate-gate",
                "subjectId": duplicate["id"],
                "predicate": VAO + "activates",
                "objectId": "urn:test:component:duplicate",
                "status": "asserted",
            }
        )
        bundle = compile_manifest(manifest)
        self.assertFalse(bundle.supported)
        self.assertIn("VAO-INT-015", {item.code for item in bundle.diagnostics})

    def test_voice_and_gate_components_may_represent_distinct_stages(self):
        manifest = playable_manifest()
        voice_activation = next(
            relation
            for relation in manifest["relations"]
            if relation["subjectId"] == "urn:test:voice"
            and relation["predicate"] == VAO + "activates"
        )
        voice_activation["objectId"] = "urn:test:component:other"
        bundle = compile_manifest(manifest)
        self.assertTrue(bundle.supported)
        self.assertEqual(bundle.gates[0].component_id, "urn:test:component")
        self.assertEqual(bundle.voices[0].component_id, "urn:test:component:other")


if __name__ == "__main__":
    unittest.main()
