"""Package, lifecycle, diagnostics, selection, and scene operators."""

from __future__ import annotations

import json
import queue
import shutil
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from typing import Any

import bpy
from bpy.props import BoolProperty, IntProperty, StringProperty
from bpy_extras.io_utils import ExportHelper, ImportHelper

from ..core.archive import ProgressRecord, ValidationLimits, validate_package
from ..core.cancellation import CancellationToken
from ..core.diagnostics import Diagnostic, Severity, Stage, ordered
from ..core.model import OutcomeState, ValidationOutcome
from .preferences import addon_preferences, cache_root
from .scene_adapter import (
    TRACE_KEYS,
    create_control_surface,
    import_visual,
    remove_materialization,
    remove_representation,
    representation_collection,
    set_representation_hidden,
    update_control_surface,
)
from .session import (
    DetachedMaterialization,
    active_session,
    close_session,
    discover_detached,
    install_outcome,
    materialization_is_shared,
    relink_mismatch_reasons,
    select_detached,
    selected_detached,
    thaw_json_value,
)

_ACTIVE_VALIDATIONS: list[Any] = []
_RUNTIME_FIELDS = (
    "session_id",
    "materialization_id",
    "root_collection_name",
    "state",
    "result_state",
    "validity_state",
    "support_state",
    "rights_state",
    "materialization_state",
    "status_message",
    "source_path",
    "source_name",
    "title",
    "package_id",
    "revision",
    "release_id",
    "format_version",
    "carrier_mode",
    "archive_sha256",
    "manifest_sha256",
    "expected_archive_sha256",
    "expected_manifest_sha256",
    "progress",
    "progress_stage",
    "progress_detail",
    "progress_completed_entries",
    "progress_total_entries",
    "progress_verified_bytes",
    "progress_total_bytes",
    "verified_assets",
    "entity_count",
    "relation_count",
    "asset_count",
    "logical_asset_count",
    "realization_count",
    "scientific_observation_count",
    "protocol_binding_count",
    "physical_component_count",
    "distribution_count",
    "frame_count",
    "pose_count",
    "measurement_count",
    "response_set_count",
    "rir_count",
    "search",
    "explore_category",
    "explore_page",
    "explore_details_page",
    "entity_properties_page",
    "relation_properties_page",
    "linked_assets_page",
    "asset_properties_page",
    "record_properties_page",
    "selected_asset_id",
    "selected_entity_id",
    "selected_relation_id",
    "selected_logical_asset_id",
    "selected_realization_id",
    "selected_record_key",
    "model_section",
    "diagnostics_page",
    "acoustic_measurement_page",
    "acoustic_response_page",
    "acoustic_rir_page",
    "rights_page",
    "detached_page",
    "play_selection_page",
    "play_gate_page",
    "rights_acknowledged",
    "media_enabled",
    "performance_active",
)


def _scene_is_live(scene) -> bool:
    try:
        return scene is not None and bpy.data.scenes.get(scene.name) == scene
    except ReferenceError:
        return False


def cancel_active_validations(scene=None) -> None:
    """Cooperatively stop validators and detach their Blender timers during teardown."""
    for operator in tuple(_ACTIVE_VALIDATIONS):
        target = getattr(operator, "_target_scene", None)
        if scene is not None and target != scene:
            continue
        token = getattr(operator, "_token", None)
        if token is not None:
            token.cancel()
        operator._finish(None)
        if _scene_is_live(target) and hasattr(target, "vao_runtime"):
            operator._restore_runtime(
                target.vao_runtime,
                state="CANCELLED",
                message="Validation cancelled during lifecycle teardown",
            )


