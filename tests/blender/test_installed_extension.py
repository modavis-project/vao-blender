"""Smoke-test an installed release ZIP in an isolated Blender user profile."""

from __future__ import annotations

import importlib
import os
from pathlib import Path

import bpy

module_root = os.environ.get("VAO_BLENDER_SMOKE_MODULE", "bl_ext.vao_rc_test.vao_blender")
package_path = Path(os.environ["VAO_BLENDER_SMOKE_PACKAGE"])

archive = importlib.import_module(f"{module_root}.vao_blender.core.archive")
model = importlib.import_module(f"{module_root}.vao_blender.core.model")
scene_adapter = importlib.import_module(f"{module_root}.vao_blender.blender.scene_adapter")
session_api = importlib.import_module(f"{module_root}.vao_blender.blender.session")

assert module_root in bpy.context.preferences.addons
assert hasattr(bpy.context.scene, "vao_runtime")
outcome = archive.validate_package(package_path)
diagnostic_summary = "; ".join(
    f"{item.code}:{item.severity.value}:{item.message}" for item in outcome.diagnostics
)
assert outcome.state == model.OutcomeState.UNSUPPORTED, (
    f"unexpected validation state {outcome.state.value}; diagnostics={diagnostic_summary}"
)
assert outcome.contract_line == "0.4.0"
assert outcome.rights_acknowledgement_required

session = session_api.install_outcome(bpy.context.scene, outcome)
runtime = bpy.context.scene.vao_runtime
assert not session.rights_ready(bpy.context.scene)
assert bpy.ops.vao.acknowledge_rights() == {"FINISHED"}
assert runtime.state == "UNSUPPORTED"
assert runtime.support_state == "UNSUPPORTED"
assert runtime.rights_state == "ACKNOWLEDGED"
collection, object_count = scene_adapter.import_visual(
    session,
    bpy.context.scene,
    runtime.selected_realization_id,
)
assert object_count == 1
assert collection["vao_format_version"] == "0.4.0"
assert collection["vao_realization_id"] == runtime.selected_realization_id
scene_adapter.remove_materialization(session)
session_api.close_all()

print("VAO_BLENDER_INSTALLED_EXTENSION_OK")
