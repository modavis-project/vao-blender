"""Narrow Blender aud adapter with gate ownership and deterministic cleanup."""

from __future__ import annotations

import math
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
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
    def __init__(
        self,
        session,
        *,
        max_polyphony: int = 64,
        device=None,
        timer_api=None,
        sound_loader: Callable[[str], object] | None = None,
        clock: Callable[[], float] = time.monotonic,
        max_cached_sounds: int | None = None,
    ) -> None:
        self.session = session
        self.device = device or aud.Device()
        self.timer_api = timer_api or bpy.app.timers
        self.sound_loader = sound_loader or aud.Sound.file
        self.clock = clock
        self.max_polyphony = max(1, int(max_polyphony))
        self.max_cached_sounds = max(
            self.max_polyphony,
            int(max_cached_sounds or self.max_polyphony * 2),
        )
        self.by_gate: dict[str, list[OwnedVoice]] = {}
        self.sounds: OrderedDict[str, object] = OrderedDict()
        self.sound_paths: dict[str, Path] = {}
        self.timers: set[Callable] = set()
        self.closed = False

    def _all_voices(self) -> list[OwnedVoice]:
        return [voice for voices in self.by_gate.values() for voice in voices]

    def _register_timer(self, callback: Callable, delay: float = 0.0) -> bool:
        if self.closed:
            return False
        self.timers.add(callback)
        try:
            self.timer_api.register(callback, first_interval=max(delay, 0.0))
        except Exception:
            self.timers.discard(callback)
            return False
        return True

    def _cancel_timer(self, callback: Callable | None) -> None:
        if callback is None:
            return
        self.timers.discard(callback)
        try:
            if self.timer_api.is_registered(callback):
                self.timer_api.unregister(callback)
        except Exception:
            pass

    def _sound(self, plan: VoicePlan):
        cached = self.sounds.get(plan.sample_sha256)
        if cached is not None:
            self.sounds.move_to_end(plan.sample_sha256)
            return cached
        asset = self.session.outcome.graph.assets[plan.sample_asset_id]
        cache = self.session.cache
        path = cache.extract(self.session.source_path, asset, protect=True)
        try:
            self.session.adopt_protected_cache_path(path, cache.root)
        except Exception:
            cache.unregister_protected(path)
            raise
        try:
            sound = self.sound_loader(str(path))
            if sound is None:
                raise RuntimeError("audio decoder did not return a sound")
        except Exception:
            self.session.release_cache_path(path)
            raise
        self.sounds[plan.sample_sha256] = sound
        self.sound_paths[plan.sample_sha256] = path
        self._prune_sounds()
        return sound

    def _prune_sounds(self) -> None:
        active = {voice.plan.sample_sha256 for voice in self._all_voices()}
        for checksum in tuple(self.sounds):
            if len(self.sounds) <= self.max_cached_sounds:
                break
            if checksum not in active:
                self.sounds.pop(checksum, None)
                path = self.sound_paths.pop(checksum, None)
                if path is not None:
                    self.session.release_cache_path(path)

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
        self._prune_sounds()

    def open_gate(self, gate_id: str, velocity: int = 100) -> int:
        if self.closed or gate_id in self.by_gate:
            return 0
        bundle = self.session.outcome.interaction_plans
        if not bundle or not bundle.supported:
            raise RuntimeError("the VAO interaction plan is not fully supported")
        if not isinstance(velocity, int) or isinstance(velocity, bool) or not 0 <= velocity <= 127:
            raise ValueError("gate velocity must be an integer from 0 through 127")
        plans = [
            plan
            for plan in bundle.voices
            if plan.gate_id == gate_id
            and plan.configuration_id in self.session.active_configurations
            and plan.minimum_velocity <= velocity <= plan.maximum_velocity
        ]
        if not plans:
            return 0
        active_count = len(self._all_voices())
        if len(plans) > self.max_polyphony or active_count + len(plans) > self.max_polyphony:
            raise RuntimeError(
                f"gate requires {len(plans)} voices with {active_count} already active; "
                f"configured polyphony is {self.max_polyphony}. No partial gate was started"
            )
        resolved = [(plan, self._sound(plan)) for plan in plans]
        started: list[OwnedVoice] = []
        lock = getattr(self.device, "lock", None)
        unlock = getattr(self.device, "unlock", None)
        lock_pair = callable(lock) and callable(unlock)
        playback_failed = False
        if lock_pair:
            lock()
        try:
            for plan, sound in resolved:
                handle = self.device.play(sound)
                if handle is None:
                    raise RuntimeError("audio device did not return a playback handle")
                try:
                    # Velocity is retained as a control-domain value but is not
                    # applied until a reviewed velocity-to-gain policy is part of
                    # the compiled plan. Inventing a linear response would change
                    # the declared instrument.
                    gain = (10.0 ** (plan.gain_db / 20.0)) * plan.sustain_level
                    handle.pitch = 1.0
                    handle.volume = 0.0 if plan.attack_seconds > 0 else gain
                    voice = OwnedVoice(gate_id, plan, handle, gain)
                    voice.started = self.clock()
                    self.by_gate.setdefault(gate_id, []).append(voice)
                    started.append(voice)
                except Exception:
                    try:
                        handle.stop()
                    except Exception:
                        pass
                    raise
        except Exception:
            playback_failed = True
            for voice in started:
                self._stop_voice(voice)
            raise
        finally:
            if lock_pair:
                try:
                    unlock()
                except Exception:
                    # A failed unlock leaves the device state uncertain. If
                    # playback itself succeeded, fail the operation atomically
                    # and stop every handle that this gate just acquired. When
                    # another exception is already propagating, preserve that
                    # primary failure after making the same best-effort cleanup.
                    for voice in tuple(started):
                        self._stop_voice(voice)
                    if not playback_failed:
                        raise
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
        started = self.clock()

        def update():
            if self.closed or voice not in self.by_gate.get(voice.gate_id, []):
                self.timers.discard(update)
                voice.ramp_timer = None
                return None
            linear_fraction = min(1.0, (self.clock() - started) / max(duration, 0.001))
            fraction = linear_fraction
            if voice.plan.envelope_curve == "equalPower":
                if end_volume >= start_volume:
                    fraction = math.sin(fraction * math.pi / 2.0)
                else:
                    fraction = 1.0 - math.cos(fraction * math.pi / 2.0)
            try:
                voice.handle.volume = start_volume + (end_volume - start_volume) * fraction
            except Exception:
                self._stop_voice(voice)
                self.timers.discard(update)
                voice.ramp_timer = None
                return None
            if linear_fraction >= 1.0:
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
            else:
                try:
                    voice.handle.volume = end_volume
                except Exception:
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
                if self.timer_api.is_registered(timer):
                    self.timer_api.unregister(timer)
            except Exception:
                pass
        self.timers.clear()
        for voice in tuple(self._all_voices()):
            self._stop_voice(voice)
        self.sounds.clear()
        for path in self.sound_paths.values():
            self.session.release_cache_path(path)
        self.sound_paths.clear()