class VAO_OT_import_package(bpy.types.Operator, ImportHelper):
    bl_idname = "vao.import_package"
    bl_label = "Open Virtual Acoustic Object"
    bl_description = "Fully validate an untrusted VAO before enabling any payload media"
    filename_ext = ".vao"
    filter_glob: StringProperty(default="*.vao", options={"HIDDEN"})
    operation: StringProperty(default="IMPORT", options={"HIDDEN", "SKIP_SAVE"})
    relink_materialization_id: StringProperty(options={"HIDDEN", "SKIP_SAVE"})
    relink_root_name: StringProperty(options={"HIDDEN", "SKIP_SAVE"})
    expected_archive_sha256: StringProperty(options={"HIDDEN", "SKIP_SAVE"})
    expected_manifest_sha256: StringProperty(options={"HIDDEN", "SKIP_SAVE"})
    expected_package_id: StringProperty(options={"HIDDEN", "SKIP_SAVE"})
    expected_revision: StringProperty(options={"HIDDEN", "SKIP_SAVE"})
    expected_release_id: StringProperty(options={"HIDDEN", "SKIP_SAVE"})
    expected_format_version: StringProperty(options={"HIDDEN", "SKIP_SAVE"})
    preflight_confirmed: BoolProperty(default=False, options={"HIDDEN", "SKIP_SAVE"})

    _executor = None
    _future = None
    _timer = None
    _token = None
    _progress = None
    _window_manager = None
    _registered_active = False
    _runtime_snapshot = None
    _target_scene = None

    def draw(self, context):
        layout = self.layout
        source = Path(self.filepath).expanduser()
        try:
            size = source.stat().st_size
            size_text = _format_bytes(size)
        except OSError:
            size_text = "unavailable"
        limits = ValidationLimits()
        title = "Exact-source relink preflight" if self.operation == "RELINK" else "VAO preflight"
        layout.label(text=title, icon="LOCKED")
        box = layout.box()
        box.label(text=f"File: {source.name or '(none)'}")
        box.label(text=f"Archive size: {size_text}")
        for line in _wrap(str(source), 86)[:3]:
            box.label(text=line)
        limits_box = layout.box()
        limits_box.label(text="Configured validation limits")
        limits_box.label(text=f"Entries: {limits.max_entries:,}")
        limits_box.label(text=f"Manifest: {_format_bytes(limits.max_manifest_bytes)}")
        limits_box.label(text=f"One entry: {_format_bytes(limits.max_entry_bytes)}")
        limits_box.label(text=f"Expanded total: {_format_bytes(limits.max_total_expanded_bytes)}")
        limits_box.label(text=f"Compression ratio: {limits.max_compression_ratio:g}:1")
        cache_box = layout.box()
        managed_root = Path(cache_root(context)).expanduser().absolute()
        preferences = addon_preferences(context)
        quota_gib = preferences.cache_quota_gib if preferences else 20
        cache_box.label(text=f"Managed cache quota: {quota_gib} GiB")
        for line in _wrap(f"Cache: {managed_root}", 86):
            cache_box.label(text=line)
        try:
            probe = managed_root
            while not probe.exists() and probe != probe.parent:
                probe = probe.parent
            free = shutil.disk_usage(probe).free
            cache_box.label(text=f"Filesystem free space: {_format_bytes(free)}")
        except OSError:
            cache_box.label(text="Filesystem free space: unavailable", icon="INFO")
        cache_box.label(text="Full validation streams and hashes every indexed payload byte.")
        warning = layout.box()
        warning.label(
            text="Treat this package as untrusted until validation completes.", icon="ERROR"
        )
        warning.label(text="No payload is decoded or added to the scene during validation.")
        warning.label(text="The operation remains cancellable from the VAO sidebar.")
        if self.operation == "RELINK":
            warning.label(text="Both saved manifest and archive hashes must match exactly.")

    def _restore_runtime(self, runtime, *, state: str, message: str) -> None:
        snapshot = self._runtime_snapshot
        self._runtime_snapshot = None
        if snapshot and snapshot.get("session_id"):
            for name, value in snapshot.items():
                setattr(runtime, name, value)
            return
        runtime.state = state
        runtime.result_state = state
        runtime.status_message = message
        runtime.progress = 0.0
        runtime.progress_stage = state.casefold()
        runtime.progress_detail = message
        runtime.media_enabled = False

    def execute(self, context):
        source = Path(self.filepath).expanduser()
        if not self.preflight_confirmed:
            if not source.is_file():
                self.report({"ERROR"}, "Choose an existing VAO file")
                return {"CANCELLED"}
            self.preflight_confirmed = True
            return context.window_manager.invoke_props_dialog(self, width=620)
        return self._begin_validation(context)

    def _begin_validation(self, context):
        cancel_active_validations(context.scene)
        self._target_scene = context.scene
        runtime = self._target_scene.vao_runtime
        self._runtime_snapshot = {name: getattr(runtime, name) for name in _RUNTIME_FIELDS}
        current = active_session(self._target_scene)
        if current is not None:
            current.stop_audio()
        runtime.state = "VALIDATING"
        runtime.result_state = ""
        runtime.validity_state = "NOT_EVALUATED"
        runtime.support_state = "NOT_EVALUATED"
        runtime.rights_state = "NOT_EVALUATED"
        runtime.media_enabled = False
        runtime.status_message = "Treating package as untrusted; validating container"
        runtime.source_name = Path(self.filepath).name
        runtime.source_path = runtime.source_name
        runtime.progress = 0.0
        runtime.progress_stage = "preflight"
        runtime.progress_detail = runtime.source_name
        runtime.progress_completed_entries = 0
        runtime.progress_total_entries = 0
        runtime.progress_verified_bytes = "0 B"
        runtime.progress_total_bytes = "0 B"
        self._token = CancellationToken()
        progress_queue = queue.Queue(maxsize=64)
        self._progress = progress_queue

        def progress(record: ProgressRecord):
            try:
                progress_queue.put_nowait(record)
            except queue.Full:
                try:
                    progress_queue.get_nowait()
                except queue.Empty:
                    pass
                try:
                    progress_queue.put_nowait(record)
                except queue.Full:
                    pass

        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="vao-validate")
        self._future = self._executor.submit(
            validate_package,
            self.filepath,
            cancellation=self._token,
            progress=progress,
        )
        self._window_manager = context.window_manager
        try:
            self._timer = self._window_manager.event_timer_add(0.1, window=context.window)
            self._window_manager.modal_handler_add(self)
        except Exception as exc:
            self._token.cancel()
            self._finish(None)
            message = f"Could not start background validation: {exc}"
            self._install_worker_error(message)
            self.report({"ERROR"}, message)
            return {"CANCELLED"}
        _ACTIVE_VALIDATIONS.append(self)
        self._registered_active = True
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        if event.type == "ESC" and self._token:
            self._token.cancel()
            if _scene_is_live(self._target_scene):
                self._target_scene.vao_runtime.status_message = "Cancelling validation safely…"
            return {"RUNNING_MODAL"}
        if event.type != "TIMER":
            return {"PASS_THROUGH"}
        if self._future is None:
            return {"CANCELLED"}
        if not _scene_is_live(self._target_scene):
            if self._token:
                self._token.cancel()
            self._finish(context)
            return {"CANCELLED"}
        runtime = self._target_scene.vao_runtime
        if self._progress:
            while True:
                try:
                    record = self._progress.get_nowait()
                except queue.Empty:
                    break
                runtime.progress_stage = record.stage
                runtime.progress_detail = record.current_path or "package"
                runtime.progress_completed_entries = record.completed_entries
                runtime.progress_total_entries = record.total_entries
                runtime.progress_verified_bytes = _format_bytes(record.verified_bytes)
                runtime.progress_total_bytes = _format_bytes(record.total_bytes)
                if record.total_bytes:
                    runtime.progress = record.verified_bytes / record.total_bytes
                elif record.total_entries:
                    runtime.progress = record.completed_entries / record.total_entries
                runtime.status_message = f"{record.stage}: {record.current_path or 'package'}"
        if not self._future.done():
            return {"RUNNING_MODAL"}
        try:
            outcome = self._future.result()
        except Exception as exc:
            self._finish(context)
            message = f"Validation worker failed safely: {type(exc).__name__}: {exc}"
            self._install_worker_error(message)
            self.report({"ERROR"}, message)
            return {"FINISHED"}
        self._finish(context)
        self._runtime_snapshot = None
        self._install_result(outcome)
        if outcome.state == OutcomeState.CANCELLED:
            self.report({"INFO"}, "Validation cancelled; the diagnostic result was retained")
        elif outcome.is_valid:
            self.report(
                {"INFO"},
                f"VAO {outcome.state.value}: {len(outcome.verified_assets)} assets verified",
            )
        else:
            message = outcome.diagnostics[0].message if outcome.diagnostics else outcome.state.value
            self.report({"ERROR"}, message)
        return {"FINISHED"}

    def _detached_record(self) -> DetachedMaterialization:
        return DetachedMaterialization(
            materialization_id=self.relink_materialization_id,
            root_name=self.relink_root_name,
            title="",
            package_id=self.expected_package_id,
            revision=self.expected_revision,
            release_id=self.expected_release_id,
            format_version=self.expected_format_version,
            manifest_sha256=self.expected_manifest_sha256,
            archive_sha256=self.expected_archive_sha256,
            source_path=self.filepath,
        )

    def _install_result(self, outcome: ValidationOutcome) -> None:
        scene = self._target_scene
        if not _scene_is_live(scene):
            return
        if self.operation != "RELINK":
            install_outcome(scene, outcome)
            return
        detached = self._detached_record()
        mismatch_reasons = list(relink_mismatch_reasons(detached, outcome))
        if not detached.root_name or bpy.data.collections.get(detached.root_name) is None:
            mismatch_reasons.append("managed collection is unavailable")
        elif materialization_is_shared(detached.root_name):
            mismatch_reasons.append("managed collection is linked into multiple scenes")
        matches = not mismatch_reasons
        if outcome.is_valid and mismatch_reasons:
            diagnostic = Diagnostic(
                "VAO-LIF-001",
                Severity.ERROR,
                Stage.LIFECYCLE,
                "Exact relink rejected: " + "; ".join(mismatch_reasons),
                related_ids=tuple(
                    value for value in (detached.package_id, detached.release_id) if value
                ),
            )
            outcome = replace(outcome, diagnostics=ordered((*outcome.diagnostics, diagnostic)))
        session = install_outcome(
            scene,
            outcome,
            detached=detached,
            source_matches_materialization=matches,
        )
        if matches:
            root = bpy.data.collections.get(detached.root_name)
            if root is not None:
                root["vao_source_name"] = Path(outcome.source_path).name
                if "vao_source_path" in root:
                    del root["vao_source_path"]
                root[TRACE_KEYS["archive"]] = outcome.archive_sha256
                root[TRACE_KEYS["session"]] = session.id
                root[TRACE_KEYS["materialization"]] = session.materialization_id
            scene.vao_runtime.materialization_state = "ATTACHED"
            scene.vao_runtime.status_message = (
                "Exact source revalidated and attached; scene data remains traceable"
            )
        elif mismatch_reasons:
            scene.vao_runtime.status_message = "Exact relink rejected: " + "; ".join(
                mismatch_reasons
            )

    def _install_worker_error(self, message: str) -> None:
        if not _scene_is_live(self._target_scene):
            return
        outcome = ValidationOutcome(
            state=OutcomeState.INVALID,
            source_path=self.filepath,
            diagnostics=(
                Diagnostic(
                    "VAO-LIF-002",
                    Severity.ERROR,
                    Stage.LIFECYCLE,
                    message,
                ),
            ),
        )
        self._runtime_snapshot = None
        install_outcome(self._target_scene, outcome)
        self._target_scene.vao_runtime.result_state = "WORKER_ERROR"
        self._target_scene.vao_runtime.state = "WORKER_ERROR"
        self._target_scene.vao_runtime.status_message = message

    def _finish(self, context):
        if self._timer is not None:
            manager = self._window_manager or getattr(context, "window_manager", None)
            try:
                if manager is not None:
                    manager.event_timer_remove(self._timer)
            except (ReferenceError, RuntimeError, ValueError):
                pass
            self._timer = None
        if self._executor is not None:
            self._executor.shutdown(wait=False, cancel_futures=True)
            self._executor = None
        self._future = None
        self._progress = None
        self._window_manager = None
        if self._registered_active:
            try:
                _ACTIVE_VALIDATIONS.remove(self)
            except ValueError:
                pass
            self._registered_active = False

    def cancel(self, context):
        if self._token:
            self._token.cancel()
        self._finish(context)
        if _scene_is_live(self._target_scene):
            self._restore_runtime(
                self._target_scene.vao_runtime,
                state="CANCELLED",
                message="Validation cancelled before the worker produced a result",
            )


