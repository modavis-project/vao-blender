"""VAO sidebar: Overview, Explore, Visual-Acoustic Scene, Play, and Diagnostics."""

from __future__ import annotations

import json
import math

import bpy

from .performance import EVENT_KEYS
from .scene_adapter import representation_collection
from .session import active_session, selected_detached

PAGE_SIZE = 8
DETAIL_PAGE_SIZE = 8
DIAGNOSTIC_PAGE_SIZE = 6
ACOUSTIC_PAGE_SIZE = 5


class VAO_PT_base:
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "VAO"


class VAO_PT_overview(VAO_PT_base, bpy.types.Panel):
    bl_idname = "VAO_PT_overview"
    bl_label = "Overview"

    def draw(self, context):
        layout = self.layout
        runtime = context.scene.vao_runtime
        session = active_session(context.scene)
        row = layout.row(align=True)
        row.operator("vao.import_package", text="Open VAO", icon="IMPORT")
        if session:
            row.operator("vao.close_package", text="Close Runtime", icon="X")

        if runtime.state == "VALIDATING":
            status = layout.box()
            status.label(text="Validating untrusted package", icon="LOCKED")
            status.prop(runtime, "progress", text=runtime.progress_stage or "Validation")
            for line in _wrap(runtime.progress_detail, 72):
                status.label(text=line)
            if runtime.progress_total_entries:
                status.label(
                    text=(
                        f"Entries {runtime.progress_completed_entries:,}/"
                        f"{runtime.progress_total_entries:,}"
                    )
                )
            if runtime.progress_total_bytes != "0 B":
                status.label(
                    text=f"Verified {runtime.progress_verified_bytes} / {runtime.progress_total_bytes}"
                )
            cancel = status.row()
            cancel.scale_y = 1.25
            cancel.operator("vao.cancel_validation", icon="CANCEL")
            status.label(text="No payload is decoded or added to the scene during validation.")
            return

        states = layout.box()
        states.label(text="Independent result dimensions")
        _state_row(states, "Package validity", runtime.validity_state)
        _state_row(states, "Runtime support", runtime.support_state)
        _state_row(states, "Rights/media", runtime.rights_state)
        _state_row(states, "Scene data", runtime.materialization_state)
        for line in _wrap(runtime.status_message, 74):
            states.label(text=line)

        if not session:
            _draw_detached(context, layout)
            return

        box = layout.box()
        box.label(text=runtime.title or runtime.source_name or "Untitled VAO", icon="PACKAGE")
        box.label(
            text=f"Format {runtime.format_version or 'unknown'} · revision {runtime.revision or '—'}"
        )
        _full_value(box, "Package", runtime.package_id)
        if runtime.release_id:
            _full_value(box, "Release", runtime.release_id)
        box.label(text=f"Entities {runtime.entity_count:,} · relations {runtime.relation_count:,}")
        if runtime.format_version in {"0.3.2", "0.4.0", "0.5.0"}:
            box.label(
                text=(
                    f"Logical assets {runtime.logical_asset_count:,} · "
                    f"realizations {runtime.realization_count:,}"
                )
            )
            box.label(
                text=f"Carrier {runtime.carrier_mode or '—'} · verified {runtime.verified_assets:,}"
            )
            if runtime.format_version == "0.5.0":
                box.label(
                    text=(
                        f"Observations {runtime.scientific_observation_count:,} · "
                        f"protocol bindings {runtime.protocol_binding_count:,}"
                    )
                )
                box.label(
                    text=(
                        f"Physical components {runtime.physical_component_count:,} · "
                        f"distributions {runtime.distribution_count:,}"
                    )
                )
        else:
            box.label(text=f"Assets {runtime.asset_count:,} · verified {runtime.verified_assets:,}")

        if session.outcome.is_valid and session.outcome.rights_acknowledgement_required:
            warning = layout.box()
            warning.label(text="Rights/access are unknown or restricted", icon="ERROR")
            manifest = session.outcome.manifest if hasattr(session.outcome.manifest, "get") else {}
            rights_value = manifest.get("rights", ())
            rights = (
                tuple(record for record in rights_value if hasattr(record, "get"))
                if isinstance(rights_value, (tuple, list))
                else ()
            )
            rights_page, rights_maximum = _page(rights, runtime.rights_page, 3)
            for record in rights_page:
                if record.get("id"):
                    _full_value(warning, "Rights record", record.get("id"))
                access = str(record.get("access", "not declared"))
                licence = str(record.get("license", "not declared"))
                warning.label(text=f"Access: {access} · licence: {_short(licence, 40)}")
                statement = record.get("statement", {})
                if hasattr(statement, "values"):
                    text = statement.get("en") or next(iter(statement.values()), "")
                else:
                    text = statement if isinstance(statement, (str, int, float, bool)) else ""
                for line in _wrap(str(text), 72):
                    warning.label(text=line)
            _pagination(warning, "rights_page", runtime.rights_page, rights_maximum)
            if not runtime.rights_acknowledged:
                warning.operator("vao.acknowledge_rights", icon="LOCKED")
            else:
                warning.label(text="Acknowledged for this live session only", icon="CHECKMARK")
                warning.label(text="This acknowledgement is not permission or a licence.")

        if session.root_collection_name:
            actions = layout.row(align=True)
            actions.operator("vao.remove_materialization", icon="TRASH")
        if not session.source_matches_materialization:
            mismatch = layout.box()
            mismatch.label(text="Different revision detected", icon="ERROR")
            mismatch.label(text="The saved materialization remains detached and media-disabled.")
            _relink_button(mismatch, runtime, text="Choose Exact Original…")
            op = mismatch.operator(
                "vao.import_package", text="Import as New Revision…", icon="DUPLICATE"
            )
            op.operation = "IMPORT"
            op.filepath = session.source_path


