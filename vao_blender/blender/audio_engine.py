"""Narrow Blender aud adapter with gate ownership and deterministic cleanup."""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Callable

import aud
import bpy

from ..core.model import VoicePlan


@dataclass(slots=True)
class OwnedVoice:
    gate_id: str
    plan: VoicePlan
    handle: object
    gain: float
    started: float = field(default_factory=time.monotonic)
    ramp_timer: Callable | None = None


class AudioEngine:
    def __init__(self, session, *, max_polyphony: int = 64) -> None:
        self.session = session
        self.device = aud.Device()
        self.max_polyphony = max_polyphony
        self.by_gate: dict[str, list[OwnedVoice]] = {}
        self.sounds: dict[str, object] = {}
        self.timers: set[Callable] = set()
        self.closed = False

    def _all_voices(self) -> list[OwnedVoice]:
        return [voice for voices in self.by_gate.values() for voice in voices]

    def _register_timer(self, callback: Callable, delay: float = 0.0) -> bool:
        if self.closed:
            return False
        self.timers.add(callback)
        try:
            bpy.app.timers.register(callback, first_interval=max(delay, 0.0))
        except Exception:
            self.timers.discard(callback)
            return False
        return True

    def _cancel_timer(self, callback: Callable | None) -> None:
        if callback is None:
            return
        self.timers.discard(callback)
        try:
            if bpy.app.timers.is_registered(callback):
                bpy.app.timers.unregister(callback)
        except Exception:
            pass

    def _sound(self, plan: VoicePlan):
        cached = self.sounds.get(plan.sample_sha256)
        if cached is not None:
            return cached
        asset = self.session.outcome.graph.assets[plan.sample_asset_id]
        path = self.session.cache.extract(self.session.source_path, asset)
        sound = aud.Sound.file(str(path))
        self.sounds[plan.sample_sha256] = sound
        return sound

    def _stop_voice(self, voice: OwnedVoice) -> None:
        self._cancel_timer(voice.ramp_timer)
        voice.ramp_timer = None
        try:
            voice.handle.stop()
        except Exception:
            pass
        voices = self.by_gate.get(voice.gate_id, [])
        if voice in voices:
            voices.remove(voice)
        if not voices:
            self.by_gate.pop(voice.gate_id, None)

    def _steal_if_needed(self, additional: int) -> None:
        voices = sorted(self._all_voices(), key=lambda item: item.started)
        excess = len(voices) + additional - self.max_polyphony
        for voice in voices[: max(0, excess)]:
            self._stop_voice(voice)

    def open_gate(self, gate_id: str, velocity: int = 100) -> int:
        if self.closed or gate_id in self.by_gate:
            return 0
        bundle = self.session.outcome.interaction_plans
        if not bundle:
            return 0
        plans = [
            plan
            for plan in bundle.voices
            if plan.gate_id == gate_id
            and plan.configuration_id in self.session.active_configurations
        ]
        self._steal_if_needed(len(plans))
        resolved = [(plan, self._sound(plan)) for plan in plans]
        started: list[OwnedVoice] = []
        lock = getattr(self.device, "lock", None)
        unlock = getattr(self.device, "unlock", None)
        if lock:
            lock()
        try:
            for plan, sound in resolved:
                handle = self.device.play(sound)
                gain = 10.0 ** (plan.gain_db / 20.0) * max(1, min(127, velocity)) / 127.0
                handle.pitch = 1.0
                handle.volume = 0.0 if plan.attack_seconds > 0 else gain
                voice = OwnedVoice(gate_id, plan, handle, gain)
                self.by_gate.setdefault(gate_id, []).append(voice)
                started.append(voice)
        except Exception:
            for voice in started:
                self._stop_voice(voice)
            raise
        finally:
            if unlock:
                unlock()
        for voice in started:
            if voice.plan.attack_seconds > 0:
                self._ramp(voice, 0.0, voice.gain, voice.plan.attack_seconds, stop_after=False)
        return len(started)

    def _ramp(
        self,
        voice: OwnedVoice,
        start_volume: float,
        end_volume: float,
        duration: float,
        *,
        stop_after: bool,
    ) -> None:
        self._cancel_timer(voice.ramp_timer)
        voice.ramp_timer = None
        started = time.monotonic()

        def update():
            if self.closed or voice not in self.by_gate.get(voice.gate_id, []):
                self.timers.discard(update)
                voice.ramp_timer = None
                return None
            fraction = min(1.0, (time.monotonic() - started) / max(duration, 0.001))
            if voice.plan.envelope_curve == "equal-power":
                fraction = math.sin(fraction * math.pi / 2.0)
            try:
                voice.handle.volume = start_volume + (end_volume - start_volume) * fraction
            except Exception:
                self._stop_voice(voice)
                self.timers.discard(update)
                voice.ramp_timer = None
                return None
            if fraction >= 1.0:
                if stop_after:
                    self._stop_voice(voice)
                self.timers.discard(update)
                voice.ramp_timer = None
                return None
            return 1.0 / 60.0

        voice.ramp_timer = update
        if not self._register_timer(update):
            voice.ramp_timer = None
            if stop_after:
                self._stop_voice(voice)

    def close_gate(self, gate_id: str) -> None:
        for voice in tuple(self.by_gate.get(gate_id, [])):
            duration = voice.plan.release_seconds
            if duration <= 0:
                self._stop_voice(voice)
            else:
                current = float(getattr(voice.handle, "volume", voice.gain))
                self._ramp(voice, current, 0.0, duration, stop_after=True)

    def preview_gate(self, gate_id: str, velocity: int = 100, duration: float = 0.5) -> int:
        count = self.open_gate(gate_id, velocity)
        if count == 0:
            return 0

        def release():
            self.timers.discard(release)
            if not self.closed:
                self.close_gate(gate_id)
            return None

        if not self._register_timer(release, duration):
            self.close_gate(gate_id)
        return count

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        for timer in tuple(self.timers):
            try:
                if bpy.app.timers.is_registered(timer):
                    bpy.app.timers.unregister(timer)
            except Exception:
                pass
        self.timers.clear()
        for voice in tuple(self._all_voices()):
            self._stop_voice(voice)
        self.sounds.clear()