class VAO_OT_cancel_validation(bpy.types.Operator):
    bl_idname = "vao.cancel_validation"
    bl_label = "Cancel Validation"
    bl_description = "Cooperatively stop validation and retain its cancelled diagnostic result"

    @classmethod
    def poll(cls, context):
        return bool(
            context.scene
            and hasattr(context.scene, "vao_runtime")
            and context.scene.vao_runtime.state == "VALIDATING"
        )

    def execute(self, context):
        found = False
        for operator in tuple(_ACTIVE_VALIDATIONS):
            if getattr(operator, "_target_scene", None) == context.scene:
                operator._token.cancel()
                found = True
        if not found:
            self.report({"WARNING"}, "No active validator belongs to this scene")
            return {"CANCELLED"}
        context.scene.vao_runtime.status_message = "Cancelling validation safely…"
        return {"FINISHED"}


class VAO_FH_import(bpy.types.FileHandler):
    bl_idname = "VAO_FH_import"
    bl_label = "Virtual Acoustic Object"
    bl_import_operator = "vao.import_package"
    bl_file_extensions = ".vao"

    @classmethod
    def poll_drop(cls, context):
        return context.area is not None and context.area.type == "VIEW_3D"


class VAO_OT_acknowledge_rights(bpy.types.Operator):
    bl_idname = "vao.acknowledge_rights"
    bl_label = "Acknowledge for This Session"
    bl_description = "Acknowledge the displayed limitation; this does not grant permission"

    @classmethod
    def poll(cls, context):
        session = active_session(context.scene)
        return bool(
            session
            and session.validation_complete
            and session.outcome.rights_acknowledgement_required
        )

    def execute(self, context):
        session = active_session(context.scene)
        if not session or not session.validation_complete:
            self.report({"ERROR"}, "Only a completely validated package can enable media")
            return {"CANCELLED"}
        runtime = context.scene.vao_runtime
        runtime.rights_acknowledged = True
        runtime.rights_state = "ACKNOWLEDGED"
        runtime.media_enabled = session.media_ready(context.scene)
        if runtime.support_state == "UNSUPPORTED":
            runtime.status_message = (
                "Rights limitation acknowledged for this session; unsupported capabilities "
                "remain disabled"
            )
        else:
            runtime.status_message = (
                "Rights limitation acknowledged for this session; this is not permission"
            )
        return {"FINISHED"}


