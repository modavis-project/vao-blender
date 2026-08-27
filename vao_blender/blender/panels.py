"""VAO sidebar: Overview, Explore, Play, and Diagnostics."""

from __future__ import annotations

import bpy

from .performance import EVENT_KEYS
from .session import active_session


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
        row = layout.row(align=True)
        row.operator("vao.import_package", text="Open VAO", icon="IMPORT")
        if runtime.session_id:
            row.operator("vao.close_package", text="Close", icon="X")
        layout.label(
            text=f"Status: {runtime.state}",
            icon="CHECKMARK" if "VALID" in runtime.state else "INFO",
        )
        layout.label(text=runtime.status_message)
        if runtime.state == "VALIDATING":
            layout.prop(runtime, "progress", text=runtime.progress_stage)
            layout.label(text="Press Escape to cancel safely")
            return
        if not runtime.session_id:
            return
        box = layout.box()
        box.label(text=runtime.title or runtime.source_name, icon="PACKAGE")
        box.label(text=f"Format {runtime.format_version} · revision {runtime.revision}")
        box.label(text=f"Entities {runtime.entity_count} · relations {runtime.relation_count}")
        if runtime.format_version in {"0.3.2", "0.4.0"}:
            box.label(
                text=f"Logical assets {runtime.logical_asset_count} · realizations {runtime.realization_count}"
            )
            box.label(text=f"Carrier {runtime.carrier_mode} · verified {runtime.verified_assets}")
        else:
            box.label(text=f"Assets {runtime.asset_count} · verified {runtime.verified_assets}")
        session = active_session(context.scene)
        if session and session.outcome.rights_acknowledgement_required:
            warning = layout.box()
            warning.label(text="Rights/access are unknown or restricted", icon="ERROR")
            rights = session.outcome.manifest.get("rights", ())
            for record in rights[:2]:
                statement = record.get("statement", {})
                text = statement.get("en") or next(iter(statement.values()), "")
                for line in _wrap(str(text), 72)[:4]:
                    warning.label(text=line)
            if not runtime.rights_acknowledged:
                warning.operator("vao.acknowledge_rights", icon="LOCKED")
            else:
                warning.label(text="Acknowledged for this session only", icon="CHECKMARK")


class VAO_PT_explore(VAO_PT_base, bpy.types.Panel):
    bl_idname = "VAO_PT_explore"
    bl_label = "Explore"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        runtime = context.scene.vao_runtime
        session = active_session(context.scene)
        if not session or not session.outcome.graph:
            layout.label(text="No validated graph")
            return
        graph = session.outcome.graph
        layout.prop(runtime, "search", icon="VIEWZOOM")
        query = runtime.search.casefold().strip()
        entities = [
            item
            for item in graph.entities.values()
            if not query or query in item.label.casefold() or query in item.id.casefold()
        ]
        assets = [
            item
            for item in graph.assets.values()
            if not query
            or query in item.id.casefold()
            or query in item.original_filename.casefold()
            or query in item.media_type.casefold()
        ]
        layout.label(text=f"Entities ({len(entities)})")
        for item in entities[:10]:
            row = layout.row(align=True)
            op = row.operator("vao.select_entity", text=item.label, icon="OUTLINER_OB_EMPTY")
            op.entity_id = item.id
            row.label(text=item.kind)
        layout.separator()
        if session.outcome.contract_line in {"0.3.2", "0.4.0"}:
            logical_assets = [
                item
                for item in session.outcome.logical_assets.values()
                if not query or query in item.id.casefold() or query in item.label.casefold()
            ]
            layout.label(text=f"Logical assets ({len(logical_assets)})")
            for item in logical_assets[:10]:
                box = layout.box()
                box.label(text=item.label, icon="FILE_FOLDER")
                box.label(text=f"{len(item.realization_ids)} exact realization(s)")
                for realization_id in item.realization_ids[:3]:
                    realization = session.outcome.realizations[realization_id]
                    row = box.row(align=True)
                    row.label(text=realization.media_type)
                    row.label(text=realization.quality_tier)
            selected = session.outcome.realizations.get(runtime.selected_realization_id)
            if selected:
                box = layout.box()
                box.label(text="Selected runtime realization", icon="MESH_DATA")
                box.label(text=selected.id)
                box.label(text=f"{selected.byte_size:,} bytes · SHA-256 verified")
        else:
            layout.label(text=f"Assets ({len(assets)})")
            for item in assets[:10]:
                row = layout.row(align=True)
                op = row.operator(
                    "vao.select_asset", text=item.original_filename or item.id[-12:], icon="FILE"
                )
                op.asset_id = item.id
                row.label(text=item.media_type)
            selected = graph.assets.get(runtime.selected_asset_id)
            if selected:
                box = layout.box()
                box.label(text=selected.id)
                box.label(text=f"{selected.byte_size:,} bytes · SHA-256 verified")
                if selected.media_type.startswith("model/gltf"):
                    box.operator("vao.load_visual", icon="MESH_DATA")


