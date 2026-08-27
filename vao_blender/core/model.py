"""Immutable boundary records for validated VAO packages and runtime plans."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import Any, Mapping

from .diagnostics import Diagnostic


class OutcomeState(StrEnum):
    VALID = "valid"
    INVALID = "invalid"
    RESOURCE_LIMITED = "resource-limited"
    UNSUPPORTED = "unsupported"
    BLOCKED_RIGHTS = "blocked-rights"
    CANCELLED = "cancelled"


def freeze(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({key: freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(freeze(item) for item in value)
    return value


@dataclass(frozen=True, slots=True)
class AssetRecord:
    id: str
    path: str
    media_type: str
    byte_size: int
    sha256: str
    roles: tuple[str, ...] = ()
    about_entity_ids: tuple[str, ...] = ()
    original_filename: str = ""
    representation_status: str = ""
    properties: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))


@dataclass(frozen=True, slots=True)
class LogicalAssetRecord:
    """Carrier-independent VAO 0.3 logical content identity."""

    id: str
    labels: Mapping[str, str]
    roles: tuple[str, ...]
    about_entity_ids: tuple[str, ...]
    realization_ids: tuple[str, ...]

    @property
    def label(self) -> str:
        return self.labels.get("en") or next(iter(self.labels.values()), self.id)


@dataclass(frozen=True, slots=True)
class RealizationRecord:
    """Exact byte realization, optionally mapped into the current carrier."""

    id: str
    logical_asset_id: str
    media_type: str
    byte_size: int
    sha256: str
    representation_status: str
    quality_tier: str
    rights_ids: tuple[str, ...]
    provenance_ids: tuple[str, ...]
    technical_metadata: Mapping[str, Any]
    embedded_path: str = ""

    @property
    def path(self) -> str:
        return self.embedded_path

    @property
    def original_filename(self) -> str:
        return self.embedded_path.rsplit("/", 1)[-1] if self.embedded_path else ""


@dataclass(frozen=True, slots=True)
class CarrierRecord:
    release_id: str
    manifest_sha256: str
    manifest_byte_size: int
    mode: str
    embedded_realizations: Mapping[str, str]
    complete_group_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CoordinateFrameRecord:
    id: str
    dimension: int
    unit: str
    handedness: str
    up_axis: str
    forward_axis: str
    parent_frame_id: str = ""
    transform_to_parent: tuple[float, ...] = ()


@dataclass(frozen=True, slots=True)
class PoseRecord:
    id: str
    subject_id: str
    frame_id: str
    position: tuple[float, ...]
    orientation_xyzw: tuple[float, ...] = ()
    local_frame_id: str = ""
    orientation_radians: float | None = None


@dataclass(frozen=True, slots=True)
class MeasurementRecord:
    id: str
    source_id: str
    receiver_id: str
    source_pose_id: str
    receiver_pose_id: str
    space_id: str = ""


@dataclass(frozen=True, slots=True)
class GeometryBindingRecord:
    id: str
    subject_id: str
    logical_asset_id: str
    role: str


@dataclass(frozen=True, slots=True)
class ResponseSetRecord:
    id: str
    response_entity_id: str
    response_kind: str
    logical_asset_id: str
    representation_status: str
    measurement_ids: tuple[str, ...]
    generated_by_id: str
    quality_flags: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ImpulseResponseRecord:
    realization_id: str
    logical_asset_id: str
    response_set_id: str
    media_type: str
    encoding: str
    sample_rate: float
    sample_count: int
    channel_count: int
    measurement_ids: tuple[str, ...]
    channel_indices: tuple[int, ...]
    representation_status: str
    byte_size: int
    sha256: str
    provenance_ids: tuple[str, ...]
    embedded_path: str = ""


@dataclass(frozen=True, slots=True)
class AcousticSceneRecord:
    coordinate_frames: Mapping[str, CoordinateFrameRecord]
    poses: Mapping[str, PoseRecord]
    measurements: Mapping[str, MeasurementRecord]
    geometry_bindings: Mapping[str, GeometryBindingRecord]
    response_sets: Mapping[str, ResponseSetRecord]
    impulse_responses: tuple[ImpulseResponseRecord, ...]
    audio_scene_count: int
    render_configuration_count: int
    runtime_visual_realization_id: str = ""
    runtime_visual_binding_id: str = ""
    common_frame_root_id: str = ""


@dataclass(frozen=True, slots=True)
class EntityNode:
    id: str
    kind: str
    types: tuple[str, ...]
    labels: Mapping[str, str]
    properties: Mapping[str, Any]

    @property
    def label(self) -> str:
        return self.labels.get("en") or next(iter(self.labels.values()), self.id)


@dataclass(frozen=True, slots=True)
class RelationEdge:
    id: str
    subject_id: str
    predicate: str
    object_id: str = ""
    literal: Any = None
    status: str = ""
    properties: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))


@dataclass(frozen=True, slots=True)
class GraphIndex:
    entities: Mapping[str, EntityNode]
    assets: Mapping[str, AssetRecord]
    relations: Mapping[str, RelationEdge]
    outgoing: Mapping[str, tuple[RelationEdge, ...]]
    incoming: Mapping[str, tuple[RelationEdge, ...]]


@dataclass(frozen=True, slots=True)
class CapabilityResult:
    capability: str
    supported: bool
    reason: str = ""


@dataclass(frozen=True, slots=True)
class VerificationRecord:
    asset_id: str
    byte_size: int
    sha256: str


@dataclass(frozen=True, slots=True)
class ValidationOutcome:
    state: OutcomeState
    source_path: str
    archive_sha256: str = ""
    manifest_sha256: str = ""
    manifest: Mapping[str, Any] | None = None
    graph: GraphIndex | None = None
    diagnostics: tuple[Diagnostic, ...] = ()
    verified_assets: Mapping[str, VerificationRecord] = field(
        default_factory=lambda: MappingProxyType({})
    )
    capabilities: tuple[CapabilityResult, ...] = ()
    interaction_plans: "InteractionBundle | None" = None
    verified_payload_bytes: int = 0
    contract_line: str = "0.2.2"
    contract_sha256: str = ""
    carrier: CarrierRecord | None = None
    logical_assets: Mapping[str, LogicalAssetRecord] = field(
        default_factory=lambda: MappingProxyType({})
    )
    realizations: Mapping[str, RealizationRecord] = field(
        default_factory=lambda: MappingProxyType({})
    )
    acoustic_scene: AcousticSceneRecord | None = None
    rights_acknowledgement_required: bool = False

    @property
    def is_valid(self) -> bool:
        return self.state in {
            OutcomeState.VALID,
            OutcomeState.UNSUPPORTED,
            OutcomeState.BLOCKED_RIGHTS,
        }

    def report(self, *, redact_paths: bool = True) -> dict[str, Any]:
        source = self.source_path
        if redact_paths and source:
            from pathlib import Path

            source = Path(source).name
        manifest = self.manifest or {}
        return {
            "reader": "VAO-Blender/0.3.0",
            "contract": {
                "line": self.contract_line,
                "releaseBundleSHA256": self.contract_sha256
                or ("76b55f33b09c94ad90aac79e8a599d007841e2c11288664f9c67987b4e68f328"),
                "status": (
                    "published-standard"
                    if self.contract_line == "0.4.0"
                    else (
                        "implemented-editor-draft"
                        if self.contract_line == "0.3.2"
                        else "private-development-release-candidate"
                    )
                ),
            },
            "state": self.state.value,
            "source": source,
            "archiveSHA256": self.archive_sha256,
            "manifestSHA256": self.manifest_sha256,
            "packageId": manifest.get("id", ""),
            "revision": (
                manifest.get("release", {}).get("revision")
                if manifest.get("release") and hasattr(manifest.get("release"), "get")
                else manifest.get("revision")
            ),
            "formatVersion": manifest.get("formatVersion", ""),
            "verifiedAssets": len(self.verified_assets),
            "verifiedPayloadBytes": self.verified_payload_bytes,
            "rightsAcknowledgementRequired": self.rights_acknowledgement_required,
            "graph": {
                "entities": len(self.graph.entities) if self.graph else 0,
                "relations": len(self.graph.relations) if self.graph else 0,
                "assets": len(self.graph.assets) if self.graph else 0,
            },
            "runtime": self.interaction_plans.summary() if self.interaction_plans else {},
            "carrier": {
                "mode": self.carrier.mode if self.carrier else "",
                "embeddedRealizations": (
                    len(self.carrier.embedded_realizations) if self.carrier else 0
                ),
            },
            "visualAcousticScene": {
                "logicalAssets": len(self.logical_assets),
                "realizations": len(self.realizations),
                "coordinateFrames": (
                    len(self.acoustic_scene.coordinate_frames) if self.acoustic_scene else 0
                ),
                "poses": len(self.acoustic_scene.poses) if self.acoustic_scene else 0,
                "measurements": (
                    len(self.acoustic_scene.measurements) if self.acoustic_scene else 0
                ),
                "geometryRealizations": sum(
                    1
                    for item in self.realizations.values()
                    if item.technical_metadata.get("kind") == "geometry"
                ),
                "impulseResponses": (
                    len(self.acoustic_scene.impulse_responses) if self.acoustic_scene else 0
                ),
                "selectedRuntimeVisualRealizationId": (
                    self.acoustic_scene.runtime_visual_realization_id if self.acoustic_scene else ""
                ),
                "support": "metadata-only; no RIR playback, convolution, or simulation",
            },
            "capabilities": [asdict(item) for item in self.capabilities],
            "diagnostics": [item.to_dict() for item in self.diagnostics],
        }


@dataclass(frozen=True, slots=True)
class SelectionPlan:
    interaction_id: str
    configuration_id: str
    label: str
    independent: bool
    relation_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class GatePlan:
    interaction_id: str
    key_number: int
    label: str
    component_id: str
    relation_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class VoicePlan:
    interaction_id: str
    gate_id: str
    key_number: int
    configuration_id: str
    sample_asset_id: str
    sample_sha256: str
    component_id: str
    parameter_set_id: str
    gain_db: float
    pitch_mode: str
    attack_seconds: float
    release_seconds: float
    envelope_curve: str
    channel_policy: str
    relation_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class InteractionBundle:
    selections: tuple[SelectionPlan, ...]
    gates: tuple[GatePlan, ...]
    voices: tuple[VoicePlan, ...]
    diagnostics: tuple[Diagnostic, ...] = ()
    supported: bool = True

    def summary(self) -> dict[str, Any]:
        return {
            "supported": self.supported,
            "selections": len(self.selections),
            "gates": len(self.gates),
            "voices": len(self.voices),
            "keys": [item.key_number for item in self.gates],
        }