class VAO_OT_select_asset(bpy.types.Operator):
    bl_idname = "vao.select_asset"
    bl_label = "Select VAO Asset"
    asset_id: StringProperty()

    def execute(self, context):
        runtime = context.scene.vao_runtime
        runtime.selected_asset_id = self.asset_id
        runtime.asset_properties_page = 0
        return {"FINISHED"}


class VAO_OT_select_realization(bpy.types.Operator):
    bl_idname = "vao.select_realization"
    bl_label = "Select VAO Realization"
    realization_id: StringProperty()
    logical_asset_id: StringProperty()

    def execute(self, context):
        runtime = context.scene.vao_runtime
        runtime.selected_realization_id = self.realization_id
        runtime.selected_asset_id = self.realization_id
        runtime.selected_logical_asset_id = self.logical_asset_id
        runtime.asset_properties_page = 0
        return {"FINISHED"}


class VAO_OT_select_relation(bpy.types.Operator):
    bl_idname = "vao.select_relation"
    bl_label = "Select VAO Relation"
    relation_id: StringProperty()

    def execute(self, context):
        runtime = context.scene.vao_runtime
        runtime.selected_relation_id = self.relation_id
        runtime.relation_properties_page = 0
        return {"FINISHED"}


class VAO_OT_select_record(bpy.types.Operator):
    bl_idname = "vao.select_record"
    bl_label = "Select VAO Model Record"
    record_key: StringProperty()

    def execute(self, context):
        runtime = context.scene.vao_runtime
        runtime.selected_record_key = self.record_key
        runtime.record_properties_page = 0
        return {"FINISHED"}


