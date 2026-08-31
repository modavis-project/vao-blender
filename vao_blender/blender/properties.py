from __future__ import annotations

import bpy
from bpy.props import (
    BoolProperty,
    CollectionProperty,
    EnumProperty,
    FloatProperty,
    IntProperty,
    PointerProperty,
    StringProperty,
)


def _reset_explore_page(self, _context) -> None:
    self.explore_page = 0
    self.explore_details_page = 0
    self.entity_properties_page = 0
    self.relation_properties_page = 0
    self.linked_assets_page = 0
    self.asset_properties_page = 0
    self.record_properties_page = 0


def _reset_diagnostics_page(self, _context) -> None:
    self.diagnostics_page = 0


class VAODetachedMaterializationProperties(bpy.types.PropertyGroup):
    materialization_id: StringProperty(name="Materialization ID")
    root_name: StringProperty(name="Collection")
    title: StringProperty(name="Title")
    package_id: StringProperty(name="Package ID")
    revision: StringProperty(name="Revision")
    release_id: StringProperty(name="Release ID")
    format_version: StringProperty(name="Format")
    manifest_sha256: StringProperty(name="Manifest SHA-256")
    archive_sha256: StringProperty(name="Archive SHA-256")
    source_path: StringProperty(
        name="Original source filename",
        options={"SKIP_SAVE"},
    )