class VAO_PT_visual_acoustic(VAO_PT_base, bpy.types.Panel):
    bl_idname = "VAO_PT_visual_acoustic"
    bl_label = "Visual-Acoustic Scene"

    @classmethod
    def poll(cls, context):
        session = active_session(context.scene)
        return bool(session and session.outcome.acoustic_scene)

    def draw(self, context):
        layout = self.layout
        session = active_session(context.scene)
        acoustic = session.outcome.acoustic_scene
        realization = session.outcome.realizations.get(acoustic.runtime_visual_realization_id)
        binding = acoustic.geometry_bindings.get(acoustic.runtime_visual_binding_id)
        geometry = layout.box()
        geometry.label(text="Runtime visual geometry", icon="MESH_DATA")
        if realization and binding:
            geometry.label(text=f"Logical asset: {realization.logical_asset_id}")
            geometry.label(text=f"Realization: {realization.id}")
            frame_id = str(realization.technical_metadata.get("coordinateFrameId", ""))
            geometry.label(text=f"Frame: {frame_id.rsplit(':', 1)[-1]}")
            geometry.label(text=f"Common root: {acoustic.common_frame_root_id.rsplit(':', 1)[-1]}")
            geometry.label(text=f"Binding role: {binding.role}")
            frame = acoustic.coordinate_frames[frame_id]
            if frame.transform_to_parent:
                geometry.label(text="Declared row-major transform")
                for row in range(4):
                    values = frame.transform_to_parent[row * 4 : row * 4 + 4]
                    geometry.label(text="  " + "  ".join(f"{value:g}" for value in values))
            geometry.operator("vao.load_visual", text="Load Visual-Acoustic Scene", icon="IMPORT")
        else:
            geometry.label(text="No supported embedded runtime-visual GLB", icon="ERROR")

        layout.label(
            text=f"Frames {len(acoustic.coordinate_frames)} · poses {len(acoustic.poses)} · measurements {len(acoustic.measurements)}"
        )
        for measurement in acoustic.measurements.values():
            pair = layout.box()
            pair.label(text="Source–receiver measurement", icon="EMPTY_AXIS")
            pair.label(text=measurement.id)
            for role, pose_id in (
                ("Source", measurement.source_pose_id),
                ("Receiver", measurement.receiver_pose_id),
            ):
                pose = acoustic.poses[pose_id]
                entity_id = measurement.source_id if role == "Source" else measurement.receiver_id
                xyz = ", ".join(f"{value:.4f}" for value in pose.position)
                pair.label(text=f"{role}: ({xyz}) m")
                pair.label(text=f"Entity: {entity_id}")
                pair.label(text=f"Pose: {pose.id}")

        for response in acoustic.response_sets.values():
            box = layout.box()
            box.label(text=f"Response set · {response.representation_status}", icon="SOUND")
            box.label(text=response.id)
            box.label(text=f"Generated by: {response.generated_by_id}")
            for rir in acoustic.impulse_responses:
                if rir.response_set_id != response.id:
                    continue
                box.label(
                    text=f"RIR {rir.encoding} · {rir.sample_rate:g} Hz · {rir.channel_count} ch"
                )
                box.label(text=f"{rir.sample_count:,} samples · {rir.byte_size:,} bytes")
                box.label(text=f"Payload: {rir.embedded_path}")
                box.label(text=f"Measurements: {', '.join(rir.measurement_ids)}")
                box.label(text=f"SHA-256 {rir.sha256[:20]}…")
                box.label(text=f"Status: {rir.representation_status.rsplit('/', 1)[-1]}")
                for provenance_id in rir.provenance_ids:
                    box.label(text=f"Provenance: {provenance_id}")
        for record in session.outcome.manifest.get("rights", ()):
            rights = layout.box()
            rights.label(text="Rights and attribution", icon="RIGHTARROW")
            rights.label(text=str(record.get("license", "")))
            for line in _wrap(str(record.get("attribution", "")), 72)[:6]:
                rights.label(text=line)
        notice = layout.box()
        notice.label(text="Metadata-only acoustic support", icon="INFO")
        notice.label(text="No RIR playback, convolution, simulation, or interpolation")