class VAO_OT_select_entity(bpy.types.Operator):
    bl_idname = "vao.select_entity"
    bl_label = "Select VAO Entity"
    entity_id: StringProperty()

    def execute(self, context):
        runtime = context.scene.vao_runtime
        runtime.selected_entity_id = self.entity_id
        runtime.selected_relation_id = ""
        runtime.explore_details_page = 0
        runtime.entity_properties_page = 0
        runtime.relation_properties_page = 0
        runtime.linked_assets_page = 0
        session = active_session(context.scene)
        if not session:
            return {"FINISHED"}
        root = bpy.data.collections.get(session.root_collection_name)
        candidates = tuple(root.all_objects) if root else ()
        for obj in context.selected_objects:
            obj.select_set(False)
        selected = []
        for obj in candidates:
            identifiers = {
                value for value in str(obj.get("vao_entity_ids", "")).split("|") if value
            }
            singular = str(obj.get("vao_entity_id", ""))
            if singular:
                identifiers.add(singular)
            if self.entity_id not in identifiers:
                continue
            try:
                obj.select_set(True)
                selected.append(obj)
            except RuntimeError:
                pass
        if selected:
            try:
                context.view_layer.objects.active = selected[0]
            except (AttributeError, RuntimeError):
                pass
        self.report(
            {"INFO"}, f"Selected {len(selected)} bound object(s) in this VAO materialization"
        )
        return {"FINISHED"}


class VAO_OT_copy_text(bpy.types.Operator):
    bl_idname = "vao.copy_text"
    bl_label = "Copy"
    bl_description = "Copy the complete value to the clipboard"
    text: StringProperty()

    def execute(self, context):
        context.window_manager.clipboard = self.text
        self.report({"INFO"}, "Copied complete value")
        return {"FINISHED"}


class VAO_OT_change_page(bpy.types.Operator):
    bl_idname = "vao.change_page"
    bl_label = "Change Page"
    property_name: StringProperty()
    delta: IntProperty(default=0)
    maximum: IntProperty(default=0, min=0)

    def execute(self, context):
        runtime = context.scene.vao_runtime
        if self.property_name not in {
            "explore_page",
            "explore_details_page",
            "diagnostics_page",
            "acoustic_measurement_page",
            "acoustic_response_page",
            "acoustic_rir_page",
            "entity_properties_page",
            "relation_properties_page",
            "linked_assets_page",
            "asset_properties_page",
            "record_properties_page",
            "rights_page",
            "detached_page",
            "play_selection_page",
            "play_gate_page",
        }:
            return {"CANCELLED"}
        value = min(self.maximum, getattr(runtime, self.property_name))
        setattr(runtime, self.property_name, max(0, min(self.maximum, value + self.delta)))
        return {"FINISHED"}