class VAO_PT_explore(VAO_PT_base, bpy.types.Panel):
    bl_idname = "VAO_PT_explore"
    bl_label = "Explore"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        runtime = context.scene.vao_runtime
        session = active_session(context.scene)
        if not session:
            layout.label(text="Open or relink a VAO to browse its validated model")
            return
        has_model_records = _has_registry_records(session.outcome.manifest or {})
        if (
            not session.outcome.graph
            and not session.outcome.logical_assets
            and not session.outcome.capabilities
            and not has_model_records
        ):
            layout.label(text="This result contains no browsable validated model", icon="INFO")
            layout.operator(
                "vao.find_diagnostics", text="Filter Diagnostics for This Result"
            ).query = ""
            return

        layout.prop(runtime, "search", icon="VIEWZOOM")
        layout.prop(runtime, "explore_category", expand=True)
        if runtime.explore_category == "ENTITIES":
            _draw_entities(layout, runtime, session)
        elif runtime.explore_category == "ASSETS":
            _draw_assets(layout, runtime, session)
        elif runtime.explore_category == "CAPABILITIES":
            _draw_capabilities(layout, runtime, session)
        else:
            _draw_records(layout, runtime, session)


class VAO_PT_visual_acoustic(VAO_PT_base, bpy.types.Panel):
    bl_idname = "VAO_PT_visual_acoustic"
    bl_label = "Visual-Acoustic Scene"

    @classmethod
    def poll(cls, context):
        session = active_session(context.scene)
        return bool(session and session.outcome.acoustic_scene)

    def draw(self, context):
        layout = self.layout
        runtime = context.scene.vao_runtime
        session = active_session(context.scene)
        acoustic = session.outcome.acoustic_scene
        realization = session.outcome.realizations.get(acoustic.runtime_visual_realization_id)
        binding = acoustic.geometry_bindings.get(acoustic.runtime_visual_binding_id)
        geometry = layout.box()
        geometry.label(text="Runtime visual geometry", icon="MESH_DATA")
        if realization and binding:
            _full_value(geometry, "Logical asset", realization.logical_asset_id)
            _full_value(geometry, "Realization", realization.id)
            frame_id = str(realization.technical_metadata.get("coordinateFrameId", ""))
            _full_value(geometry, "Frame", frame_id)
            _full_value(geometry, "Common root", acoustic.common_frame_root_id)
            geometry.label(text=f"Binding role: {binding.role}")
            frame = acoustic.coordinate_frames.get(frame_id)
            if frame and frame.transform_to_parent:
                geometry.label(text="Declared row-major transform")
                for row_index in range(4):
                    values = frame.transform_to_parent[row_index * 4 : row_index * 4 + 4]
                    geometry.label(text="  " + "  ".join(f"{value:g}" for value in values))
            existing = representation_collection(session, realization.id)
            if existing:
                _representation_actions(geometry, realization.id, existing.hide_viewport)
            else:
                row = geometry.row()
                row.enabled = session.media_ready(context.scene)
                row.operator("vao.load_visual", text="Load Visual-Acoustic Scene", icon="IMPORT")
        else:
            geometry.label(text="No supported embedded runtime-visual GLB", icon="ERROR")

        layout.label(
            text=(
                f"Frames {len(acoustic.coordinate_frames):,} · poses {len(acoustic.poses):,} · "
                f"measurements {len(acoustic.measurements):,}"
            )
        )
        measurements = sorted(acoustic.measurements.values(), key=lambda item: item.id)
        page, maximum = _page(measurements, runtime.acoustic_measurement_page, ACOUSTIC_PAGE_SIZE)
        layout.label(text=f"Source–receiver measurements ({len(measurements):,})")
        for measurement in page:
            pair = layout.box()
            _full_value(pair, "Measurement", measurement.id)
            for role, pose_id, entity_id in (
                ("Source", measurement.source_pose_id, measurement.source_id),
                ("Receiver", measurement.receiver_pose_id, measurement.receiver_id),
            ):
                pose = acoustic.poses[pose_id]
                xyz = ", ".join(f"{value:.4f}" for value in pose.position)
                pair.label(text=f"{role}: ({xyz}) m")
                _full_value(pair, f"{role} entity", entity_id)
                _full_value(pair, f"{role} pose", pose.id)
        _pagination(layout, "acoustic_measurement_page", runtime.acoustic_measurement_page, maximum)

        responses = sorted(acoustic.response_sets.values(), key=lambda item: item.id)
        page, maximum = _page(responses, runtime.acoustic_response_page, ACOUSTIC_PAGE_SIZE)
        layout.label(text=f"Response sets ({len(responses):,})")
        for response in page:
            box = layout.box()
            box.label(text=f"Response set · {response.representation_status}", icon="SOUND")
            _full_value(box, "ID", response.id)
            _full_value(box, "Response entity", response.response_entity_id)
            _full_value(box, "Logical asset", response.logical_asset_id)
            box.label(text=f"Kind: {response.response_kind or 'not declared'}")
            _full_value(box, "Generated by", response.generated_by_id)
            _full_value(box, "Measurements", _json_value(response.measurement_ids))
            if response.quality_flags:
                _full_value(box, "Quality flags", _json_value(response.quality_flags))
        _pagination(layout, "acoustic_response_page", runtime.acoustic_response_page, maximum)

        impulse_responses = sorted(acoustic.impulse_responses, key=lambda item: item.realization_id)
        page, maximum = _page(impulse_responses, runtime.acoustic_rir_page, ACOUSTIC_PAGE_SIZE)
        layout.label(text=f"Impulse-response realizations ({len(impulse_responses):,})")
        for rir in page:
            box = layout.box()
            box.label(
                text=f"{rir.encoding} · {rir.sample_rate:g} Hz · {rir.channel_count} ch",
                icon="SOUND",
            )
            _full_value(box, "Realization", rir.realization_id)
            _full_value(box, "Logical asset", rir.logical_asset_id)
            _full_value(box, "Response set", rir.response_set_id)
            box.label(text=f"{rir.sample_count:,} samples · {rir.byte_size:,} bytes")
            box.label(text=f"Status: {rir.representation_status or 'not declared'}")
            _full_value(box, "Payload", rir.embedded_path or "not embedded")
            _full_value(box, "SHA-256", rir.sha256)
            _full_value(box, "Measurements", _json_value(rir.measurement_ids))
            _full_value(box, "Channel indices", _json_value(rir.channel_indices))
            if rir.provenance_ids:
                _full_value(box, "Provenance", _json_value(rir.provenance_ids))
        _pagination(layout, "acoustic_rir_page", runtime.acoustic_rir_page, maximum)
        notice = layout.box()
        notice.label(text="Metadata-only acoustic support", icon="INFO")
        notice.label(text="No RIR playback, convolution, simulation, or interpolation")


