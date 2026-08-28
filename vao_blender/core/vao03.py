"""VAO 0.3–0.5 record conversion and coordinate utilities.

Contract and carrier validation are intentionally delegated to the exact pinned
reference validator for the dispatched VAO version. This module only converts
their already validated shared logical-asset and visual-acoustic records.
"""

from __future__ import annotations

import math
from collections import defaultdict
from types import MappingProxyType
from typing import Any, Iterable, Mapping

from .model import (
    AcousticSceneRecord,
    CoordinateFrameRecord,
    EntityNode,
    GeometryBindingRecord,
    GraphIndex,
    ImpulseResponseRecord,
    LogicalAssetRecord,
    MeasurementRecord,
    PoseRecord,
    RealizationRecord,
    RelationEdge,
    ResponseSetRecord,
    freeze,
)

SUPPORTED_GLTF_MEDIA = {"model/gltf-binary"}
IDENTITY_4X4 = (
    1.0,
    0.0,
    0.0,
    0.0,
    0.0,
    1.0,
    0.0,
    0.0,
    0.0,
    0.0,
    1.0,
    0.0,
    0.0,
    0.0,
    0.0,
    1.0,
)


def matrix_multiply(left: Iterable[float], right: Iterable[float]) -> tuple[float, ...]:
    """Multiply two row-major homogeneous 4x4 matrices."""
    a = tuple(float(value) for value in left)
    b = tuple(float(value) for value in right)
    if len(a) != 16 or len(b) != 16:
        raise ValueError("VAO coordinate transforms must contain 16 row-major values")
    return tuple(
        sum(a[row * 4 + item] * b[item * 4 + column] for item in range(4))
        for row in range(4)
        for column in range(4)
    )


def matrix_inverse(values: Iterable[float]) -> tuple[float, ...]:
    """Invert a finite row-major 4x4 matrix with guarded pivoting."""
    source = tuple(float(value) for value in values)
    if len(source) != 16 or not all(math.isfinite(value) for value in source):
        raise ValueError("VAO coordinate transform is not a finite 4x4 matrix")
    augmented = [
        list(source[row * 4 : row * 4 + 4]) + [1.0 if row == column else 0.0 for column in range(4)]
        for row in range(4)
    ]
    for column in range(4):
        pivot = max(range(column, 4), key=lambda row: abs(augmented[row][column]))
        if abs(augmented[pivot][column]) < 1e-12:
            raise ValueError("VAO coordinate transform is not invertible")
        augmented[column], augmented[pivot] = augmented[pivot], augmented[column]
        scale = augmented[column][column]
        augmented[column] = [value / scale for value in augmented[column]]
        for row in range(4):
            if row == column:
                continue
            factor = augmented[row][column]
            augmented[row] = [
                augmented[row][item] - factor * augmented[column][item] for item in range(8)
            ]
    return tuple(augmented[row][column] for row in range(4) for column in range(4, 8))


def transform_point(matrix: Iterable[float], point: Iterable[float]) -> tuple[float, float, float]:
    """Apply a row-major homogeneous transform to one Cartesian position."""
    values = tuple(float(value) for value in matrix)
    coordinates = tuple(float(value) for value in point)
    if len(values) != 16 or len(coordinates) != 3:
        raise ValueError("a 4x4 transform and a three-dimensional point are required")
    vector = coordinates + (1.0,)
    result = tuple(
        sum(values[row * 4 + column] * vector[column] for column in range(4)) for row in range(4)
    )
    if abs(result[3]) < 1e-12:
        raise ValueError("coordinate transform produced a point at infinity")
    return (result[0] / result[3], result[1] / result[3], result[2] / result[3])