class VAO_OT_select_detached(bpy.types.Operator):
    bl_idname = "vao.select_detached"
    bl_label = "Select Detached Materialization"
    materialization_id: StringProperty()

    def execute(self, context):
        if active_session(context.scene):
            close_session(context.scene)
        if not select_detached(context.scene, self.materialization_id):
            return {"CANCELLED"}
        return {"FINISHED"}


class VAO_OT_load_visual(bpy.types.Operator):
    bl_idname = "vao.load_visual"
    bl_label = "Load Verified Visual"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        session = active_session(context.scene)
        if not session or not session.media_ready(context.scene):
            return False
        runtime = context.scene.vao_runtime
        identifier = runtime.selected_realization_id or runtime.selected_asset_id
        if session.outcome.contract_line in {"0.3.2", "0.4.0", "0.5.0"}:
            acoustic = session.outcome.acoustic_scene
            realization = session.outcome.realizations.get(identifier)
            return bool(
                acoustic
                and realization
                and identifier == acoustic.runtime_visual_realization_id
                and realization.media_type == "model/gltf-binary"
                and identifier in session.outcome.verified_assets
            )
        graph = session.outcome.graph
        asset = graph.assets.get(identifier) if graph else None
        return bool(
            asset
            and asset.media_type == "model/gltf-binary"
            and identifier in session.outcome.verified_assets
        )

    def execute(self, context):
        session = active_session(context.scene)
        if not session or not session.media_ready(context.scene):
            self.report({"ERROR"}, "No complete, exact-source, media-ready VAO session")
            return {"CANCELLED"}
        runtime = context.scene.vao_runtime
        asset_id = runtime.selected_realization_id or runtime.selected_asset_id
        try:
            collection, count = import_visual(session, context.scene, asset_id)
        except Exception as exc:
            runtime.materialization_state = "DEGRADED"
            self.report({"ERROR"}, f"Visual import rolled back: {exc}")
            return {"CANCELLED"}
        runtime.root_collection_name = session.root_collection_name
        runtime.materialization_state = "READY"
        runtime.status_message = f"Loaded {count} objects into {collection.name}"
        return {"FINISHED"}


class VAO_OT_select_representation(bpy.types.Operator):
    bl_idname = "vao.select_representation"
    bl_label = "Select Representation"
    identifier: StringProperty()

    def execute(self, context):
        session = active_session(context.scene)
        collection = representation_collection(session, self.identifier) if session else None
        if collection is None:
            self.report({"WARNING"}, "Representation is not loaded")
            return {"CANCELLED"}
        for obj in context.selected_objects:
            obj.select_set(False)
        selected = []
        for obj in collection.all_objects:
            try:
                obj.select_set(True)
                selected.append(obj)
            except RuntimeError:
                pass
        if selected:
            context.view_layer.objects.active = selected[0]
        self.report({"INFO"}, f"Selected {len(selected)} representation object(s)")
        return {"FINISHED"}


class VAO_OT_frame_representation(bpy.types.Operator):
    bl_idname = "vao.frame_representation"
    bl_label = "Frame Representation"
    identifier: StringProperty()

    def execute(self, context):
        result = bpy.ops.vao.select_representation(identifier=self.identifier)
        if "FINISHED" not in result:
            return {"CANCELLED"}
        if context.area and context.area.type == "VIEW_3D":
            bpy.ops.view3d.view_selected(use_all_regions=False)
        else:
            self.report({"INFO"}, "Representation selected; frame it from a 3D Viewport")
        return {"FINISHED"}


class VAO_OT_toggle_representation(bpy.types.Operator):
    bl_idname = "vao.toggle_representation"
    bl_label = "Hide/Show Representation"
    bl_options = {"REGISTER", "UNDO"}
    identifier: StringProperty()

    def execute(self, context):
        session = active_session(context.scene)
        collection = representation_collection(session, self.identifier) if session else None
        if collection is None:
            self.report({"WARNING"}, "Representation is not loaded")
            return {"CANCELLED"}
        set_representation_hidden(session, self.identifier, not collection.hide_viewport)
        return {"FINISHED"}