class VAO_PT_play(VAO_PT_base, bpy.types.Panel):
    bl_idname = "VAO_PT_play"
    bl_label = "Play"

    def draw(self, context):
        layout = self.layout
        runtime = context.scene.vao_runtime
        session = active_session(context.scene)
        if session and session.outcome.contract_line in {"0.3.2", "0.4.0", "0.5.0"}:
            layout.label(text="Modern program-audio/acoustic execution is unavailable", icon="INFO")
            layout.label(text="Validated records remain inspectable; supported geometry can load")
            return
        if not session or not session.outcome.interaction_plans:
            layout.label(text="No compiled playable interaction plan")
            return
        bundle = session.outcome.interaction_plans
        if not bundle.supported:
            layout.label(
                text="Runtime plan is unsupported; partial execution is disabled", icon="ERROR"
            )
            layout.operator(
                "vao.find_diagnostics", text="Show Interaction Diagnostics"
            ).query = "VAO-INT"
            return
        if not bundle.gates or not bundle.voices:
            layout.label(text="No executable gate/voice mappings were compiled", icon="INFO")
            return
        if not session.media_ready(context.scene):
            layout.label(
                text="Playback is disabled by validation, relink, or rights state", icon="LOCKED"
            )
            return
        layout.label(
            text=(
                f"{len(bundle.selections)} selections · {len(bundle.gates)} keys · "
                f"{len(bundle.voices)} voices"
            )
        )
        layout.label(text="Selections")
        selection_page, selection_maximum = _page(
            bundle.selections, runtime.play_selection_page, PAGE_SIZE
        )
        for selection in selection_page:
            active = selection.configuration_id in session.active_configurations
            op = layout.operator(
                "vao.toggle_selection",
                text=selection.label,
                icon="CHECKBOX_HLT" if active else "CHECKBOX_DEHLT",
                depress=active,
            )
            op.configuration_id = selection.configuration_id
        _pagination(
            layout,
            "play_selection_page",
            runtime.play_selection_page,
            selection_maximum,
        )
        row = layout.row(align=True)
        row.operator("vao.performance_mode", icon="PLAY")
        row.operator("vao.create_controls", text="Board", icon="CUBE")
        layout.label(text="Mapped keyboard / click preview")
        grid = layout.grid_flow(columns=6, even_columns=True, align=True)
        gate_page_size = 12
        gate_page, gate_maximum = _page(bundle.gates, runtime.play_gate_page, gate_page_size)
        gate_page_index = min(runtime.play_gate_page, gate_maximum)
        for index, gate in enumerate(gate_page, start=gate_page_index * gate_page_size):
            event = EVENT_KEYS[index] if index < len(EVENT_KEYS) else "—"
            op = grid.operator("vao.preview_gate", text=f"{gate.key_number} {event}")
            op.gate_id = gate.interaction_id
        _pagination(layout, "play_gate_page", runtime.play_gate_page, gate_maximum)