def frame_to_root(
    frames: Mapping[str, CoordinateFrameRecord], frame_id: str
) -> tuple[str, tuple[float, ...]]:
    """Evaluate a declared child-to-parent graph into its root frame."""
    current = frame_id
    transform = IDENTITY_4X4
    seen: set[str] = set()
    while True:
        frame = frames.get(current)
        if frame is None:
            raise ValueError(f"unknown VAO coordinate frame {current!r}")
        if current in seen:
            raise ValueError(f"cycle in VAO coordinate-frame graph at {current!r}")
        seen.add(current)
        if not frame.parent_frame_id:
            return current, transform
        transform = matrix_multiply(frame.transform_to_parent, transform)
        current = frame.parent_frame_id


def quaternion_matrix_xyzw(values: Iterable[float]) -> tuple[float, ...]:
    """Return a normalized active-rotation matrix for an XYZW quaternion."""
    items = tuple(float(value) for value in values)
    if len(items) != 4:
        raise ValueError("VAO pose orientation must contain four XYZW values")
    x, y, z, w = items
    if not all(math.isfinite(value) for value in items):
        raise ValueError("VAO pose orientation contains a non-finite value")
    norm = math.sqrt(x * x + y * y + z * z + w * w)
    if norm < 1e-12:
        raise ValueError("VAO pose orientation has zero magnitude")
    x, y, z, w = (value / norm for value in (x, y, z, w))
    return (
        1.0 - 2.0 * (y * y + z * z),
        2.0 * (x * y - z * w),
        2.0 * (x * z + y * w),
        0.0,
        2.0 * (x * y + z * w),
        1.0 - 2.0 * (x * x + z * z),
        2.0 * (y * z - x * w),
        0.0,
        2.0 * (x * z - y * w),
        2.0 * (y * z + x * w),
        1.0 - 2.0 * (x * x + y * y),
        0.0,
        0.0,
        0.0,
        0.0,
        1.0,
    )


def pose_to_root(
    frames: Mapping[str, CoordinateFrameRecord], pose: PoseRecord
) -> tuple[str, tuple[float, ...]]:
    """Compose a declared pose (translation and XYZW orientation) into its root."""
    root_id, frame_transform = frame_to_root(frames, pose.frame_id)
    if len(pose.position) not in {2, 3}:
        raise ValueError("VAO pose position must contain two or three values")
    position = pose.position if len(pose.position) == 3 else pose.position + (0.0,)
    translation = (
        1.0,
        0.0,
        0.0,
        float(position[0]),
        0.0,
        1.0,
        0.0,
        float(position[1]),
        0.0,
        0.0,
        1.0,
        float(position[2]),
        0.0,
        0.0,
        0.0,
        1.0,
    )
    if pose.orientation_xyzw:
        orientation = quaternion_matrix_xyzw(pose.orientation_xyzw)
    elif pose.orientation_radians is not None:
        cosine = math.cos(pose.orientation_radians)
        sine = math.sin(pose.orientation_radians)
        orientation = (
            cosine,
            -sine,
            0.0,
            0.0,
            sine,
            cosine,
            0.0,
            0.0,
            0.0,
            0.0,
            1.0,
            0.0,
            0.0,
            0.0,
            0.0,
            1.0,
        )
    else:
        orientation = IDENTITY_4X4
    return root_id, matrix_multiply(frame_transform, matrix_multiply(translation, orientation))


