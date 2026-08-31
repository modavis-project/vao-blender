from __future__ import annotations

import bpy
from bpy.props import BoolProperty, IntProperty, StringProperty


def _addon_id() -> str:
    parts = __package__.split(".")
    return ".".join(parts[:3]) if parts[0] == "bl_ext" else parts[0]


class VAOAddonPreferences(bpy.types.AddonPreferences):
    bl_idname = _addon_id()

    cache_root: StringProperty(
        name="Verified media cache",
        subtype="DIR_PATH",
        description=(
            "Dedicated managed content-addressed cache. A custom directory must be new/empty "
            "or already marked by VAO-Blender; source VAOs are never modified"
        ),
        default="",
    )
    cache_quota_gib: IntProperty(name="Cache quota (GiB)", default=20, min=1, max=1024)
    max_polyphony: IntProperty(name="Maximum voices", default=64, min=1, max=512)
    diagnostics_redact_paths: BoolProperty(
        name="Redact absolute paths in diagnostics", default=True
    )

    def draw(self, _context):
        layout = self.layout
        layout.prop(self, "cache_root")
        layout.prop(self, "cache_quota_gib")
        layout.prop(self, "max_polyphony")
        layout.prop(self, "diagnostics_redact_paths")
        box = layout.box()
        box.label(text="Effective managed cache root:")
        for line in _wrap(cache_root(), 80):
            box.label(text=line)
        box.label(text="Custom roots are adopted only when empty.", icon="INFO")
        box.label(text="Clear Cache confirms this exact path and protects active assets.")
        layout.label(text="Offline reader: no network permission is requested", icon="LOCKED")


def addon_preferences(context=None) -> VAOAddonPreferences | None:
    context = context or bpy.context
    package = _addon_id()
    addon = context.preferences.addons.get(package)
    return addon.preferences if addon else None


def cache_root(context=None) -> str:
    preferences = addon_preferences(context)
    if preferences and preferences.cache_root:
        return bpy.path.abspath(preferences.cache_root)
    return bpy.utils.user_resource("DATAFILES", path="vao_blender/cache", create=True)


def _wrap(text: str, width: int) -> list[str]:
    if len(text) <= width:
        return [text]
    return [text[index : index + width] for index in range(0, len(text), width)]
