"""Typed, deterministic diagnostics shared by the core and Blender UI."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Iterable


class Severity(StrEnum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class Stage(StrEnum):
    CONTAINER = "container"
    SCHEMA = "schema"
    SEMANTIC = "semantic"
    CAPABILITY = "capability"
    GLTF = "gltf"
    INTERACTION = "interaction"
    AUDIO = "audio"
    LIFECYCLE = "lifecycle"


@dataclass(frozen=True, slots=True)
class Diagnostic:
    code: str
    severity: Severity
    stage: Stage
    message: str
    pointer: str = ""
    archive_path: str = ""
    related_ids: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        value = asdict(self)
        value["severity"] = self.severity.value
        value["stage"] = self.stage.value
        return value


def ordered(diagnostics: Iterable[Diagnostic]) -> tuple[Diagnostic, ...]:
    """Return diagnostics in a reproducible order independent of hash iteration."""
    return tuple(
        sorted(
            diagnostics,
            key=lambda item: (
                item.stage.value,
                item.code,
                item.pointer,
                item.archive_path,
                item.related_ids,
                item.message,
            ),
        )
    )
