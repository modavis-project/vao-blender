"""Run with Blender --background --factory-startup --python this_file.py."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import bpy

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tests.unit.test_vao04 import build_visual_bootstrap
from vao_blender.blender.scene_adapter import import_visual, remove_materialization
from vao_blender.blender.session import close_all, install_outcome
from vao_blender.core.archive import validate_package
from vao_blender.core.model import OutcomeState
from vao_blender.registration import register, unregister

register()
with tempfile.TemporaryDirectory() as directory:
    carrier = build_visual_bootstrap(Path(directory) / "visual-bootstrap.vao")
    outcome = validate_package(carrier)
    assert outcome.state == OutcomeState.UNSUPPORTED
    assert outcome.contract_line == "0.4.0"
    assert outcome.rights_acknowledgement_required
    assert len(outcome.verified_assets) == 1

    session = install_outcome(bpy.context.scene, outcome)
    runtime = bpy.context.scene.vao_runtime
    assert runtime.format_version == "0.4.0"
    assert runtime.carrier_mode == "bootstrap"
    assert runtime.logical_asset_count == 16
    assert runtime.realization_count == 17
    assert runtime.frame_count == 3
    assert runtime.pose_count == 3
    assert runtime.measurement_count == 1
    assert not session.rights_ready(bpy.context.scene)
    runtime.rights_acknowledged = True
    assert session.rights_ready(bpy.context.scene)

    expected_realization = "urn:vao:fixture:acousticrooms:realization:geometry:glb"
    assert runtime.selected_realization_id == expected_realization
    collection, object_count = import_visual(session, bpy.context.scene, expected_realization)
    assert object_count > 0
    assert collection["vao_format_version"] == "0.4.0"
    assert collection["vao_realization_id"] == expected_realization
    assert collection["vao_geometry_binding_id"] == (
        "urn:vao:fixture:acousticrooms:geometry-binding:visual"
    )
    assert collection["vao_common_frame_root_id"] == ("urn:vao:fixture:acousticrooms:frame:dataset")
    meshes = [obj for obj in collection.all_objects if obj.type == "MESH"]
    assert len(meshes) == 1
    assert len(meshes[0].data.vertices) == 17429
    assert len(meshes[0].data.polygons) == 21760

    root = bpy.data.collections[session.root_collection_name]
    assert root["vao_format_version"] == "0.4.0"
    markers = [obj for obj in root.children["Spatial"].objects if obj.get("vao_measurement_id")]
    assert len(markers) == 2
    assert all(marker["vao_format_version"] == "0.4.0" for marker in markers)
    try:
        session.ensure_audio()
        raise AssertionError("VAO 0.4 Playable/RIR content was exposed to the legacy audio engine")
    except RuntimeError as exc:
        assert "0.4 Playable" in str(exc)

    close_all()
    remove_materialization(session)

unregister()
print("VAO_BLENDER_04_INTEGRATION_OK")