class VAO_OT_remove_representation(bpy.types.Operator):
    bl_idname = "vao.remove_representation"
    bl_label = "Remove Representation"
    bl_description = "Remove only the selected managed representation"
    bl_options = {"REGISTER", "UNDO"}
    identifier: StringProperty()

    def execute(self, context):
        session = active_session(context.scene)
        if not session:
            return {"CANCELLED"}
        try:
            remove_representation(session, self.identifier)
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        context.scene.vao_runtime.status_message = "Selected representation removed"
        return {"FINISHED"}


class VAO_OT_create_controls(bpy.types.Operator):
    bl_idname = "vao.create_controls"
    bl_label = "Create Interaction Board"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        session = active_session(context.scene)
        return bool(
            session
            and session.media_ready(context.scene)
            and session.outcome.interaction_plans
            and session.outcome.interaction_plans.supported
            and (
                session.outcome.interaction_plans.gates
                or session.outcome.interaction_plans.selections
            )
        )

    def execute(self, context):
        session = active_session(context.scene)
        if not session:
            return {"CANCELLED"}
        try:
            count = create_control_surface(session, context.scene)
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        self.report({"INFO"}, f"Interaction board contains {count} controls")
        return {"FINISHED"}


class VAO_OT_toggle_selection(bpy.types.Operator):
    bl_idname = "vao.toggle_selection"
    bl_label = "Toggle Selection"
    configuration_id: StringProperty()

    def execute(self, context):
        session = active_session(context.scene)
        bundle = session.outcome.interaction_plans if session else None
        if not session or not bundle or not bundle.supported:
            return {"CANCELLED"}
        selection = next(
            (item for item in bundle.selections if item.configuration_id == self.configuration_id),
            None,
        )
        if selection is None:
            return {"CANCELLED"}
        if self.configuration_id in session.active_configurations:
            session.active_configurations.remove(self.configuration_id)
        else:
            if not selection.independent:
                exclusive_ids = {
                    item.configuration_id for item in bundle.selections if not item.independent
                }
                session.active_configurations.difference_update(exclusive_ids)
            session.active_configurations.add(self.configuration_id)
        update_control_surface(session)
        context.area.tag_redraw() if context.area else None
        return {"FINISHED"}


class VAO_OT_preview_gate(bpy.types.Operator):
    bl_idname = "vao.preview_gate"
    bl_label = "Preview Note"
    gate_id: StringProperty()
    velocity: IntProperty(default=100, min=1, max=127)

    @classmethod
    def poll(cls, context):
        session = active_session(context.scene)
        bundle = session.outcome.interaction_plans if session else None
        return bool(
            session
            and bundle
            and bundle.supported
            and bundle.gates
            and bundle.voices
            and session.media_ready(context.scene)
        )

    def execute(self, context):
        session = active_session(context.scene)
        if not session or not session.media_ready(context.scene):
            self.report({"ERROR"}, "No media-ready validated session")
            return {"CANCELLED"}
        try:
            engine = session.ensure_audio()
            count = engine.preview_gate(self.gate_id, self.velocity)
        except Exception as exc:
            self.report({"ERROR"}, f"Audio playback failed: {exc}")
            return {"CANCELLED"}
        if count == 0:
            self.report({"WARNING"}, "Select at least one compatible configuration")
            return {"CANCELLED"}
        return {"FINISHED"}


class VAO_OT_find_diagnostics(bpy.types.Operator):
    bl_idname = "vao.find_diagnostics"
    bl_label = "Find Related Diagnostics"
    query: StringProperty()

    def execute(self, context):
        runtime = context.scene.vao_runtime
        runtime.diagnostics_search = self.query
        runtime.diagnostics_page = 0
        return {"FINISHED"}


