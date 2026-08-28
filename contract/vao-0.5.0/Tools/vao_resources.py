#!/usr/bin/env python3
"""Locate VAO schema resources in a source checkout or installed wheel."""

from __future__ import annotations

from importlib import import_module
from pathlib import Path


_MARKER = "vao-manifest-0.4.0.schema.json"


def source_root() -> Path | None:
    """Return the repository root when executing directly from a checkout."""
    candidate = Path(__file__).resolve().parent.parent
    if (candidate / "Schemas" / _MARKER).is_file():
        return candidate
    return None


def schema_directory() -> Path:
    """Return the filesystem directory containing the distributed schemas."""
    root = source_root()
    if root is not None:
        return root / "Schemas"
    try:
        package = import_module("vao_standard_schemas")
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "VAO schema resources are unavailable. Install the complete "
            "vao-standard-tools distribution or run from its source checkout."
        ) from exc
    package_file = getattr(package, "__file__", None)
    if package_file is None:
        raise RuntimeError("The installed VAO schema resource package has no path.")
    candidate = Path(package_file).resolve().parent
    if not (candidate / _MARKER).is_file():
        raise RuntimeError(
            f"The installed VAO schema resource package is incomplete: {candidate}"
        )
    return candidate


def dependency_lock() -> Path | None:
    """Return the source-checkout release lock, if it is locally available."""
    root = source_root()
    if root is None:
        return None
    candidate = root / "requirements-lock.txt"
    return candidate if candidate.is_file() else None
