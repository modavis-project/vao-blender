#!/usr/bin/env python3
"""VAO 0.3 reference validator, carrier writer, receipt writer, and 0.2 migrator.

The module deliberately uses only the Python standard library. Repository
network access is adapter policy and is tested separately against Zenodo
Sandbox; this validator never follows package-supplied network locations.
"""

from __future__ import annotations

import argparse
from decimal import Decimal
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import sys
import unicodedata
import uuid
import zipfile
from datetime import datetime, timezone
from typing import Any, BinaryIO, Callable, Iterable

import vaom as vao02
import vao_resources


FORMAT_VERSION = "0.3.3"
MIMETYPE = "application/vnd.modavis.vao+zip"
MANIFEST_NAME = "vao-manifest.json"
CARRIER_NAME = "META-INF/vao-carrier.json"
SCHEMA_URI = "https://w3id.org/modavis/vao/0.3/schema/manifest.json"
CONTEXT_URI = "https://w3id.org/modavis/vao/0.3/context.jsonld"
CORE_PROFILE = "https://w3id.org/modavis/vao/profile/core/0.3"
DYNAMIC_PROFILE = "https://w3id.org/modavis/vao/profile/dynamic-delivery/0.3"
ZENODO_PROFILE = "https://w3id.org/modavis/vao/profile/repository/zenodo/0.3"
SPATIAL_PROFILE = "https://w3id.org/modavis/vao/profile/spatial/0.3"
ACOUSTICS_PROFILE = "https://w3id.org/modavis/vao/profile/acoustics/0.3"
PLAYABLE_PROFILE = "https://w3id.org/modavis/vao/profile/playable/0.3"
PROFILE_BASE = "https://w3id.org/modavis/vao/profile/"
CAPABILITY_BASE = "https://w3id.org/modavis/vao/vocab/capability/"
SEMANTIC_BUILDING_MODEL = CAPABILITY_BASE + "semantic-building-model"
MEASURED_IMPULSE_RESPONSE = CAPABILITY_BASE + "measured-impulse-response"
SIMULATED_IMPULSE_RESPONSE = CAPABILITY_BASE + "simulated-impulse-response"
POSITION_REGISTERED_SCENE = CAPABILITY_BASE + "position-registered-acoustic-scene"
VISUAL_ACOUSTIC_SCENE = CAPABILITY_BASE + "visual-acoustic-scene"
SPATIAL_RESPONSE_FIELD = CAPABILITY_BASE + "spatial-response-field"
SPATIAL_AUDIO_SCENE = CAPABILITY_BASE + "spatial-audio-scene"
ACOUSTIC_CAPABILITIES = {
    SEMANTIC_BUILDING_MODEL,
    MEASURED_IMPULSE_RESPONSE,
    SIMULATED_IMPULSE_RESPONSE,
    POSITION_REGISTERED_SCENE,
    VISUAL_ACOUSTIC_SCENE,
    SPATIAL_RESPONSE_FIELD,
    SPATIAL_AUDIO_SCENE,
    *(
        CAPABILITY_BASE + name
        for name in (
            "source-directivity",
            "room-acoustic-metrics",
            "building-acoustic-performance",
            "tracked-listener-convolution",
            "tracked-sources",
            "geometry-acoustic-rendering",
            "hybrid-acoustic-rendering",
            "learned-acoustic-field",
        )
    ),
}
INTERACTION = CAPABILITY_BASE + "interaction"
PLAYABLE_INTERACTION = CAPABILITY_BASE + "playable-interaction"
SAMPLED_INSTRUMENT_PLAYBACK = CAPABILITY_BASE + "sampled-instrument-playback"
SAMPLE_LOOPING = CAPABILITY_BASE + "sample-looping"
TUNING_MAP = CAPABILITY_BASE + "tuning-map"
MULTI_PERSPECTIVE_SAMPLING = CAPABILITY_BASE + "multi-perspective-sampling"
RECORDED_RELEASE = CAPABILITY_BASE + "recorded-release"
SOURCE_SAMPLER_SEMANTICS = CAPABILITY_BASE + "source-sampler-semantics"
STATEFUL_INTERACTION = CAPABILITY_BASE + "stateful-interaction"
CONDITIONAL_ROUTING = CAPABILITY_BASE + "conditional-routing"
COMPOSITE_ACTUATION = CAPABILITY_BASE + "composite-actuation"
TIMED_PROCESS = CAPABILITY_BASE + "timed-process"
ACTUATOR_TRANSFER = CAPABILITY_BASE + "actuator-transfer"
CAPTURE_EVENT_ALIGNMENT = CAPABILITY_BASE + "capture-event-alignment"
COMPLEX_INTERACTION_CAPABILITIES = {
    STATEFUL_INTERACTION,
    CONDITIONAL_ROUTING,
    COMPOSITE_ACTUATION,
    TIMED_PROCESS,
    ACTUATOR_TRANSFER,
    CAPTURE_EVENT_ALIGNMENT,
}
PLAYABLE_CAPABILITIES = {
    INTERACTION,
    PLAYABLE_INTERACTION,
    SAMPLED_INSTRUMENT_PLAYBACK,
    SAMPLE_LOOPING,
    TUNING_MAP,
    MULTI_PERSPECTIVE_SAMPLING,
    RECORDED_RELEASE,
    SOURCE_SAMPLER_SEMANTICS,
    *COMPLEX_INTERACTION_CAPABILITIES,
}
SCHEMA_DIR = vao_resources.schema_directory()
MANIFEST_SCHEMA = SCHEMA_DIR / "vao-manifest-0.3.schema.json"
CARRIER_SCHEMA = SCHEMA_DIR / "vao-carrier-0.3.schema.json"
RELEASE_SCHEMA = SCHEMA_DIR / "vao-release-0.3.schema.json"
PACK_SCHEMA = SCHEMA_DIR / "vao-pack-manifest-0.3.schema.json"
RECEIPT_SCHEMA = SCHEMA_DIR / "vao-materialization-receipt-0.3.schema.json"
ZENODO_METADATA_SCHEMA = SCHEMA_DIR / "vao-zenodo-metadata-0.3.schema.json"
ZENODO_REPOSITORY_TYPE = "https://w3id.org/modavis/vao/repository/zenodo"
MAX_ENTRIES = 100_000
MAX_MANIFEST_BYTES = 64 * 1024 * 1024
MAX_DESCRIPTOR_BYTES = 16 * 1024 * 1024
MAX_ENTRY_BYTES = 1024**4
MAX_TOTAL_BYTES = 4 * 1024**4
CHUNK = 1024 * 1024


class VAO03Error(vao02.VAOError):
    pass


def now() -> str:
    return (
        datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    )


def json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True, allow_nan=False)
        + "\n"
    ).encode("utf-8")


