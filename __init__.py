"""Blender extension entry point."""

from .vao_blender.registration import register, unregister

__all__ = ("register", "unregister")
