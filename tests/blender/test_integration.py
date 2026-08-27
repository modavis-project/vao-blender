"""Run with Blender --background --factory-startup --python this_file.py."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import bpy

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from vao_blender.blender.scene_adapter import create_control_surface, import_visual
from vao_blender.blender.session import close_all, install_outcome
from vao_blender.core.archive import validate_package
from vao_blender.registration import register, unregister

register()
register()
assert hasattr(bpy.types.Scene, "vao_runtime")
package = ROOT / "dist/Cuntz-Positiv-4010243-VAO-0.2.2.vao"
outcome = validate_package(package, verify_payload=False, hash_archive=False)
assert outcome.is_valid
session = install_outcome(bpy.context.scene, outcome)
assert bpy.context.scene.vao_runtime.state == "BLOCKED-RIGHTS"
assert outcome.interaction_plans.summary()["selections"] == 5
assert outcome.interaction_plans.summary()["gates"] == 45
assert outcome.interaction_plans.summary()["voices"] == 225
assert bpy.ops.vao.acknowledge_rights() == {"FINISHED"}
assert bpy.context.scene.vao_runtime.rights_acknowledged
assert bpy.context.scene.vao_runtime.state == "VALID"
asset = next(
    item for item in outcome.graph.assets.values() if item.original_filename == "positiv_keys.glb"
)
collection, count = import_visual(session, bpy.context.scene, asset.id)
assert count > 0 and collection.get("vao_asset_id") == asset.id
bound_asset = next(
    item
    for item in outcome.graph.assets.values()
    if item.original_filename == "4010243_segmented.glb"
)
bound_collection, bound_count = import_visual(session, bpy.context.scene, bound_asset.id)
assert bound_count > 0 and bound_collection.get("vao_asset_id") == bound_asset.id
assert any(obj.get("vao_geometry_binding_id") for obj in bound_collection.all_objects)
assert create_control_surface(session, bpy.context.scene) == 50
output = Path(os.environ.get("VAO_TEST_BLEND", "/tmp/vao-blender-integration.blend"))
bpy.ops.wm.save_as_mainfile(filepath=str(output), check_existing=False)
assert output.is_file()
close_all()
unregister()
register()
unregister()
unregister()
print(f"VAO_BLENDER_INTEGRATION_OK objects={count + bound_count} blend={output}")
