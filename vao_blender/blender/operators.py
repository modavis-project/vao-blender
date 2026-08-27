"""Package, diagnostics, selection, and scene operators."""

from __future__ import annotations

import json
import queue
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import bpy
from bpy.props import IntProperty, StringProperty
from bpy_extras.io_utils import ExportHelper, ImportHelper

from ..core.archive import ProgressRecord, validate_package
from ..core.cancellation import CancellationToken
from .preferences import addon_preferences, cache_root
from .scene_adapter import create_control_surface, import_visual
from .session import SESSIONS, active_session, install_outcome

_ACTIVE_VALIDATIONS: list[Any] = []
_RUNTIME_FIELDS = (
    "session_id",
    "state",
    "status_message",
    "source_name",
    "title",
    "package_id",
    "revision",
    "release_id",
    "format_version",
    "carrier_mode",
    "progress",
    "progress_stage",
    "verified_assets",
    "entity_count",
    "relation_count",
    "asset_count",
    "logical_asset_count",
    "realization_count",
    "frame_count",
    "pose_count",
    "measurement_count",
    "response_set_count",
    "rir_count",
    "search",
    "explore_page",
    "selected_asset_id",
    "selected_entity_id",
    "selected_logical_asset_id",
    "selected_realization_id",
    "rights_acknowledged",
    "performance_active",
)


def cancel_active_validations(scene=None) -> None:
    """Cooperatively stop validators and detach their Blender timers during teardown."""
    for operator in tuple(_ACTIVE_VALIDATIONS):
        token = getattr(operator, "_token", None)
        if token is not None:
            token.cancel()
        operator._finish(None)
        if scene is not None and hasattr(scene, "vao_runtime"):
            operator._restore_runtime(
                scene.vao_runtime,
                state="CANCELLED",
                message="Validation cancelled; no package data was installed",
            )


class VAO_OT_import_package(bpy.types.Operator, ImportHelper):
    bl_idname = "vao.import_package"
    bl_label = "Import Virtual Acoustic Object"
    bl_description = "Validate a VAO completely before making any payload media available"
    filename_ext = ".vao"
    filter_glob: StringProperty(default="*.vao", options={"HIDDEN"})

    _executor = None
    _future = None
    _timer = None
    _token = None
    _progress = None
    _window_manager = None
    _registered_active = False
    _runtime_snapshot = None

    def _restore_runtime(self, runtime, *, state: str, message: str) -> None:
        snapshot = self._runtime_snapshot
        self._runtime_snapshot = None
        if snapshot and snapshot.get("session_id"):
            for name, value in snapshot.items():
                setattr(runtime, name, value)
            return
        runtime.state = state
        runtime.status_message = message
        runtime.progress = 0.0
        runtime.progress_stage = state.casefold()

    def execute(self, context):
        cancel_active_validations(context.scene)
        runtime = context.scene.vao_runtime
        self._runtime_snapshot = {name: getattr(runtime, name) for name in _RUNTIME_FIELDS}
        runtime.state = "VALIDATING"
        runtime.status_message = "Treating package as untrusted; validating container"
        runtime.source_name = Path(self.filepath).name
        runtime.progress = 0.0
        runtime.progress_stage = "preflight"
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
            self._restore_runtime(runtime, state="ERROR", message=message)
            self.report({"ERROR"}, message)
            return {"CANCELLED"}
        _ACTIVE_VALIDATIONS.append(self)
        self._registered_active = True
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        if event.type == "ESC" and self._token:
            self._token.cancel()
            if hasattr(context.scene, "vao_runtime"):
                context.scene.vao_runtime.status_message = "Cancelling validation safely…"
            return {"RUNNING_MODAL"}
        if event.type != "TIMER":
            return {"PASS_THROUGH"}
        if self._future is None:
            return {"CANCELLED"}
        runtime = context.scene.vao_runtime
        if self._progress:
            while True:
                try:
                    record = self._progress.get_nowait()
                except queue.Empty:
                    break
                runtime.progress_stage = record.stage
                if record.total_bytes:
                    runtime.progress = record.verified_bytes / record.total_bytes
                elif record.total_entries:
                    runtime.progress = record.completed_entries / record.total_entries
                runtime.status_message = (
                    f"{record.stage}: {record.current_path or 'package'} "
                    f"({runtime.progress * 100:.1f}%)"
                )
        if not self._future.done():
            return {"RUNNING_MODAL"}
        try:
            outcome = self._future.result()
        except Exception as exc:
            self._finish(context)
            message = f"Validation worker failed safely: {type(exc).__name__}: {exc}"
            self._restore_runtime(runtime, state="ERROR", message=message)
            self.report({"ERROR"}, message)
            return {"CANCELLED"}
        self._finish(context)
        if outcome.state.value == "cancelled":
            self._restore_runtime(
                runtime,
                state="CANCELLED",
                message="Validation cancelled; no package data was installed",
            )
            return {"CANCELLED"}
        if outcome.is_valid:
            self._runtime_snapshot = None
            install_outcome(context.scene, outcome)
            self.report(
                {"INFO"},
                f"VAO {outcome.state.value}: {len(outcome.verified_assets)} assets verified",
            )
            return {"FINISHED"}
        message = outcome.diagnostics[0].message if outcome.diagnostics else outcome.state.value
        self._restore_runtime(runtime, state="INVALID", message=message)
        self.report({"ERROR"}, message)
        return {"CANCELLED"}

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
        if hasattr(context.scene, "vao_runtime"):
            self._restore_runtime(
                context.scene.vao_runtime,
                state="CANCELLED",
                message="Validation cancelled; no package data was installed",
            )


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

    def execute(self, context):
        runtime = context.scene.vao_runtime
        runtime.rights_acknowledged = True
        runtime.state = "VALID"
        runtime.status_message = "Valid and media-enabled by this session's rights acknowledgement"
        return {"FINISHED"}