def build_graph_03(manifest: dict[str, Any]) -> GraphIndex:
    """Build the shared entity/relation graph without conflating 0.3 assets."""
    entities: dict[str, EntityNode] = {}
    for raw in sorted(manifest.get("entities", []), key=lambda item: item["id"]):
        entities[raw["id"]] = EntityNode(
            raw["id"],
            raw["kind"],
            tuple(raw.get("types", [])),
            freeze(raw.get("labels", {})),
            freeze(raw.get("properties", {})),
        )
    relations: dict[str, RelationEdge] = {}
    outgoing: dict[str, list[RelationEdge]] = defaultdict(list)
    incoming: dict[str, list[RelationEdge]] = defaultdict(list)
    for raw in sorted(manifest.get("relations", []), key=lambda item: item["id"]):
        edge = RelationEdge(
            raw["id"],
            raw["subjectId"],
            raw["predicate"],
            raw.get("objectId", ""),
            freeze(raw.get("literal")),
            raw.get("status", ""),
            freeze(raw.get("properties", {})),
        )
        relations[edge.id] = edge
        outgoing[edge.subject_id].append(edge)
        if edge.object_id:
            incoming[edge.object_id].append(edge)

    def freeze_edges(index: dict[str, list[RelationEdge]]) -> MappingProxyType:
        return MappingProxyType(
            {
                key: tuple(sorted(value, key=lambda edge: (edge.predicate, edge.id)))
                for key, value in sorted(index.items())
            }
        )

    return GraphIndex(
        MappingProxyType(entities),
        MappingProxyType({}),
        MappingProxyType(relations),
        freeze_edges(outgoing),
        freeze_edges(incoming),
    )


def build_records_03(
    manifest: dict[str, Any], embedded_paths: Mapping[str, str]
) -> tuple[
    Mapping[str, LogicalAssetRecord],
    Mapping[str, RealizationRecord],
    AcousticSceneRecord | None,
]:
    logical_assets = {
        raw["id"]: LogicalAssetRecord(
            raw["id"],
            freeze(raw.get("labels", {})),
            tuple(raw.get("roles", [])),
            tuple(raw.get("aboutEntityIds", [])),
            tuple(raw.get("realizationIds", [])),
        )
        for raw in sorted(manifest.get("logicalAssets", []), key=lambda item: item["id"])
    }
    realizations = {
        raw["id"]: RealizationRecord(
            raw["id"],
            raw["assetId"],
            raw["mediaType"],
            int(raw["byteSize"]),
            raw["sha256"],
            raw["representationStatus"],
            raw["qualityTier"],
            tuple(raw.get("rightsIds", [])),
            tuple(raw.get("provenanceIds", [])),
            freeze(raw.get("technicalMetadata", {})),
            embedded_paths.get(raw["id"], ""),
        )
        for raw in sorted(manifest.get("realizations", []), key=lambda item: item["id"])
    }
    acoustics = manifest.get("acoustics")
    if not isinstance(acoustics, dict):
        return MappingProxyType(logical_assets), MappingProxyType(realizations), None

    frames = {
        raw["id"]: CoordinateFrameRecord(
            raw["id"],
            int(raw["dimension"]),
            raw["unit"],
            raw["handedness"],
            raw["upAxis"],
            raw["forwardAxis"],
            raw.get("parentFrameId", ""),
            tuple(float(value) for value in raw.get("transformToParent", [])),
        )
        for raw in acoustics.get("coordinateFrames", [])
    }
    poses = {
        raw["id"]: PoseRecord(
            raw["id"],
            raw["subjectId"],
            raw["frameId"],
            tuple(float(value) for value in raw["position"]),
            tuple(float(value) for value in raw.get("orientationXYZW", [])),
            raw.get("localFrameId", ""),
            (float(raw["orientationRadians"]) if "orientationRadians" in raw else None),
        )
        for raw in acoustics.get("poses", [])
    }
    measurements = {
        raw["id"]: MeasurementRecord(
            raw["id"],
            raw["sourceId"],
            raw["receiverId"],
            raw["sourcePoseId"],
            raw["receiverPoseId"],
            raw.get("spaceId", ""),
        )
        for raw in acoustics.get("measurements", [])
    }
    geometry_bindings = {
        raw["id"]: GeometryBindingRecord(
            raw["id"], raw["subjectId"], raw["logicalAssetId"], raw["role"]
        )
        for raw in acoustics.get("geometryBindings", [])
    }
    response_sets = {
        raw["id"]: ResponseSetRecord(
            raw["id"],
            raw["responseEntityId"],
            raw["responseKind"],
            raw["logicalAssetId"],
            raw["representationStatus"],
            tuple(raw.get("measurementIds", [])),
            raw["generatedById"],
            tuple(raw.get("qualityFlags", [])),
        )
        for raw in acoustics.get("responseSets", [])
    }
    impulse_responses: list[ImpulseResponseRecord] = []
    for realization in realizations.values():
        metadata = realization.technical_metadata
        impulse = metadata.get("impulseResponse")
        if metadata.get("kind") != "audio" or not hasattr(impulse, "get"):
            continue
        mappings = tuple(impulse.get("measurementMappings", ()))
        impulse_responses.append(
            ImpulseResponseRecord(
                realization.id,
                realization.logical_asset_id,
                impulse.get("responseSetId", ""),
                realization.media_type,
                impulse.get("encoding", ""),
                float(metadata.get("sampleRate", 0)),
                int(impulse.get("sampleCount", 0)),
                int(metadata.get("channelCount", 0)),
                tuple(item.get("measurementId", "") for item in mappings),
                tuple(int(index) for item in mappings for index in item.get("channelIndices", ())),
                realization.representation_status,
                realization.byte_size,
                realization.sha256,
                realization.provenance_ids,
                realization.embedded_path,
            )
        )

    selected_realization_id, selected_binding_id = choose_runtime_visual(
        logical_assets, realizations, geometry_bindings
    )
    roots: set[str] = set()
    for measurement in measurements.values():
        for pose_id in (measurement.source_pose_id, measurement.receiver_pose_id):
            pose = poses[pose_id]
            roots.add(frame_to_root(frames, pose.frame_id)[0])
    selected_visual = realizations.get(selected_realization_id)
    if selected_visual is not None:
        visual_frame_id = str(selected_visual.technical_metadata.get("coordinateFrameId", ""))
        if visual_frame_id:
            roots.add(frame_to_root(frames, visual_frame_id)[0])
    common_root = next(iter(roots)) if len(roots) == 1 else ""
    scene = AcousticSceneRecord(
        MappingProxyType(dict(sorted(frames.items()))),
        MappingProxyType(dict(sorted(poses.items()))),
        MappingProxyType(dict(sorted(measurements.items()))),
        MappingProxyType(dict(sorted(geometry_bindings.items()))),
        MappingProxyType(dict(sorted(response_sets.items()))),
        tuple(sorted(impulse_responses, key=lambda item: item.realization_id)),
        len(acoustics.get("audioScenes", [])),
        len(acoustics.get("renderConfigurations", [])),
        selected_realization_id,
        selected_binding_id,
        common_root,
    )
    return MappingProxyType(logical_assets), MappingProxyType(realizations), scene


