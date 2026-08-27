"""Compile supported declarative interactions into immutable runtime plans."""

from __future__ import annotations

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
            if timing.get("selection") != "toggle" or timing.get("exclusivity") not in {
                "independent",
                "exclusive",
            }:
                fail("VAO-INT-002", "unsupported selection/timing policy", interaction.id)
                continue
            selections.append(
                SelectionPlan(
                    interaction_id=interaction.id,
                    configuration_id=configuration.object_id,
                    label=interaction.label,
                    independent=timing.get("exclusivity") == "independent",
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
    matrix: set[tuple[str, int]] = set()
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
        props = parameter.properties
        envelope = props.get(AUDIO + "envelope", {})
        pitch_mode = props.get(AUDIO + "pitchTrackingMode", "")
        note_off = props.get(AUDIO + "noteOffPolicy", "")
        curve = envelope.get("curve") if hasattr(envelope, "get") else None
        if props.get(AUDIO + "status") != "reviewed":
            fail("VAO-INT-010", "playback parameters are not reviewed", interaction.id)
            continue
        if pitch_mode not in {"preserveRecordedPitch", "resample"}:
            fail("VAO-INT-011", "unsupported pitch tracking mode", interaction.id)
            continue
        if note_off != "voice-scoped-fade" or curve not in {"linear", "equal-power"}:
            fail("VAO-INT-012", "unsupported note-off or envelope policy", interaction.id)
            continue
        key = (configuration.object_id, gate.key_number)
        if key in matrix:
            fail("VAO-INT-013", "ambiguous duplicate configuration/key voice", interaction.id)
            continue
        matrix.add(key)
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
                gain_db=float(props.get(AUDIO + "gainDB", 0.0)),
                pitch_mode=pitch_mode,
                attack_seconds=float(envelope.get("attackSeconds", 0.0)),
                release_seconds=float(envelope.get("releaseSeconds", 0.0)),
                envelope_curve=curve,
                channel_policy=str(props.get(AUDIO + "channelPolicy", "stereo-preserve")),
                relation_ids=relation_ids,
            )
        )

    diagnostics = list(ordered(diagnostics))
    return InteractionBundle(
        selections=tuple(sorted(selections, key=lambda item: (item.label, item.interaction_id))),
        gates=tuple(sorted(gates, key=lambda item: (item.key_number, item.interaction_id))),
        voices=tuple(sorted(voices, key=lambda item: (item.key_number, item.configuration_id))),
        diagnostics=tuple(diagnostics),
        supported=not any(item.severity == Severity.ERROR for item in diagnostics),
    )