class VAO_PT_diagnostics(VAO_PT_base, bpy.types.Panel):
    bl_idname = "VAO_PT_diagnostics"
    bl_label = "Diagnostics"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        runtime = context.scene.vao_runtime
        session = active_session(context.scene)
        if not session:
            layout.label(text="No live diagnostic result")
            if runtime.materialization_state == "DETACHED":
                layout.label(text="Relink the exact source to restore validated diagnostics.")
            return
        outcome = session.outcome
        summary = layout.box()
        _state_row(summary, "Validity", runtime.validity_state)
        _state_row(summary, "Support", runtime.support_state)
        _state_row(summary, "Rights", runtime.rights_state)
        _state_row(summary, "Scene data", runtime.materialization_state)
        _full_value(summary, "Archive SHA-256", outcome.archive_sha256 or "not computed")
        _full_value(summary, "Manifest SHA-256", outcome.manifest_sha256 or "not available")
        contract_status = {
            "0.3.2": "Pinned private VAO 0.3.2 implemented editor draft",
            "0.4.0": "Pinned published VAO 0.4.0 standard",
            "0.5.0": "Pinned VAO 0.5.0 standard candidate",
        }.get(outcome.contract_line, "Pinned private VAO 0.2.2 development snapshot")
        summary.label(text=contract_status, icon="INFO")

        row = layout.row(align=True)
        row.prop(runtime, "diagnostics_severity", text="")
        row.prop(runtime, "diagnostics_stage", text="")
        layout.prop(runtime, "diagnostics_search", icon="VIEWZOOM")
        diagnostics = _filtered_diagnostics(runtime, outcome.diagnostics)
        layout.label(
            text=f"Diagnostics ({len(diagnostics):,} matching / {len(outcome.diagnostics):,} total)"
        )
        page, maximum = _page(diagnostics, runtime.diagnostics_page, DIAGNOSTIC_PAGE_SIZE)
        for diagnostic in page:
            icon = {
                "error": "ERROR",
                "warning": "ERROR",
                "info": "INFO",
            }.get(diagnostic.severity.value, "INFO")
            box = layout.box()
            box.label(
                text=f"{diagnostic.code} · {diagnostic.severity.value} · {diagnostic.stage.value}",
                icon=icon,
            )
            for line in _wrap(diagnostic.message, 72):
                box.label(text=line)
            if diagnostic.pointer:
                _full_value(box, "JSON pointer", diagnostic.pointer)
            if diagnostic.archive_path:
                _full_value(box, "Archive path", diagnostic.archive_path)
            for related_id in diagnostic.related_ids:
                _full_value(box, "Related ID", related_id)
            op = box.operator("vao.copy_text", text="Copy Complete Diagnostic", icon="COPYDOWN")
            op.text = json.dumps(diagnostic.to_dict(), ensure_ascii=False, indent=2)
        if not diagnostics:
            layout.label(text="No diagnostics match these filters", icon="INFO")
        _pagination(layout, "diagnostics_page", runtime.diagnostics_page, maximum)
        row = layout.row(align=True)
        row.operator("vao.export_diagnostics", icon="EXPORT")
        row.operator("vao.clear_cache", text="Clear Cache…", icon="TRASH")


def _draw_detached(context, layout) -> None:
    runtime = context.scene.vao_runtime
    if not runtime.detached_materializations:
        return
    box = layout.box()
    box.label(text=f"Detached materializations ({runtime.detached_count})", icon="UNLINKED")
    detached_page, detached_maximum = _page(
        tuple(runtime.detached_materializations), runtime.detached_page, PAGE_SIZE
    )
    for item in detached_page:
        selected = item.materialization_id == runtime.materialization_id
        row = box.row(align=True)
        op = row.operator(
            "vao.select_detached",
            text=f"{item.title} · r{item.revision or '—'}",
            depress=selected,
        )
        op.materialization_id = item.materialization_id
        row.operator("vao.copy_text", text="", icon="COPYDOWN").text = item.package_id
    _pagination(box, "detached_page", runtime.detached_page, detached_maximum)
    detached = selected_detached(context.scene)
    if detached:
        details = layout.box()
        details.label(text=detached.title or detached.root_name, icon="OUTLINER_COLLECTION")
        _full_value(details, "Package", detached.package_id)
        _full_value(details, "Manifest SHA-256", detached.manifest_sha256)
        if detached.archive_sha256:
            _full_value(details, "Archive SHA-256", detached.archive_sha256)
        _relink_button(details, runtime)
        details.operator("vao.remove_materialization", icon="TRASH")


def _relink_button(layout, runtime, *, text: str = "Relink Exact Source…") -> None:
    op = layout.operator("vao.import_package", text=text, icon="FILE_REFRESH")
    op.operation = "RELINK"
    op.filepath = runtime.source_path
    op.relink_materialization_id = runtime.materialization_id
    op.relink_root_name = runtime.root_collection_name
    op.expected_archive_sha256 = runtime.expected_archive_sha256
    op.expected_manifest_sha256 = runtime.expected_manifest_sha256
    op.expected_package_id = runtime.package_id
    op.expected_revision = runtime.revision
    op.expected_release_id = runtime.release_id
    op.expected_format_version = runtime.format_version


