"""Exercise AudioEngine policy atomically with a fake Blender audio device."""

from __future__ import annotations

import sys
from pathlib import Path
from types import MappingProxyType, SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from vao_blender.blender.audio_engine import AudioEngine
from vao_blender.core.model import AssetRecord, InteractionBundle, VoicePlan


class FakeHandle:
    def __init__(self) -> None:
        self.pitch = 0.0
        self.volume = -1.0
        self.stopped = False

    def stop(self) -> None:
        self.stopped = True


class SetupFailHandle(FakeHandle):
    def __setattr__(self, name, value):
        if name == "pitch" and value == 1.0:
            raise RuntimeError("injected handle setup failure")
        super().__setattr__(name, value)


class FakeDevice:
    def __init__(self, *, fail=False, fail_unlock=False, handle_type=FakeHandle) -> None:
        self.fail = fail
        self.fail_unlock = fail_unlock
        self.handle_type = handle_type
        self.handles: list[FakeHandle] = []
        self.locks = 0
        self.unlocks = 0

    def lock(self) -> None:
        self.locks += 1

    def unlock(self) -> None:
        self.unlocks += 1
        if self.fail_unlock:
            raise RuntimeError("injected unlock failure")

    def play(self, _sound):
        if self.fail:
            raise RuntimeError("injected play failure")
        handle = self.handle_type()
        self.handles.append(handle)
        return handle


class FakeTimers:
    def __init__(self, *, reject=False) -> None:
        self.reject = reject
        self.callbacks: set = set()

    def register(self, callback, *, first_interval=0.0):
        if self.reject:
            raise RuntimeError("injected timer failure")
        self.callbacks.add(callback)

    def is_registered(self, callback) -> bool:
        return callback in self.callbacks

    def unregister(self, callback) -> None:
        self.callbacks.discard(callback)


class FakeCache:
    root = Path("/verified/cache")

    def extract(self, _source, _asset, *, protect=False):
        assert protect
        return Path("/verified/sample.wav")


def voice(
    configuration: str,
    checksum: str,
    *,
    attack=0.0,
    sustain=1.0,
    release=0.0,
    curve="linear",
    minimum_velocity=1,
    maximum_velocity=127,
) -> VoicePlan:
    return VoicePlan(
        interaction_id=f"urn:test:voice:{configuration}",
        gate_id="urn:test:gate",
        key_number=60,
        configuration_id=configuration,
        sample_asset_id=f"urn:test:asset:{configuration}",
        sample_sha256=checksum,
        component_id="urn:test:component",
        parameter_set_id="urn:test:parameters",
        root_key_number=60,
        minimum_key_number=60,
        maximum_key_number=60,
        minimum_velocity=minimum_velocity,
        maximum_velocity=maximum_velocity,
        target_frequency_hz=261.625565,
        gain_db=0.0,
        pitch_mode="preserveRecordedPitch",
        attack_seconds=attack,
        sustain_level=sustain,
        release_seconds=release,
        envelope_curve=curve,
        channel_policy="stereo-preserve",
        relation_ids=(),
    )


def session_for(voices: tuple[VoicePlan, ...], *, supported=True):
    assets = {
        item.sample_asset_id: AssetRecord(
            item.sample_asset_id,
            f"payload/{index}.wav",
            "audio/wav",
            1,
            item.sample_sha256,
        )
        for index, item in enumerate(voices)
    }
    bundle = InteractionBundle((), (), voices, supported=supported)
    outcome = SimpleNamespace(
        interaction_plans=bundle,
        graph=SimpleNamespace(assets=MappingProxyType(assets)),
    )
    protected: list[Path] = []

    def release(path: Path) -> None:
        protected.remove(path)

    return SimpleNamespace(
        outcome=outcome,
        active_configurations={item.configuration_id for item in voices},
        cache=FakeCache(),
        source_path="source.vao",
        adopt_protected_cache_path=lambda path, _root: protected.append(path),
        release_cache_path=release,
        protected_cache_paths=protected,
    )


first = voice("a", "a" * 64)
device = FakeDevice()
first_session = session_for((first,))
engine = AudioEngine(
    first_session,
    max_polyphony=2,
    device=device,
    timer_api=FakeTimers(),
    sound_loader=lambda _path: object(),
)
assert engine.open_gate(first.gate_id, velocity=1) == 1
assert device.handles[0].volume == 1.0, "undeclared velocity-to-gain response was applied"
assert device.handles[0].pitch == 1.0
engine.close()
assert device.handles[0].stopped
assert device.locks == device.unlocks == 1
assert not first_session.protected_cache_paths

# Velocity selects declared layers but does not invent a velocity-to-gain curve.
lower = voice("lower", "1" * 64, minimum_velocity=1, maximum_velocity=63)
upper = voice("upper", "2" * 64, minimum_velocity=64, maximum_velocity=127)
device = FakeDevice()
engine = AudioEngine(
    session_for((lower, upper)),
    max_polyphony=2,
    device=device,
    timer_api=FakeTimers(),
    sound_loader=lambda _path: object(),
)
assert engine.open_gate(lower.gate_id, velocity=63) == 1
assert engine.by_gate[lower.gate_id][0].plan.configuration_id == "lower"
engine.close()

