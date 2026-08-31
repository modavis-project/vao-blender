"""Blender extension entry point."""

from .vao_blender.registration import register, unregister

__version__ = "0.4.0-rc.1"

__all__ = ("__version__", "register", "unregister")