def _draw_entities(layout, runtime, session) -> None:
    graph = session.outcome.graph
    if not graph:
        layout.label(text="No entity graph in this result")
        return
    layout.prop(runtime, "entity_kind_filter")
    layout.prop(runtime, "relation_status_filter")
    query = runtime.search.casefold().strip()
    kind_filter = runtime.entity_kind_filter.casefold().strip()
    entities = [
        item
        for item in graph.entities.values()
        if (
            not query
            or query in item.label.casefold()
            or query in item.id.casefold()
            or any(query in value.casefold() for value in item.types)
        )
        and (
            not kind_filter
            or kind_filter in item.kind.casefold()
            or any(kind_filter in value.casefold() for value in item.types)
        )
    ]
    entities.sort(key=lambda item: (item.label.casefold(), item.id))
    layout.label(text=f"Entities ({len(entities):,})")
    page, maximum = _page(entities, runtime.explore_page, PAGE_SIZE)
    for item in page:
        row = layout.row(align=True)
        op = row.operator(
            "vao.select_entity",
            text=item.label or item.id,
            icon="OUTLINER_OB_EMPTY",
            depress=item.id == runtime.selected_entity_id,
        )
        op.entity_id = item.id
        row.label(text=item.kind.rsplit("/", 1)[-1])
        row.operator("vao.copy_text", text="", icon="COPYDOWN").text = item.id
    _pagination(layout, "explore_page", runtime.explore_page, maximum)
    selected = graph.entities.get(runtime.selected_entity_id)
    if not selected:
        return
    details = layout.box()
    details.label(text=selected.label, icon="OUTLINER_OB_EMPTY")
    _full_value(details, "ID", selected.id)
    _full_value(details, "Kind", selected.kind)
    for item_type in selected.types:
        _full_value(details, "Type", item_type)
    _draw_mapping(
        details,
        "Properties",
        selected.properties,
        runtime=runtime,
        page_property="entity_properties_page",
    )
    relation_filter = runtime.relation_status_filter.casefold().strip()
    relations = [
        ("Outgoing", edge)
        for edge in graph.outgoing.get(selected.id, ())
        if not relation_filter or relation_filter in edge.status.casefold()
    ]
    relations.extend(
        ("Incoming", edge)
        for edge in graph.incoming.get(selected.id, ())
        if not relation_filter or relation_filter in edge.status.casefold()
    )
    relations.sort(key=lambda item: (item[0], item[1].id))
    details.label(text=f"Relations ({len(relations):,})")
    rel_page, rel_maximum = _page(relations, runtime.explore_details_page, DETAIL_PAGE_SIZE)
    for direction, edge in rel_page:
        box = details.box()
        row = box.row(align=True)
        op = row.operator(
            "vao.select_relation",
            text=f"{direction} · {edge.status or 'status not declared'}",
            depress=edge.id == runtime.selected_relation_id,
        )
        op.relation_id = edge.id
        row.operator("vao.copy_text", text="", icon="COPYDOWN").text = edge.id
        _full_value(box, "Relation", edge.id)
        _full_value(box, "Predicate", edge.predicate)
        if edge.subject_id:
            _full_value(box, "Subject", edge.subject_id)
        if edge.object_id:
            _full_value(box, "Object", edge.object_id)
        elif edge.literal is not None:
            _full_value(box, "Literal", _json_value(edge.literal))
    _pagination(details, "explore_details_page", runtime.explore_details_page, rel_maximum)

    selected_relation = graph.relations.get(runtime.selected_relation_id)
    if selected_relation and selected.id in {
        selected_relation.subject_id,
        selected_relation.object_id,
    }:
        relation_details = details.box()
        relation_details.label(text="Selected relation details", icon="LINKED")
        _full_value(relation_details, "ID", selected_relation.id)
        _full_value(relation_details, "Predicate", selected_relation.predicate)
        _full_value(relation_details, "Subject", selected_relation.subject_id)
        if selected_relation.object_id:
            _full_value(relation_details, "Object", selected_relation.object_id)
        elif selected_relation.literal is not None:
            _full_value(relation_details, "Literal", _json_value(selected_relation.literal))
        _draw_mapping(
            relation_details,
            "Properties",
            selected_relation.properties,
            runtime=runtime,
            page_property="relation_properties_page",
        )

    linked = [
        ("asset", item) for item in graph.assets.values() if selected.id in item.about_entity_ids
    ]
    linked.extend(
        ("logical", item)
        for item in session.outcome.logical_assets.values()
        if selected.id in item.about_entity_ids
    )
    if linked:
        details.label(text=f"Linked assets ({len(linked):,})")
        linked.sort(key=lambda item: item[1].id)
        linked_page, linked_maximum = _page(linked, runtime.linked_assets_page, DETAIL_PAGE_SIZE)
        for record_type, asset in linked_page:
            row = details.row(align=True)
            if record_type == "asset":
                op = row.operator("vao.select_asset", text=asset.original_filename or asset.id)
                op.asset_id = asset.id
                row.label(text=asset.media_type)
            else:
                realization = next(
                    (
                        session.outcome.realizations.get(identifier)
                        for identifier in asset.realization_ids
                        if session.outcome.realizations.get(identifier) is not None
                    ),
                    None,
                )
                if realization is not None:
                    op = row.operator("vao.select_realization", text=asset.label or asset.id)
                    op.realization_id = realization.id
                    op.logical_asset_id = asset.id
                    row.label(text=realization.media_type)
                else:
                    row.label(text=asset.label or asset.id, icon="FILE")
            row.operator("vao.copy_text", text="", icon="COPYDOWN").text = asset.id
        _pagination(
            details,
            "linked_assets_page",
            runtime.linked_assets_page,
            linked_maximum,
        )
    op = details.operator("vao.find_diagnostics", text="Find Related Diagnostics", icon="VIEWZOOM")
    op.query = selected.id


