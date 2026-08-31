from __future__ import annotations

import bpy
from bpy.app.handlers import persistent

from .session import close_all, discover_detached, resync_after_undo


def _cancel_background_work() -> None:
    from .operators import cancel_active_validations

    cancel_active_validations()


@persistent
def on_load_pre(_unused):
    _cancel_background_work()
    close_all()


@persistent
def on_load_post(_unused):
    for scene in bpy.data.scenes:
        if hasattr(scene, "vao_runtime"):
            discover_detached(scene)


@persistent
def on_quit_pre(_unused):
    _cancel_background_work()
    close_all()


@persistent
def on_undo_redo_post(_unused):
    for scene in bpy.data.scenes:
        if hasattr(scene, "vao_runtime"):
            resync_after_undo(scene)


def register() -> None:
    if on_load_pre not in bpy.app.handlers.load_pre:
        bpy.app.handlers.load_pre.append(on_load_pre)
    if on_load_post not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(on_load_post)
    quit_handlers = getattr(bpy.app.handlers, "quit_pre", None)
    if quit_handlers is not None and on_quit_pre not in quit_handlers:
        quit_handlers.append(on_quit_pre)
    for handler_name in ("undo_post", "redo_post"):
        handlers = getattr(bpy.app.handlers, handler_name, None)
        if handlers is not None and on_undo_redo_post not in handlers:
            handlers.append(on_undo_redo_post)


def unregister() -> None:
    _cancel_background_work()
    close_all()
    handler_pairs = [
        (bpy.app.handlers.load_pre, on_load_pre),
        (bpy.app.handlers.load_post, on_load_post),
    ]
    quit_handlers = getattr(bpy.app.handlers, "quit_pre", None)
    if quit_handlers is not None:
        handler_pairs.append((quit_handlers, on_quit_pre))
    for handler_name in ("undo_post", "redo_post"):
        handlers = getattr(bpy.app.handlers, handler_name, None)
        if handlers is not None:
            handler_pairs.append((handlers, on_undo_redo_post))
    for handlers, callback in handler_pairs:
        if callback in handlers:
            handlers.remove(callback)