def strict_json_bytes(data: bytes, label: str) -> dict[str, Any]:
    def pairs(values: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in values:
            if key in result:
                raise ValueError(f"duplicate JSON property {key!r}")
            result[key] = value
        return result

    def reject(value: str) -> None:
        raise ValueError(f"non-finite JSON number {value!r}")

    def binary64(value: str) -> float:
        result = float(value)
        if not math.isfinite(result):
            raise ValueError(f"JSON number {value!r} overflows finite binary64")
        if result == 0.0 and Decimal(value) != 0:
            raise ValueError(f"JSON number {value!r} underflows finite binary64")
        return result

    def reject_surrogates(value: Any, path: str = "$") -> None:
        if isinstance(value, str):
            if any(0xD800 <= ord(character) <= 0xDFFF for character in value):
                raise ValueError(f"non-scalar Unicode value at {path}")
        elif isinstance(value, list):
            for index, item in enumerate(value):
                reject_surrogates(item, f"{path}[{index}]")
        elif isinstance(value, dict):
            for key, item in value.items():
                reject_surrogates(key, f"{path}.<property-name>")
                reject_surrogates(item, f"{path}.{key}")

    try:
        parsed = json.loads(
            data.decode("utf-8"),
            object_pairs_hook=pairs,
            parse_constant=reject,
            parse_float=binary64,
        )
        reject_surrogates(parsed)
    except (UnicodeError, json.JSONDecodeError, ValueError, RecursionError) as exc:
        raise VAO03Error(f"{label} is not strict UTF-8 JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise VAO03Error(f"{label} root must be an object")
    return parsed


def load_json(path: Path) -> tuple[dict[str, Any], bytes]:
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise VAO03Error(f"Cannot read {path}: {exc}") from exc
    return strict_json_bytes(data, str(path)), data


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_bytes(json_bytes(value))
    os.replace(temporary, path)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_stream(stream: BinaryIO) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    while True:
        block = stream.read(CHUNK)
        if not block:
            return digest.hexdigest(), size
        digest.update(block)
        size += len(block)


def sha256_file(path: Path) -> tuple[str, int]:
    with path.open("rb") as stream:
        return sha256_stream(stream)


def is_identifier(value: Any) -> bool:
    return (
        isinstance(value, str)
        and value.startswith(("urn:", "http://", "https://"))
        and not any(c.isspace() for c in value)
    )


def is_safe_path(value: Any, prefix: str | None = None) -> bool:
    if (
        not isinstance(value, str)
        or not value
        or value.startswith("/")
        or "\\" in value
        or "\x00" in value
    ):
        return False
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in ("", ".", "..") for part in path.parts):
        return False
    return prefix is None or (bool(path.parts) and path.parts[0] == prefix)


def normalized_carrier_path(value: str) -> str:
    """Canonical comparison key; carrier spelling itself remains evidence."""
    return unicodedata.normalize("NFC", value)


def schema_document(path: Path) -> dict[str, Any]:
    value, _ = load_json(path)
    return value


def schema_errors(value: Any, path: Path) -> list[str]:
    return vao02.schema_validation_errors(value, schema_document(path))


def non_finite_paths(value: Any, location: str = "$") -> list[str]:
    if isinstance(value, float) and not math.isfinite(value):
        return [location]
    if isinstance(value, list):
        return [
            p
            for i, item in enumerate(value)
            for p in non_finite_paths(item, f"{location}[{i}]")
        ]
    if isinstance(value, dict):
        return [
            p
            for key, item in value.items()
            for p in non_finite_paths(item, f"{location}.{key}")
        ]
    return []


def records_by_id(
    records: Any, label: str, errors: list[str], global_ids: dict[str, str]
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    if not isinstance(records, list):
        return result
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            continue
        identifier = record.get("id")
        if not is_identifier(identifier):
            errors.append(f"{label}[{index}] has an invalid id.")
            continue
        if identifier in global_ids:
            errors.append(
                f"Identifier {identifier!r} is duplicated in {global_ids[identifier]} and {label}."
            )
        else:
            global_ids[identifier] = label
        result[identifier] = record
    return result


def matrix4_is_invertible(values: Any) -> bool:
    if (
        not isinstance(values, list)
        or len(values) != 16
        or any(
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or not math.isfinite(value)
            for value in values
        )
    ):
        return False
    matrix = [list(map(float, values[row * 4 : (row + 1) * 4])) for row in range(4)]
    for column in range(4):
        pivot = max(range(column, 4), key=lambda row: abs(matrix[row][column]))
        if abs(matrix[pivot][column]) < 1e-12:
            return False
        matrix[column], matrix[pivot] = matrix[pivot], matrix[column]
        for row in range(column + 1, 4):
            scale = matrix[row][column] / matrix[column][column]
            for item in range(column, 4):
                matrix[row][item] -= scale * matrix[column][item]
    return True


def validate_acoustics(
    manifest: dict[str, Any],
    entities: dict[str, dict[str, Any]],
    logical_assets: dict[str, dict[str, Any]],
    realizations: dict[str, dict[str, Any]],
    paradata: dict[str, dict[str, Any]],
    analyses: dict[str, dict[str, Any]],
    acoustic_records: dict[str, dict[str, dict[str, Any]]],
    errors: list[str],
    warnings: list[str],
) -> None:
    acoustics = manifest.get("acoustics")
    profile_records = [
        record
        for record in manifest.get("profiles", [])
        + manifest.get("materializableProfiles", [])
        if isinstance(record, dict)
    ]
    profiles = {record.get("id") for record in profile_records}
    acoustic_profile_records = [
        record for record in profile_records if record.get("id") == ACOUSTICS_PROFILE
    ]
    declared_capabilities = {
        capability
        for record in acoustic_profile_records
        for capability in record.get("requiredCapabilities", [])
    }

    if ACOUSTICS_PROFILE in profiles:
        if SPATIAL_PROFILE not in profiles:
            errors.append("The Acoustics 0.3 profile requires the Spatial 0.3 profile.")
        if not isinstance(acoustics, dict):
            errors.append(
                "The Acoustics 0.3 profile requires the closed top-level acoustics object."
            )
        if declared_capabilities.isdisjoint(ACOUSTIC_CAPABILITIES):
            errors.append(
                "The Acoustics 0.3 profile requires at least one standard acoustic capability."
            )
    if SPATIAL_PROFILE in profiles and not isinstance(acoustics, dict):
        errors.append(
            "The Spatial 0.3 profile requires the closed top-level acoustics object."
        )
    if not isinstance(acoustics, dict):
        return
    if ACOUSTICS_PROFILE not in profiles:
        warnings.append(
            "An acoustics object is present without an Acoustics 0.3 profile claim."
        )

    frames = acoustic_records["coordinateFrames"]
    poses = acoustic_records["poses"]
    geometry_bindings = acoustic_records["geometryBindings"]
    materials = acoustic_records["materialModels"]
    measurements = acoustic_records["measurements"]
    responses = acoustic_records["responseSets"]
    scenes = acoustic_records["audioScenes"]
    renderers = acoustic_records["renderConfigurations"]
    activity_ids = set(paradata) | set(analyses)

    frame_edges: dict[str, list[str]] = {}
    for frame in frames.values():
        frame_id = frame["id"]
        parent = frame.get("parentFrameId")
        frame_edges[frame_id] = [parent] if isinstance(parent, str) else []
        if parent is not None and parent not in frames:
            errors.append(
                f"Coordinate frame {frame_id!r} has unresolved parentFrameId."
            )
        if parent is not None and not matrix4_is_invertible(
            frame.get("transformToParent")
        ):
            errors.append(
                f"Coordinate frame {frame_id!r} requires an invertible transformToParent."
            )
        up = frame.get("upAxis", "not-applicable")
        forward = frame.get("forwardAxis", "not-applicable")
        if (
            up != "not-applicable"
            and forward != "not-applicable"
            and str(up)[-1:] == str(forward)[-1:]
        ):
            errors.append(
                f"Coordinate frame {frame_id!r} cannot use the same axis for up and forward."
            )
        generated = frame.get("generatedById")
        if generated is not None and generated not in activity_ids:
            errors.append(
                f"Coordinate frame {frame_id!r} has unresolved generatedById."
            )

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit_frame(frame_id: str) -> None:
        if frame_id in visiting:
            errors.append(f"Coordinate-frame graph contains a cycle at {frame_id!r}.")
            return
        if frame_id in visited:
            return
        visiting.add(frame_id)
        for parent in frame_edges.get(frame_id, []):
            if parent in frames:
                visit_frame(parent)
        visiting.remove(frame_id)
        visited.add(frame_id)

    for frame_id in frames:
        visit_frame(frame_id)

    def frame_root(frame_id: Any) -> str | None:
        if frame_id not in frames:
            return None
        seen: set[str] = set()
        current = frame_id
        while current in frames and current not in seen:
            seen.add(current)
            parent = frames[current].get("parentFrameId")
            if parent is None:
                return current
            current = parent
        return None

    for pose in poses.values():
        pose_id = pose["id"]
        subject = pose.get("subjectId")
        frame_id = pose.get("frameId")
        if subject not in entities:
            errors.append(f"Pose {pose_id!r} has unresolved subjectId.")
        if frame_id not in frames:
            errors.append(f"Pose {pose_id!r} has unresolved frameId.")
        else:
            position = pose.get("position")
            if not isinstance(position, list) or len(position) != frames[frame_id].get(
                "dimension"
            ):
                errors.append(
                    f"Pose {pose_id!r} position dimension does not match its coordinate frame."
                )
        quaternion = pose.get("orientationXYZW")
        if isinstance(quaternion, list) and (
            len(quaternion) != 4
            or not math.isclose(
                sum(float(value) ** 2 for value in quaternion),
                1.0,
                rel_tol=1e-6,
                abs_tol=1e-6,
            )
        ):
            errors.append(
                f"Pose {pose_id!r} orientationXYZW must be a normalized XYZW quaternion."
            )
        trajectory = pose.get("trajectoryAssetId")
        if trajectory is not None and trajectory not in logical_assets:
            errors.append(f"Pose {pose_id!r} has unresolved trajectoryAssetId.")
        generated = pose.get("generatedById")
        if generated is not None and generated not in activity_ids:
            errors.append(f"Pose {pose_id!r} has unresolved generatedById.")

    geometry_frame_roots: set[str] = set()
    for binding in geometry_bindings.values():
        binding_id = binding["id"]
        subject = binding.get("subjectId")
        asset_id = binding.get("logicalAssetId")
        if subject not in entities:
            errors.append(f"Geometry binding {binding_id!r} has unresolved subjectId.")
        if asset_id not in logical_assets:
            errors.append(
                f"Geometry binding {binding_id!r} has unresolved logicalAssetId."
            )
            continue
        asset = logical_assets[asset_id]
        if not any(
            role.endswith(("/spatial-model", "/three-dimensional-model"))
            for role in asset.get("roles", [])
        ):
            errors.append(
                f"Geometry binding {binding_id!r} requires a spatial-model logical asset role."
            )
        geometry_realizations = [
            realizations[ref]
            for ref in asset.get("realizationIds", [])
            if ref in realizations
            and realizations[ref].get("technicalMetadata", {}).get("kind") == "geometry"
        ]
        if not geometry_realizations:
            errors.append(
                f"Geometry binding {binding_id!r} has no geometry realization."
            )
        for realization in geometry_realizations:
            root = frame_root(
                realization.get("technicalMetadata", {}).get("coordinateFrameId")
            )
            if root:
                geometry_frame_roots.add(root)
        selector = binding.get("selector")
        if (
            isinstance(selector, dict)
            and selector.get("selectorType") == "gltf-node-index"
        ):
            if not isinstance(selector.get("value"), int) or isinstance(
                selector.get("value"), bool
            ):
                errors.append(
                    f"Geometry binding {binding_id!r} requires an integer glTF node index."
                )
            if not any(
                realization.get("mediaType") in {"model/gltf+json", "model/gltf-binary"}
                for realization in geometry_realizations
            ):
                errors.append(
                    f"Geometry binding {binding_id!r} uses a glTF selector without a glTF realization."
                )

    measurement_frame_roots: set[str] = set()
    for measurement in measurements.values():
        measurement_id = measurement["id"]
        source_id = measurement.get("sourceId")
        receiver_id = measurement.get("receiverId")
        source_pose = poses.get(measurement.get("sourcePoseId"))
        receiver_pose = poses.get(measurement.get("receiverPoseId"))
        for key in (
            "sourceId",
            "receiverId",
            "spaceId",
            "sourceSpaceId",
            "receivingSpaceId",
            "separatingElementId",
            "configurationId",
            "stateId",
        ):
            reference = measurement.get(key)
            if reference is not None and reference not in entities:
                errors.append(f"Measurement {measurement_id!r} has unresolved {key}.")
        if source_pose is None:
            errors.append(
                f"Measurement {measurement_id!r} has unresolved sourcePoseId."
            )
        elif source_pose.get("subjectId") != source_id:
            errors.append(
                f"Measurement {measurement_id!r} sourcePoseId does not describe sourceId."
            )
        if receiver_pose is None:
            errors.append(
                f"Measurement {measurement_id!r} has unresolved receiverPoseId."
            )
        elif receiver_pose.get("subjectId") != receiver_id:
            errors.append(
                f"Measurement {measurement_id!r} receiverPoseId does not describe receiverId."
            )
        roots = {
            frame_root(pose.get("frameId"))
            for pose in (source_pose, receiver_pose)
            if pose is not None
        }
        roots.discard(None)
        if len(roots) > 1:
            errors.append(
                f"Measurement {measurement_id!r} source and receiver poses are not transformable to a common frame."
            )
        measurement_frame_roots.update(roots)

    for response in responses.values():
        response_id = response["id"]
        asset_id = response.get("logicalAssetId")
        if response.get("responseEntityId") not in entities:
            errors.append(
                f"Response set {response_id!r} has unresolved responseEntityId."
            )
        if asset_id not in logical_assets:
            errors.append(
                f"Response set {response_id!r} has unresolved logicalAssetId."
            )
            continue
        asset = logical_assets[asset_id]
        if not any(
            role.endswith("/impulse-response") for role in asset.get("roles", [])
        ):
            errors.append(
                f"Response set {response_id!r} requires an impulse-response logical asset role."
            )
        expected_measurements = set(response.get("measurementIds", []))
        for measurement_id in expected_measurements:
            if measurement_id not in measurements:
                errors.append(
                    f"Response set {response_id!r} has unresolved measurement {measurement_id!r}."
                )
        generated = response.get("generatedById")
        if generated not in activity_ids:
            errors.append(f"Response set {response_id!r} has unresolved generatedById.")
        response_realizations = [
            realizations[ref]
            for ref in asset.get("realizationIds", [])
            if ref in realizations
        ]
        if not response_realizations:
            errors.append(f"Response set {response_id!r} has no realization.")
        for realization in response_realizations:
            technical = realization.get("technicalMetadata", {})
            impulse = technical.get("impulseResponse")
            if technical.get("kind") != "audio" or not isinstance(impulse, dict):
                errors.append(
                    f"Response-set realization {realization['id']!r} requires typed impulseResponse audio metadata."
                )
                continue
            if impulse.get("responseSetId") != response_id:
                errors.append(
                    f"Response-set realization {realization['id']!r} has the wrong responseSetId."
                )
            mappings = impulse.get("measurementMappings", [])
            mapped_ids = [
                mapping.get("measurementId")
                for mapping in mappings
                if isinstance(mapping, dict)
            ]
            if (
                len(mapped_ids) != len(set(mapped_ids))
                or set(mapped_ids) != expected_measurements
            ):
                errors.append(
                    f"Response-set realization {realization['id']!r} must map every response measurement exactly once."
                )
            data_indices = [
                mapping.get("dataIRIndex")
                for mapping in mappings
                if isinstance(mapping, dict) and mapping.get("dataIRIndex") is not None
            ]
            if len(data_indices) != len(set(data_indices)):
                errors.append(
                    f"Response-set realization {realization['id']!r} repeats a dataIRIndex."
                )
            channels = technical.get("channelCount")
            for mapping in mappings:
                if not isinstance(mapping, dict):
                    continue
                if isinstance(channels, int) and any(
                    index >= channels
                    for index in mapping.get("channelIndices", [])
                    if isinstance(index, int)
                ):
                    errors.append(
                        f"Response-set realization {realization['id']!r} maps a channel outside channelCount."
                    )
            if impulse.get("encoding") in {"WAV", "FLAC"} and len(mappings) != 1:
                errors.append(
                    f"WAV/FLAC response-set realization {realization['id']!r} is limited to one fixed source-receiver measurement."
                )
            expected_status = response.get("representationStatus")
            if expected_status and not str(
                realization.get("representationStatus", "")
            ).endswith("/" + expected_status):
                errors.append(
                    f"Response-set realization {realization['id']!r} representation status disagrees with its response set."
                )

    for material in materials.values():
        material_id = material["id"]
        if material.get("materialEntityId") not in entities:
            errors.append(
                f"Material model {material_id!r} has unresolved materialEntityId."
            )
        bands = material.get("bandAxis", {}).get("centerFrequenciesHz", [])
        for key in ("absorption", "scattering", "transmissionLossDB"):
            if key in material and len(material[key]) != len(bands):
                errors.append(
                    f"Material model {material_id!r} {key} length must match its frequency axis."
                )

    for scene in scenes.values():
        scene_id = scene["id"]
        if scene.get("sceneEntityId") not in entities:
            errors.append(f"Audio scene {scene_id!r} has unresolved sceneEntityId.")
        if scene.get("coordinateFrameId") not in frames:
            errors.append(f"Audio scene {scene_id!r} has unresolved coordinateFrameId.")
        for asset_id in scene.get("mediaAssetIds", []):
            if asset_id not in logical_assets:
                errors.append(f"Audio scene {scene_id!r} has unresolved mediaAssetId.")

    for renderer in renderers.values():
        renderer_id = renderer["id"]
        if renderer.get("sceneId") not in scenes:
            errors.append(
                f"Render configuration {renderer_id!r} has unresolved sceneId."
            )
        if renderer.get("coordinateFrameId") not in frames:
            errors.append(
                f"Render configuration {renderer_id!r} has unresolved coordinateFrameId."
            )
        if renderer.get("outsideDomainPolicy") == "fallback" and not renderer.get(
            "fallbackIds"
        ):
            errors.append(
                f"Render configuration {renderer_id!r} selects fallback policy without a fallback."
            )

    if (
        declared_capabilities & {POSITION_REGISTERED_SCENE, VISUAL_ACOUSTIC_SCENE}
        and not measurements
    ):
        errors.append(
            "A position-registered acoustic-scene capability requires source/receiver measurements."
        )
    if (
        POSITION_REGISTERED_SCENE in declared_capabilities
        and not measurement_frame_roots
    ):
        errors.append(
            "The position-registered-acoustic-scene capability requires resolvable pose frames."
        )
    if VISUAL_ACOUSTIC_SCENE in declared_capabilities:
        if not geometry_bindings or not responses:
            errors.append(
                "The visual-acoustic-scene capability requires geometry bindings and response sets."
            )
        elif not (geometry_frame_roots & measurement_frame_roots):
            errors.append(
                "The visual-acoustic-scene capability requires geometry and response poses transformable to a common coordinate frame."
            )
    if MEASURED_IMPULSE_RESPONSE in declared_capabilities and not any(
        response.get("representationStatus") == "measured"
        for response in responses.values()
    ):
        errors.append(
            "The measured-impulse-response capability requires a measured response set."
        )
    if SIMULATED_IMPULSE_RESPONSE in declared_capabilities and not any(
        response.get("representationStatus") in {"simulated", "hybrid"}
        for response in responses.values()
    ):
        errors.append(
            "The simulated-impulse-response capability requires a simulated or hybrid response set."
        )
    if SEMANTIC_BUILDING_MODEL in declared_capabilities:
        kinds = {entity.get("kind") for entity in entities.values()}
        if not {"building", "space", "boundary"}.issubset(kinds) or not any(
            binding.get("role") == "authoritative-semantic"
            for binding in geometry_bindings.values()
        ):
            errors.append(
                "The semantic-building-model capability requires building, space, boundary, and authoritative semantic geometry."
            )
    if SPATIAL_RESPONSE_FIELD in declared_capabilities and not any(
        response.get("interpolation") for response in responses.values()
    ):
        errors.append(
            "The spatial-response-field capability requires an interpolation contract."
        )
    if SPATIAL_AUDIO_SCENE in declared_capabilities and not scenes:
        errors.append("The spatial-audio-scene capability requires an audio scene.")


def validate_playable(
    manifest: dict[str, Any],
    entities: dict[str, dict[str, Any]],
    realizations: dict[str, dict[str, Any]],
    paradata: dict[str, dict[str, Any]],
    analyses: dict[str, dict[str, Any]],
    relations: dict[str, dict[str, Any]],
    playable_records: dict[str, dict[str, dict[str, Any]]],
    errors: list[str],
) -> None:
    playable = manifest.get("playable")
    profile_records = [
        record
        for record in manifest.get("profiles", [])
        + manifest.get("materializableProfiles", [])
        if isinstance(record, dict)
    ]
    playable_profiles = [
        record for record in profile_records if record.get("id") == PLAYABLE_PROFILE
    ]
    profile_ids = {record.get("id") for record in profile_records}
    declares_profile = bool(playable_profiles)
    capabilities = {
        capability
        for record in playable_profiles
        for capability in record.get("requiredCapabilities", [])
    }

    if declares_profile:
        if PLAYABLE_PROFILE not in manifest.get("conformsTo", []):
            errors.append(
                "The Playable 0.3 profile record must also appear in conformsTo."
            )
        if not ({INTERACTION, PLAYABLE_INTERACTION} & capabilities):
            errors.append(
                "The Playable 0.3 profile requires an interaction capability."
            )
        interactions = [
            record
            for record in entities.values()
            if record.get("kind") == "interaction"
        ]
        if not interactions:
            errors.append(
                "The Playable 0.3 profile requires at least one interaction entity."
            )
        outgoing = {
            "https://w3id.org/modavis/vao/ontology#activates",
            "https://w3id.org/modavis/vao/ontology#modulates",
        }
        for interaction in interactions:
            properties = (
                interaction.get("properties")
                if isinstance(interaction.get("properties"), dict)
                else {}
            )
            for local_name in (
                "interactionType",
                "controlProtocol",
                "controlDomain",
                "timingPolicy",
            ):
                if (
                    "https://w3id.org/modavis/vao/ontology#" + local_name
                    not in properties
                ):
                    errors.append(
                        f"Playable interaction {interaction.get('id')!r} is missing {local_name}."
                    )
            if not any(
                relation.get("subjectId") == interaction.get("id")
                and relation.get("predicate") in outgoing
                and relation.get("status") not in {"rejected", "superseded"}
                for relation in relations.values()
            ):
                errors.append(
                    f"Playable interaction {interaction.get('id')!r} has no active activates/modulates relation."
                )
    elif isinstance(playable, dict):
        errors.append("A playable object requires a Playable 0.3 profile claim.")
    sample_capabilities = capabilities & {
        SAMPLED_INSTRUMENT_PLAYBACK,
        SAMPLE_LOOPING,
        TUNING_MAP,
        MULTI_PERSPECTIVE_SAMPLING,
        RECORDED_RELEASE,
        SOURCE_SAMPLER_SEMANTICS,
    }
    if sample_capabilities and SAMPLED_INSTRUMENT_PLAYBACK not in capabilities:
        errors.append(
            "Playable sample sub-capabilities require sampled-instrument-playback."
        )
    if SAMPLED_INSTRUMENT_PLAYBACK in capabilities and not isinstance(playable, dict):
        errors.append(
            "The sampled-instrument-playback capability requires the closed top-level playable object."
        )
    if not isinstance(playable, dict):
        return

    regions = playable_records["signalRegions"]
    loops = playable_records["loopPointSets"]
    tunings = playable_records["tuningMaps"]
    perspectives = playable_records["perspectiveGroups"]
    variants = playable_records["sampleVariants"]
    known_activity_ids = set(paradata) | set(analyses) | set(relations)
    acoustics = (
        manifest.get("acoustics") if isinstance(manifest.get("acoustics"), dict) else {}
    )
    acoustic_pose_ids = {
        record.get("id")
        for record in acoustics.get("poses", [])
        if isinstance(record, dict) and is_identifier(record.get("id"))
    }

    def usable(status: Any) -> bool:
        return status in {"asserted", "reviewed", "accepted"}

    def evidence(record: dict[str, Any], label: str) -> None:
        identifier = record["id"]
        generated_by = record.get("generatedById")
        if (
            record.get("status") == "inferred" or record.get("source") == "algorithmic"
        ) and generated_by is None:
            errors.append(
                f"{label} {identifier!r} is inferred or algorithmic but lacks generatedById."
            )
        if generated_by is not None and generated_by not in known_activity_ids:
            errors.append(
                f"{label} {identifier!r} has unresolved generatedById {generated_by!r}."
            )
        if record.get("source") == "algorithmic" and record.get("status") == "asserted":
            errors.append(
                f"{label} {identifier!r} cannot describe algorithmic output as asserted source metadata."
            )

    for region in regions.values():
        evidence(region, "Signal region")
        realization = realizations.get(region.get("realizationId"))
        if realization is None:
            errors.append(
                f"Signal region {region['id']!r} has unresolved realizationId."
            )
            continue
        technical = realization.get("technicalMetadata", {})
        if technical.get("kind") != "audio":
            errors.append(
                f"Signal region {region['id']!r} must reference an audio realization."
            )
        start = region.get("startFrameInclusive")
        end = region.get("endFrameExclusive")
        if isinstance(start, int) and isinstance(end, int) and end <= start:
            errors.append(
                f"Signal region {region['id']!r} has an empty or reversed half-open frame range."
            )
        frame_count = technical.get("frameCount")
        if isinstance(end, int) and isinstance(frame_count, int) and end > frame_count:
            errors.append(
                f"Signal region {region['id']!r} exceeds the realization frameCount."
            )

    for loop in loops.values():
        evidence(loop, "Loop-point set")
        resolved = []
        for region_id in loop.get("regionIds", []):
            if region_id not in regions:
                errors.append(
                    f"Loop-point set {loop['id']!r} has unresolved region {region_id!r}."
                )
            else:
                resolved.append(regions[region_id])
        if any(region.get("role") != "sustain-loop" for region in resolved):
            errors.append(
                f"Every region in loop-point set {loop['id']!r} must have role sustain-loop."
            )
        if len({region.get("realizationId") for region in resolved}) > 1:
            errors.append(
                f"Loop-point set {loop['id']!r} spans more than one realization."
            )
        crossfade = loop.get("crossfadeFrames")
        lengths = [
            region.get("endFrameExclusive", 0) - region.get("startFrameInclusive", 0)
            for region in resolved
        ]
        if isinstance(crossfade, int) and lengths and crossfade > min(lengths):
            errors.append(
                f"Loop-point set {loop['id']!r} has a crossfade longer than a loop region."
            )
        reviewed_by = loop.get("reviewedById")
        if reviewed_by is not None and reviewed_by not in known_activity_ids:
            errors.append(
                f"Loop-point set {loop['id']!r} has unresolved reviewedById {reviewed_by!r}."
            )

    for tuning in tunings.values():
        evidence(tuning, "Tuning map")
        keys = [
            entry.get("key")
            for entry in tuning.get("entries", [])
            if isinstance(entry, dict)
        ]
        if len(keys) != len(set(keys)):
            errors.append(f"Tuning map {tuning['id']!r} contains duplicate MIDI keys.")

    for perspective in perspectives.values():
        evidence(perspective, "Perspective group")
        for realization_id in perspective.get("realizationIds", []):
            realization = realizations.get(realization_id)
            if realization is None:
                errors.append(
                    f"Perspective group {perspective['id']!r} has unresolved realization {realization_id!r}."
                )
                continue
            technical = realization.get("technicalMetadata", {})
            if technical.get("kind") != "audio":
                errors.append(
                    f"Perspective group {perspective['id']!r} must reference audio realizations."
                )
            channel_count = technical.get("channelCount")
            if isinstance(channel_count, int) and any(
                index >= channel_count
                for index in perspective.get("channelIndices", [])
            ):
                errors.append(
                    f"Perspective group {perspective['id']!r} contains a channel outside realization {realization_id!r}."
                )
        for pose_id in perspective.get("poseIds", []):
            if pose_id not in acoustic_pose_ids:
                errors.append(
                    f"Perspective group {perspective['id']!r} has unresolved acoustic pose {pose_id!r}."
                )
        if perspective.get(
            "geometryStatus"
        ) == "position-registered" and not perspective.get("poseIds"):
            errors.append(
                f"Position-registered perspective group {perspective['id']!r} requires poseIds."
            )
        if (
            perspective.get("geometryStatus") == "position-registered"
            and SPATIAL_PROFILE not in profile_ids
        ):
            errors.append(
                f"Position-registered perspective group {perspective['id']!r} requires the Spatial 0.3 profile."
            )

    for variant in variants.values():
        evidence(variant, "Sample variant")
        realization_id = variant.get("realizationId")
        realization = realizations.get(realization_id)
        if realization is None:
            errors.append(
                f"Sample variant {variant['id']!r} has unresolved realizationId."
            )
            continue
        if realization.get("technicalMetadata", {}).get("kind") != "audio":
            errors.append(
                f"Sample variant {variant['id']!r} must reference an audio realization."
            )
        for region_id in variant.get("signalRegionIds", []):
            region = regions.get(region_id)
            if region is None:
                errors.append(
                    f"Sample variant {variant['id']!r} has unresolved signal region {region_id!r}."
                )
            elif region.get("realizationId") != realization_id:
                errors.append(
                    f"Sample variant {variant['id']!r} references a region from another realization."
                )
            elif not usable(region.get("status")):
                errors.append(
                    f"Sample variant {variant['id']!r} uses a rejected, superseded, or unreviewed inferred region {region_id!r}."
                )
        for loop_id in variant.get("loopPointSetIds", []):
            loop = loops.get(loop_id)
            if loop is None:
                errors.append(
                    f"Sample variant {variant['id']!r} has unresolved loop-point set {loop_id!r}."
                )
                continue
            realization_ids = {
                regions[region_id].get("realizationId")
                for region_id in loop.get("regionIds", [])
                if region_id in regions
            }
            if realization_ids != {realization_id}:
                errors.append(
                    f"Sample variant {variant['id']!r} references a loop from another realization."
                )
            if not usable(loop.get("status")):
                errors.append(
                    f"Sample variant {variant['id']!r} uses a rejected, superseded, or unreviewed inferred loop {loop_id!r}."
                )
        perspective_id = variant.get("perspectiveGroupId")
        if perspective_id is not None:
            perspective = perspectives.get(perspective_id)
            if perspective is None:
                errors.append(
                    f"Sample variant {variant['id']!r} has unresolved perspectiveGroupId."
                )
            elif realization_id not in perspective.get("realizationIds", []):
                errors.append(
                    f"Sample variant {variant['id']!r} is not a member of its perspective group."
                )
            elif not usable(perspective.get("status")):
                errors.append(
                    f"Sample variant {variant['id']!r} uses a rejected, superseded, or unreviewed inferred perspective group."
                )

    usable_mapping_count = 0
    mapped_variant_ids: set[str] = set()
    mappings = playable_records["sampleMappings"]
    for mapping in mappings.values():
        evidence(mapping, "Sample mapping")
        key_range = mapping.get("keyRange", {})
        velocity_range = mapping.get("velocityRange", {})
        if key_range.get("minimum", 0) > key_range.get("maximum", 0):
            errors.append(
                f"Sample mapping {mapping['id']!r} has a reversed MIDI key range."
            )
        if velocity_range.get("minimum", 0) > velocity_range.get("maximum", 0):
            errors.append(
                f"Sample mapping {mapping['id']!r} has a reversed velocity range."
            )
        for key in ("instrumentEntityId", "componentEntityId", "rankEntityId"):
            entity_id = mapping.get(key)
            if entity_id is not None and entity_id not in entities:
                errors.append(
                    f"Sample mapping {mapping['id']!r} has unresolved entity {entity_id!r}."
                )
        instrument = entities.get(mapping.get("instrumentEntityId"))
        if instrument is not None and instrument.get("kind") != "instrument":
            errors.append(
                f"Sample mapping {mapping['id']!r} instrumentEntityId does not identify an instrument entity."
            )
        tuning_id = mapping.get("tuningMapId")
        if tuning_id is not None and tuning_id not in tunings:
            errors.append(
                f"Sample mapping {mapping['id']!r} has unresolved tuningMapId."
            )
        elif tuning_id is not None and not usable(tunings[tuning_id].get("status")):
            errors.append(
                f"Sample mapping {mapping['id']!r} uses a rejected, superseded, or unreviewed inferred tuning map."
            )
        resolved_variants = []
        for variant_id in mapping.get("variantIds", []):
            if variant_id not in variants:
                errors.append(
                    f"Sample mapping {mapping['id']!r} has unresolved variant {variant_id!r}."
                )
            else:
                resolved_variants.append(variants[variant_id])
        if not any(
            variant.get("trigger") == "note-on" for variant in resolved_variants
        ):
            errors.append(
                f"Sample mapping {mapping['id']!r} requires at least one note-on variant."
            )
        if any(not usable(variant.get("status")) for variant in resolved_variants):
            errors.append(
                f"Sample mapping {mapping['id']!r} references rejected, superseded, or unreviewed inferred variants."
            )
        if mapping.get("noteOffPolicy") == "recorded-release" and not any(
            variant.get("trigger") == "note-off"
            and variant.get("signalRole") == "release"
            for variant in resolved_variants
        ):
            errors.append(
                f"Sample mapping {mapping['id']!r} claims recorded-release without a note-off release variant."
            )
        if usable(mapping.get("status")):
            usable_mapping_count += 1
            if all(usable(variant.get("status")) for variant in resolved_variants):
                mapped_variant_ids.update(mapping.get("variantIds", []))

    if SAMPLED_INSTRUMENT_PLAYBACK in capabilities and usable_mapping_count == 0:
        errors.append(
            "The sampled-instrument-playback capability requires at least one usable sample mapping."
        )
    mapped_variants = [
        variants[identifier]
        for identifier in mapped_variant_ids
        if identifier in variants
    ]
    if SAMPLE_LOOPING in capabilities and not any(
        variant.get("loopPointSetIds") for variant in mapped_variants
    ):
        errors.append(
            "The sample-looping capability requires a mapped sample variant bound to a loop-point set."
        )
    if TUNING_MAP in capabilities and not any(
        usable(mapping.get("status")) and mapping.get("tuningMapId") in tunings
        for mapping in mappings.values()
    ):
        errors.append(
            "The tuning-map capability requires a usable sample mapping bound to a tuning map."
        )
    mapped_perspectives = {
        variant.get("perspectiveGroupId")
        for variant in mapped_variants
        if variant.get("perspectiveGroupId") in perspectives
    }
    if MULTI_PERSPECTIVE_SAMPLING in capabilities and len(mapped_perspectives) < 2:
        errors.append(
            "The multi-perspective-sampling capability requires mapped variants from at least two perspective groups."
        )
    if RECORDED_RELEASE in capabilities and not any(
        mapping.get("noteOffPolicy") == "recorded-release"
        for mapping in mappings.values()
    ):
        errors.append(
            "The recorded-release capability requires a mapping with recorded-release policy."
        )
    if SOURCE_SAMPLER_SEMANTICS in capabilities:
        source_backed = any(
            mapping.get("source") == "native-definition"
            for mapping in mappings.values()
        ) and any(
            variant.get("source") in {"native-definition", "embedded-metadata"}
            for variant in variants.values()
        )
        if not source_backed:
            errors.append(
                "The source-sampler-semantics capability requires native-definition mappings and source-backed variants."
            )


def validate_complex_interaction(
    manifest: dict[str, Any],
    entities: dict[str, dict[str, Any]],
    realizations: dict[str, dict[str, Any]],
    paradata: dict[str, dict[str, Any]],
    analyses: dict[str, dict[str, Any]],
    relations: dict[str, dict[str, Any]],
    interaction_records: dict[str, dict[str, dict[str, Any]]],
    capture_records: dict[str, dict[str, dict[str, Any]]],
    playable_records: dict[str, dict[str, dict[str, Any]]],
    errors: list[str],
) -> None:
    interaction_model = manifest.get("interactionModel")
    capture_documentation = manifest.get("captureDocumentation")
    profile_records = [
        record
        for record in manifest.get("profiles", [])
        + manifest.get("materializableProfiles", [])
        if isinstance(record, dict) and record.get("id") == PLAYABLE_PROFILE
    ]
    capabilities = {
        capability
        for record in profile_records
        for capability in record.get("requiredCapabilities", [])
    }
    complex_claims = capabilities & COMPLEX_INTERACTION_CAPABILITIES
    if complex_claims and not isinstance(interaction_model, dict):
        errors.append(
            "Complex interaction capabilities require the closed top-level interactionModel object."
        )
    if isinstance(interaction_model, dict) and not profile_records:
        errors.append(
            "An interactionModel object requires a Playable 0.3 profile claim."
        )
    if CAPTURE_EVENT_ALIGNMENT in capabilities and not isinstance(
        capture_documentation, dict
    ):
        errors.append(
            "The capture-event-alignment capability requires captureDocumentation."
        )
    if isinstance(capture_documentation, dict) and not profile_records:
        errors.append(
            "A captureDocumentation object requires a Playable 0.3 profile claim."
        )
    if not isinstance(interaction_model, dict) and not isinstance(
        capture_documentation, dict
    ):
        return

    controls = interaction_records["controls"]
    events = interaction_records["eventTypes"]
    bindings = interaction_records["protocolBindings"]
    states = interaction_records["stateVariables"]
    transitions = interaction_records["transitions"]
    routes = interaction_records["routingRules"]
    processes = interaction_records["processModels"]
    timings = interaction_records["timingConstraints"]
    transfers = interaction_records["transferFunctions"]
    renders = interaction_records["renderBindings"]
    known_activity_ids = set(paradata) | set(analyses) | set(relations)
    usable_statuses = {"asserted", "reviewed", "accepted"}

    def evidence(record: dict[str, Any], label: str) -> None:
        generated_by = record.get("generatedById")
        reviewed_by = record.get("reviewedById")
        if (
            record.get("status") == "inferred" or record.get("source") == "algorithmic"
        ) and generated_by is None:
            errors.append(
                f"{label} {record.get('id')!r} is inferred or algorithmic but lacks generatedById."
            )
        if generated_by is not None and generated_by not in known_activity_ids:
            errors.append(
                f"{label} {record.get('id')!r} has unresolved generatedById {generated_by!r}."
            )
        if reviewed_by is not None and reviewed_by not in known_activity_ids:
            errors.append(
                f"{label} {record.get('id')!r} has unresolved reviewedById {reviewed_by!r}."
            )
        if record.get("source") == "algorithmic" and record.get("status") == "asserted":
            errors.append(
                f"{label} {record.get('id')!r} cannot describe algorithmic output as asserted source metadata."
            )

    def check_condition(condition: Any, owner: str) -> None:
        if (
            isinstance(condition, dict)
            and condition.get("stateVariableId") not in states
        ):
            errors.append(
                f"{owner} has unresolved stateVariableId {condition.get('stateVariableId')!r}."
            )

    def check_action(action: Any, owner: str) -> None:
        if not isinstance(action, dict):
            return
        operation = action.get("operation")
        target = action.get("targetId")
        targets = {
            "set-state": states,
            "toggle-state": states,
            "increment-state": states,
            "emit-event": events,
            "start-process": processes,
            "stop-process": processes,
            "route-event": routes,
            "select-render-binding": renders,
        }.get(operation, {})
        if target not in targets:
            errors.append(
                f"{owner} action {operation!r} has unresolved or incompatible targetId {target!r}."
            )
        delay = action.get("delayConstraintId")
        if delay is not None and delay not in timings:
            errors.append(f"{owner} action has unresolved delayConstraintId {delay!r}.")
        if operation == "set-state" and "value" not in action:
            errors.append(f"{owner} set-state action requires value.")
        if operation == "increment-state" and not isinstance(
            action.get("value"), (int, float)
        ):
            errors.append(f"{owner} increment-state action requires a numeric value.")
        if operation != "route-event" and "keyOffset" in action:
            errors.append(f"{owner} uses keyOffset on a non-routing action.")

    for control in controls.values():
        evidence(control, "Interaction control")
        entity_id = control.get("entityId")
        if entity_id is not None and entity_id not in entities:
            errors.append(
                f"Interaction control {control['id']!r} has unresolved entityId."
            )
        minimum, maximum = control.get("minimumValue"), control.get("maximumValue")
        if (
            isinstance(minimum, (int, float))
            and isinstance(maximum, (int, float))
            and minimum > maximum
        ):
            errors.append(
                f"Interaction control {control['id']!r} has reversed value bounds."
            )
        if control.get("controlBehavior") == "stepped" and not isinstance(
            control.get("stepCount"), int
        ):
            errors.append(
                f"Stepped interaction control {control['id']!r} requires stepCount."
            )
        if control.get("valueType") == "enumerated" and not control.get(
            "allowedValues"
        ):
            errors.append(
                f"Enumerated interaction control {control['id']!r} requires allowedValues."
            )

    for event in events.values():
        evidence(event, "Interaction event type")

    for binding in bindings.values():
        evidence(binding, "Protocol binding")
        if binding.get("controlId") not in controls:
            errors.append(
                f"Protocol binding {binding['id']!r} has unresolved controlId."
            )
        if binding.get("eventTypeId") not in events:
            errors.append(
                f"Protocol binding {binding['id']!r} has unresolved eventTypeId."
            )
        if binding.get("protocol") in {"MIDI-1.0", "MIDI-2.0"}:
            channel_base = binding.get("channelNumberingBase")
            data_base = binding.get("dataNumberingBase")
            channel = binding.get("channel")
            number = binding.get("number")
            if channel_base not in {0, 1} or data_base not in {0, 1}:
                errors.append(
                    f"MIDI protocol binding {binding['id']!r} requires explicit channelNumberingBase and dataNumberingBase."
                )
            if (
                not isinstance(channel, int)
                or channel_base not in {0, 1}
                or not channel_base <= channel <= channel_base + 15
            ):
                errors.append(
                    f"MIDI protocol binding {binding['id']!r} has a channel outside its declared numbering base."
                )
            if binding.get("messageType") not in {
                "pitch-bend",
                "channel-pressure",
                "system-exclusive",
            }:
                if (
                    not isinstance(number, int)
                    or data_base not in {0, 1}
                    or not data_base <= number <= data_base + 127
                ):
                    errors.append(
                        f"MIDI protocol binding {binding['id']!r} has a number outside its declared numbering base."
                    )
        elif binding.get("messageType") == "addressed-value" and not binding.get(
            "address"
        ):
            errors.append(
                f"Addressed protocol binding {binding['id']!r} requires address."
            )

    for state in states.values():
        evidence(state, "State variable")
        subject = state.get("subjectEntityId")
        if subject is not None and subject not in entities:
            errors.append(
                f"State variable {state['id']!r} has unresolved subjectEntityId."
            )
        minimum, maximum = state.get("minimumValue"), state.get("maximumValue")
        if (
            isinstance(minimum, (int, float))
            and isinstance(maximum, (int, float))
            and minimum > maximum
        ):
            errors.append(f"State variable {state['id']!r} has reversed value bounds.")
        if state.get("valueType") == "enumerated" and state.get(
            "defaultValue"
        ) not in state.get("allowedValues", []):
            errors.append(
                f"Enumerated state variable {state['id']!r} has a default outside allowedValues."
            )

    for transition in transitions.values():
        evidence(transition, "Interaction transition")
        if transition.get("eventTypeId") not in events:
            errors.append(
                f"Interaction transition {transition['id']!r} has unresolved eventTypeId."
            )
        control_id = transition.get("controlId")
        if control_id is not None and control_id not in controls:
            errors.append(
                f"Interaction transition {transition['id']!r} has unresolved controlId."
            )
        for condition in transition.get("conditions", []):
            check_condition(condition, f"Interaction transition {transition['id']!r}")
        for action in transition.get("actions", []):
            check_action(action, f"Interaction transition {transition['id']!r}")

    route_edges: dict[str, list[str]] = {}
    for route in routes.values():
        evidence(route, "Routing rule")
        source_id, target_id = route.get("sourceEntityId"), route.get("targetEntityId")
        if source_id not in entities or target_id not in entities:
            errors.append(
                f"Routing rule {route['id']!r} has an unresolved source or target entity."
            )
        elif route.get("routingBehavior") in {"copies", "transposes"}:
            route_edges.setdefault(source_id, []).append(target_id)
        source_control = route.get("sourceControlId")
        if source_control is not None and source_control not in controls:
            errors.append(
                f"Routing rule {route['id']!r} has unresolved sourceControlId."
            )
        key_range = route.get("inputRange", {})
        if key_range.get("minimum", 0) > key_range.get("maximum", 0):
            errors.append(f"Routing rule {route['id']!r} has a reversed input range.")
        transform = route.get("keyTransform", {})
        kind = transform.get("kind")
        if kind == "transpose" and not isinstance(transform.get("semitoneOffset"), int):
            errors.append(
                f"Routing rule {route['id']!r} transpose transform requires semitoneOffset."
            )
        if kind == "transpose" and isinstance(transform.get("semitoneOffset"), int):
            offset = transform["semitoneOffset"]
            if (
                key_range.get("minimum", 0) + offset < 0
                or key_range.get("maximum", 127) + offset > 127
            ):
                errors.append(
                    f"Routing rule {route['id']!r} transposes outside the MIDI key domain."
                )
        if kind == "fixed" and not transform.get("fixedOutputKeys"):
            errors.append(
                f"Routing rule {route['id']!r} fixed transform requires fixedOutputKeys."
            )
        if kind == "table":
            table_inputs = [
                entry.get("inputKey")
                for entry in transform.get("entries", [])
                if isinstance(entry, dict)
            ]
            if not table_inputs or len(table_inputs) != len(set(table_inputs)):
                errors.append(
                    f"Routing rule {route['id']!r} table transform needs unique entries."
                )
        for condition in route.get("conditions", []):
            check_condition(condition, f"Routing rule {route['id']!r}")

    def find_cycles(edges: dict[str, list[str]], label: str) -> None:
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(node: str) -> None:
            if node in visiting:
                errors.append(f"{label} contains a cycle at {node!r}.")
                return
            if node in visited:
                return
            visiting.add(node)
            for target in edges.get(node, []):
                visit(target)
            visiting.remove(node)
            visited.add(node)

        for node in edges:
            visit(node)

    find_cycles(route_edges, "Interaction routing graph")

    for timing in timings.values():
        evidence(timing, "Timing constraint")
        values = [
            timing.get(key)
            for key in ("minimum", "typical", "maximum")
            if isinstance(timing.get(key), (int, float))
        ]
        if values != sorted(values):
            errors.append(
                f"Timing constraint {timing['id']!r} has inconsistent minimum/typical/maximum ordering."
            )
        for target in timing.get("appliesToIds", []):
            if (
                target not in controls
                and target not in routes
                and target not in processes
                and target not in entities
            ):
                errors.append(
                    f"Timing constraint {timing['id']!r} has unresolved appliesToId {target!r}."
                )

    process_edges: dict[str, list[str]] = {}
    for process in processes.values():
        evidence(process, "Process model")
        children = process.get("childProcessIds", [])
        process_edges[process["id"]] = [
            child for child in children if child in processes
        ]
        for child in children:
            if child not in processes:
                errors.append(
                    f"Process model {process['id']!r} has unresolved child process {child!r}."
                )
        for timing_id in process.get("timingConstraintIds", []):
            if timing_id not in timings:
                errors.append(
                    f"Process model {process['id']!r} has unresolved timing constraint {timing_id!r}."
                )
        for action in process.get("actions", []):
            check_action(action, f"Process model {process['id']!r}")
        kind = process.get("processKind")
        termination = process.get("terminationPolicy")
        if kind in {"repeating", "stochastic"} and termination == "completed":
            errors.append(
                f"Process model {process['id']!r} is potentially unbounded and needs an explicit termination mechanism."
            )
        if termination == "maximum-iterations" and not isinstance(
            process.get("maximumIterations"), int
        ):
            errors.append(
                f"Process model {process['id']!r} requires maximumIterations."
            )
        if (
            termination == "duration-bound"
            and process.get("durationConstraintId") not in timings
        ):
            errors.append(
                f"Process model {process['id']!r} requires a resolved durationConstraintId."
            )
        if (
            termination in {"on-control-release", "external-cancel"}
            and process.get("cancellationControlId") not in controls
        ):
            errors.append(
                f"Process model {process['id']!r} requires a resolved cancellationControlId."
            )
        if kind == "compound" and len(process.get("actions", [])) + len(children) < 2:
            errors.append(
                f"Compound process model {process['id']!r} requires at least two actions or child processes."
            )
    find_cycles(process_edges, "Interaction process graph")

    for transfer in transfers.values():
        evidence(transfer, "Transfer function")
        inputs = [
            point.get("input")
            for point in transfer.get("points", [])
            if isinstance(point, dict)
        ]
        if inputs != sorted(inputs) or len(inputs) != len(set(inputs)):
            errors.append(
                f"Transfer function {transfer['id']!r} points must have unique ascending inputs."
            )
        for target in transfer.get("appliesToIds", []):
            if (
                target not in controls
                and target not in states
                and target not in routes
                and target not in playable_records["sampleMappings"]
            ):
                errors.append(
                    f"Transfer function {transfer['id']!r} has unresolved appliesToId {target!r}."
                )

    for render in renders.values():
        evidence(render, "Render binding")
        event_id = render.get("eventTypeId")
        process_id = render.get("processModelId")
        if event_id is not None and event_id not in events:
            errors.append(
                f"Render binding {render['id']!r} has unresolved eventTypeId."
            )
        if process_id is not None and process_id not in processes:
            errors.append(
                f"Render binding {render['id']!r} has unresolved processModelId."
            )
        for condition in render.get("conditions", []):
            check_condition(condition, f"Render binding {render['id']!r}")
        for mapping_id in render.get("sampleMappingIds", []):
            if mapping_id not in playable_records["sampleMappings"]:
                errors.append(
                    f"Render binding {render['id']!r} has unresolved sample mapping {mapping_id!r}."
                )
        for variant_id in render.get("sampleVariantIds", []):
            if variant_id not in playable_records["sampleVariants"]:
                errors.append(
                    f"Render binding {render['id']!r} has unresolved sample variant {variant_id!r}."
                )

    if STATEFUL_INTERACTION in capabilities and not (states and transitions):
        errors.append(
            "The stateful-interaction capability requires state variables and transitions."
        )
    if CONDITIONAL_ROUTING in capabilities and not any(
        route.get("conditions") for route in routes.values()
    ):
        errors.append(
            "The conditional-routing capability requires a routing rule with state conditions."
        )
    if COMPOSITE_ACTUATION in capabilities and not any(
        process.get("processKind") == "compound"
        and process.get("status") in usable_statuses
        for process in processes.values()
    ):
        errors.append(
            "The composite-actuation capability requires a usable compound process model."
        )
    if TIMED_PROCESS in capabilities and not any(
        process.get("timingConstraintIds") for process in processes.values()
    ):
        errors.append(
            "The timed-process capability requires a process bound to timing constraints."
        )
    if ACTUATOR_TRANSFER in capabilities and not any(
        transfer.get("status") in usable_statuses for transfer in transfers.values()
    ):
        errors.append(
            "The actuator-transfer capability requires a usable transfer function."
        )

    capture_states = capture_records["captureStates"]
    alignments = capture_records["eventAlignments"]
    take_sets = capture_records["takeSets"]
    derivations = capture_records["derivationMaps"]
    for capture_state in capture_states.values():
        evidence(capture_state, "Capture state")
        instrument = entities.get(capture_state.get("instrumentEntityId"))
        if instrument is None or instrument.get("kind") != "instrument":
            errors.append(
                f"Capture state {capture_state['id']!r} does not resolve an instrument entity."
            )
        assignment_ids = [
            item.get("stateVariableId")
            for item in capture_state.get("stateAssignments", [])
            if isinstance(item, dict)
        ]
        if len(assignment_ids) != len(set(assignment_ids)):
            errors.append(
                f"Capture state {capture_state['id']!r} assigns a state variable more than once."
            )
        for state_id in assignment_ids:
            if state_id not in states:
                errors.append(
                    f"Capture state {capture_state['id']!r} has unresolved state variable {state_id!r}."
                )

    for alignment in alignments.values():
        evidence(alignment, "Event alignment")
        audio = realizations.get(alignment.get("audioRealizationId"))
        event_log = realizations.get(alignment.get("eventLogRealizationId"))
        if audio is None or audio.get("technicalMetadata", {}).get("kind") != "audio":
            errors.append(
                f"Event alignment {alignment['id']!r} must reference an audio realization."
            )
        if event_log is None:
            errors.append(
                f"Event alignment {alignment['id']!r} has unresolved event-log realization."
            )
        frame_count = (
            audio.get("technicalMetadata", {}).get("frameCount") if audio else None
        )
        for event_mapping in alignment.get("eventMappings", []):
            if not isinstance(event_mapping, dict):
                continue
            event_id = event_mapping.get("eventTypeId")
            if event_id is not None and event_id not in events:
                errors.append(
                    f"Event alignment {alignment['id']!r} has unresolved eventTypeId {event_id!r}."
                )
            start, end = (
                event_mapping.get("startFrame"),
                event_mapping.get("endFrameExclusive"),
            )
            if isinstance(end, int) and isinstance(start, int) and end <= start:
                errors.append(
                    f"Event alignment {alignment['id']!r} has an empty event frame range."
                )
            if (
                isinstance(end, int)
                and isinstance(frame_count, int)
                and end > frame_count
            ):
                errors.append(
                    f"Event alignment {alignment['id']!r} exceeds audio frameCount."
                )

    for take_set in take_sets.values():
        evidence(take_set, "Take set")
        if take_set.get("captureStateId") not in capture_states:
            errors.append(f"Take set {take_set['id']!r} has unresolved captureStateId.")
        for realization_id in take_set.get("realizationIds", []):
            if realization_id not in realizations:
                errors.append(
                    f"Take set {take_set['id']!r} has unresolved realization {realization_id!r}."
                )
        if (
            take_set.get("setRole") == "round-robin"
            and take_set.get("selectionStatus") != "accepted"
        ):
            errors.append(
                f"Round-robin take set {take_set['id']!r} must be explicitly accepted."
            )

    derivation_edges: dict[str, list[str]] = {}
    for derivation in derivations.values():
        evidence(derivation, "Derivation map")
        source_id, derived_id = (
            derivation.get("sourceRealizationId"),
            derivation.get("derivedRealizationId"),
        )
        source_realization, derived_realization = (
            realizations.get(source_id),
            realizations.get(derived_id),
        )
        if source_realization is None or derived_realization is None:
            errors.append(
                f"Derivation map {derivation['id']!r} has an unresolved source or derived realization."
            )
        elif source_id == derived_id:
            errors.append(
                f"Derivation map {derivation['id']!r} cannot derive a realization from itself."
            )
        else:
            derivation_edges.setdefault(source_id, []).append(derived_id)
        frame_range = derivation.get("sourceFrameRange", {})
        start, end = (
            frame_range.get("startFrameInclusive"),
            frame_range.get("endFrameExclusive"),
        )
        if isinstance(start, int) and isinstance(end, int) and end <= start:
            errors.append(
                f"Derivation map {derivation['id']!r} has an empty source frame range."
            )
        frame_count = (
            source_realization.get("technicalMetadata", {}).get("frameCount")
            if source_realization
            else None
        )
        if isinstance(end, int) and isinstance(frame_count, int) and end > frame_count:
            errors.append(
                f"Derivation map {derivation['id']!r} exceeds source frameCount."
            )
        channel_count = (
            source_realization.get("technicalMetadata", {}).get("channelCount")
            if source_realization
            else None
        )
        if isinstance(channel_count, int) and any(
            index >= channel_count for index in derivation.get("channelMap", [])
        ):
            errors.append(
                f"Derivation map {derivation['id']!r} contains an out-of-range source channel."
            )
        for operation in derivation.get("operations", []):
            activity_id = (
                operation.get("activityId") if isinstance(operation, dict) else None
            )
            if activity_id is not None and activity_id not in known_activity_ids:
                errors.append(
                    f"Derivation map {derivation['id']!r} has unresolved operation activityId {activity_id!r}."
                )
    find_cycles(derivation_edges, "Capture derivation graph")

    if CAPTURE_EVENT_ALIGNMENT in capabilities and not any(
        alignment.get("status") in usable_statuses for alignment in alignments.values()
    ):
        errors.append(
            "The capture-event-alignment capability requires a usable event alignment."
        )

    for mapping in playable_records["sampleMappings"].values():
        if mapping.get("velocitySensitivity") == "transfer-function" and not any(
            mapping["id"] in transfer.get("appliesToIds", [])
            for transfer in transfers.values()
        ):
            errors.append(
                f"Sample mapping {mapping['id']!r} declares transfer-function velocity sensitivity without an applicable transfer function."
            )


def validate_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    errors = list(schema_errors(manifest, MANIFEST_SCHEMA))
    warnings: list[str] = []
    errors.extend(
        f"Manifest contains non-finite number at {path}."
        for path in non_finite_paths(manifest)
    )

    if manifest.get("$schema") != SCHEMA_URI:
        errors.append("Manifest uses the wrong VAO 0.3 schema IRI.")
    contexts = manifest.get("@context", [])
    if CONTEXT_URI not in contexts:
        errors.append("Manifest does not contain the VAO 0.3 context IRI.")

    global_ids: dict[str, str] = {}
    entities = records_by_id(manifest.get("entities"), "entities", errors, global_ids)
    relations = records_by_id(
        manifest.get("relations"), "relations", errors, global_ids
    )
    logical_assets = records_by_id(
        manifest.get("logicalAssets"), "logicalAssets", errors, global_ids
    )
    realizations = records_by_id(
        manifest.get("realizations"), "realizations", errors, global_ids
    )
    distributions = records_by_id(
        manifest.get("distributions"), "distributions", errors, global_ids
    )
    bindings = records_by_id(
        manifest.get("repositoryBindings"), "repositoryBindings", errors, global_ids
    )
    groups = records_by_id(
        manifest.get("assetGroups"), "assetGroups", errors, global_ids
    )
    rights = records_by_id(manifest.get("rights"), "rights", errors, global_ids)
    paradata = records_by_id(manifest.get("paradata"), "paradata", errors, global_ids)
    analyses = records_by_id(manifest.get("analyses"), "analyses", errors, global_ids)
    acoustics = (
        manifest.get("acoustics") if isinstance(manifest.get("acoustics"), dict) else {}
    )
    acoustic_records = {
        key: records_by_id(acoustics.get(key), f"acoustics.{key}", errors, global_ids)
        for key in (
            "coordinateFrames",
            "poses",
            "geometryBindings",
            "materialModels",
            "measurements",
            "responseSets",
            "metricSets",
            "audioScenes",
            "renderConfigurations",
        )
    }
    playable = (
        manifest.get("playable") if isinstance(manifest.get("playable"), dict) else {}
    )
    playable_records = {
        key: records_by_id(playable.get(key), f"playable.{key}", errors, global_ids)
        for key in (
            "signalRegions",
            "loopPointSets",
            "tuningMaps",
            "perspectiveGroups",
            "sampleVariants",
            "sampleMappings",
        )
    }
    interaction_model = (
        manifest.get("interactionModel")
        if isinstance(manifest.get("interactionModel"), dict)
        else {}
    )
    interaction_records = {
        key: records_by_id(
            interaction_model.get(key), f"interactionModel.{key}", errors, global_ids
        )
        for key in (
            "controls",
            "eventTypes",
            "protocolBindings",
            "stateVariables",
            "transitions",
            "routingRules",
            "processModels",
            "timingConstraints",
            "transferFunctions",
            "renderBindings",
        )
    }
    capture_documentation = (
        manifest.get("captureDocumentation")
        if isinstance(manifest.get("captureDocumentation"), dict)
        else {}
    )
    capture_records = {
        key: records_by_id(
            capture_documentation.get(key),
            f"captureDocumentation.{key}",
            errors,
            global_ids,
        )
        for key in ("captureStates", "eventAlignments", "takeSets", "derivationMaps")
    }
    known = set(global_ids)

    primary = manifest.get("primaryEntityId")
    if primary not in entities:
        errors.append("primaryEntityId does not resolve to a local entity.")
    focus = (
        manifest.get("focusEntityIds")
        if isinstance(manifest.get("focusEntityIds"), list)
        else []
    )
    if primary not in focus:
        errors.append("focusEntityIds must contain primaryEntityId.")
    for ref in focus:
        if ref not in entities:
            errors.append(f"focusEntityIds contains unresolved entity {ref!r}.")

    for relation in relations.values():
        if relation.get("subjectId") not in known:
            errors.append(f"Relation {relation['id']!r} has unresolved subjectId.")
        object_id = relation.get("objectId")
        if (
            object_id is not None
            and object_id not in known
            and not is_identifier(object_id)
        ):
            errors.append(f"Relation {relation['id']!r} has invalid objectId.")
        for key in ("evidenceIds", "generatedByIds"):
            for ref in relation.get(key, []):
                if ref not in known:
                    errors.append(
                        f"Relation {relation['id']!r} has unresolved {key} reference {ref!r}."
                    )

    for asset in logical_assets.values():
        for entity_id in asset.get("aboutEntityIds", []):
            if entity_id not in entities:
                errors.append(
                    f"Logical asset {asset['id']!r} has unresolved subject {entity_id!r}."
                )
        refs = asset.get("realizationIds", [])
        for ref in refs:
            if ref not in realizations:
                errors.append(
                    f"Logical asset {asset['id']!r} has unresolved realization {ref!r}."
                )
            elif realizations[ref].get("assetId") != asset["id"]:
                errors.append(
                    f"Logical asset/realization inverse mismatch for {ref!r}."
                )

    remote_realizations: set[str] = set()
    for realization in realizations.values():
        asset_id = realization.get("assetId")
        if asset_id not in logical_assets:
            errors.append(f"Realization {realization['id']!r} has unresolved assetId.")
        elif realization["id"] not in logical_assets[asset_id].get(
            "realizationIds", []
        ):
            errors.append(
                f"Realization/logical asset inverse mismatch for {realization['id']!r}."
            )
        for ref in realization.get("distributionIds", []):
            if ref not in distributions:
                errors.append(
                    f"Realization {realization['id']!r} has unresolved distribution {ref!r}."
                )
            else:
                remote_realizations.add(realization["id"])
        for ref in realization.get("rightsIds", []):
            if ref not in rights:
                errors.append(
                    f"Realization {realization['id']!r} has unresolved rights record {ref!r}."
                )
        for ref in realization.get("provenanceIds", []):
            if ref not in paradata and ref not in analyses and ref not in relations:
                errors.append(
                    f"Realization {realization['id']!r} has unresolved provenance {ref!r}."
                )
        technical = realization.get("technicalMetadata", {})
        if (
            technical.get("kind") == "geometry"
            and technical.get("coordinateFrameId")
            not in acoustic_records["coordinateFrames"]
        ):
            errors.append(
                f"Geometry realization {realization['id']!r} has unresolved coordinate frame."
            )
        if "ambisonicsOrder" in technical:
            order = technical.get("ambisonicsOrder")
            dimensionality = technical.get("ambisonicsDimensionality")
            expected = (
                (order + 1) ** 2
                if isinstance(order, int) and dimensionality == "3D"
                else (2 * order + 1 if isinstance(order, int) else None)
            )
            if technical.get("channelCount") != expected:
                errors.append(
                    f"Ambisonics realization {realization['id']!r} has inconsistent channelCount."
                )

    zenodo_used = False
    for distribution in distributions.values():
        if distribution.get("kind") == "repository":
            binding_id = distribution.get("repositoryBindingId")
            if binding_id not in bindings:
                errors.append(
                    f"Distribution {distribution['id']!r} has unresolved repository binding."
                )
                continue
            binding = bindings[binding_id]
            if (
                binding.get("repositoryType")
                == "https://w3id.org/modavis/vao/repository/zenodo"
            ):
                zenodo_used = True
                exact = distribution.get("persistentIdentifier", "")
                concept = distribution.get("conceptIdentifier")
                if concept is not None and exact == concept:
                    errors.append(
                        f"Zenodo distribution {distribution['id']!r} uses the concept PID as the exact PID."
                    )
                if not str(exact).startswith(
                    "https://doi.org/10.5072/zenodo."
                ) and not str(exact).startswith("https://doi.org/10.5281/zenodo."):
                    errors.append(
                        f"Zenodo distribution {distribution['id']!r} requires an exact Zenodo DOI URL."
                    )
        elif distribution.get("kind") == "pack-member":
            pack_id = distribution.get("packRealizationId")
            if pack_id not in realizations:
                errors.append(
                    f"Pack-member distribution {distribution['id']!r} has unresolved outer pack realization."
                )
            if not is_safe_path(distribution.get("memberPath")):
                errors.append(
                    f"Pack-member distribution {distribution['id']!r} has an unsafe member path."
                )

    profile_records = (
        manifest.get("profiles") if isinstance(manifest.get("profiles"), list) else []
    )
    materializable = (
        manifest.get("materializableProfiles")
        if isinstance(manifest.get("materializableProfiles"), list)
        else []
    )
    embedded_profile_ids = {
        record.get("id") for record in profile_records if isinstance(record, dict)
    }
    materializable_ids = {
        record.get("id") for record in materializable if isinstance(record, dict)
    }
    conforms = set(manifest.get("conformsTo", []))
    if CORE_PROFILE not in embedded_profile_ids or CORE_PROFILE not in conforms:
        errors.append(
            "Every VAO 0.3 carrier must embed and claim the Core 0.3 profile."
        )
    if DYNAMIC_PROFILE not in embedded_profile_ids or DYNAMIC_PROFILE not in conforms:
        errors.append(
            "Every VAO 0.3 carrier must embed and claim the Dynamic Delivery 0.3 profile."
        )
    if embedded_profile_ids & materializable_ids:
        errors.append("A profile cannot be both embedded and materializable.")
    for profile_id in embedded_profile_ids | materializable_ids | conforms:
        if (
            isinstance(profile_id, str)
            and profile_id.startswith(PROFILE_BASE)
            and profile_id.endswith("/0.2")
        ):
            errors.append(f"VAO 0.3 must not reuse VAO 0.2 profile IRI {profile_id!r}.")
    if zenodo_used and ZENODO_PROFILE not in embedded_profile_ids:
        errors.append(
            "A Zenodo binding requires the embedded Zenodo repository profile."
        )
    if not zenodo_used and ZENODO_PROFILE in embedded_profile_ids:
        errors.append(
            "The optional Zenodo profile must not be claimed without a Zenodo binding."
        )

    validate_acoustics(
        manifest,
        entities,
        logical_assets,
        realizations,
        paradata,
        analyses,
        acoustic_records,
        errors,
        warnings,
    )
    validate_playable(
        manifest,
        entities,
        realizations,
        paradata,
        analyses,
        relations,
        playable_records,
        errors,
    )
    validate_complex_interaction(
        manifest,
        entities,
        realizations,
        paradata,
        analyses,
        relations,
        interaction_records,
        capture_records,
        playable_records,
        errors,
    )

    for profile in materializable:
        if not isinstance(profile, dict):
            continue
        for group_id in profile.get("groupIds", []):
            if group_id not in groups:
                errors.append(
                    f"Materializable profile {profile.get('id')!r} has unresolved group {group_id!r}."
                )
            elif profile.get("id") not in groups[group_id].get(
                "materializesProfileIds", []
            ):
                errors.append(
                    f"Group {group_id!r} does not declare materializable profile {profile.get('id')!r}."
                )

    group_edges: dict[str, list[str]] = {}
    fallback_edges: dict[str, list[str]] = {}
    for group in groups.values():
        realization_ids = group.get("realizationIds", [])
        for ref in realization_ids:
            if ref not in realizations:
                errors.append(
                    f"Asset group {group['id']!r} has unresolved realization {ref!r}."
                )
        computed = sum(
            realizations[ref].get("byteSize", 0)
            for ref in set(realization_ids)
            if ref in realizations
        )
        if group.get("totalByteSize") != computed:
            errors.append(
                f"Asset group {group['id']!r} totalByteSize is {group.get('totalByteSize')}, expected {computed}."
            )
        dependencies = group.get("dependsOnGroupIds", [])
        group_edges[group["id"]] = dependencies
        for ref in dependencies:
            if ref not in groups:
                errors.append(
                    f"Asset group {group['id']!r} has unresolved dependency {ref!r}."
                )
        fallback = group.get("fallbackGroupId")
        fallback_edges[group["id"]] = [fallback] if fallback is not None else []
        if fallback is not None and fallback not in groups:
            errors.append(
                f"Asset group {group['id']!r} has unresolved fallback {fallback!r}."
            )

    def find_cycle(edges: dict[str, list[str]], label: str) -> None:
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(node: str) -> None:
            if node in visiting:
                errors.append(
                    f"Asset-group {label} graph contains a cycle at {node!r}."
                )
                return
            if node in visited:
                return
            visiting.add(node)
            for target in edges.get(node, []):
                if target in edges:
                    visit(target)
            visiting.remove(node)
            visited.add(node)

        for node in edges:
            visit(node)

    find_cycle(group_edges, "dependency")
    find_cycle(fallback_edges, "fallback")

    required_coverage = {manifest.get("id")} | set(logical_assets) | set(realizations)
    actual_coverage = {
        ref for record in rights.values() for ref in record.get("appliesToIds", [])
    }
    for ref in sorted(required_coverage - actual_coverage, key=str):
        errors.append(f"No rights record covers {ref!r}.")
    for record in rights.values():
        for ref in record.get("appliesToIds", []):
            if ref not in required_coverage and ref not in entities:
                warnings.append(
                    f"Rights record {record['id']!r} covers non-local identifier {ref!r}."
                )

    bootstrap = [
        group for group in groups.values() if group.get("qualityTier") == "bootstrap"
    ]
    if not bootstrap or not any(group.get("realizationIds") for group in bootstrap):
        errors.append("At least one non-empty bootstrap asset group is required.")
    for realization_id in set(realizations) - remote_realizations:
        if not any(
            realization_id in group.get("realizationIds", [])
            and group.get("availability") == "offline-required"
            for group in groups.values()
        ):
            warnings.append(
                f"Realization {realization_id!r} has no remote distribution and is not in an offline-required group."
            )

    return {
        "valid": not errors,
        "formatVersion": manifest.get("formatVersion"),
        "id": manifest.get("id"),
        "releaseId": manifest.get("release", {}).get("id")
        if isinstance(manifest.get("release"), dict)
        else None,
        "logicalAssetCount": len(logical_assets),
        "realizationCount": len(realizations),
        "distributionCount": len(distributions),
        "groupCount": len(groups),
        "errors": sorted(set(errors)),
        "warnings": sorted(set(warnings)),
    }


def validate_carrier_parts(
    manifest_data: bytes,
    carrier_data: bytes,
    payload_names: Iterable[str],
    payload_reader: Callable[[str], tuple[str, int]],
) -> dict[str, Any]:
    try:
        manifest = strict_json_bytes(manifest_data, MANIFEST_NAME)
        carrier = strict_json_bytes(carrier_data, CARRIER_NAME)
    except VAO03Error as exc:
        return {
            "valid": False,
            "formatVersion": None,
            "errors": [str(exc)],
            "warnings": [],
        }
    report = validate_manifest(manifest)
    errors = list(report["errors"])
    warnings = list(report["warnings"])
    errors.extend(schema_errors(carrier, CARRIER_SCHEMA))
    manifest_sha = sha256_bytes(manifest_data)
    if carrier.get("manifestSHA256") != manifest_sha:
        errors.append(
            "Carrier descriptor manifestSHA256 does not match exact manifest bytes."
        )
    if carrier.get("manifestByteSize") != len(manifest_data):
        errors.append(
            "Carrier descriptor manifestByteSize does not match exact manifest bytes."
        )
    release_id = (
        manifest.get("release", {}).get("id")
        if isinstance(manifest.get("release"), dict)
        else None
    )
    if carrier.get("releaseId") != release_id:
        errors.append("Carrier releaseId does not match manifest release.id.")

    realizations = {
        record.get("id"): record
        for record in manifest.get("realizations", [])
        if isinstance(record, dict)
    }
    groups = {
        record.get("id"): record
        for record in manifest.get("assetGroups", [])
        if isinstance(record, dict)
    }
    payload_by_normalized: dict[str, str] = {}
    for payload_name in payload_names:
        normalized = normalized_carrier_path(payload_name)
        if normalized in payload_by_normalized:
            errors.append(
                f"Carrier payload paths {payload_by_normalized[normalized]!r} and {payload_name!r} collide after NFC normalization."
            )
        else:
            payload_by_normalized[normalized] = payload_name
    payload_set = set(payload_by_normalized)
    mapped_paths: set[str] = set()
    embedded_ids: set[str] = set()
    verified_bytes = 0
    for mapping in carrier.get("embeddedRealizations", []):
        if not isinstance(mapping, dict):
            continue
        realization_id = mapping.get("realizationId")
        path = mapping.get("path")
        if realization_id in embedded_ids:
            errors.append(
                f"Carrier maps realization {realization_id!r} more than once."
            )
        embedded_ids.add(realization_id)
        normalized_path = (
            normalized_carrier_path(path)
            if isinstance(path, str)
            else f"<invalid:{path!r}>"
        )
        if normalized_path in mapped_paths:
            errors.append(f"Carrier maps payload path {path!r} more than once.")
        mapped_paths.add(normalized_path)
        realization = realizations.get(realization_id)
        if realization is None:
            errors.append(f"Carrier maps unknown realization {realization_id!r}.")
            continue
        if not is_safe_path(path, "payload") or normalized_path not in payload_set:
            errors.append(f"Carrier maps missing or unsafe payload path {path!r}.")
            continue
        try:
            digest, size = payload_reader(payload_by_normalized[normalized_path])
        except Exception as exc:
            errors.append(f"Cannot read embedded realization {path!r}: {exc}")
            continue
        if digest != realization.get("sha256") or size != realization.get("byteSize"):
            errors.append(
                f"Embedded realization {realization_id!r} fails byte size or SHA-256 verification."
            )
        else:
            verified_bytes += size
    for path in sorted(payload_set - mapped_paths):
        errors.append(f"Unindexed payload file {payload_by_normalized[path]!r}.")
    for path in sorted(mapped_paths - payload_set, key=str):
        errors.append(f"Mapped payload file {path!r} is missing.")

    def expand(group_id: str, seen: set[str]) -> set[str]:
        if group_id in seen or group_id not in groups:
            return set()
        seen.add(group_id)
        group = groups[group_id]
        required = set(group.get("realizationIds", []))
        for dependency in group.get("dependsOnGroupIds", []):
            required |= expand(dependency, seen)
        return required

    for group_id in carrier.get("completeGroupIds", []):
        if group_id not in groups:
            errors.append(
                f"Carrier completeGroupIds contains unknown group {group_id!r}."
            )
            continue
        missing = expand(group_id, set()) - embedded_ids
        if missing:
            errors.append(
                f"Carrier marks group {group_id!r} complete but lacks {sorted(missing)!r}."
            )
    if carrier.get("carrierMode") == "bootstrap" and not embedded_ids:
        errors.append("A bootstrap carrier must embed at least one realization.")
    if carrier.get("carrierMode") == "preservation-closure":
        all_group_ids = set(groups)
        if set(carrier.get("completeGroupIds", [])) != all_group_ids:
            errors.append(
                "A preservation-closure carrier must mark every asset group complete."
            )
        if set(realizations) - embedded_ids:
            errors.append(
                "A preservation-closure carrier must embed every realization."
            )

    report.update(
        {
            "valid": not errors,
            "errors": sorted(set(errors)),
            "warnings": sorted(set(warnings)),
            "manifestSHA256": manifest_sha,
            "embeddedRealizationCount": len(embedded_ids),
            "verifiedBytes": verified_bytes,
            "carrierMode": carrier.get("carrierMode"),
        }
    )
    return report


def workspace_payload_names(path: Path) -> list[str]:
    payload = path / "payload"
    if not payload.exists():
        return []
    return sorted(
        p.relative_to(path).as_posix()
        for p in payload.rglob("*")
        if p.is_file() and not p.is_symlink()
    )


def validate_workspace(path: Path) -> dict[str, Any]:
    if not path.is_dir():
        return {
            "valid": False,
            "errors": [f"Workspace does not exist: {path}"],
            "warnings": [],
        }
    try:
        manifest_data = (path / MANIFEST_NAME).read_bytes()
        carrier_data = (path / CARRIER_NAME).read_bytes()
        mimetype_data = (path / "mimetype").read_bytes()
    except OSError as exc:
        return {
            "valid": False,
            "errors": [f"Cannot read required VAO 0.3 file: {exc}"],
            "warnings": [],
        }

    if mimetype_data != MIMETYPE.encode("utf-8"):
        return {
            "valid": False,
            "errors": ["Workspace mimetype content is not the exact VAO media type."],
            "warnings": [],
        }

    def reader(name: str) -> tuple[str, int]:
        return sha256_file(path.joinpath(*PurePosixPath(name).parts))

    return validate_carrier_parts(
        manifest_data, carrier_data, workspace_payload_names(path), reader
    )


def validate_archive(path: Path) -> dict[str, Any]:
    errors: list[str] = []
    try:
        with zipfile.ZipFile(path, "r", allowZip64=True) as archive:
            infos = archive.infolist()
            if not infos:
                return {
                    "valid": False,
                    "errors": ["VAO archive is empty."],
                    "warnings": [],
                }
            if len(infos) > MAX_ENTRIES:
                errors.append("Archive exceeds the entry-count limit.")
            first = infos[0]
            if (
                first.filename != "mimetype"
                or first.compress_type != zipfile.ZIP_STORED
            ):
                errors.append("mimetype must be the first uncompressed archive entry.")
            names: set[str] = set()
            total = 0
            payload_names: list[str] = []
            allowed_exact = {"mimetype", MANIFEST_NAME, CARRIER_NAME}
            for info in infos:
                name = info.filename
                if info.is_dir():
                    continue
                if not is_safe_path(name):
                    errors.append(f"Unsafe archive path {name!r}.")
                    continue
                normalized_name = normalized_carrier_path(name)
                if normalized_name in names:
                    errors.append(
                        f"Duplicate archive path after NFC normalization: {name!r}."
                    )
                names.add(normalized_name)
                mode = (info.external_attr >> 16) & 0o170000
                if mode == stat.S_IFLNK:
                    errors.append(f"Symbolic link entry is forbidden: {name!r}.")
                if info.flag_bits & 0x1:
                    errors.append(f"Encrypted entry is forbidden: {name!r}.")
                if info.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
                    errors.append(f"Unsupported compression method for {name!r}.")
                if info.file_size > MAX_ENTRY_BYTES:
                    errors.append(f"Entry exceeds size limit: {name!r}.")
                total += info.file_size
                if name.startswith("payload/"):
                    payload_names.append(name)
                elif name not in allowed_exact:
                    errors.append(f"Unknown carrier entry {name!r}.")
            if total > MAX_TOTAL_BYTES:
                errors.append("Archive exceeds total uncompressed size limit.")
            for required in allowed_exact:
                if required not in names:
                    errors.append(f"Archive is missing required entry {required!r}.")
            if errors:
                return {"valid": False, "errors": sorted(set(errors)), "warnings": []}
            mimetype = archive.read("mimetype")
            if mimetype != MIMETYPE.encode("utf-8"):
                errors.append("mimetype content is not the VAO media type.")
            manifest_info = archive.getinfo(MANIFEST_NAME)
            carrier_info = archive.getinfo(CARRIER_NAME)
            if (
                manifest_info.file_size > MAX_MANIFEST_BYTES
                or carrier_info.file_size > MAX_DESCRIPTOR_BYTES
            ):
                errors.append("Manifest or carrier descriptor exceeds its size limit.")
            if errors:
                return {"valid": False, "errors": sorted(set(errors)), "warnings": []}
            manifest_data = archive.read(MANIFEST_NAME)
            carrier_data = archive.read(CARRIER_NAME)

            def reader(name: str) -> tuple[str, int]:
                with archive.open(name, "r") as stream:
                    return sha256_stream(stream)

            return validate_carrier_parts(
                manifest_data, carrier_data, payload_names, reader
            )
    except (OSError, zipfile.BadZipFile, KeyError, RuntimeError) as exc:
        return {
            "valid": False,
            "errors": [f"Cannot read VAO archive: {exc}"],
            "warnings": [],
        }


def detect_version(path: Path) -> str | None:
    try:
        if path.is_dir():
            manifest, _ = load_json(path / MANIFEST_NAME)
        else:
            with zipfile.ZipFile(path, "r", allowZip64=True) as archive:
                manifest = strict_json_bytes(archive.read(MANIFEST_NAME), MANIFEST_NAME)
        return (
            manifest.get("formatVersion")
            if isinstance(manifest.get("formatVersion"), str)
            else None
        )
    except Exception:
        return None


def validate(path: Path) -> dict[str, Any]:
    return validate_workspace(path) if path.is_dir() else validate_archive(path)


def zip_info(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_STORED
    info.create_system = 3
    info.external_attr = (stat.S_IFREG | 0o644) << 16
    info.flag_bits |= 0x800
    return info


def pack_workspace(workspace: Path, output: Path) -> None:
    report = validate_workspace(workspace)
    if not report["valid"]:
        raise VAO03Error("Workspace is invalid: " + "; ".join(report["errors"][:8]))
    if output.exists():
        raise VAO03Error(f"Output already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    payload_names = workspace_payload_names(workspace)
    try:
        with zipfile.ZipFile(
            output, "x", compression=zipfile.ZIP_STORED, allowZip64=True
        ) as archive:
            archive.writestr(zip_info("mimetype"), MIMETYPE.encode("utf-8"))
            archive.writestr(
                zip_info(MANIFEST_NAME), (workspace / MANIFEST_NAME).read_bytes()
            )
            archive.writestr(
                zip_info(CARRIER_NAME), (workspace / CARRIER_NAME).read_bytes()
            )
            for name in payload_names:
                archive.write(
                    workspace.joinpath(*PurePosixPath(name).parts),
                    name,
                    compress_type=zipfile.ZIP_STORED,
                )
            archive.comment = b"VAO/0.3"
        final = validate_archive(output)
        if not final["valid"]:
            output.unlink(missing_ok=True)
            raise VAO03Error(
                "Created carrier failed validation: " + "; ".join(final["errors"][:8])
            )
    except Exception:
        output.unlink(missing_ok=True)
        raise


def validate_descriptor(path: Path, schema_path: Path) -> dict[str, Any]:
    try:
        value, _ = load_json(path)
        errors = schema_errors(value, schema_path)
    except VAO03Error as exc:
        errors = [str(exc)]
    return {"valid": not errors, "errors": errors, "warnings": []}


def release_semantic_errors(value: dict[str, Any]) -> list[str]:
    """Checks publication-topology invariants that JSON Schema cannot express."""
    errors: list[str] = []
    publication = value.get("publication")
    if not isinstance(publication, dict):
        return errors
    root = publication.get("rootRecord")
    members = publication.get("familyMembers")
    if not isinstance(root, dict) or not isinstance(members, list):
        return errors
    records = [("rootRecord", root)] + [
        (f"familyMembers[{index}]", member.get("record", {}))
        for index, member in enumerate(members)
        if isinstance(member, dict)
    ]
    record_ids: set[str] = set()
    version_pids: set[str] = set()
    for label, record in records:
        if not isinstance(record, dict):
            continue
        record_id = record.get("id")
        if record_id in record_ids:
            errors.append(f"Publication record id {record_id!r} is duplicated.")
        elif isinstance(record_id, str):
            record_ids.add(record_id)
        version_pid = record.get("versionPersistentIdentifier")
        concept_pid = record.get("conceptPersistentIdentifier")
        if version_pid == concept_pid and version_pid is not None:
            errors.append(f"{label} uses its concept PID as its exact version PID.")
        if version_pid in version_pids:
            errors.append(f"Publication version PID {version_pid!r} is duplicated.")
        elif isinstance(version_pid, str):
            version_pids.add(version_pid)
        files = record.get("files")
        if isinstance(files, list):
            names = [
                file.get("fileIdentifier") for file in files if isinstance(file, dict)
            ]
            if len(names) != len(set(names)):
                errors.append(f"{label} contains duplicate file identifiers.")
            if "vao-release.json" in names:
                errors.append(
                    f"{label} must not self-hash vao-release.json in its own file inventory."
                )
    root_roles = [
        file.get("role") for file in root.get("files", []) if isinstance(file, dict)
    ]
    if root_roles.count("manifest") != 1:
        errors.append("The publication root must inventory exactly one manifest file.")
    if "carrier" not in root_roles:
        errors.append(
            "The publication root must inventory at least one bootstrap carrier."
        )
    return sorted(set(errors))


def validate_release_descriptor(path: Path) -> dict[str, Any]:
    try:
        value, _ = load_json(path)
        errors = schema_errors(value, RELEASE_SCHEMA) + release_semantic_errors(value)
    except VAO03Error as exc:
        errors = [str(exc)]
    return {"valid": not errors, "errors": sorted(set(errors)), "warnings": []}


def validate_zenodo_metadata_descriptor(path: Path) -> dict[str, Any]:
    try:
        value, _ = load_json(path)
        errors = schema_errors(value, ZENODO_METADATA_SCHEMA)
        metadata = value.get("metadata", {})
        if isinstance(metadata, dict) and "VAO 0.3" not in metadata.get("keywords", []):
            errors.append("Zenodo metadata keywords must include 'VAO 0.3'.")
    except VAO03Error as exc:
        errors = [str(exc)]
    return {"valid": not errors, "errors": sorted(set(errors)), "warnings": []}


def validate_publication_set(
    release_path: Path, metadata_paths: Iterable[Path]
) -> dict[str, Any]:
    """Validate a release descriptor and the Zenodo metadata projections for its records."""
    try:
        release, _ = load_json(release_path)
        documents = [load_json(path)[0] for path in metadata_paths]
    except VAO03Error as exc:
        return {"valid": False, "errors": [str(exc)], "warnings": []}
    errors = schema_errors(release, RELEASE_SCHEMA) + release_semantic_errors(release)
    for document in documents:
        errors.extend(schema_errors(document, ZENODO_METADATA_SCHEMA))
        metadata = document.get("metadata", {})
        if isinstance(metadata, dict) and "VAO 0.3" not in metadata.get("keywords", []):
            errors.append("Zenodo metadata keywords must include 'VAO 0.3'.")

    publication = release.get("publication", {})
    root = publication.get("rootRecord", {}) if isinstance(publication, dict) else {}
    members = (
        publication.get("familyMembers", []) if isinstance(publication, dict) else []
    )
    records: dict[str, dict[str, Any]] = {}
    if isinstance(root, dict) and isinstance(root.get("id"), str):
        records[root["id"]] = root
    for member in members if isinstance(members, list) else []:
        if (
            isinstance(member, dict)
            and isinstance(member.get("record"), dict)
            and isinstance(member["record"].get("id"), str)
        ):
            records[member["record"]["id"]] = member["record"]

    docs_by_id: dict[str, dict[str, Any]] = {}
    for document in documents:
        record_id = document.get("publicationRecordId")
        if record_id in docs_by_id:
            errors.append(
                f"Zenodo metadata for publication record {record_id!r} is duplicated."
            )
        elif isinstance(record_id, str):
            docs_by_id[record_id] = document
        if document.get("releaseId") != release.get("releaseId"):
            errors.append(f"Zenodo metadata for {record_id!r} has the wrong releaseId.")
        if record_id not in records:
            errors.append(
                f"Zenodo metadata names unknown publication record {record_id!r}."
            )

    zenodo_ids = {
        record_id
        for record_id, record in records.items()
        if record.get("repositoryType") == ZENODO_REPOSITORY_TYPE
    }
    for record_id in sorted(zenodo_ids - set(docs_by_id)):
        errors.append(
            f"Zenodo publication record {record_id!r} lacks a metadata projection."
        )
    for record_id in sorted(set(docs_by_id) - zenodo_ids):
        errors.append(
            f"Metadata projection {record_id!r} does not describe a Zenodo publication record."
        )

    topology = publication.get("topology") if isinstance(publication, dict) else None
    root_id = root.get("id") if isinstance(root, dict) else None
    root_doc = docs_by_id.get(root_id)
    if root_doc:
        expected_role = (
            "monolithic-root" if topology == "single-record" else "family-root"
        )
        if root_doc.get("recordRole") != expected_role:
            errors.append(f"Root Zenodo metadata recordRole must be {expected_role!r}.")
        if root_doc.get("metadata", {}).get("version") != release.get("contentVersion"):
            errors.append(
                "Root Zenodo metadata version must equal release contentVersion."
            )

    def relation_pairs(document: dict[str, Any] | None) -> set[tuple[str, str]]:
        if not document:
            return set()
        related = document.get("metadata", {}).get("related_identifiers", [])
        return {
            (item.get("identifier"), item.get("relation"))
            for item in related
            if isinstance(item, dict)
            and isinstance(item.get("identifier"), str)
            and isinstance(item.get("relation"), str)
        }

    root_relations = relation_pairs(root_doc)
    root_pid = (
        root.get("versionPersistentIdentifier") if isinstance(root, dict) else None
    )
    for member in members if isinstance(members, list) else []:
        if not isinstance(member, dict) or not isinstance(member.get("record"), dict):
            continue
        record = member["record"]
        record_id = record.get("id")
        member_doc = docs_by_id.get(record_id)
        if member_doc and member_doc.get("recordRole") != "family-member":
            errors.append(
                f"Family-member metadata {record_id!r} must use recordRole 'family-member'."
            )
        version_pid = record.get("versionPersistentIdentifier")
        relation = member.get("relationFromRoot")
        if root_doc and (version_pid, relation) not in root_relations:
            errors.append(
                f"Root Zenodo metadata lacks {relation!r} relation to exact member PID {version_pid!r}."
            )
        concept_pid = record.get("conceptPersistentIdentifier")
        if concept_pid and (concept_pid, relation) in root_relations:
            errors.append(
                f"Root Zenodo metadata uses concept PID {concept_pid!r} for a family relation."
            )
        inverse = member.get("inverseRelationFromMember")
        if (
            inverse
            and member_doc
            and (root_pid, inverse) not in relation_pairs(member_doc)
        ):
            errors.append(
                f"Member metadata {record_id!r} lacks inverse {inverse!r} relation to exact root PID {root_pid!r}."
            )
    return {"valid": not errors, "errors": sorted(set(errors)), "warnings": []}


def create_receipt(
    workspace: Path, output: Path, instance_id: str | None = None
) -> None:
    report = validate_workspace(workspace)
    if not report["valid"]:
        raise VAO03Error(
            "Cannot issue receipt for invalid workspace: "
            + "; ".join(report["errors"][:8])
        )
    manifest, manifest_data = load_json(workspace / MANIFEST_NAME)
    carrier, _ = load_json(workspace / CARRIER_NAME)
    realizations = {r["id"]: r for r in manifest["realizations"]}
    embedded = {item["realizationId"] for item in carrier["embeddedRealizations"]}
    acquisitions = []
    for realization_id in sorted(embedded):
        realization = realizations[realization_id]
        acquisitions.append(
            {
                "realizationId": realization_id,
                "distributionId": "urn:vao:distribution:carrier-embedded",
                "byteSize": realization["byteSize"],
                "sha256": realization["sha256"],
                "status": "verified",
                "verifiedAt": now(),
            }
        )
    receipt = {
        "$schema": "https://w3id.org/modavis/vao/0.3/schema/materialization-receipt.json",
        "type": "VAOMaterializationReceipt",
        "formatVersion": FORMAT_VERSION,
        "releaseId": manifest["release"]["id"],
        "manifestSHA256": sha256_bytes(manifest_data),
        "instanceId": instance_id or f"urn:uuid:{uuid.uuid4()}",
        "createdAt": now(),
        "selectedGroupIds": carrier["completeGroupIds"],
        "acquisitions": acquisitions,
        "profileStates": [
            {"profileId": p["id"], "state": "embedded-valid"}
            for p in manifest["profiles"]
        ],
    }
    errors = schema_errors(receipt, RECEIPT_SCHEMA)
    if errors:
        raise VAO03Error("Generated receipt is invalid: " + "; ".join(errors))
    write_json(output, receipt)


def technical_metadata_for(
    path: Path, media_type: str, properties: dict[str, Any], warnings: list[str]
) -> dict[str, Any]:
    if media_type == "model/gltf-binary" or media_type.startswith("model/"):
        frame = next(
            (
                value
                for key, value in properties.items()
                if key.endswith("coordinateFrameId") and is_identifier(value)
            ),
            None,
        )
        if frame:
            return {
                "kind": "geometry",
                "coordinateFrameId": frame,
                "coordinateUnit": "http://qudt.org/vocab/unit/M",
                "handedness": "right",
                "upAxis": "Y",
                "lod": 0,
            }
        warnings.append(
            f"Geometry {path} lacks a typed coordinate frame; migrated as 'other' pending review."
        )
        return {"kind": "other"}
    if media_type.startswith("audio/"):
        try:
            import wave

            with wave.open(str(path), "rb") as audio:
                return {
                    "kind": "audio",
                    "sampleRate": audio.getframerate(),
                    "channelCount": audio.getnchannels(),
                    "bitDepth": audio.getsampwidth() * 8,
                    "audioContainer": "WAVE",
                }
        except Exception:
            warnings.append(
                f"Audio {path} could not be parsed for typed metadata; migrated as 'other' pending review."
            )
            return {"kind": "other"}
    if media_type.startswith("image/"):
        return {"kind": "image"}
    if media_type.startswith("text/") or media_type in {"application/pdf"}:
        return {"kind": "document"}
    if media_type in {"application/json", "application/ld+json", "text/csv"}:
        return {"kind": "data"}
    return {"kind": "other"}


def migrate_02(source: Path, destination: Path) -> dict[str, Any]:
    source_report = vao02.validate_workspace(source)
    if not source_report["valid"]:
        raise VAO03Error(
            "Source VAO 0.2 workspace is invalid: "
            + "; ".join(source_report["errors"][:8])
        )
    if destination.exists():
        raise VAO03Error(f"Destination already exists: {destination}")
    source_manifest, source_bytes = load_json(source / MANIFEST_NAME)
    source_playable_capabilities = {
        capability
        for profile in source_manifest.get("profiles", [])
        if isinstance(profile, dict) and profile.get("id") == vao02.PLAYABLE_PROFILE
        for capability in profile.get("requiredCapabilities", [])
    }
    if vao02.SAMPLED_INSTRUMENT_PLAYBACK in source_playable_capabilities:
        raise VAO03Error(
            "VAO 0.2 sampled-instrument migration requires producer enrichment for the 0.3.3 "
            "closed playable model (exact realization variants, mapping ranges, tuning, loop/release "
            "selection, and evidence status); the source was not modified."
        )
    if "acoustics" in source_manifest:
        raise VAO03Error(
            "VAO 0.2 Spatial/Acoustics migration requires producer enrichment for the 0.3.3 "
            "closed scene model (stable measurement IDs, exact realization sample/channel layout, "
            "and verified coordinate transforms); the source was not modified."
        )
    release_id = f"urn:uuid:{uuid.uuid4()}"
    warnings: list[str] = []
    mappings: list[dict[str, str]] = []
    rights: list[dict[str, Any]] = []
    asset_ids = [asset["id"] for asset in source_manifest.get("assets", [])]
    realization_ids = [
        asset["id"] + ":realization:0.3" for asset in source_manifest.get("assets", [])
    ]
    for index, record in enumerate(source_manifest.get("rights", [])):
        right_id = (
            record.get("id")
            if is_identifier(record.get("id"))
            else f"urn:vao:rights:migrated:{index + 1}"
        )
        statement = (
            record.get("statement")
            if isinstance(record.get("statement"), dict)
            else {"und": str(record.get("accessCondition", "Rights unknown"))}
        )
        converted = {
            "id": right_id,
            "appliesToIds": [source_manifest["id"], *asset_ids, *realization_ids],
            "statement": statement,
            "access": "unknown",
        }
        if is_identifier(record.get("license")):
            converted["license"] = record["license"]
        rights.append(converted)
    if not rights:
        rights = [
            {
                "id": "urn:vao:rights:migrated:unknown",
                "appliesToIds": [source_manifest["id"], *asset_ids, *realization_ids],
                "statement": {
                    "und": "Rights not stated in source VAO 0.2 manifest; review required."
                },
                "access": "unknown",
            }
        ]
        warnings.append(
            "Source had no rights record; an explicit unknown-rights record was added."
        )
    rights_ids = [record["id"] for record in rights]

    logical_assets: list[dict[str, Any]] = []
    realizations: list[dict[str, Any]] = []
    mappings_for_carrier: list[dict[str, str]] = []
    for asset in source_manifest.get("assets", []):
        realization_id = asset["id"] + ":realization:0.3"
        logical_assets.append(
            {
                "id": asset["id"],
                "type": "LogicalAsset",
                "roles": asset["roles"],
                "aboutEntityIds": asset["aboutEntityIds"],
                "realizationIds": [realization_id],
                "properties": asset.get("properties", {}),
            }
        )
        provenance = [
            record["id"]
            for record in source_manifest.get("paradata", [])
            if asset["id"] in record.get("outputIds", [])
        ]
        realizations.append(
            {
                "id": realization_id,
                "type": "Realization",
                "assetId": asset["id"],
                "variantSetId": asset["id"],
                "qualityTier": "bootstrap",
                "mediaType": asset["mediaType"],
                "byteSize": asset["byteSize"],
                "sha256": asset["sha256"],
                "representationStatus": asset["representationStatus"],
                "rightsIds": rights_ids,
                "provenanceIds": provenance,
                "technicalMetadata": technical_metadata_for(
                    source / asset["path"],
                    asset["mediaType"],
                    asset.get("properties", {}),
                    warnings,
                ),
                "distributionIds": [],
            }
        )
        mappings_for_carrier.append(
            {"realizationId": realization_id, "path": asset["path"]}
        )
        mappings.append(
            {
                "sourceAssetId": asset["id"],
                "logicalAssetId": asset["id"],
                "realizationId": realization_id,
            }
        )

    profile_map: dict[str, dict[str, Any]] = {}
    for profile in source_manifest.get("profiles", []):
        profile_id = profile.get("id", "").replace("/0.2", "/0.3")
        profile_map[profile_id] = {
            "id": profile_id,
            "version": "0.3",
            "requiredCapabilities": profile.get("requiredCapabilities", []),
        }
    for profile_id, capabilities in (
        (
            CORE_PROFILE,
            [
                "https://w3id.org/modavis/vao/vocab/capability/core-graph",
                "https://w3id.org/modavis/vao/vocab/capability/fixity",
            ],
        ),
        (
            DYNAMIC_PROFILE,
            [
                "https://w3id.org/modavis/vao/vocab/capability/immutable-release",
                "https://w3id.org/modavis/vao/vocab/capability/carrier-mapping",
            ],
        ),
    ):
        profile_map.setdefault(
            profile_id,
            {"id": profile_id, "version": "0.3", "requiredCapabilities": capabilities},
        )
    profiles = list(profile_map.values())
    group_id = "urn:vao:group:migrated-bootstrap"
    manifest = {
        "$schema": SCHEMA_URI,
        "@context": [CONTEXT_URI],
        "type": "VirtualAcousticObject",
        "formatVersion": FORMAT_VERSION,
        "id": source_manifest["id"],
        "release": {
            "id": release_id,
            "revision": int(source_manifest.get("revision", 1)) + 1,
            "contentVersion": f"{source_manifest.get('formatVersion', '0.2.2')}-migrated",
            "migratedFromManifestSHA256": sha256_bytes(source_bytes),
        },
        "createdAt": source_manifest.get("createdAt", now()),
        "modifiedAt": now(),
        "title": source_manifest["title"],
        "description": source_manifest.get(
            "description", {"und": "Migrated from VAO 0.2.2."}
        ),
        "conformsTo": [profile["id"] for profile in profiles],
        "profiles": profiles,
        "materializableProfiles": [],
        "modavisBinding": source_manifest["modavisBinding"],
        "primaryEntityId": source_manifest["primaryEntityId"],
        "focusEntityIds": source_manifest["focusEntityIds"],
        "entities": source_manifest["entities"],
        "relations": source_manifest["relations"],
        "paradata": source_manifest.get("paradata", []),
        "analyses": source_manifest.get("analyses", []),
        "logicalAssets": logical_assets,
        "realizations": realizations,
        "distributions": [],
        "repositoryBindings": [],
        "assetGroups": [
            {
                "id": group_id,
                "type": "AssetGroup",
                "labels": {"en": "Migrated bootstrap"},
                "selectionSetId": "bootstrap",
                "qualityTier": "bootstrap",
                "availability": "offline-required",
                "selectionPolicy": "independent",
                "realizationIds": realization_ids,
                "dependsOnGroupIds": [],
                "totalByteSize": sum(
                    a["byteSize"] for a in source_manifest.get("assets", [])
                ),
                "requiredCapabilities": [],
                "materializesProfileIds": [],
                "cachePolicy": {"evictable": False, "priority": 100},
            }
        ],
        "rights": rights,
        "integrity": {
            "algorithm": "sha256",
            "manifestDigestLocation": "external-release-and-carrier-descriptors",
            "carrierDescriptor": CARRIER_NAME,
        },
    }
    destination.mkdir(parents=True)
    try:
        for name in workspace_payload_names(source):
            target = destination.joinpath(*PurePosixPath(name).parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source.joinpath(*PurePosixPath(name).parts), target)
        manifest_data = json_bytes(manifest)
        (destination / MANIFEST_NAME).write_bytes(manifest_data)
        carrier = {
            "$schema": "https://w3id.org/modavis/vao/0.3/schema/carrier.json",
            "type": "VAOCarrier",
            "formatVersion": FORMAT_VERSION,
            "releaseId": release_id,
            "manifestSHA256": sha256_bytes(manifest_data),
            "manifestByteSize": len(manifest_data),
            "carrierMode": "bootstrap",
            "embeddedRealizations": mappings_for_carrier,
            "completeGroupIds": [group_id],
        }
        write_json(destination / CARRIER_NAME, carrier)
        (destination / "mimetype").write_bytes(MIMETYPE.encode("utf-8"))
        report = validate_workspace(destination)
        if not report["valid"]:
            raise VAO03Error(
                "Migrated workspace failed VAO 0.3 validation: "
                + "; ".join(report["errors"][:12])
            )
        migration_report = {
            "type": "VAOMigrationReport",
            "sourceFormatVersion": source_manifest["formatVersion"],
            "targetFormatVersion": FORMAT_VERSION,
            "sourceManifestSHA256": sha256_bytes(source_bytes),
            "targetManifestSHA256": sha256_bytes(manifest_data),
            "releaseId": release_id,
            "mappings": mappings,
            "warnings": warnings,
        }
        write_json(destination / "MIGRATION_REPORT.json", migration_report)
        return migration_report
    except Exception:
        shutil.rmtree(destination, ignore_errors=True)
        raise


def print_report(report: dict[str, Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True))
        return
    print(
        ("VALID" if report.get("valid") else "INVALID")
        + f": VAO {report.get('formatVersion', 'unknown')} {report.get('id', '')}".rstrip()
    )
    for warning in report.get("warnings", []):
        print(f"warning: {warning}")
    for error in report.get("errors", []):
        print(f"error: {error}")


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="VAO 0.3 reference manager")
    sub = result.add_subparsers(dest="command", required=True)
    validate_cmd = sub.add_parser("validate")
    validate_cmd.add_argument("path")
    validate_cmd.add_argument("--json", action="store_true")
    pack_cmd = sub.add_parser("pack")
    pack_cmd.add_argument("workspace")
    pack_cmd.add_argument("output")
    migrate_cmd = sub.add_parser("migrate-0.2")
    migrate_cmd.add_argument("source")
    migrate_cmd.add_argument("destination")
    receipt_cmd = sub.add_parser("receipt")
    receipt_cmd.add_argument("workspace")
    receipt_cmd.add_argument("output")
    descriptor_cmd = sub.add_parser("validate-descriptor")
    descriptor_cmd.add_argument(
        "kind", choices=["release", "pack", "receipt", "zenodo-metadata"]
    )
    descriptor_cmd.add_argument("path")
    descriptor_cmd.add_argument("--json", action="store_true")
    publication_cmd = sub.add_parser("validate-publication")
    publication_cmd.add_argument("release")
    publication_cmd.add_argument("metadata", nargs="+")
    publication_cmd.add_argument("--json", action="store_true")
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "validate":
            report = validate(Path(args.path))
            print_report(report, args.json)
            return 0 if report["valid"] else 1
        if args.command == "pack":
            pack_workspace(Path(args.workspace), Path(args.output))
            print(args.output)
            return 0
        if args.command == "migrate-0.2":
            report = migrate_02(Path(args.source), Path(args.destination))
            print(json.dumps(report, indent=2, sort_keys=True))
            return 0
        if args.command == "receipt":
            create_receipt(Path(args.workspace), Path(args.output))
            print(args.output)
            return 0
        if args.command == "validate-publication":
            report = validate_publication_set(
                Path(args.release), [Path(path) for path in args.metadata]
            )
            print_report(report, args.json)
            return 0 if report["valid"] else 1
        schemas = {"pack": PACK_SCHEMA, "receipt": RECEIPT_SCHEMA}
        if args.kind == "release":
            report = validate_release_descriptor(Path(args.path))
        elif args.kind == "zenodo-metadata":
            report = validate_zenodo_metadata_descriptor(Path(args.path))
        else:
            report = validate_descriptor(Path(args.path), schemas[args.kind])
        print_report(report, args.json)
        return 0 if report["valid"] else 1
    except (VAO03Error, OSError, ValueError, zipfile.BadZipFile) as exc:
        print(f"vao03: {exc}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