def _draw_assets(layout, runtime, session) -> None:
    layout.prop(runtime, "role_filter")
    layout.prop(runtime, "representation_status_filter")
    query = runtime.search.casefold().strip()
    role_filter = runtime.role_filter.casefold().strip()
    status_filter = runtime.representation_status_filter.casefold().strip()
    if session.outcome.realizations:
        records = []
        for realization in session.outcome.realizations.values():
            logical = session.outcome.logical_assets.get(realization.logical_asset_id)
            roles = logical.roles if logical else ()
            label = logical.label if logical else realization.logical_asset_id
            if query and not any(
                query in value.casefold()
                for value in (
                    realization.id,
                    realization.logical_asset_id,
                    realization.embedded_path,
                    realization.media_type,
                    label,
                    *roles,
                )
            ):
                continue
            if role_filter and not any(role_filter in role.casefold() for role in roles):
                continue
            if status_filter and status_filter not in realization.representation_status.casefold():
                continue
            records.append((label, realization, roles))
        records.sort(key=lambda value: (value[0].casefold(), value[1].id))
        layout.label(text=f"Exact realizations ({len(records):,})")
        page, maximum = _page(records, runtime.explore_page, PAGE_SIZE)
        for label, realization, _roles in page:
            row = layout.row(align=True)
            op = row.operator(
                "vao.select_realization",
                text=label or realization.id,
                icon="FILE",
                depress=realization.id == runtime.selected_realization_id,
            )
            op.realization_id = realization.id
            op.logical_asset_id = realization.logical_asset_id
            row.label(text=realization.media_type.rsplit("/", 1)[-1])
            row.operator("vao.copy_text", text="", icon="COPYDOWN").text = realization.id
        _pagination(layout, "explore_page", runtime.explore_page, maximum)
        selected = session.outcome.realizations.get(runtime.selected_realization_id)
        if selected:
            logical = session.outcome.logical_assets.get(selected.logical_asset_id)
            box = layout.box()
            box.label(text=logical.label if logical else "Selected realization", icon="FILE")
            _full_value(box, "Logical asset", selected.logical_asset_id)
            _full_value(box, "Realization", selected.id)
            _full_value(box, "Payload", selected.embedded_path or "not embedded")
            _full_value(box, "SHA-256", selected.sha256)
            box.label(text=f"{selected.byte_size:,} bytes · {selected.media_type}")
            box.label(text=f"Status: {selected.representation_status or 'not declared'}")
            box.label(text=f"Quality tier: {selected.quality_tier or 'not declared'}")
            if logical:
                for role in logical.roles:
                    _full_value(box, "Role", role)
                for entity_id in logical.about_entity_ids:
                    _full_value(box, "About entity", entity_id)
            for rights_id in selected.rights_ids:
                _full_value(box, "Rights record", rights_id)
            for provenance_id in selected.provenance_ids:
                _full_value(box, "Provenance", provenance_id)
            _draw_mapping(
                box,
                "Technical metadata",
                selected.technical_metadata,
                runtime=runtime,
                page_property="asset_properties_page",
            )
            _asset_actions(box, session, selected.id, selected.media_type)
        return

    graph = session.outcome.graph
    assets = [] if not graph else list(graph.assets.values())
    assets = [
        item
        for item in assets
        if (
            not query
            or query in item.id.casefold()
            or query in item.original_filename.casefold()
            or query in item.media_type.casefold()
            or any(query in value.casefold() for value in item.roles)
        )
        and (not role_filter or any(role_filter in role.casefold() for role in item.roles))
        and (not status_filter or status_filter in item.representation_status.casefold())
    ]
    assets.sort(key=lambda item: (item.original_filename.casefold(), item.id))
    layout.label(text=f"Assets ({len(assets):,})")
    page, maximum = _page(assets, runtime.explore_page, PAGE_SIZE)
    for item in page:
        row = layout.row(align=True)
        op = row.operator(
            "vao.select_asset",
            text=item.original_filename or item.id,
            icon="FILE",
            depress=item.id == runtime.selected_asset_id,
        )
        op.asset_id = item.id
        row.label(text=item.media_type.rsplit("/", 1)[-1])
        row.operator("vao.copy_text", text="", icon="COPYDOWN").text = item.id
    _pagination(layout, "explore_page", runtime.explore_page, maximum)
    selected = graph.assets.get(runtime.selected_asset_id) if graph else None
    if selected:
        box = layout.box()
        box.label(text=selected.original_filename or "Selected asset", icon="FILE")
        _full_value(box, "ID", selected.id)
        _full_value(box, "Payload", selected.path)
        _full_value(box, "SHA-256", selected.sha256)
        box.label(text=f"{selected.byte_size:,} bytes · {selected.media_type}")
        box.label(text=f"Status: {selected.representation_status or 'not declared'}")
        for role in selected.roles:
            _full_value(box, "Role", role)
        for entity_id in selected.about_entity_ids:
            _full_value(box, "About entity", entity_id)
        _draw_mapping(
            box,
            "Properties",
            selected.properties,
            runtime=runtime,
            page_property="asset_properties_page",
        )
        _asset_actions(box, session, selected.id, selected.media_type)


def _asset_actions(layout, session, identifier: str, media_type: str) -> None:
    existing = representation_collection(session, identifier)
    if existing:
        _representation_actions(layout, identifier, existing.hide_viewport)
    elif media_type == "model/gltf-binary":
        row = layout.row()
        row.enabled = session.media_ready(session.scene)
        row.operator("vao.load_visual", icon="MESH_DATA")
    op = layout.operator("vao.find_diagnostics", text="Find Related Diagnostics", icon="VIEWZOOM")
    op.query = identifier


def _representation_actions(layout, identifier: str, hidden: bool) -> None:
    row = layout.row(align=True)
    row.operator(
        "vao.select_representation", text="Select", icon="RESTRICT_SELECT_OFF"
    ).identifier = identifier
    row.operator("vao.frame_representation", text="Frame", icon="VIEWZOOM").identifier = identifier
    row = layout.row(align=True)
    op = row.operator(
        "vao.toggle_representation",
        text="Show" if hidden else "Hide",
        icon="HIDE_OFF" if hidden else "HIDE_ON",
    )
    op.identifier = identifier
    row.operator("vao.remove_representation", text="Remove", icon="TRASH").identifier = identifier


