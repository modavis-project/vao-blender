"""Cooperative cancellation primitives for streaming validation."""

from __future__ import annotations

from dataclasses import dataclass, field
from threading import Event


class CancelledError(RuntimeError):
    pass


@dataclass(slots=True)
class CancellationToken:
    _event: Event = field(default_factory=Event)

    def cancel(self) -> None:
        self._event.set()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    def check(self) -> None:
        if self.cancelled:
            raise CancelledError("VAO validation cancelled")