class VAO_OT_export_diagnostics(bpy.types.Operator, ExportHelper):
    bl_idname = "vao.export_diagnostics"
    bl_label = "Export VAO Diagnostic Report"
    filename_ext = ".json"
    filter_glob: StringProperty(default="*.json", options={"HIDDEN"})

    def invoke(self, context, event):
        runtime = context.scene.vao_runtime
        self.filepath = f"{runtime.source_name or 'vao'}.diagnostics.json"
        return super().invoke(context, event)

    def execute(self, context):
        session = active_session(context.scene)
        if not session:
            self.report({"ERROR"}, "No live diagnostic result")
            return {"CANCELLED"}
        preferences = addon_preferences(context)
        redact = preferences.diagnostics_redact_paths if preferences else True
        report = session.outcome.report(redact_paths=redact)
        runtime = context.scene.vao_runtime
        report["hostState"] = {
            "validity": runtime.validity_state,
            "support": runtime.support_state,
            "rights": runtime.rights_state,
            "materialization": runtime.materialization_state,
            "sourceMatchesMaterialization": session.source_matches_materialization,
            "materializationId": runtime.materialization_id,
        }
        with open(self.filepath, "w", encoding="utf-8") as stream:
            json.dump(thaw_json_value(report), stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        self.report({"INFO"}, "Diagnostic report exported without modifying the VAO")
        return {"FINISHED"}


class VAO_OT_clear_cache(bpy.types.Operator):
    bl_idname = "vao.clear_cache"
    bl_label = "Clear Managed VAO Cache"
    target_path: StringProperty(options={"HIDDEN", "SKIP_SAVE"})

    def draw(self, _context):
        layout = self.layout
        layout.label(text="Delete managed cache contents?", icon="ERROR")
        layout.label(text="Exact managed root:")
        for line in _wrap(self.target_path, 86):
            layout.label(text=line)
        layout.label(
            text="Active session assets are protected; clearing will refuse if any are in use."
        )
        layout.label(text="Source VAO files and unrelated directory contents are never deleted.")

    def invoke(self, context, _event):
        self.target_path = str(Path(cache_root(context)).expanduser().resolve())
        return context.window_manager.invoke_props_dialog(self, width=620)

    def execute(self, context):
        from ..core.cache import AssetCache

        configured = Path(cache_root(context)).expanduser().resolve()
        target = Path(self.target_path).expanduser().resolve() if self.target_path else configured
        if target != configured:
            self.report(
                {"ERROR"},
                "Configured cache root changed after confirmation; reopen Clear Cache",
            )
            return {"CANCELLED"}
        try:
            AssetCache(configured).clear()
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        self.report({"INFO"}, f"Cleared managed cache at {configured}")
        return {"FINISHED"}


class VAO_OT_close_package(bpy.types.Operator):
    bl_idname = "vao.close_package"
    bl_label = "Close VAO Runtime"

    def execute(self, context):
        session = close_session(context.scene)
        runtime = context.scene.vao_runtime
        discover_detached(context.scene)
        runtime.state = "CLOSED"
        runtime.result_state = ""
        runtime.validity_state = "NOT_EVALUATED"
        runtime.support_state = "NOT_EVALUATED"
        runtime.rights_state = "NOT_EVALUATED"
        runtime.status_message = (
            "Runtime closed; imported scene data was retained"
            if session and session.root_collection_name
            else "Runtime closed"
        )
        return {"FINISHED"}


class VAO_OT_remove_materialization(bpy.types.Operator):
    bl_idname = "vao.remove_materialization"
    bl_label = "Remove Imported VAO Scene Data"
    bl_description = "Remove only the selected traceable VAO materialization"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        session = active_session(context.scene)
        detached = selected_detached(context.scene)
        try:
            if session and session.root_collection_name:
                remove_materialization(session)
            elif detached:
                remove_materialization(
                    root_name=detached.root_name,
                    materialization_id=detached.materialization_id,
                )
            else:
                self.report({"WARNING"}, "No managed materialization is selected")
                return {"CANCELLED"}
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        discover_detached(context.scene)
        context.scene.vao_runtime.status_message = "Managed VAO scene data removed"
        return {"FINISHED"}


def _format_bytes(value: int) -> str:
    value = max(0, int(value))
    size = float(value)
    units = ("B", "KiB", "MiB", "GiB", "TiB")
    for unit in units:
        if size < 1024.0 or unit == units[-1]:
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.2f} {unit}"
        size /= 1024.0
    return f"{value} B"


def _wrap(text: str, width: int) -> list[str]:
    if not text:
        return [""]
    words: list[str] = []
    for value in text.split():
        while len(value) > width:
            words.append(value[:width])
            value = value[width:]
        if value:
            words.append(value)
    if not words:
        return [text]
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
    VAO_OT_import_package,
    VAO_OT_cancel_validation,
    VAO_FH_import,
    VAO_OT_acknowledge_rights,
    VAO_OT_select_asset,
    VAO_OT_select_realization,
    VAO_OT_select_relation,
    VAO_OT_select_record,
    VAO_OT_select_entity,
    VAO_OT_copy_text,
    VAO_OT_change_page,
    VAO_OT_select_detached,
    VAO_OT_load_visual,
    VAO_OT_select_representation,
    VAO_OT_frame_representation,
    VAO_OT_toggle_representation,
    VAO_OT_remove_representation,
    VAO_OT_create_controls,
    VAO_OT_toggle_selection,
    VAO_OT_preview_gate,
    VAO_OT_find_diagnostics,
    VAO_OT_export_diagnostics,
    VAO_OT_clear_cache,
    VAO_OT_close_package,
    VAO_OT_remove_materialization,
)