class VAORuntimeProperties(bpy.types.PropertyGroup):
    session_id: StringProperty(name="Live session")
    materialization_id: StringProperty(name="Materialization")
    root_collection_name: StringProperty(name="Managed collection")
    state: StringProperty(name="Result", default="EMPTY")
    result_state: StringProperty(name="Validation result")
    validity_state: StringProperty(name="Validity", default="NOT_EVALUATED")
    support_state: StringProperty(name="Runtime support", default="NOT_EVALUATED")
    rights_state: StringProperty(name="Media rights", default="NOT_EVALUATED")
    materialization_state: StringProperty(name="Scene data", default="NONE")
    status_message: StringProperty(name="Status", default="Choose a .vao package to begin")
    source_path: StringProperty(
        name="Source",
        subtype="FILE_PATH",
        options={"SKIP_SAVE"},
    )
    source_name: StringProperty(name="Source name")
    title: StringProperty(name="Title")
    package_id: StringProperty(name="Package ID")
    revision: StringProperty(name="Revision")
    release_id: StringProperty(name="Release ID")
    format_version: StringProperty(name="Format")
    carrier_mode: StringProperty(name="Carrier mode")
    archive_sha256: StringProperty(name="Archive SHA-256")
    manifest_sha256: StringProperty(name="Manifest SHA-256")
    expected_archive_sha256: StringProperty(name="Expected archive SHA-256")
    expected_manifest_sha256: StringProperty(name="Expected manifest SHA-256")
    progress: FloatProperty(name="Progress", min=0.0, max=1.0, subtype="PERCENTAGE")
    progress_stage: StringProperty(name="Stage")
    progress_detail: StringProperty(name="Current item")
    progress_completed_entries: IntProperty(name="Completed entries", min=0)
    progress_total_entries: IntProperty(name="Total entries", min=0)
    progress_verified_bytes: StringProperty(name="Verified bytes")
    progress_total_bytes: StringProperty(name="Total bytes")
    verified_assets: IntProperty(name="Verified assets", default=0)
    entity_count: IntProperty(name="Entities", default=0)
    relation_count: IntProperty(name="Relations", default=0)
    asset_count: IntProperty(name="Assets", default=0)
    logical_asset_count: IntProperty(name="Logical assets", default=0)
    realization_count: IntProperty(name="Realizations", default=0)
    scientific_observation_count: IntProperty(name="Scientific observations", default=0)
    protocol_binding_count: IntProperty(name="Protocol bindings", default=0)
    physical_component_count: IntProperty(name="Physical components", default=0)
    distribution_count: IntProperty(name="Distributions", default=0)
    frame_count: IntProperty(name="Coordinate frames", default=0)
    pose_count: IntProperty(name="Poses", default=0)
    measurement_count: IntProperty(name="Measurements", default=0)
    response_set_count: IntProperty(name="Response sets", default=0)
    rir_count: IntProperty(name="Impulse responses", default=0)

    search: StringProperty(
        name="Search",
        description="Filter identifiers, labels, types, filenames, media types, and roles",
        update=_reset_explore_page,
    )
    explore_category: EnumProperty(
        name="Explore",
        items=(
            ("ENTITIES", "Entities", "Browse graph entities and relations"),
            ("ASSETS", "Assets", "Browse byte assets and realizations"),
            ("CAPABILITIES", "Capabilities", "Browse supported and unsupported capabilities"),
            (
                "RECORDS",
                "Records",
                "Browse validated scientific, interaction, physical, rights, and provenance records",
            ),
        ),
        default="ENTITIES",
        update=_reset_explore_page,
    )
    entity_kind_filter: StringProperty(name="Kind/type contains", update=_reset_explore_page)
    role_filter: StringProperty(name="Role contains", update=_reset_explore_page)
    representation_status_filter: StringProperty(
        name="Representation status contains", update=_reset_explore_page
    )
    relation_status_filter: StringProperty(
        name="Relation status contains", update=_reset_explore_page
    )
    capability_filter: EnumProperty(
        name="Capability support",
        items=(
            ("ALL", "All", "Show every negotiated capability"),
            ("SUPPORTED", "Supported", "Show supported capabilities"),
            ("UNSUPPORTED", "Unsupported", "Show unsupported capabilities"),
        ),
        default="ALL",
        update=_reset_explore_page,
    )
    explore_page: IntProperty(name="Page", default=0, min=0)
    explore_details_page: IntProperty(name="Detail page", default=0, min=0)
    entity_properties_page: IntProperty(name="Entity properties page", default=0, min=0)
    relation_properties_page: IntProperty(name="Relation properties page", default=0, min=0)
    linked_assets_page: IntProperty(name="Linked assets page", default=0, min=0)
    asset_properties_page: IntProperty(name="Asset properties page", default=0, min=0)
    record_properties_page: IntProperty(name="Record properties page", default=0, min=0)
    selected_asset_id: StringProperty(name="Selected asset")
    selected_entity_id: StringProperty(name="Selected entity")
    selected_relation_id: StringProperty(name="Selected relation")
    selected_logical_asset_id: StringProperty(name="Selected logical asset")
    selected_realization_id: StringProperty(name="Selected realization")
    selected_record_key: StringProperty(name="Selected model record")
    model_section: EnumProperty(
        name="Record family",
        items=(
            ("SCIENTIFIC", "Scientific", "Scientific provenance and evidence records"),
            ("INTERACTION", "Interaction", "Interaction model registries"),
            ("PHYSICAL", "Physical", "Physical-system topology records"),
            ("DISTRIBUTIONS", "Distributions", "Distribution and carrier records"),
            ("RIGHTS", "Rights", "Rights and access records"),
            ("PROVENANCE", "Provenance", "Top-level provenance records"),
        ),
        default="SCIENTIFIC",
        update=_reset_explore_page,
    )

    diagnostics_search: StringProperty(name="Search diagnostics", update=_reset_diagnostics_page)
    diagnostics_severity: EnumProperty(
        name="Severity",
        items=(
            ("ALL", "All", "Show all severities"),
            ("ERROR", "Errors", "Show errors"),
            ("WARNING", "Warnings", "Show warnings"),
            ("INFO", "Information", "Show informational diagnostics"),
        ),
        default="ALL",
        update=_reset_diagnostics_page,
    )
    diagnostics_stage: EnumProperty(
        name="Stage",
        items=(
            ("ALL", "All", "Show every validation stage"),
            ("CONTAINER", "Container", "Container and archive checks"),
            ("SCHEMA", "Schema", "Schema checks"),
            ("SEMANTIC", "Semantic", "Semantic checks"),
            ("CAPABILITY", "Capability", "Capability negotiation"),
            ("GLTF", "glTF", "glTF checks"),
            ("INTERACTION", "Interaction", "Interaction compilation"),
            ("AUDIO", "Audio", "Audio checks"),
            ("LIFECYCLE", "Lifecycle", "Lifecycle and local host checks"),
        ),
        default="ALL",
        update=_reset_diagnostics_page,
    )
    diagnostics_page: IntProperty(name="Diagnostic page", default=0, min=0)
    acoustic_measurement_page: IntProperty(name="Measurement page", default=0, min=0)
    acoustic_response_page: IntProperty(name="Response page", default=0, min=0)
    acoustic_rir_page: IntProperty(name="Impulse-response page", default=0, min=0)
    rights_page: IntProperty(name="Rights page", default=0, min=0)
    detached_page: IntProperty(name="Detached materializations page", default=0, min=0)
    play_selection_page: IntProperty(name="Playable selections page", default=0, min=0)
    play_gate_page: IntProperty(name="Playable gates page", default=0, min=0)

    rights_acknowledged: BoolProperty(
        name="Acknowledge rights/access limitations",
        description="Session-only acknowledgement; this is not permission or a licence",
        default=False,
        options={"SKIP_SAVE"},
    )
    media_enabled: BoolProperty(name="Media enabled", default=False, options={"SKIP_SAVE"})
    performance_active: BoolProperty(name="Performance mode", default=False, options={"SKIP_SAVE"})
    detached_count: IntProperty(name="Detached materializations", default=0, min=0)
    detached_materializations: CollectionProperty(type=VAODetachedMaterializationProperties)


CLASSES = (VAODetachedMaterializationProperties, VAORuntimeProperties)


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