def choose_runtime_visual(
    logical_assets: Mapping[str, LogicalAssetRecord],
    realizations: Mapping[str, RealizationRecord],
    geometry_bindings: Mapping[str, GeometryBindingRecord],
) -> tuple[str, str]:
    """Resolve runtime visual geometry exclusively through stable VAO identifiers."""
    quality_rank = {
        "production-spatial": 4,
        "bootstrap": 3,
        "preservation": 2,
        "preview": 1,
    }
    candidates: list[tuple[int, str, str]] = []
    for binding in geometry_bindings.values():
        if binding.role != "runtime-visual":
            continue
        logical = logical_assets.get(binding.logical_asset_id)
        if logical is None:
            continue
        for realization_id in logical.realization_ids:
            realization = realizations.get(realization_id)
            if (
                realization is not None
                and realization.media_type in SUPPORTED_GLTF_MEDIA
                and realization.technical_metadata.get("kind") == "geometry"
                and realization.embedded_path
            ):
                candidates.append(
                    (
                        quality_rank.get(realization.quality_tier, 0),
                        realization.id,
                        binding.id,
                    )
                )
    if not candidates:
        return "", ""
    _rank, realization_id, binding_id = max(candidates, key=lambda item: (item[0], item[1]))
    return realization_id, binding_id
