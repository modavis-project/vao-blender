"""Smoke-test the Kinoorgel bootstrap with an installed VAO Blender build."""

from __future__ import annotations

import importlib
import os
from pathlib import Path

import bpy

module_root = os.environ.get("VAO_BLENDER_SMOKE_MODULE", "bl_ext.vao_rc_test.vao_blender")
package_path = Path(os.environ["KINOORGEL_VAO_BOOTSTRAP"])

archive = importlib.import_module(f"{module_root}.vao_blender.core.archive")
model = importlib.import_module(f"{module_root}.vao_blender.core.model")
session_api = importlib.import_module(f"{module_root}.vao_blender.blender.session")

assert module_root in bpy.context.preferences.addons
outcome = archive.validate_package(package_path)
assert outcome.state == model.OutcomeState.UNSUPPORTED
assert outcome.is_valid
assert outcome.contract_line == "0.5.0"
assert outcome.carrier.mode == "bootstrap"
assert len(outcome.verified_assets) == 36
assert len(outcome.logical_assets) == 1462
assert len(outcome.realizations) == 4584
assert not outcome.rights_acknowledgement_required
assert outcome.acoustic_scene is None

session = session_api.install_outcome(bpy.context.scene, outcome)
runtime = bpy.context.scene.vao_runtime
assert runtime.format_version == "0.5.0"
assert runtime.carrier_mode == "bootstrap"
assert runtime.scientific_observation_count == 5766
assert runtime.protocol_binding_count == 543
assert runtime.physical_component_count == 110
assert runtime.distribution_count == 4548
assert session.rights_ready(bpy.context.scene)

session_api.close_all()
print("VAO_BLENDER_INSTALLED_KINOORGEL_05_OK")