def _draw_records(layout, runtime, session) -> None:
    """Browse closed registries parsed from modern VAO manifests."""
    layout.prop(runtime, "model_section")
    records = _registry_records(session.outcome.manifest or {}, runtime.model_section)
    query = runtime.search.casefold().strip()
    if query:
        records = [
            record
            for record in records
            if query
            in " ".join(
                (
                    record[1],
                    record[2],
                    record[3],
                    _record_search_text(record[4]),
                )
            ).casefold()
        ]
    if not session.outcome.is_valid:
        layout.label(text="Parsed records are not a valid/complete model", icon="ERROR")
    layout.label(
        text=(f"{'Validated' if session.outcome.is_valid else 'Parsed'} records ({len(records):,})")
    )
    page, maximum = _page(records, runtime.explore_page, PAGE_SIZE)
    for key, group, identifier, label, _record in page:
        row = layout.row(align=True)
        op = row.operator(
            "vao.select_record",
            text=label or identifier or f"{group} record",
            icon="PRESET",
            depress=key == runtime.selected_record_key,
        )
        op.record_key = key
        row.label(text=group)
        row.operator("vao.copy_text", text="", icon="COPYDOWN").text = identifier or key
    _pagination(layout, "explore_page", runtime.explore_page, maximum)
    selected = next(
        (record for record in records if record[0] == runtime.selected_record_key), None
    )
    if selected is None:
        if records:
            layout.label(text="Select a record to inspect all fields", icon="INFO")
        else:
            layout.label(text="This result declares no records in this family", icon="INFO")
        return
    key, group, identifier, label, record = selected
    box = layout.box()
    box.label(text=label or identifier or group, icon="PRESET")
    box.label(text=f"Registry: {group}")
    if identifier:
        _full_value(box, "ID", identifier)
    _draw_mapping(
        box,
        "Fields",
        record,
        runtime=runtime,
        page_property="record_properties_page",
    )
    op = box.operator("vao.copy_text", text="Copy Complete Record", icon="COPYDOWN")
    op.text = _json_value(record)
    op = box.operator("vao.find_diagnostics", text="Find Related Diagnostics", icon="VIEWZOOM")
    op.query = identifier or key


def _registry_records(manifest, section: str):
    if not hasattr(manifest, "get"):
        return []
    source_name = {
        "SCIENTIFIC": "scientific",
        "INTERACTION": "interactionModel",
        "PHYSICAL": "physicalSystem",
        "DISTRIBUTIONS": "distributions",
        "RIGHTS": "rights",
        "PROVENANCE": "provenance",
    }[section]
    source = manifest.get(source_name)
    registries = source.items() if hasattr(source, "items") else ((source_name, source or ()),)
    records = []
    for group, values in sorted(registries, key=lambda item: str(item[0])):
        if hasattr(values, "items"):
            values = (values,)
        if not isinstance(values, (tuple, list)):
            continue
        for index, raw in enumerate(values):
            record = raw if hasattr(raw, "items") else {"value": raw}
            identifier = str(record.get("id", ""))
            label = _record_label(
                record,
                identifier or f"{group} {index + 1}",
            )
            key = f"{section}\0{group}\0{index}\0{identifier}"
            records.append((key, str(group), identifier, label, record))
    records.sort(key=lambda item: (item[1].casefold(), item[3].casefold(), item[0]))
    return records


def _has_registry_records(manifest) -> bool:
    if not hasattr(manifest, "get"):
        return False
    for key in (
        "scientific",
        "interactionModel",
        "physicalSystem",
        "distributions",
        "rights",
        "provenance",
    ):
        value = manifest.get(key)
        if hasattr(value, "values"):
            if any(
                isinstance(items, (tuple, list)) and bool(items) or hasattr(items, "items")
                for items in value.values()
            ):
                return True
        elif isinstance(value, (tuple, list)) and value:
            return True
    return False


def _record_label(record, fallback: str) -> str:
    for field in ("labels", "title"):
        value = record.get(field)
        if hasattr(value, "values"):
            candidate = value.get("en") or next(iter(value.values()), "")
            if isinstance(candidate, (str, int, float, bool)):
                return str(candidate)
        elif isinstance(value, (str, int, float, bool)):
            return str(value)
    name = record.get("name")
    return str(name) if isinstance(name, (str, int, float, bool)) else fallback


def _record_search_text(record) -> str:
    """Build a bounded search projection so large records do not stall panel redraws."""
    parts: list[str] = []
    remaining = 8192

    def visit(value) -> None:
        nonlocal remaining
        if remaining <= 0:
            return
        if hasattr(value, "items"):
            for key, item in value.items():
                visit(str(key))
                visit(item)
                if remaining <= 0:
                    break
        elif isinstance(value, (tuple, list)):
            for item in value:
                visit(item)
                if remaining <= 0:
                    break
        elif isinstance(value, (str, int, float, bool)) or value is None:
            text = str(value)[:remaining]
            parts.append(text)
            remaining -= len(text) + 1

    visit(record)
    return " ".join(parts)


