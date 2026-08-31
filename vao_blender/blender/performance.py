"""Modal keyboard and viewport-picking performance operator."""

from __future__ import annotations

import bpy
from bpy_extras import view3d_utils

from .scene_adapter import update_control_surface
from .session import active_session

EVENT_KEYS = (
    "Z",
    "S",
    "X",
    "D",
    "C",
    "V",
    "G",
    "B",
    "H",
    "N",
    "J",
    "M",
    "COMMA",
    "L",
    "PERIOD",
    "SEMICOLON",
    "SLASH",
    "Q",
    "TWO",
    "W",
    "THREE",
    "E",
    "R",
    "FIVE",
    "T",
    "SIX",
    "Y",
    "SEVEN",
    "U",
    "I",
    "NINE",
    "O",
    "ZERO",
    "P",
    "LEFT_BRACKET",
    "RIGHT_BRACKET",
    "A",
    "F",
    "K",
    "APOSTROPHE",
    "ONE",
    "FOUR",
    "EIGHT",
    "MINUS",
    "EQUAL",
)


class VAO_OT_performance_mode(bpy.types.Operator):
    bl_idname = "vao.performance_mode"
    bl_label = "Enter VAO Performance Mode"
    bl_description = "Capture declared note gates; Escape stops owned voices and exits"
    bl_options = {"REGISTER", "BLOCKING"}

    _event_to_gate = None
    _pressed = None
    _mouse_gate = ""
    _finished = False
    _session = None
    _scene = None

    @classmethod
    def poll(cls, context):
        if (
            context.area is None
            or context.area.type != "VIEW_3D"
            or not hasattr(context.scene, "vao_runtime")
            or context.scene.vao_runtime.performance_active
        ):
            return False
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

    def invoke(self, context, _event):
        session = active_session(context.scene)
        bundle = session.outcome.interaction_plans if session else None
        if (
            not session
            or not bundle
            or not bundle.supported
            or not bundle.gates
            or not bundle.voices
        ):
            self.report({"ERROR"}, "No fully supported playable VAO session")
            return {"CANCELLED"}
        if not session.media_ready(context.scene):
            self.report({"ERROR"}, "The session is not fully verified and media-ready")
            return {"CANCELLED"}
        gates = bundle.gates
        self._event_to_gate = {
            event: gate.interaction_id for event, gate in zip(EVENT_KEYS, gates, strict=False)
        }
        self._pressed = set()
        self._mouse_gate = ""
        self._finished = False
        self._session = session
        self._scene = context.scene
        context.scene.vao_runtime.performance_active = True
        unmapped = max(0, len(gates) - len(self._event_to_gate))
        suffix = f"; {unmapped} additional control(s) use pointer/preview" if unmapped else ""
        context.scene.vao_runtime.status_message = (
            f"Performance mode: {len(self._event_to_gate)} mapped keys{suffix}; Escape exits"
        )
        context.window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def _gate(self, context, gate_id: str, opening: bool) -> bool:
        session = active_session(context.scene)
        if not session or session is not self._session:
            return False
        engine = session.ensure_audio()
        if opening:
            if gate_id not in session.pressed_gates:
                if engine.open_gate(gate_id, 100) > 0:
                    session.pressed_gates.add(gate_id)
        else:
            engine.close_gate(gate_id)
            session.pressed_gates.discard(gate_id)
        update_control_surface(session)
        return True

    def _pick(self, context, event):
        area = context.area
        if area is None or area.type != "VIEW_3D":
            return None
        region = next((item for item in area.regions if item.type == "WINDOW"), None)
        space = area.spaces.active
        region_data = getattr(space, "region_3d", None)
        if region is None or region_data is None:
            return None
        coordinate = (event.mouse_x - region.x, event.mouse_y - region.y)
        if not (0 <= coordinate[0] < region.width and 0 <= coordinate[1] < region.height):
            return None
        origin = view3d_utils.region_2d_to_origin_3d(region, region_data, coordinate)
        direction = view3d_utils.region_2d_to_vector_3d(region, region_data, coordinate)
        hit, _location, _normal, _index, obj, _matrix = context.scene.ray_cast(
            context.evaluated_depsgraph_get(), origin, direction
        )
        return obj if hit else None

    def modal(self, context, event):
        if event.type in {"ESC", "WINDOW_DEACTIVATE"}:
            return self._finish(context)
        if context.area is None or context.area.type != "VIEW_3D":
            return self._finish(context, cancelled=True)
        try:
            session = active_session(context.scene)
            if not session or session is not self._session:
                return self._finish(context, cancelled=True)
            gate_id = self._event_to_gate.get(event.type)
            if gate_id:
                if event.value == "PRESS" and event.type not in self._pressed:
                    self._pressed.add(event.type)
                    self._gate(context, gate_id, True)
                elif event.value == "RELEASE":
                    self._pressed.discard(event.type)
                    self._gate(context, gate_id, False)
                return {"RUNNING_MODAL"}
            if event.type == "LEFTMOUSE":
                if event.value == "PRESS":
                    obj = self._pick(context, event)
                    owned = bool(obj and obj.get("vao_session_id") == session.id)
                    if owned and obj.get("vao_gate_id"):
                        self._mouse_gate = obj["vao_gate_id"]
                        self._gate(context, self._mouse_gate, True)
                    elif owned and obj.get("vao_configuration_id"):
                        configuration = obj["vao_configuration_id"]
                        if configuration in session.active_configurations:
                            session.active_configurations.remove(configuration)
                        else:
                            selection = next(
                                (
                                    item
                                    for item in session.outcome.interaction_plans.selections
                                    if item.configuration_id == configuration
                                ),
                                None,
                            )
                            if selection is None:
                                return {"RUNNING_MODAL"}
                            if not selection.independent:
                                exclusive_ids = {
                                    item.configuration_id
                                    for item in session.outcome.interaction_plans.selections
                                    if not item.independent
                                }
                                session.active_configurations.difference_update(exclusive_ids)
                            session.active_configurations.add(configuration)
                        update_control_surface(session)
                elif event.value == "RELEASE" and self._mouse_gate:
                    self._gate(context, self._mouse_gate, False)
                    self._mouse_gate = ""
                return {"RUNNING_MODAL"}
        except Exception as exc:
            self.report({"ERROR"}, f"Performance mode stopped safely: {type(exc).__name__}: {exc}")
            return self._finish(context, cancelled=True)
        return {"PASS_THROUGH"}

    def _finish(self, context, cancelled=False):
        if self._finished:
            return {"CANCELLED" if cancelled else "FINISHED"}
        self._finished = True
        scene = self._scene or getattr(context, "scene", None)
        session = self._session
        if session:
            session.stop_audio()
        if scene is not None and hasattr(scene, "vao_runtime"):
            scene.vao_runtime.performance_active = False
            scene.vao_runtime.status_message = "Performance mode ended; all owned voices stopped"
        self._pressed = set()
        self._mouse_gate = ""
        self._session = None
        self._scene = None
        return {"CANCELLED" if cancelled else "FINISHED"}


CLASSES = (VAO_OT_performance_mode,)