# Sustain level is part of the declared envelope and scales the held gain.
sustained = voice("sustain", "3" * 64, sustain=0.25)
device = FakeDevice()
engine = AudioEngine(
    session_for((sustained,)),
    device=device,
    timer_api=FakeTimers(),
    sound_loader=lambda _path: object(),
)
assert engine.open_gate(sustained.gate_id) == 1
assert device.handles[0].volume == 0.25
engine.close()

for invalid_velocity in (-1, 128, 1.5, True):
    engine = AudioEngine(
        session_for((first,)),
        device=FakeDevice(),
        timer_api=FakeTimers(),
        sound_loader=lambda _path: object(),
    )
    try:
        engine.open_gate(first.gate_id, invalid_velocity)
        raise AssertionError(f"invalid velocity {invalid_velocity!r} was accepted")
    except ValueError:
        pass
    engine.close()

# A gate is atomic: local polyphony never starts a subset of its declared voices.
second = voice("b", "b" * 64)
device = FakeDevice()
engine = AudioEngine(
    session_for((first, second)),
    max_polyphony=1,
    device=device,
    timer_api=FakeTimers(),
    sound_loader=lambda _path: object(),
)
try:
    engine.open_gate(first.gate_id)
    raise AssertionError("over-capacity gate was partially started")
except RuntimeError as exc:
    assert "No partial gate" in str(exc)
assert not device.handles

# Unsupported bundles remain non-executable even when invoked outside the panel.
engine = AudioEngine(
    session_for((first,), supported=False),
    device=FakeDevice(),
    timer_api=FakeTimers(),
    sound_loader=lambda _path: object(),
)
try:
    engine.open_gate(first.gate_id)
    raise AssertionError("unsupported bundle executed")
except RuntimeError as exc:
    assert "not fully supported" in str(exc)

# Failure paths balance the device lock and do not leave owned handles.
device = FakeDevice(fail=True)
engine = AudioEngine(
    session_for((first,)),
    device=device,
    timer_api=FakeTimers(),
    sound_loader=lambda _path: object(),
)
try:
    engine.open_gate(first.gate_id)
    raise AssertionError("injected device failure did not propagate")
except RuntimeError as exc:
    assert "injected play failure" in str(exc)
assert device.locks == device.unlocks == 1
assert not engine.by_gate

# An unlock failure after successful acquisition is an atomic gate failure too.
device = FakeDevice(fail_unlock=True)
engine = AudioEngine(
    session_for((first,)),
    device=device,
    timer_api=FakeTimers(),
    sound_loader=lambda _path: object(),
)
try:
    engine.open_gate(first.gate_id)
    raise AssertionError("injected unlock failure did not propagate")
except RuntimeError as exc:
    assert "unlock failure" in str(exc)
assert device.handles[0].stopped
assert device.locks == device.unlocks == 1
assert not engine.by_gate

# A handle obtained before a property/setup failure is still stopped.
device = FakeDevice(handle_type=SetupFailHandle)
engine = AudioEngine(
    session_for((first,)),
    device=device,
    timer_api=FakeTimers(),
    sound_loader=lambda _path: object(),
)
try:
    engine.open_gate(first.gate_id)
    raise AssertionError("injected handle setup failure did not propagate")
except RuntimeError as exc:
    assert "setup failure" in str(exc)
assert device.handles[0].stopped
assert device.locks == device.unlocks == 1
assert not engine.by_gate

# Decoder failures release cache protection immediately.
failing_session = session_for((first,))
engine = AudioEngine(
    failing_session,
    device=FakeDevice(),
    timer_api=FakeTimers(),
    sound_loader=lambda _path: (_ for _ in ()).throw(RuntimeError("decode failed")),
)
try:
    engine.open_gate(first.gate_id)
    raise AssertionError("injected decoder failure did not propagate")
except RuntimeError as exc:
    assert "decode failed" in str(exc)
assert not failing_session.protected_cache_paths

# If Blender refuses an attack timer, the voice reaches declared gain instead of
# remaining silently alive at zero volume.
attack_voice = voice("attack", "c" * 64, attack=0.25)
device = FakeDevice()
engine = AudioEngine(
    session_for((attack_voice,)),
    device=device,
    timer_api=FakeTimers(reject=True),
    sound_loader=lambda _path: object(),
)
assert engine.open_gate(attack_voice.gate_id) == 1
assert device.handles[0].volume == 1.0
engine.close()

# Equal-power release completion uses unshaped time, avoiding a cosine
# floating-point endpoint that would otherwise keep a silent handle forever.
release_voice = voice("release", "d" * 64, release=0.25, curve="equalPower")
clock = [0.0]
timers = FakeTimers()
device = FakeDevice()
engine = AudioEngine(
    session_for((release_voice,)),
    device=device,
    timer_api=timers,
    sound_loader=lambda _path: object(),
    clock=lambda: clock[0],
)
assert engine.open_gate(release_voice.gate_id) == 1
engine.close_gate(release_voice.gate_id)
clock[0] = 0.25
next(iter(timers.callbacks))()
assert device.handles[0].stopped
assert not engine.by_gate

print("VAO_AUDIO_ENGINE_POLICY_OK")
