"""Compile supported declarative interactions into immutable runtime plans."""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

from .diagnostics import Diagnostic, Severity, Stage, ordered
from .model import GatePlan, GraphIndex, InteractionBundle, SelectionPlan, VoicePlan

VAO = "https://w3id.org/modavis/vao/ontology#"
AUDIO = "https://w3id.org/modavis/ontology/audio#"
P_CONFIGURATION = VAO + "configuration"
P_ACTIVATES = VAO + "activates"
P_TRIGGERED_BY = VAO + "triggeredBy"
P_USES_SAMPLE = VAO + "usesSample"
P_PARAMETERS = AUDIO + "usesPlaybackParameters"
K_PROTOCOL = VAO + "controlProtocol"
K_DOMAIN = VAO + "controlDomain"
K_TIMING = VAO + "timingPolicy"

# This is deliberately narrower than the historical schema.  A policy is only
# accepted here when the Blender adapter implements it exactly; otherwise the
# package stays inspectable but cannot acquire a misleading playable status.
SUPPORTED_PITCH_MODES = {"preserveRecordedPitch"}
SUPPORTED_CHANNEL_POLICIES = {"stereo-preserve"}
SUPPORTED_ENVELOPE_CURVES = {"linear", "equalPower"}
SUPPORTED_PARAMETER_STATUSES = {"reviewed", "accepted"}
MIN_GAIN_DB = -120.0
MAX_GAIN_DB = 24.0
MAX_ENVELOPE_SECONDS = 30.0


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _is_midi_value(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 127


def _only(edges: list, predicate: str):
    matches = [
        edge
        for edge in edges
        if edge.predicate == predicate and edge.status in {"accepted", "asserted"}
    ]
    return matches[0] if len(matches) == 1 else None


def compile_interactions(graph: GraphIndex) -> InteractionBundle:
    diagnostics: list[Diagnostic] = []

    def fail(code: str, message: str, identifier: str) -> None:
        diagnostics.append(
            Diagnostic(
                code=code,
                severity=Severity.ERROR,
                stage=Stage.INTERACTION,
                message=message,
                related_ids=(identifier,),
            )
        )

    interactions = [entity for entity in graph.entities.values() if entity.kind == "interaction"]
    selections: list[SelectionPlan] = []
    gates: list[GatePlan] = []
    internal_voices: list[Any] = []
    gates_by_id: dict[str, GatePlan] = {}
    configuration_ids: set[str] = set()
    gate_keys: set[int] = set()

    for interaction in interactions:
        protocol = interaction.properties.get(K_PROTOCOL, {})
        binding = protocol.get("binding") if hasattr(protocol, "get") else None
        edges = list(graph.outgoing.get(interaction.id, ()))
        if binding == "host-toggle":
            configuration = _only(edges, P_CONFIGURATION)
            timing = interaction.properties.get(K_TIMING, {})
            if configuration is None:
                fail(
                    "VAO-INT-001",
                    "selection must resolve exactly one configuration",
                    interaction.id,
                )
                continue
            if timing.get("selection") != "toggle" or timing.get("exclusivity") != "independent":
                fail(
                    "VAO-INT-002",
                    "only independent host-toggle selections are implemented; exclusive "
                    "selection requires an explicit, supported grouping policy",
                    interaction.id,
                )
                continue
            if configuration.object_id in configuration_ids:
                fail(
                    "VAO-INT-014",
                    "multiple host-toggle interactions resolve the same configuration",
                    interaction.id,
                )
                continue
            configuration_ids.add(configuration.object_id)
            selections.append(
                SelectionPlan(
                    interaction_id=interaction.id,
                    configuration_id=configuration.object_id,
                    label=interaction.label,
                    independent=True,
                    relation_ids=(configuration.id,),
                )
            )
        elif binding == "host-note-gate":
            domain = interaction.properties.get(K_DOMAIN, {})
            activation = _only(edges, P_ACTIVATES)
            key = domain.get("keyNumber") if hasattr(domain, "get") else None
            timing = interaction.properties.get(K_TIMING, {})
            if not isinstance(key, int) or not 0 <= key <= 127 or activation is None:
                fail(
                    "VAO-INT-003", "note gate needs one MIDI key and one component", interaction.id
                )
                continue
            if timing.get("release") != "on-gate-close":
                fail("VAO-INT-004", "unsupported note-gate release policy", interaction.id)
                continue
            if key in gate_keys:
                fail("VAO-INT-015", "MIDI key is bound by more than one host gate", interaction.id)
                continue
            gate_keys.add(key)
            plan = GatePlan(
                interaction_id=interaction.id,
                key_number=key,
                label=interaction.label,
                component_id=activation.object_id,
                relation_ids=(activation.id,),
            )
            gates.append(plan)
            gates_by_id[interaction.id] = plan
        elif binding == "internal-scoped-voice":
            internal_voices.append(interaction)
        else:
            fail("VAO-INT-005", f"unsupported interaction binding {binding!r}", interaction.id)

    voices: list[VoicePlan] = []
    velocity_ranges: dict[tuple[str, int], list[tuple[int, int]]] = {}
    for interaction in internal_voices:
        edges = list(graph.outgoing.get(interaction.id, ()))
        triggered = _only(edges, P_TRIGGERED_BY)
        configuration = _only(edges, P_CONFIGURATION)
        sample = _only(edges, P_USES_SAMPLE)
        component = _only(edges, P_ACTIVATES)
        parameters = _only(edges, P_PARAMETERS)
        required = [triggered, configuration, sample, component, parameters]
        if any(edge is None for edge in required):
            fail("VAO-INT-006", "voice relation set is incomplete or ambiguous", interaction.id)
            continue
        assert triggered and configuration and sample and component and parameters
        gate = gates_by_id.get(triggered.object_id)
        asset = graph.assets.get(sample.object_id)
        parameter = graph.entities.get(parameters.object_id)
        domain = interaction.properties.get(K_DOMAIN, {})
        if gate is None or asset is None or parameter is None:
            fail(
                "VAO-INT-007",
                "voice resolves an unknown gate, asset, or parameter set",
                interaction.id,
            )
            continue
        if parameter.kind != "parameterSet":
            fail(
                "VAO-INT-016",
                "voice playback parameters do not resolve a parameterSet",
                interaction.id,
            )
            continue
        if asset.media_type not in {"audio/wav", "audio/x-wav", "audio/wave"}:
            fail("VAO-INT-008", "voice sample is not a supported WAVE asset", interaction.id)
            continue
        if (
            domain.get("keyNumber") != gate.key_number
            or domain.get("configurationId") != configuration.object_id
        ):
            fail(
                "VAO-INT-009",
                "voice scope conflicts with its gate/configuration relations",
                interaction.id,
            )
            continue
        if configuration.object_id not in configuration_ids:
            fail(
                "VAO-INT-017",
                "voice configuration has no supported host-toggle selection",
                interaction.id,
            )
            continue
        props = parameter.properties
        envelope = props.get(AUDIO + "envelope", {})
        pitch_mode = props.get(AUDIO + "pitchTrackingMode", "")
        note_off = props.get(AUDIO + "noteOffPolicy", "")
        curve = envelope.get("curve") if isinstance(envelope, Mapping) else None
        if props.get(AUDIO + "status") not in SUPPORTED_PARAMETER_STATUSES:
            fail("VAO-INT-010", "playback parameters are not reviewed or accepted", interaction.id)
            continue
        if pitch_mode not in SUPPORTED_PITCH_MODES:
            fail(
                "VAO-INT-011",
                "unsupported pitch tracking mode; resampling requires an explicit reviewed "
                "source/target pitch ratio",
                interaction.id,
            )
            continue
        channel_policy = str(props.get(AUDIO + "channelPolicy", ""))
        if channel_policy not in SUPPORTED_CHANNEL_POLICIES:
            fail("VAO-INT-019", "unsupported audio channel policy", interaction.id)
            continue
        if note_off != "voice-scoped-fade" or curve not in SUPPORTED_ENVELOPE_CURVES:
            fail("VAO-INT-012", "unsupported note-off or envelope policy", interaction.id)
            continue
        numeric = {
            "gain": props.get(AUDIO + "gainDB"),
            "target frequency": props.get(AUDIO + "targetFrequencyHz"),
            "attack": envelope.get("attackSeconds") if isinstance(envelope, Mapping) else None,
            "sustain": envelope.get("sustainLevel") if isinstance(envelope, Mapping) else None,
            "release": envelope.get("releaseSeconds") if isinstance(envelope, Mapping) else None,
        }
        if not all(_is_number(value) for value in numeric.values()):
            fail(
                "VAO-INT-020",
                "playback gain, target frequency, and envelope values must be explicit numbers",
                interaction.id,
            )
            continue
        gain_db = float(numeric["gain"])
        target_frequency_hz = float(numeric["target frequency"])
        attack_seconds = float(numeric["attack"])
        sustain_level = float(numeric["sustain"])
        release_seconds = float(numeric["release"])
        root_key_number = props.get(AUDIO + "rootKeyNumber")
        minimum_key_number = props.get(AUDIO + "minimumKeyNumber")
        maximum_key_number = props.get(AUDIO + "maximumKeyNumber")
        minimum_velocity = props.get(AUDIO + "minimumVelocity")
        maximum_velocity = props.get(AUDIO + "maximumVelocity")
        midi_values = (
            root_key_number,
            minimum_key_number,
            maximum_key_number,
            minimum_velocity,
            maximum_velocity,
        )
        if not all(_is_midi_value(value) for value in midi_values):
            fail(
                "VAO-INT-023",
                "playback key and velocity bounds must be MIDI integers",
                interaction.id,
            )
            continue
        assert isinstance(root_key_number, int)
        assert isinstance(minimum_key_number, int)
        assert isinstance(maximum_key_number, int)
        assert isinstance(minimum_velocity, int)
        assert isinstance(maximum_velocity, int)
        if not (
            minimum_key_number <= root_key_number <= maximum_key_number
            and minimum_key_number <= gate.key_number <= maximum_key_number
            and minimum_velocity <= maximum_velocity
        ):
            fail(
                "VAO-INT-024",
                "playback key/velocity ranges are reversed or do not include the gate key",
                interaction.id,
            )
            continue
        unsupported_controls = {
            AUDIO + "roundRobinGroup",
            AUDIO + "roundRobinIndex",
            AUDIO + "selectionPriority",
        }
        if any(name in props for name in unsupported_controls):
            fail(
                "VAO-INT-025",
                "round-robin or priority voice selection is not implemented",
                interaction.id,
            )
            continue
        neutral_controls = {
            AUDIO + "normalizationGainDB": 0.0,
            AUDIO + "tuningOffsetCents": 0.0,
            AUDIO + "latencyCompensationFrames": 0,
        }
        if any(
            name in props and (not _is_number(props[name]) or float(props[name]) != float(neutral))
            for name, neutral in neutral_controls.items()
        ):
            fail(
                "VAO-INT-026",
                "non-neutral normalization, tuning, or latency controls are not implemented",
                interaction.id,
            )
            continue
        if not math.isfinite(gain_db) or not MIN_GAIN_DB <= gain_db <= MAX_GAIN_DB:
            fail(
                "VAO-INT-021", "playback gain is outside the implemented safe range", interaction.id
            )
            continue
        if not math.isfinite(target_frequency_hz) or target_frequency_hz <= 0.0:
            fail(
                "VAO-INT-027",
                "playback target frequency must be positive and finite",
                interaction.id,
            )
            continue
        if (
            not math.isfinite(attack_seconds)
            or not math.isfinite(sustain_level)
            or not math.isfinite(release_seconds)
            or not 0.0 <= attack_seconds <= MAX_ENVELOPE_SECONDS
            or not 0.0 <= sustain_level <= 1.0
            or not 0.0 <= release_seconds <= MAX_ENVELOPE_SECONDS
        ):
            fail(
                "VAO-INT-022",
                "attack, sustain, or release is outside the implemented safe range",
                interaction.id,
            )
            continue
        key = (configuration.object_id, gate.key_number)
        ranges = velocity_ranges.setdefault(key, [])
        if any(
            minimum_velocity <= existing_maximum and existing_minimum <= maximum_velocity
            for existing_minimum, existing_maximum in ranges
        ):
            fail(
                "VAO-INT-013",
                "configuration/key voices have overlapping velocity ranges",
                interaction.id,
            )
            continue
        ranges.append((minimum_velocity, maximum_velocity))
        relation_ids = tuple(sorted(edge.id for edge in required if edge is not None))
        voices.append(
            VoicePlan(
                interaction_id=interaction.id,
                gate_id=gate.interaction_id,
                key_number=gate.key_number,
                configuration_id=configuration.object_id,
                sample_asset_id=asset.id,
                sample_sha256=asset.sha256,
                component_id=component.object_id,
                parameter_set_id=parameter.id,
                root_key_number=root_key_number,
                minimum_key_number=minimum_key_number,
                maximum_key_number=maximum_key_number,
                minimum_velocity=minimum_velocity,
                maximum_velocity=maximum_velocity,
                target_frequency_hz=target_frequency_hz,
                gain_db=gain_db,
                pitch_mode=pitch_mode,
                attack_seconds=attack_seconds,
                sustain_level=sustain_level,
                release_seconds=release_seconds,
                envelope_curve=curve,
                channel_policy=channel_policy,
                relation_ids=relation_ids,
            )
        )

    diagnostics = list(ordered(diagnostics))
    return InteractionBundle(
        selections=tuple(sorted(selections, key=lambda item: (item.label, item.interaction_id))),
        gates=tuple(sorted(gates, key=lambda item: (item.key_number, item.interaction_id))),
        voices=tuple(
            sorted(
                voices,
                key=lambda item: (
                    item.key_number,
                    item.configuration_id,
                    item.minimum_velocity,
                    item.maximum_velocity,
                    item.interaction_id,
                ),
            )
        ),
        diagnostics=tuple(diagnostics),
        supported=not any(item.severity == Severity.ERROR for item in diagnostics),
    )
