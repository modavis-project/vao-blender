from __future__ import annotations

import bpy
from bpy.props import BoolProperty, FloatProperty, IntProperty, PointerProperty, StringProperty


class VAORuntimeProperties(bpy.types.PropertyGroup):
    session_id: StringProperty(name="Session")
    state: StringProperty(name="State", default="EMPTY")
    status_message: StringProperty(name="Status", default="Choose a .vao package to begin")
    source_name: StringProperty(name="Source")
    title: StringProperty(name="Title")
    package_id: StringProperty(name="Package ID")
    revision: StringProperty(name="Revision")
    release_id: StringProperty(name="Release ID")
    format_version: StringProperty(name="Format")
    carrier_mode: StringProperty(name="Carrier mode")
    progress: FloatProperty(name="Progress", min=0.0, max=1.0, subtype="PERCENTAGE")
    progress_stage: StringProperty(name="Stage")
    verified_assets: IntProperty(name="Verified assets", default=0)
    entity_count: IntProperty(name="Entities", default=0)
    relation_count: IntProperty(name="Relations", default=0)
    asset_count: IntProperty(name="Assets", default=0)
    logical_asset_count: IntProperty(name="Logical assets", default=0)
    realization_count: IntProperty(name="Realizations", default=0)
    frame_count: IntProperty(name="Coordinate frames", default=0)
    pose_count: IntProperty(name="Poses", default=0)
    measurement_count: IntProperty(name="Measurements", default=0)
    response_set_count: IntProperty(name="Response sets", default=0)
    rir_count: IntProperty(name="Impulse responses", default=0)
    search: StringProperty(name="Search", description="Filter entities and assets")
    explore_page: IntProperty(name="Page", default=0, min=0)
    selected_asset_id: StringProperty(name="Selected asset")
    selected_entity_id: StringProperty(name="Selected entity")
    selected_logical_asset_id: StringProperty(name="Selected logical asset")
    selected_realization_id: StringProperty(name="Selected realization")
    rights_acknowledged: BoolProperty(
        name="Acknowledge rights/access limitations",
        description="Session-only acknowledgement; this is not permission or a licence",
        default=False,
    )
    performance_active: BoolProperty(name="Performance mode", default=False)


CLASSES = (VAORuntimeProperties,)


def register() -> None:
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.vao_runtime = PointerProperty(type=VAORuntimeProperties)


def unregister() -> None:
    if hasattr(bpy.types.Scene, "vao_runtime"):
        del bpy.types.Scene.vao_runtime
    for cls in reversed(CLASSES):
        if getattr(cls, "is_registered", False):
            bpy.utils.unregister_class(cls)