def _draw_capabilities(layout, runtime, session) -> None:
    layout.prop(runtime, "capability_filter", expand=True)
    query = runtime.search.casefold().strip()
    capabilities = [
        item
        for item in session.outcome.capabilities
        if (not query or query in item.capability.casefold() or query in item.reason.casefold())
        and (
            runtime.capability_filter == "ALL"
            or (runtime.capability_filter == "SUPPORTED" and item.supported)
            or (runtime.capability_filter == "UNSUPPORTED" and not item.supported)
        )
    ]
    capabilities.sort(key=lambda item: item.capability)
    layout.label(text=f"Negotiated capabilities ({len(capabilities):,})")
    page, maximum = _page(capabilities, runtime.explore_page, PAGE_SIZE)
    for item in page:
        box = layout.box()
        box.label(
            text="Supported" if item.supported else "Unsupported",
            icon="CHECKMARK" if item.supported else "ERROR",
        )
        _full_value(box, "Capability", item.capability)
        if item.reason:
            for line in _wrap(item.reason, 72):
                box.label(text=line)
        if not item.supported:
            box.operator(
                "vao.find_diagnostics", text="Find Related Diagnostics"
            ).query = item.capability
    _pagination(layout, "explore_page", runtime.explore_page, maximum)


def _draw_mapping(
    layout,
    label: str,
    mapping,
    *,
    runtime,
    page_property: str,
) -> None:
    if not mapping:
        return
    layout.label(text=f"{label} ({len(mapping):,})")
    items = [(key, mapping[key]) for key in sorted(mapping)]
    page, maximum = _page(items, getattr(runtime, page_property), DETAIL_PAGE_SIZE)
    for key, raw_value in page:
        row = layout.row(align=True)
        value = _json_value(raw_value)
        row.label(text=f"{key}: {_short(value, 52)}")
        row.operator("vao.copy_text", text="", icon="COPYDOWN").text = f"{key}\n{value}"
    _pagination(layout, page_property, getattr(runtime, page_property), maximum)


def _full_value(layout, label: str, value: str) -> None:
    value = str(value)
    row = layout.row(align=True)
    row.label(text=f"{label}: {_short(value, 58)}")
    row.operator("vao.copy_text", text="", icon="COPYDOWN").text = value


def _state_row(layout, label: str, value: str) -> None:
    positive = value in {"VALID", "SUPPORTED", "READY", "ACKNOWLEDGED", "ATTACHED"}
    neutral = value in {"NOT_EVALUATED", "NONE", "PREVIOUSLY_VALIDATED", "CLOSED", ""}
    icon = "CHECKMARK" if positive else ("INFO" if neutral else "ERROR")
    layout.label(text=f"{label}: {value.replace('_', ' ').title() if value else '—'}", icon=icon)


def _filtered_diagnostics(runtime, diagnostics):
    query = runtime.diagnostics_search.casefold().strip()
    result = []
    for item in diagnostics:
        if runtime.diagnostics_severity != "ALL" and (
            item.severity.value.upper() != runtime.diagnostics_severity
        ):
            continue
        if (
            runtime.diagnostics_stage != "ALL"
            and item.stage.value.upper() != runtime.diagnostics_stage
        ):
            continue
        haystack = " ".join(
            (
                item.code,
                item.message,
                item.pointer,
                item.archive_path,
                *item.related_ids,
            )
        ).casefold()
        if query and query not in haystack:
            continue
        result.append(item)
    return sorted(
        result,
        key=lambda item: (
            {"error": 0, "warning": 1, "info": 2}.get(item.severity.value, 3),
            item.stage.value,
            item.code,
            item.pointer,
            item.archive_path,
        ),
    )


def _page(items, page: int, size: int):
    maximum = max(0, math.ceil(len(items) / size) - 1)
    page = min(max(0, page), maximum)
    return items[page * size : (page + 1) * size], maximum


def _pagination(layout, property_name: str, current: int, maximum: int) -> None:
    if maximum <= 0:
        return
    current = min(current, maximum)
    row = layout.row(align=True)
    previous = row.row(align=True)
    previous.enabled = current > 0
    op = previous.operator("vao.change_page", text="Previous", icon="TRIA_LEFT")
    op.property_name = property_name
    op.delta = -1
    op.maximum = maximum
    row.label(text=f"Page {current + 1:,} / {maximum + 1:,}")
    following = row.row(align=True)
    following.enabled = current < maximum
    op = following.operator("vao.change_page", text="Next", icon="TRIA_RIGHT")
    op.property_name = property_name
    op.delta = 1
    op.maximum = maximum


def _json_value(value) -> str:
    return json.dumps(_thaw(value), ensure_ascii=False, sort_keys=True)


def _thaw(value):
    if hasattr(value, "items"):
        return {str(key): _thaw(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_thaw(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return sorted(_thaw(item) for item in value)
    return value


def _short(value: str, width: int) -> str:
    return value if len(value) <= width else f"{value[: max(1, width - 1)]}…"


def _wrap(text: str, width: int) -> list[str]:
    words: list[str] = []
    for value in str(text).split():
        while len(value) > width:
            words.append(value[:width])
            value = value[width:]
        if value:
            words.append(value)
    if not words:
        return [""]
    lines: list[str] = []
    current = ""
    for word in words:
        if current and len(current) + len(word) + 1 > width:
            lines.append(current)
            current = word
        else:
            current = f"{current} {word}".strip()
    if current:
        lines.append(current)
    return lines


CLASSES = (
    VAO_PT_overview,
    VAO_PT_explore,
    VAO_PT_visual_acoustic,
    VAO_PT_play,
    VAO_PT_diagnostics,
)