class VAO_OT_select_asset(bpy.types.Operator):
    bl_idname = "vao.select_asset"
    bl_label = "Select VAO Asset"
    asset_id: StringProperty()

    def execute(self, context):
        context.scene.vao_runtime.selected_asset_id = self.asset_id
        return {"FINISHED"}


class VAO_OT_select_entity(bpy.types.Operator):
    bl_idname = "vao.select_entity"
    bl_label = "Select VAO Entity"
    entity_id: StringProperty()

    def execute(self, context):
        context.scene.vao_runtime.selected_entity_id = self.entity_id
        session = active_session(context.scene)
        if session:
            for obj in context.selected_objects:
                obj.select_set(False)
            for obj in bpy.data.objects:
                identifiers = str(obj.get("vao_entity_ids", "")).split("|")
                if self.entity_id in identifiers:
                    obj.select_set(True)
        return {"FINISHED"}


class VAO_OT_load_visual(bpy.types.Operator):
    bl_idname = "vao.load_visual"
    bl_label = "Load Verified Visual"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        session = active_session(context.scene)
        if not session:
            self.report({"ERROR"}, "No validated VAO session")
            return {"CANCELLED"}
        if not session.rights_ready(context.scene):
            self.report({"ERROR"}, "Acknowledge the displayed rights/access limitation first")
            return {"CANCELLED"}
        asset_id = context.scene.vao_runtime.selected_asset_id
        try:
            collection, count = import_visual(session, context.scene, asset_id)
        except Exception as exc:
            self.report({"ERROR"}, f"Visual import rolled back: {exc}")
            return {"CANCELLED"}
        context.scene.vao_runtime.status_message = f"Loaded {count} objects into {collection.name}"
        return {"FINISHED"}


class VAO_OT_create_controls(bpy.types.Operator):
    bl_idname = "vao.create_controls"
    bl_label = "Create Interaction Board"
    bl_options = {"REGISTER", "UNDO"}

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
        if not session:
            return {"CANCELLED"}
        if self.configuration_id in session.active_configurations:
            session.active_configurations.remove(self.configuration_id)
        else:
            session.active_configurations.add(self.configuration_id)
        context.area.tag_redraw() if context.area else None
        return {"FINISHED"}


class VAO_OT_preview_gate(bpy.types.Operator):
    bl_idname = "vao.preview_gate"
    bl_label = "Preview Note"
    gate_id: StringProperty()
    velocity: IntProperty(default=100, min=1, max=127)

    def execute(self, context):
        session = active_session(context.scene)
        if not session or not session.rights_ready(context.scene):
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
            return {"CANCELLED"}
        preferences = addon_preferences(context)
        redact = preferences.diagnostics_redact_paths if preferences else True
        with open(self.filepath, "w", encoding="utf-8") as stream:
            json.dump(
                session.outcome.report(redact_paths=redact), stream, ensure_ascii=False, indent=2
            )
            stream.write("\n")
        self.report({"INFO"}, "Diagnostic report exported without modifying the VAO")
        return {"FINISHED"}


class VAO_OT_clear_cache(bpy.types.Operator):
    bl_idname = "vao.clear_cache"
    bl_label = "Clear Managed VAO Cache"

    def invoke(self, context, _event):
        return context.window_manager.invoke_confirm(self, _event)

    def execute(self, context):
        session = active_session(context.scene)
        try:
            if session:
                session.stop_audio()
                session.cache.clear()
            else:
                from ..core.cache import AssetCache

                AssetCache(cache_root()).clear()
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        self.report({"INFO"}, f"Cleared managed cache at {cache_root()}")
        return {"FINISHED"}


class VAO_OT_close_package(bpy.types.Operator):
    bl_idname = "vao.close_package"
    bl_label = "Close VAO Runtime"

    def execute(self, context):
        runtime = context.scene.vao_runtime
        session = SESSIONS.pop(runtime.session_id, None)
        if session:
            session.stop_audio()
        runtime.session_id = ""
        runtime.state = "CLOSED"
        runtime.status_message = "Runtime closed; imported scene data was retained"
        runtime.performance_active = False
        return {"FINISHED"}


CLASSES = (
    VAO_OT_import_package,
    VAO_FH_import,
    VAO_OT_acknowledge_rights,
    VAO_OT_select_asset,
    VAO_OT_select_entity,
    VAO_OT_load_visual,
    VAO_OT_create_controls,
    VAO_OT_toggle_selection,
    VAO_OT_preview_gate,
    VAO_OT_export_diagnostics,
    VAO_OT_clear_cache,
    VAO_OT_close_package,
)
