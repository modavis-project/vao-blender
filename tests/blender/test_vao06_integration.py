"""Inspect 0.6.0 Core and MMIC data with the installed extension."""

from __future__ import annotations

import importlib
import os
import sys
import tempfile
from pathlib import Path

import bpy

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tests.unit.test_vao04 import build_visual_bootstrap

FIXTURES = ROOT / "tests" / "fixtures" / "vao-0.6.0" / "carriers"
NAME = os.environ.get("VAO_BLENDER_SMOKE_MODULE", "bl_ext.vao_rc_test.vao_blender")
assert NAME in bpy.context.preferences.addons
archive = importlib.import_module(f"{NAME}.vao_blender.core.archive")
sessions = importlib.import_module(f"{NAME}.vao_blender.blender.session")

for filename, expected in (("minimal.vao", "SUPPORTED"), ("mmic-design.vao", "UNSUPPORTED")):
    outcome = archive.validate_package(FIXTURES / filename)
    assert outcome.is_valid, outcome.report()
    session = sessions.install_outcome(bpy.context.scene, outcome)
    runtime = bpy.context.scene.vao_runtime
    assert sessions.active_session(bpy.context.scene) is session
    assert runtime.format_version == "0.6.0"
    assert runtime.support_state == expected
    assert runtime.logical_asset_count == len(outcome.logical_assets)
    assert runtime.verified_assets == len(outcome.verified_assets)
    assert runtime.carrier_mode == "preservation-closure"
    assert not bpy.ops.vao.load_visual.poll()
    assert not session.outcome.interaction_plans
    if expected == "UNSUPPORTED":
        assert any(
            result.capability.endswith("/mmic/1.0.0") and not result.supported
            for result in outcome.capabilities
        )
    sessions.close_all()

with tempfile.TemporaryDirectory() as directory:
    fixture = build_visual_bootstrap(Path(directory) / "visual06.vao", format_version="0.6.0")
    outcome = archive.validate_package(fixture)
    assert outcome.is_valid, outcome.report()
    session = sessions.install_outcome(bpy.context.scene, outcome)
    runtime = bpy.context.scene.vao_runtime
    assert runtime.selected_realization_id.endswith(":geometry:glb")
    assert bpy.ops.vao.acknowledge_rights() == {"FINISHED"}
    assert bpy.ops.vao.load_visual.poll()
    assert bpy.ops.vao.load_visual() == {"FINISHED"}
    meshes = [
        obj
        for obj in bpy.data.objects
        if obj.type == "MESH" and obj.get("vao_format_version") == "0.6.0"
    ]
    assert len(meshes) == 1
    assert len(meshes[0].data.vertices) == 17429
    assert len(meshes[0].data.polygons) == 21760
    sessions.close_all()

print("VAO_BLENDER_06_INSTALLED_EXTENSION_OK")