class VAO_PT_play(VAO_PT_base, bpy.types.Panel):
    bl_idname = "VAO_PT_play"
    bl_label = "Play"

    def draw(self, context):
        layout = self.layout
        session = active_session(context.scene)
        if session and session.outcome.contract_line in {"0.3.2", "0.4.0"}:
            layout.label(text="Impulse responses are metadata/filter-kernel records", icon="INFO")
            layout.label(text="Program-audio playback and convolution are not implemented")
            return
        if not session or not session.outcome.interaction_plans:
            layout.label(text="No compiled playable interaction plan")
            return
        bundle = session.outcome.interaction_plans
        if not bundle.supported:
            layout.label(text="Runtime plan is unsupported", icon="ERROR")
            return
        layout.label(
            text=f"{len(bundle.selections)} selections · {len(bundle.gates)} keys · {len(bundle.voices)} voices"
        )
        layout.label(text="Selections")
        for selection in bundle.selections:
            active = selection.configuration_id in session.active_configurations
            op = layout.operator(
                "vao.toggle_selection",
                text=selection.label,
                icon="CHECKBOX_HLT" if active else "CHECKBOX_DEHLT",
                depress=active,
            )
            op.configuration_id = selection.configuration_id
        row = layout.row(align=True)
        row.operator("vao.performance_mode", icon="PLAY")
        row.operator("vao.create_controls", text="Board", icon="CUBE")
        layout.label(text="Mapped keyboard / click preview")
        grid = layout.grid_flow(columns=6, even_columns=True, align=True)
        for index, gate in enumerate(bundle.gates):
            event = EVENT_KEYS[index] if index < len(EVENT_KEYS) else "—"
            op = grid.operator("vao.preview_gate", text=f"{gate.key_number} {event}")
            op.gate_id = gate.interaction_id


class VAO_PT_diagnostics(VAO_PT_base, bpy.types.Panel):
    bl_idname = "VAO_PT_diagnostics"
    bl_label = "Diagnostics"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        session = active_session(context.scene)
        if not session:
            layout.label(text="No diagnostic result")
            return
        outcome = session.outcome
        layout.label(text=f"Archive SHA-256: {outcome.archive_sha256[:20]}…")
        layout.label(text=f"Manifest SHA-256: {outcome.manifest_sha256[:20]}…")
        if outcome.contract_line == "0.3.2":
            layout.label(text="Pinned private VAO 0.3.2 implemented editor draft", icon="INFO")
        elif outcome.contract_line == "0.4.0":
            layout.label(text="Pinned published VAO 0.4.0 standard", icon="INFO")
        else:
            layout.label(text="Pinned private VAO 0.2.2 development snapshot", icon="INFO")
        for diagnostic in outcome.diagnostics[:12]:
            icon = "ERROR" if diagnostic.severity.value == "error" else "INFO"
            box = layout.box()
            box.label(text=f"{diagnostic.code} · {diagnostic.stage.value}", icon=icon)
            for line in _wrap(diagnostic.message, 72)[:3]:
                box.label(text=line)
        row = layout.row(align=True)
        row.operator("vao.export_diagnostics", icon="EXPORT")
        row.operator("vao.clear_cache", text="Clear Cache", icon="TRASH")


def _wrap(text: str, width: int) -> list[str]:
    words = text.split()
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
