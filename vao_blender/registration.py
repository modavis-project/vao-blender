"""Symmetric Blender registration for the VAO extension."""

from __future__ import annotations

import bpy

from .blender import handlers, operators, panels, performance, properties
from .blender.preferences import VAOAddonPreferences
from .core.contract import verify_contracts


def _menu_import(self, _context):
    self.layout.operator(
        operators.VAO_OT_import_package.bl_idname,
        text="Virtual Acoustic Object (.vao)",
    )


REGISTER_CLASSES = (
    VAOAddonPreferences,
    *operators.CLASSES,
    *performance.CLASSES,
    *panels.CLASSES,
)

_REGISTERED = False
_REGISTERED_CLASSES: list[type] = []
_MENU_REGISTERED = False


def register() -> None:
    global _REGISTERED, _MENU_REGISTERED
    if _REGISTERED:
        return
    verify_contracts()
    try:
        properties.register()
        for cls in REGISTER_CLASSES:
            bpy.utils.register_class(cls)
            _REGISTERED_CLASSES.append(cls)
        bpy.types.TOPBAR_MT_file_import.append(_menu_import)
        _MENU_REGISTERED = True
        handlers.register()
        _REGISTERED = True
    except Exception:
        handlers.unregister()
        if _MENU_REGISTERED:
            try:
                bpy.types.TOPBAR_MT_file_import.remove(_menu_import)
            except (ValueError, RuntimeError):
                pass
            _MENU_REGISTERED = False
        for cls in reversed(_REGISTERED_CLASSES):
            if getattr(cls, "is_registered", False):
                bpy.utils.unregister_class(cls)
        _REGISTERED_CLASSES.clear()
        properties.unregister()
        raise


def unregister() -> None:
    global _REGISTERED, _MENU_REGISTERED
    handlers.unregister()
    if _MENU_REGISTERED:
        try:
            bpy.types.TOPBAR_MT_file_import.remove(_menu_import)
        except (ValueError, RuntimeError):
            pass
        _MENU_REGISTERED = False
    classes = _REGISTERED_CLASSES or list(REGISTER_CLASSES)
    for cls in reversed(classes):
        if getattr(cls, "is_registered", False):
            bpy.utils.unregister_class(cls)
    _REGISTERED_CLASSES.clear()
    properties.unregister()
    _REGISTERED = False
