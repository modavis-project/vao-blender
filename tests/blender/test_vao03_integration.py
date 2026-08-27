"""Run with Blender --background --factory-startup --python this_file.py."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

import bpy

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from vao_blender.blender.scene_adapter import import_visual, remove_materialization
from vao_blender.blender.session import SESSIONS, close_all, install_outcome
from vao_blender.core.archive import validate_package
from vao_blender.registration import register, unregister

FIXTURE_ROOT = ROOT / "tests" / "fixtures" / "vao-0.3.2"
FIXTURE = FIXTURE_ROOT / "acousticrooms-bathrooms-idx-0.vao"
ORACLE = json.loads((FIXTURE_ROOT / "expected-inspection.json").read_text(encoding="utf-8"))


register()
register()
outcome = validate_package(FIXTURE)
assert outcome.is_valid
assert outcome.contract_line == "0.3.2"
assert outcome.archive_sha256 == ORACLE["carrierSHA256"]
assert len(outcome.verified_assets) == ORACLE["embeddedRealizationCount"]
assert outcome.interaction_plans is None

session = install_outcome(bpy.context.scene, outcome)
runtime = bpy.context.scene.vao_runtime
assert runtime.format_version == "0.3.2"
assert runtime.carrier_mode == "preservation-closure"
assert runtime.logical_asset_count == 7
assert runtime.realization_count == 8
assert runtime.frame_count == 2
assert runtime.pose_count == 2
assert runtime.measurement_count == 1
assert runtime.rir_count == 1
assert runtime.selected_realization_id == ORACLE["visualGeometry"]["realizationId"]
try:
    session.ensure_audio()
    raise AssertionError("VAO 0.3.2 RIR was incorrectly exposed to the program-audio engine")
except RuntimeError as exc:
    assert "convolution" in str(exc)

# A decoder/preparation failure must leave every Blender scene datablock untouched.
before = {
    "objects": set(bpy.data.objects),
    "collections": set(bpy.data.collections),
    "meshes": set(bpy.data.meshes),
}
with patch(
    "vao_blender.blender.scene_adapter.inject_glb_node_indices",
    side_effect=RuntimeError("forced transactional rollback"),
):
    try:
        import_visual(session, bpy.context.scene, runtime.selected_realization_id)
        raise AssertionError("forced materialization failure did not propagate")
    except RuntimeError as exc:
        assert "forced transactional rollback" in str(exc)
assert set(bpy.data.objects) == before["objects"]
assert set(bpy.data.collections) == before["collections"]
assert set(bpy.data.meshes) == before["meshes"]
assert not session.root_collection_name

collection, count = import_visual(session, bpy.context.scene, runtime.selected_realization_id)
assert count > 0
expected_visual = ORACLE["visualGeometry"]
assert collection["vao_realization_id"] == expected_visual["realizationId"]
assert collection["vao_asset_sha256"] == expected_visual["sha256"]
assert collection["vao_logical_asset_id"] == ("urn:vao:fixture:acousticrooms:asset:room-geometry")
assert collection["vao_geometry_binding_id"] == (
    "urn:vao:fixture:acousticrooms:geometry-binding:visual"
)
assert collection["vao_coordinate_frame_id"] == expected_visual["frameId"]
assert collection["vao_common_frame_root_id"] == ("urn:vao:fixture:acousticrooms:frame:dataset")
declared = tuple(float(value) for value in collection["vao_declared_transform_row_major"])
assert declared == (
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
)

mesh_objects = [obj for obj in collection.all_objects if obj.type == "MESH"]
assert len(mesh_objects) == 1
mesh_object = mesh_objects[0]
assert mesh_object.name.startswith(expected_visual["expectedMeshName"])
assert mesh_object.data.name.startswith(expected_visual["expectedMeshName"])
assert len(mesh_object.data.vertices) == expected_visual["expectedVertexCount"]
assert len(mesh_object.data.polygons) == expected_visual["expectedPolygonCount"]
vertex_count = len(mesh_object.data.vertices)
for obj in collection.all_objects:
    assert obj["vao_package_id"] == outcome.manifest["id"]
    assert obj["vao_manifest_sha256"] == outcome.manifest_sha256
    assert obj["vao_realization_id"] == expected_visual["realizationId"]
    assert obj["vao_geometry_binding_id"] == (
        "urn:vao:fixture:acousticrooms:geometry-binding:visual"
    )

root = bpy.data.collections[session.root_collection_name]
assert root["vao_package_id"] == outcome.manifest["id"]
assert root["vao_release_id"] == outcome.manifest["release"]["id"]
assert root["vao_format_version"] == "0.3.2"
spatial = root.children["Spatial"]
assert spatial["vao_metadata_only"] is True
for child in root.children:
    assert child["vao_package_id"] == outcome.manifest["id"]
    assert child["vao_manifest_sha256"] == outcome.manifest_sha256
assert collection["vao_release_id"] == outcome.manifest["release"]["id"]
markers = [obj for obj in spatial.objects if obj.get("vao_measurement_id")]
assert len(markers) == 2
measurement_id = "urn:vao:fixture:acousticrooms:measurement:S000-R0011"
for marker in markers:
    assert marker["vao_measurement_id"] == measurement_id
    assert marker["vao_response_set_id"] == "urn:vao:fixture:acousticrooms:response-set"
    assert marker["vao_rir_realization_id"] == ORACLE["impulseResponse"]["realizationId"]
    assert marker["vao_rir_path"] == ORACLE["impulseResponse"]["path"]
    assert marker["vao_rir_sample_rate"] == ORACLE["impulseResponse"]["sampleRate"]
    assert marker["vao_rir_sample_count"] == ORACLE["impulseResponse"]["sampleCount"]
    assert marker["vao_rir_channel_count"] == ORACLE["impulseResponse"]["channelCount"]
    assert marker["vao_rir_encoding"] == ORACLE["impulseResponse"]["encoding"]
    assert marker["vao_format_version"] == "0.3.2"
    assert marker["vao_release_id"] == outcome.manifest["release"]["id"]
source = next(obj for obj in markers if obj["vao_spatial_role"] == "source")
receiver = next(obj for obj in markers if obj["vao_spatial_role"] == "receiver")
assert source["vao_entity_id"] == ORACLE["source"]["entityId"]
assert source["vao_pose_id"] == ORACLE["source"]["poseId"]
assert list(source["vao_declared_position"]) == ORACLE["source"]["position"]
assert receiver["vao_entity_id"] == ORACLE["receiver"]["entityId"]
assert receiver["vao_pose_id"] == ORACLE["receiver"]["poseId"]
assert list(receiver["vao_declared_position"]) == ORACLE["receiver"]["position"]
assert len(source["vao_pose_transform_row_major"]) == 16
assert len(receiver["vao_pose_transform_row_major"]) == 16
for actual, expected in zip(source.location, ORACLE["source"]["position"], strict=True):
    assert abs(actual - expected) < 1e-6
for actual, expected in zip(receiver.location, ORACLE["receiver"]["position"], strict=True):
    assert abs(actual - expected) < 1e-6

assert collection["vao_rir_support"] == "metadata-only"
assert collection["vao_rir_realization_id"] == ORACLE["impulseResponse"]["realizationId"]
assert collection["vao_rir_sha256"] == ORACLE["impulseResponse"]["sha256"]
assert collection["vao_rir_encoding"] == ORACLE["impulseResponse"]["encoding"]
assert collection["vao_rir_sample_rate"] == ORACLE["impulseResponse"]["sampleRate"]
assert collection["vao_rir_sample_count"] == ORACLE["impulseResponse"]["sampleCount"]
assert collection["vao_rir_channel_count"] == ORACLE["impulseResponse"]["channelCount"]
assert not [obj for obj in root.all_objects if obj.type == "SPEAKER"]

output = Path(os.environ.get("VAO_TEST_VAO03_BLEND", "/tmp/vao-blender-vao03-integration.blend"))
bpy.ops.wm.save_as_mainfile(filepath=str(output), check_existing=False)
assert output.is_file()

# Runtime teardown keeps user scene data; explicit materialization cleanup removes
# only the traceable root and its owned objects/datablocks.
root_name = session.root_collection_name
close_all()
assert not SESSIONS
assert root_name in bpy.data.collections
remove_materialization(session)
assert root_name not in bpy.data.collections
assert not [obj for obj in bpy.data.objects if obj.get("vao_package_id") == outcome.manifest["id"]]
assert set(bpy.data.objects) == before["objects"]
assert set(bpy.data.collections) == before["collections"]
assert set(bpy.data.meshes) == before["meshes"]

unregister()
unregister()
print(f"VAO_BLENDER_03_INTEGRATION_OK objects={count} vertices={vertex_count} blend={output}")
