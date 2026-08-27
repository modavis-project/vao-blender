"""Modal keyboard and viewport-picking performance operator."""

from __future__ import annotations

import bpy
from bpy_extras import view3d_utils

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

    @classmethod
    def poll(cls, context):
        return (
            context.area is not None
            and context.area.type == "VIEW_3D"
            and hasattr(context.scene, "vao_runtime")
            and not context.scene.vao_runtime.performance_active
        )

    def invoke(self, context, _event):
        session = active_session(context.scene)
        if not session or not session.outcome.interaction_plans:
            self.report({"ERROR"}, "No compiled playable VAO session")
            return {"CANCELLED"}
        if not session.rights_ready(context.scene):
            self.report({"ERROR"}, "Acknowledge rights/access limitations first")
            return {"CANCELLED"}
        gates = session.outcome.interaction_plans.gates
        self._event_to_gate = {
            event: gate.interaction_id for event, gate in zip(EVENT_KEYS, gates, strict=False)
        }
        self._pressed = set()
        self._mouse_gate = ""
        self._finished = False
        context.scene.vao_runtime.performance_active = True
        context.scene.vao_runtime.status_message = (
            f"Performance mode: {len(self._event_to_gate)} mapped keys; Escape exits"
        )
        context.window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def _gate(self, context, gate_id: str, opening: bool) -> bool:
        session = active_session(context.scene)
        if not session:
            return False
        engine = session.ensure_audio()
        if opening:
            if gate_id not in session.pressed_gates:
                if engine.open_gate(gate_id, 100) > 0:
                    session.pressed_gates.add(gate_id)
        else:
            engine.close_gate(gate_id)
            session.pressed_gates.discard(gate_id)
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
        try:
            session = active_session(context.scene)
            if not session:
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
                    if obj and obj.get("vao_gate_id"):
                        self._mouse_gate = obj["vao_gate_id"]
                        self._gate(context, self._mouse_gate, True)
                    elif obj and obj.get("vao_configuration_id"):
                        configuration = obj["vao_configuration_id"]
                        if configuration in session.active_configurations:
                            session.active_configurations.remove(configuration)
                        else:
                            session.active_configurations.add(configuration)
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
        scene = getattr(context, "scene", None)
        session = active_session(scene)
        if session:
            session.stop_audio()
        if scene is not None and hasattr(scene, "vao_runtime"):
            scene.vao_runtime.performance_active = False
            scene.vao_runtime.status_message = "Performance mode ended; all owned voices stopped"
        self._pressed = set()
        self._mouse_gate = ""
        return {"CANCELLED" if cancelled else "FINISHED"}


CLASSES = (VAO_OT_performance_mode,)
