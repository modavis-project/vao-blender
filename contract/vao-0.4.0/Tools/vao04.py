#!/usr/bin/env python3
"""VAO 0.4.0 reference validator, carrier writer, and 0.3.3 migrator."""

from __future__ import annotations

import argparse
import copy
from datetime import datetime
from fractions import Fraction
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import sys
import unicodedata
import uuid
import zipfile
from typing import Any, Callable, Iterable
from urllib.parse import urlsplit

from jsonschema import Draft202012Validator, FormatChecker

import vao03
import vao04_runtime
import vao_resources


FORMAT_VERSION = "0.4.0"
MAX_SAFE_INTEGER = (1 << 53) - 1
MAX_INLINE_COVARIANCE_DIMENSION = 64
MAX_TOTAL_COVARIANCE_CELLS = 262_144
MAX_JSON_DEPTH = 128
MAX_PATH_SEGMENTS = 128
AFFINE_CONDITION_THRESHOLD = 1e-12
TWO_DIMENSIONAL_EMBEDDING_TOLERANCE = 1e-12
QUATERNION_NORM_SQUARED_TOLERANCE = 1e-9
MIMETYPE = vao03.MIMETYPE
MANIFEST_NAME = vao03.MANIFEST_NAME
CARRIER_NAME = vao03.CARRIER_NAME
BASE = f"https://w3id.org/modavis/vao/{FORMAT_VERSION}"
SCHEMA_URI = f"{BASE}/schema/manifest.json"
CONTEXT_URI = f"{BASE}/context.jsonld"
PROFILE_BASE = "https://w3id.org/modavis/vao/profile/"
CORE_PROFILE = PROFILE_BASE + f"core/{FORMAT_VERSION}"
DYNAMIC_PROFILE = PROFILE_BASE + f"dynamic-delivery/{FORMAT_VERSION}"
SCIENTIFIC_PROFILE = PROFILE_BASE + f"scientific/{FORMAT_VERSION}"
MULTIMODAL_PROFILE = PROFILE_BASE + f"multimodal/{FORMAT_VERSION}"
PHYSICAL_PROFILE = PROFILE_BASE + f"physical-instrument/{FORMAT_VERSION}"
RUNTIME_PROFILE = PROFILE_BASE + f"deterministic-runtime/{FORMAT_VERSION}"
SPATIAL_PROFILE = PROFILE_BASE + f"spatial/{FORMAT_VERSION}"
ACOUSTICS_PROFILE = PROFILE_BASE + f"acoustics/{FORMAT_VERSION}"
PLAYABLE_PROFILE = PROFILE_BASE + f"playable/{FORMAT_VERSION}"
ZENODO_PROFILE = PROFILE_BASE + f"repository/zenodo/{FORMAT_VERSION}"
CAPABILITY_BASE = "https://w3id.org/modavis/vao/vocab/capability/"
REQUIRED_PROFILE_CAPABILITIES = {
    CORE_PROFILE: {CAPABILITY_BASE + "core-graph", CAPABILITY_BASE + "fixity"},
    DYNAMIC_PROFILE: {
        CAPABILITY_BASE + "immutable-release",
        CAPABILITY_BASE + "carrier-mapping",
    },
    PLAYABLE_PROFILE: {CAPABILITY_BASE + "interaction"},
    SCIENTIFIC_PROFILE: {CAPABILITY_BASE + "typed-scientific-provenance"},
    MULTIMODAL_PROFILE: {CAPABILITY_BASE + "multimodal-synchronization"},
    PHYSICAL_PROFILE: {CAPABILITY_BASE + "physical-system-topology"},
    RUNTIME_PROFILE: {CAPABILITY_BASE + "deterministic-render-trace"},
    SPATIAL_PROFILE: {CAPABILITY_BASE + "spatial"},
}
ACOUSTIC_CAPABILITIES = {
    CAPABILITY_BASE + name
    for name in (
        "semantic-building-model",
        "measured-impulse-response",
        "simulated-impulse-response",
        "position-registered-acoustic-scene",
        "visual-acoustic-scene",
        "spatial-response-field",
        "spatial-audio-scene",
        "source-directivity",
        "room-acoustic-metrics",
        "building-acoustic-performance",
        "tracked-listener-convolution",
        "tracked-sources",
        "geometry-acoustic-rendering",
        "hybrid-acoustic-rendering",
        "learned-acoustic-field",
    )
}
SCHEMA_DIR = vao_resources.schema_directory()
MANIFEST_SCHEMA = SCHEMA_DIR / f"vao-manifest-{FORMAT_VERSION}.schema.json"
CARRIER_SCHEMA = SCHEMA_DIR / f"vao-carrier-{FORMAT_VERSION}.schema.json"
RELEASE_SCHEMA = SCHEMA_DIR / f"vao-release-{FORMAT_VERSION}.schema.json"
PACK_SCHEMA = SCHEMA_DIR / f"vao-pack-manifest-{FORMAT_VERSION}.schema.json"
RECEIPT_SCHEMA = (
    SCHEMA_DIR / f"vao-materialization-receipt-{FORMAT_VERSION}.schema.json"
)
ZENODO_METADATA_SCHEMA = (
    SCHEMA_DIR / f"vao-zenodo-metadata-{FORMAT_VERSION}.schema.json"
)
MAX_ENTRIES = vao03.MAX_ENTRIES
MAX_MANIFEST_BYTES = vao03.MAX_MANIFEST_BYTES
MAX_DESCRIPTOR_BYTES = vao03.MAX_DESCRIPTOR_BYTES
MAX_ENTRY_BYTES = vao03.MAX_ENTRY_BYTES
MAX_TOTAL_BYTES = vao03.MAX_TOTAL_BYTES
# Deflate can represent hostile amounts of output in a tiny input.  The ratio
# check is an implementation safety limit, not a constraint on the VAO model.
MAX_COMPRESSION_RATIO = 1_000
RATIO_CHECK_MIN_BYTES = 64 * 1024 * 1024


class VAO04Error(vao03.VAO03Error):
    pass


json_bytes = vao03.json_bytes
sha256_bytes = vao03.sha256_bytes
strict_json_bytes = vao03.strict_json_bytes
load_json = vao03.load_json
write_json = vao03.write_json
is_identifier = vao03.is_identifier
normalized_carrier_path = vao03.normalized_carrier_path


def is_safe_path(value: Any, prefix: str | None = None) -> bool:
    """Apply the VAO path grammar plus the 0.4 control-character exclusion."""
    return vao03.is_safe_path(value, prefix) and not any(
        ord(character) < 0x20 or ord(character) == 0x7F for character in value
    )


def portable_carrier_path_key(value: str) -> str:
    """Comparison key for canonical-Unicode and case-insensitive filesystems."""
    return normalized_carrier_path(value).casefold()


def _open_regular_nofollow(path: Path) -> Any:
    """Open a regular file without following a final-component symbolic link."""
    if not hasattr(os, "O_NOFOLLOW") and path.is_symlink():
        raise VAO04Error(f"Refusing symbolic link {path}.")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise VAO04Error(f"Cannot safely open {path}: {exc}") from exc
    try:
        stream = os.fdopen(descriptor, "rb")
    except Exception:
        os.close(descriptor)
        raise
    opened_stat = os.fstat(stream.fileno())
    if not stat.S_ISREG(opened_stat.st_mode):
        stream.close()
        raise VAO04Error(f"Refusing non-regular file {path}.")
    if opened_stat.st_nlink > 1:
        stream.close()
        raise VAO04Error(f"Refusing hard-linked workspace file {path}.")
    return stream


def _read_bounded_regular(path: Path, maximum: int, label: str) -> bytes:
    with _open_regular_nofollow(path) as stream:
        return _read_stream_bounded(stream, maximum, label)


def _read_stream_bounded(stream: Any, maximum: int, label: str) -> bytes:
    data = stream.read(maximum + 1)
    if len(data) > maximum:
        raise VAO04Error(f"{label} exceeds the reference validator size limit.")
    return data


def sha256_stream_bounded(stream: Any, maximum: int) -> tuple[str, int]:
    """Hash at most ``maximum`` bytes and reject growth while streaming."""
    digest = hashlib.sha256()
    size = 0
    while True:
        block = stream.read(min(vao03.CHUNK, maximum - size + 1))
        if not block:
            return digest.hexdigest(), size
        size += len(block)
        if size > maximum:
            raise VAO04Error("Payload exceeds its permitted bound while streaming.")
        digest.update(block)


def _copy_stream_bounded(source: Any, target: Any, maximum: int) -> int:
    size = 0
    while True:
        block = source.read(min(vao03.CHUNK, maximum - size + 1))
        if not block:
            return size
        size += len(block)
        if size > maximum:
            raise VAO04Error(
                "Payload exceeds its declared realization byteSize while packing."
            )
        target.write(block)


def _digest_bytes(algorithm: str, data: bytes) -> bytes:
    if algorithm == "sha256":
        return hashlib.sha256(data).digest()
    if algorithm == "sha512":
        return hashlib.sha512(data).digest()
    raise VAO04Error(f"Unsupported digest algorithm {algorithm!r}.")


def merkle_root(chunks: list[dict[str, Any]], algorithm: str) -> str:
    if not chunks:
        raise VAO04Error("Cannot calculate a Merkle root without chunks.")
    level = [
        _digest_bytes(algorithm, b"\x00" + bytes.fromhex(chunk["digest"]["value"]))
        for chunk in chunks
    ]
    while len(level) > 1:
        if len(level) % 2:
            level.append(level[-1])
        level = [
            _digest_bytes(algorithm, b"\x01" + level[index] + level[index + 1])
            for index in range(0, len(level), 2)
        ]
    return level[0].hex()


def validate_chunk_stream(realization: dict[str, Any], stream: Any) -> list[str]:
    errors: list[str] = []
    chunking = realization.get("chunking")
    if not isinstance(chunking, dict) or not chunking.get("chunks"):
        return errors
    position = 0
    for chunk in sorted(chunking["chunks"], key=lambda item: item["index"]):
        if chunk["offset"] != position:
            break
        remaining = chunk["length"]
        algorithm = chunk["digest"]["algorithm"]
        hasher = hashlib.sha256() if algorithm == "sha256" else hashlib.sha512()
        while remaining:
            block = stream.read(min(vao03.CHUNK, remaining))
            if not block:
                errors.append(
                    f"Realization {realization['id']!r} ends inside chunk {chunk['index']}."
                )
                return errors
            hasher.update(block)
            remaining -= len(block)
            position += len(block)
        if hasher.hexdigest() != chunk["digest"]["value"]:
            errors.append(
                f"Realization {realization['id']!r} chunk {chunk['index']} fails its {algorithm} digest."
            )
    return errors


def schema_errors(value: Any, path: Path) -> list[str]:
    schema = strict_json_bytes(path.read_bytes(), str(path))
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors: list[str] = []
    for error in sorted(
        validator.iter_errors(value), key=lambda item: list(item.absolute_path)
    ):
        location = "$"
        for token in error.absolute_path:
            location += f"[{token}]" if isinstance(token, int) else f".{token}"
        errors.append(f"{location}: {error.message}")
    return errors


def _replace_profile(value: str) -> str:
    if value.startswith(PROFILE_BASE) and value.endswith(f"/{FORMAT_VERSION}"):
        return value[: -len(FORMAT_VERSION)] + "0.3"
    return value


def project_to_03(manifest: dict[str, Any]) -> dict[str, Any]:
    """Lossless-for-0.3-semantics internal projection used to retain mature checks."""
    value = copy.deepcopy(manifest)
    value["$schema"] = vao03.SCHEMA_URI
    value["@context"] = [
        vao03.CONTEXT_URI if item == CONTEXT_URI else item
        for item in value.get("@context", [])
    ]
    value["formatVersion"] = vao03.FORMAT_VERSION
    value["conformsTo"] = [
        _replace_profile(item) for item in value.get("conformsTo", [])
    ]
    for registry in ("profiles", "materializableProfiles"):
        for profile in value.get(registry, []):
            profile["id"] = _replace_profile(profile["id"])
            profile["version"] = "0.3"

    scientific = value.pop("scientific", {})
    value["paradata"] = [
        *scientific.get("agents", []),
        *scientific.get("activities", []),
        *scientific.get("observations", []),
        *scientific.get("calibrations", []),
        *scientific.get("protocols", []),
        *scientific.get("softwareEnvironments", []),
        *scientific.get("consents", []),
    ]
    value["analyses"] = [
        *scientific.get("analyses", []),
        *scientific.get("claims", []),
        *scientific.get("reviews", []),
    ]
    for key in ("multimodal", "physicalSystem", "runtime", "discovery"):
        value.pop(key, None)

    allowed_technical = set(
        json.loads(vao03.MANIFEST_SCHEMA.read_text(encoding="utf-8"))["$defs"][
            "technicalMetadata"
        ]["properties"]
    )
    for realization in value.get("realizations", []):
        realization.pop("contentDigests", None)
        realization.pop("chunking", None)
        realization.pop("streamingIndexRealizationId", None)
        realization.pop("authenticityEnvelopeRealizationId", None)
        realization.pop("extensions", None)
        technical = realization.get("technicalMetadata", {})
        if technical.get("kind") not in {
            "audio",
            "geometry",
            "image",
            "document",
            "data",
            "software",
            "other",
        }:
            technical["kind"] = "data"
        for key in list(technical):
            if key not in allowed_technical:
                technical.pop(key)

    allowed_rights = set(
        json.loads(vao03.MANIFEST_SCHEMA.read_text(encoding="utf-8"))["$defs"][
            "rights"
        ]["properties"]
    )
    for record in value.get("rights", []):
        for key in list(record):
            if key not in allowed_rights:
                record.pop(key)
    integrity = value.get("integrity", {})
    integrity.pop("schemaBundleDigest", None)
    integrity.pop("signatureEnvelopeRealizationId", None)

    model = value.get("interactionModel")
    if isinstance(model, dict):
        model.pop("executionSemantics", None)
        model.pop("randomSources", None)
        allowed_protocol = set(
            json.loads(vao03.MANIFEST_SCHEMA.read_text(encoding="utf-8"))["$defs"][
                "protocolBinding"
            ]["properties"]
        )
        for binding in model.get("protocolBindings", []):
            for key in list(binding):
                if key not in allowed_protocol:
                    binding.pop(key)
        for route in model.get("routingRules", []):
            delayed = route.pop("delayConstraintId", None)
            if delayed is not None and route.get("routingBehavior") in {
                "copies",
                "transposes",
            }:
                route["routingBehavior"] = "activates"
        for process in model.get("processModels", []):
            # VAO 0.4 stochastic Processes perform one bounded candidate
            # selection.  Represent that newer completed semantics as one
            # iteration when applying the retained 0.3 safety checks.
            if (
                process.get("processKind") == "stochastic"
                and process.get("terminationPolicy") == "completed"
            ):
                process["terminationPolicy"] = "maximum-iterations"
                process["maximumIterations"] = 1
            process.pop("randomSourceId", None)
            process.pop("probabilityDistribution", None)
        for transfer in model.get("transferFunctions", []):
            for key in (
                "inputKinds",
                "validDomain",
                "extrapolationPolicy",
                "hysteresis",
                "dynamicModel",
                "fitResidual",
            ):
                transfer.pop(key, None)
            for point in transfer.get("points", []):
                inputs = point.pop("inputs", None)
                if "input" not in point and inputs:
                    point["input"] = inputs[0]
                point.pop("uncertainty", None)
    acoustics = value.get("acoustics")
    if isinstance(acoustics, dict):
        for frame in acoustics.get("coordinateFrames", []):
            axis_units = frame.pop("axisUnits", None)
            if axis_units and "unit" not in frame:
                frame["unit"] = axis_units[0]
            if frame.get("transformToParent") is not None:
                # The 0.3 checker used an absolute pivot threshold that rejects
                # valid uniformly small coordinate scales.  The 0.4 validator
                # applies its scale-invariant condition test separately.
                frame["transformToParent"] = [
                    1,
                    0,
                    0,
                    0,
                    0,
                    1,
                    0,
                    0,
                    0,
                    0,
                    1,
                    0,
                    0,
                    0,
                    0,
                    1,
                ]
        for pose in acoustics.get("poses", []):
            pose.pop("localFrameId", None)
            pose.pop("orientationRadians", None)
            trajectory = pose.pop("trajectoryRealizationId", None)
            if trajectory is not None:
                pose["trajectoryAssetId"] = next(
                    (
                        realization["assetId"]
                        for realization in value.get("realizations", [])
                        if realization["id"] == trajectory
                    ),
                    trajectory,
                )
        for config in acoustics.get("renderConfigurations", []):
            listener = config.get("listener", {})
            trajectory = listener.pop("trajectoryRealizationId", None)
            if trajectory is not None:
                listener["trajectoryAssetId"] = next(
                    (
                        realization["assetId"]
                        for realization in value.get("realizations", [])
                        if realization["id"] == trajectory
                    ),
                    trajectory,
                )
        for material in acoustics.get("materialModels", []):
            absorption_uncertainty = material.pop("absorptionUncertainty", None)
            material.pop("scatteringUncertainty", None)
            material.pop("transmissionLossUncertainty", None)
            if absorption_uncertainty is not None:
                material["uncertainty"] = absorption_uncertainty
        for metric_set in acoustics.get("metricSets", []):
            for metric in metric_set.get("metrics", []):
                uncertainty = metric.pop("uncertainty", None)
                if (
                    isinstance(uncertainty, dict)
                    and uncertainty.get("kind") != "covariance"
                    and isinstance(uncertainty.get("value"), list)
                ):
                    metric["uncertainties"] = uncertainty["value"]

        def project_uncertainty(record: Any) -> None:
            if isinstance(record, dict):
                if "kind" in record and "value" in record:
                    axis_units = record.pop("axisUnits", None)
                    if axis_units and "unit" not in record:
                        record["unit"] = axis_units[0]
                for child in record.values():
                    project_uncertainty(child)
            elif isinstance(record, list):
                for child in record:
                    project_uncertainty(child)

        project_uncertainty(acoustics)
    return value


def _registry(
    records: Any, label: str, errors: list[str], identifiers: dict[str, str]
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for index, record in enumerate(records if isinstance(records, list) else []):
        if not isinstance(record, dict) or not is_identifier(record.get("id")):
            errors.append(f"{label}[{index}] has an invalid id.")
            continue
        key = record["id"]
        if key in identifiers:
            errors.append(
                f"Identifier {key!r} is duplicated in {identifiers[key]} and {label}."
            )
        else:
            identifiers[key] = label
        result[key] = record
    return result


def _find_cycle(edges: dict[str, list[str]], label: str, errors: list[str]) -> None:
    """Detect directed cycles without depending on the Python call-stack limit."""
    state: dict[str, int] = {}
    for start in edges:
        if state.get(start, 0) != 0:
            continue
        state[start] = 1
        stack: list[tuple[str, int]] = [(start, 0)]
        while stack:
            node, index = stack[-1]
            neighbours = edges.get(node, [])
            if index >= len(neighbours):
                state[node] = 2
                stack.pop()
                continue
            target = neighbours[index]
            stack[-1] = (node, index + 1)
            if target not in edges:
                continue
            target_state = state.get(target, 0)
            if target_state == 1:
                errors.append(f"{label} contains a cycle at {target!r}.")
            elif target_state == 0:
                state[target] = 1
                stack.append((target, 0))


def _json_depth_exceeded(value: Any) -> bool:
    """Apply the reference processor's finite JSON nesting budget iteratively."""
    stack: list[tuple[Any, int]] = [(value, 1)]
    while stack:
        current, depth = stack.pop()
        if depth > MAX_JSON_DEPTH:
            return True
        if isinstance(current, dict):
            stack.extend((child, depth + 1) for child in current.values())
        elif isinstance(current, list):
            stack.extend((child, depth + 1) for child in current)
    return False


_DECLARATION_SCAN_SKIP = {
    "body",  # annotation bodies containing only id are references
    "extensions",
    "parameterValues",
    "parameters",
    "properties",
}


def _global_identifiers(manifest: dict[str, Any], errors: list[str]) -> dict[str, str]:
    """Build the normative global identifier registry across every module."""
    identifiers: dict[str, str] = {}

    def walk(value: Any, path: str, key: str | None = None) -> None:
        if key in _DECLARATION_SCAN_SKIP:
            return
        if isinstance(value, dict):
            identifier = value.get("id")
            if is_identifier(identifier):
                previous = identifiers.get(identifier)
                if previous is not None:
                    errors.append(
                        f"Identifier {identifier!r} is declared more than once at "
                        f"{previous} and {path}."
                    )
                else:
                    identifiers[identifier] = path
            for child_key, child in value.items():
                walk(child, f"{path}.{child_key}", child_key)
        elif isinstance(value, list):
            for index, child in enumerate(value):
                walk(child, f"{path}[{index}]", key)

    walk(manifest, "$")
    return identifiers


def _validate_numeric_domain(value: Any, errors: list[str], path: str = "$") -> None:
    """Enforce the cross-language numeric and Unicode scalar JSON domain."""
    if isinstance(value, str):
        if any(0xD800 <= ord(character) <= 0xDFFF for character in value):
            errors.append(f"{path} contains a non-scalar Unicode surrogate.")
    elif isinstance(value, bool):
        return
    if isinstance(value, int):
        if abs(value) > MAX_SAFE_INTEGER:
            errors.append(
                f"JSON integer at {path} exceeds the interoperable 2^53-1 range."
            )
    elif isinstance(value, float):
        if not math.isfinite(value):
            errors.append(f"Manifest contains non-finite number at {path}.")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _validate_numeric_domain(item, errors, f"{path}[{index}]")
    elif isinstance(value, dict):
        for key, item in value.items():
            invalid_key = any(0xD800 <= ord(character) <= 0xDFFF for character in key)
            if invalid_key:
                errors.append(f"{path} contains a non-scalar Unicode property name.")
            child_path = f"{path}.<property>" if invalid_key else f"{path}.{key}"
            _validate_numeric_domain(item, errors, child_path)


_RFC3339_INSTANT = re.compile(
    r"^(?P<year>[0-9]{4})-(?P<month>[0-9]{2})-(?P<day>[0-9]{2})"
    r"[Tt](?P<hour>[0-9]{2}):(?P<minute>[0-9]{2}):(?P<second>[0-5][0-9])"
    r"(?:\.(?P<fraction>[0-9]{1,18}))?"
    r"(?P<offset>[Zz]|[+-][0-9]{2}:[0-9]{2})$"
)


def _instant(value: str) -> Fraction:
    """Return exact elapsed nominal seconds for the VAO RFC 3339 subset."""
    if value.endswith("-00:00"):
        raise ValueError("unknown RFC 3339 offset -00:00 is not comparable")
    match = _RFC3339_INSTANT.fullmatch(value)
    if match is None:
        raise ValueError("timestamp is outside the exact VAO RFC 3339 subset")
    parts = {
        name: int(match[name])
        for name in ("year", "month", "day", "hour", "minute", "second")
    }
    civil = datetime(**parts)
    offset = match["offset"]
    offset_seconds = 0
    if offset.lower() != "z":
        sign = 1 if offset[0] == "+" else -1
        offset_seconds = sign * (int(offset[1:3]) * 3600 + int(offset[4:6]) * 60)
    whole = (
        (civil.toordinal() - 1) * 86400
        + civil.hour * 3600
        + civil.minute * 60
        + civil.second
        - offset_seconds
    )
    fraction = match["fraction"]
    return Fraction(whole) + (
        Fraction(int(fraction), 10 ** len(fraction)) if fraction else Fraction()
    )


def _time_order(
    owner: str,
    start: Any,
    end: Any,
    errors: list[str],
    *,
    strict: bool = False,
) -> None:
    if not isinstance(start, str) or not isinstance(end, str):
        return
    try:
        invalid = (
            _instant(end) <= _instant(start)
            if strict
            else _instant(end) < _instant(start)
        )
    except ValueError as exc:
        errors.append(f"{owner} has a non-comparable timestamp: {exc}.")
        return
    if invalid:
        relation = "not after" if strict else "before"
        errors.append(f"{owner} end is {relation} its start.")


def _number_fraction(value: int | float) -> Fraction:
    """Represent a conforming JSON integer/binary64 number exactly."""
    return Fraction(value) if isinstance(value, int) else Fraction.from_float(value)


def _linear_rcond(matrix: list[list[float]]) -> float:
    """Estimate reciprocal infinity-norm condition number without scale overflow."""
    size = len(matrix)
    scale = max(abs(value) for row in matrix for value in row)
    if scale == 0 or not math.isfinite(scale):
        return 0.0
    normalized = [[value / scale for value in row] for row in matrix]
    norm = max(sum(abs(value) for value in row) for row in normalized)
    if size == 2:
        a, b = normalized[0]
        c, d = normalized[1]
        determinant = a * d - b * c
        adjugate = [[d, -b], [-c, a]]
    elif size == 3:
        a, b, c = normalized[0]
        d, e, f = normalized[1]
        g, h, i = normalized[2]
        cofactors = [
            [e * i - f * h, -(d * i - f * g), d * h - e * g],
            [-(b * i - c * h), a * i - c * g, -(a * h - b * g)],
            [b * f - c * e, -(a * f - c * d), a * e - b * d],
        ]
        determinant = a * cofactors[0][0] + b * cofactors[0][1] + c * cofactors[0][2]
        adjugate = [[cofactors[column][row] for column in range(3)] for row in range(3)]
    else:  # pragma: no cover - the VAO spatial contract uses only 2D and 3D.
        raise ValueError("linear condition estimate requires a 2x2 or 3x3 matrix")
    adjugate_norm = max(sum(abs(value) for value in row) for row in adjugate)
    denominator = norm * adjugate_norm
    if denominator == 0 or not math.isfinite(determinant):
        return 0.0
    return abs(determinant) / denominator


def _numeric_shape(value: Any) -> tuple[int, ...] | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return ()
    if not isinstance(value, list) or not value:
        return None
    if all(
        not isinstance(item, bool) and isinstance(item, (int, float)) for item in value
    ):
        return (len(value),)
    if all(isinstance(item, list) and item for item in value):
        widths = {len(item) for item in value}
        if len(widths) == 1 and all(
            not isinstance(cell, bool) and isinstance(cell, (int, float))
            for row in value
            for cell in row
        ):
            return (len(value), widths.pop())
    return None


def _dimensionless_psd(matrix: list[list[float]]) -> bool:
    """Scale-relative LDLᵀ test after covariance normalization."""
    size = len(matrix)
    scale = max(abs(x) for row in matrix for x in row)
    if not math.isfinite(scale):
        return False
    tolerance = 1e-12 * scale
    lower = [[0.0] * size for _ in range(size)]
    diagonal = [0.0] * size
    for column in range(size):
        lower[column][column] = 1.0
        pivot = matrix[column][column] - sum(
            lower[column][index] ** 2 * diagonal[index] for index in range(column)
        )
        if not math.isfinite(pivot):
            return False
        if pivot < -tolerance:
            return False
        diagonal[column] = 0.0 if abs(pivot) <= tolerance else pivot
        for row in range(column + 1, size):
            residual = matrix[row][column] - sum(
                lower[row][index] * lower[column][index] * diagonal[index]
                for index in range(column)
            )
            if not math.isfinite(residual):
                return False
            if diagonal[column] == 0.0:
                if abs(residual) > tolerance:
                    return False
            else:
                lower[row][column] = residual / diagonal[column]
                if not math.isfinite(lower[row][column]):
                    return False
    return True


def _covariance_is_psd(matrix: list[list[float]]) -> bool:
    """Check PSD after unit-invariant normalization to a correlation matrix."""
    size = len(matrix)
    variances = [matrix[index][index] for index in range(size)]
    if any(variance < 0 for variance in variances):
        return False
    normalized = [[0.0] * size for _ in range(size)]
    for row in range(size):
        normalized[row][row] = 1.0 if variances[row] > 0 else 0.0
        for column in range(row):
            if variances[row] == 0 or variances[column] == 0:
                if matrix[row][column] != 0:
                    return False
                coefficient = 0.0
            else:
                denominator = math.sqrt(variances[row]) * math.sqrt(variances[column])
                coefficient = matrix[row][column] / denominator
                if not math.isfinite(coefficient) or abs(coefficient) > 1.0 + 1e-12:
                    return False
            normalized[row][column] = coefficient
            normalized[column][row] = coefficient
    return _dimensionless_psd(normalized)


def _validate_uncertainty(
    owner: str,
    uncertainty: dict[str, Any],
    errors: list[str],
    quantity_shape: tuple[int, ...] | None = None,
    quantity_unit: str | None = None,
    quantity_axis_units: list[str] | None = None,
    *,
    matrix_integrity: bool = True,
) -> None:
    shape = _numeric_shape(uncertainty.get("value"))
    if shape is None:
        errors.append(f"{owner} uncertainty has a ragged or non-numeric value.")
        return
    kind = uncertainty.get("kind")
    if kind == "registration-rms" and not uncertainty.get("method"):
        errors.append(
            f"{owner} registration-rms must identify its metric space and residual method."
        )
    if kind == "covariance":
        value = uncertainty["value"]
        if len(shape) != 2 or shape[0] != shape[1]:
            errors.append(f"{owner} covariance must be a non-empty square matrix.")
            return
        if shape[0] > MAX_INLINE_COVARIANCE_DIMENSION:
            errors.append(
                f"{owner} covariance dimension exceeds the inline limit of "
                f"{MAX_INLINE_COVARIANCE_DIMENSION}."
            )
            return
        dimension = math.prod(quantity_shape) if quantity_shape is not None else None
        if dimension is not None and shape != (dimension, dimension):
            errors.append(
                f"{owner} covariance dimension {shape[0]} does not match "
                f"the {dimension}-component quantity."
            )
        if matrix_integrity:
            if any(
                abs(value[row][column] - value[column][row])
                > 1e-12 * max(abs(value[row][column]), abs(value[column][row]))
                for row in range(shape[0])
                for column in range(row)
            ):
                errors.append(f"{owner} covariance matrix is not symmetric.")
            elif not _covariance_is_psd(value):
                errors.append(
                    f"{owner} covariance matrix is not positive semidefinite."
                )
    elif (
        kind != "registration-rms"
        and quantity_shape is not None
        and shape != quantity_shape
    ):
        errors.append(
            f"{owner} uncertainty shape {shape} does not match quantity shape "
            f"{quantity_shape}."
        )
    component_count = shape[0] if kind == "covariance" else math.prod(shape or (1,))
    axis_units = uncertainty.get("axisUnits")
    if axis_units is not None and len(axis_units) != component_count:
        errors.append(
            f"{owner} uncertainty axisUnits length does not match its component count."
        )
    if quantity_unit is not None and uncertainty.get("unit") != quantity_unit:
        errors.append(f"{owner} uncertainty unit does not match the quantity unit.")
    if (
        kind != "registration-rms"
        and quantity_axis_units is not None
        and uncertainty.get("axisUnits") != quantity_axis_units
    ):
        errors.append(f"{owner} uncertainty axisUnits do not match the quantity axes.")
    confidence = uncertainty.get("confidenceLevel")
    if confidence is not None and confidence <= 0:
        errors.append(f"{owner} uncertainty confidenceLevel must be greater than zero.")


def _validate_measurements(manifest: dict[str, Any], errors: list[str]) -> None:
    uncertainty_kinds = {
        "standard",
        "expanded",
        "bound",
        "covariance",
        "registration-rms",
    }
    validated_uncertainties: set[int] = set()
    covariance_cells = 0
    covariance_budget_reported = False

    def validate_uncertainty_once(
        owner: str,
        uncertainty: dict[str, Any],
        quantity_shape: tuple[int, ...] | None = None,
        quantity_unit: str | None = None,
    ) -> None:
        nonlocal covariance_cells, covariance_budget_reported
        marker = id(uncertainty)
        if marker in validated_uncertainties:
            return
        validated_uncertainties.add(marker)
        shape = _numeric_shape(uncertainty.get("value"))
        if uncertainty.get("kind") == "covariance" and shape is not None:
            cells = math.prod(shape)
            covariance_cells += cells
            if covariance_cells > MAX_TOTAL_COVARIANCE_CELLS:
                if not covariance_budget_reported:
                    errors.append(
                        "Inline covariance cells exceed the manifest-wide limit of "
                        f"{MAX_TOTAL_COVARIANCE_CELLS}."
                    )
                    covariance_budget_reported = True
                return
        _validate_uncertainty(
            owner,
            uncertainty,
            errors,
            quantity_shape,
            quantity_unit,
        )

    def walk(value: Any, path: str, parent: str | None = None) -> None:
        if isinstance(value, dict):
            if (
                value.get("kind") in uncertainty_kinds
                and "value" in value
                and ("unit" in value or "axisUnits" in value)
            ):
                validate_uncertainty_once(path, value)
            elif {"value", "unit"} <= value.keys() and parent != "literal":
                shape = _numeric_shape(value.get("value"))
                if shape is None:
                    errors.append(f"{path} has a ragged or non-numeric quantity value.")
                uncertainty = value.get("uncertainty")
                if isinstance(uncertainty, dict) and shape is not None:
                    validate_uncertainty_once(
                        path,
                        uncertainty,
                        shape,
                        value.get("unit"),
                    )
            for child_key, child in value.items():
                walk(child, f"{path}.{child_key}", child_key)
        elif isinstance(value, list):
            for index, child in enumerate(value):
                walk(child, f"{path}[{index}]", parent)

    walk(manifest, "$")


def _orcid_valid(value: str) -> bool:
    match = re.fullmatch(
        r"https://orcid\.org/(\d{4})-(\d{4})-(\d{4})-(\d{3}[\dX])", value
    )
    if match is None:
        return False
    compact = "".join(match.groups())
    total = 0
    for character in compact[:15]:
        total = (total + int(character)) * 2
    check = (12 - total % 11) % 11
    return compact[-1] == ("X" if check == 10 else str(check))


def _ror_valid(value: str) -> bool:
    match = re.fullmatch(r"https://ror\.org/0([a-hj-km-np-tv-z0-9]{6})(\d{2})", value)
    if match is None:
        return False
    alphabet = "0123456789abcdefghjkmnpqrstvwxyz"
    try:
        number = 0
        for character in match.group(1):
            number = number * 32 + alphabet.index(character)
    except ValueError:
        return False
    return int(match.group(2)) == 98 - ((number * 100) % 97)


def validate_discovery(manifest: dict[str, Any], errors: list[str]) -> None:
    """Validate identifier lexemes whose scheme is explicit in discovery metadata."""
    discovery = manifest.get("discovery", {})
    for index, record in enumerate(discovery.get("relatedIdentifiers", [])):
        identifier = record["identifier"]
        identifier_type = record["identifierType"]
        owner = f"discovery.relatedIdentifiers[{index}]"
        if identifier_type == "DOI":
            value = identifier.removeprefix("https://doi.org/").removeprefix(
                "http://doi.org/"
            )
            if re.fullmatch(r"10\.\d{4,9}/\S+", value, re.IGNORECASE) is None:
                errors.append(f"{owner} has an invalid DOI lexical form.")
        elif identifier_type == "URL":
            parsed = urlsplit(identifier)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                errors.append(f"{owner} URL must be an absolute HTTP(S) URL.")
        elif identifier_type == "URN" and not identifier.lower().startswith("urn:"):
            errors.append(f"{owner} URN must start with 'urn:'.")
        elif identifier_type == "w3id" and not identifier.startswith(
            "https://w3id.org/"
        ):
            errors.append(f"{owner} w3id must use the canonical HTTPS w3id.org base.")
        elif (
            identifier_type == "SWHID"
            and re.fullmatch(r"swh:1:[a-z]+:[0-9a-f]{40}(;\S+)?", identifier) is None
        ):
            errors.append(f"{owner} has an invalid SWHID lexical form.")

    for index, record in enumerate(discovery.get("fundingReferences", [])):
        identifier = record.get("funderIdentifier")
        identifier_type = record.get("funderIdentifierType")
        owner = f"discovery.fundingReferences[{index}]"
        if identifier_type == "ROR" and not _ror_valid(identifier or ""):
            errors.append(f"{owner} has an invalid ROR identifier or checksum.")
        elif identifier_type == "Crossref Funder ID":
            value = (identifier or "").removeprefix("https://doi.org/")
            if re.fullmatch(r"10\.13039/\d+", value) is None:
                errors.append(f"{owner} has an invalid Crossref Funder ID.")


def validate_scientific(
    manifest: dict[str, Any], known: set[str], errors: list[str]
) -> dict[str, dict[str, dict[str, Any]]]:
    scientific = manifest.get("scientific", {})
    ids: dict[str, str] = {}
    registries = {
        name: _registry(scientific.get(name), f"scientific.{name}", errors, ids)
        for name in (
            "agents",
            "activities",
            "observations",
            "analyses",
            "calibrations",
            "protocols",
            "softwareEnvironments",
            "claims",
            "reviews",
            "consents",
        )
    }
    all_known = known | set(ids)
    entity_ids = {record["id"] for record in manifest.get("entities", [])}
    realization_ids = {record["id"] for record in manifest.get("realizations", [])}
    sensors = {
        record["id"]: record
        for record in manifest.get("physicalSystem", {}).get("sensors", [])
    }
    physical_components = {
        record["id"]: record
        for record in manifest.get("physicalSystem", {}).get("components", [])
    }
    sensor_ids = set(sensors)
    runtime_random = {
        record["id"] for record in manifest.get("runtime", {}).get("randomSources", [])
    }
    runtime_random |= {
        record["id"]
        for record in manifest.get("interactionModel", {}).get("randomSources", [])
    }

    for environment in registries["softwareEnvironments"].values():
        for dependency in environment.get("dependencies", []):
            role = dependency["dependencyRole"]
            scope = dependency["identityScope"]
            if role == "environment-lock" and scope != "environment-lock":
                errors.append(
                    f"Software environment {environment['id']!r} has an "
                    "environment-lock dependency whose identityScope is not "
                    "environment-lock."
                )
            if role == "source" and scope not in {"source-file", "source-bundle"}:
                errors.append(
                    f"Software environment {environment['id']!r} has a source "
                    "dependency whose identityScope is not source-file/source-bundle."
                )

    def require(owner: str, reference: Any, allowed: set[str] | None = None) -> None:
        if reference is not None and reference not in (
            allowed if allowed is not None else all_known
        ):
            errors.append(f"{owner} has unresolved reference {reference!r}.")

    for record in registries["activities"].values():
        _time_order(
            f"Activity {record['id']!r}",
            record["startedAt"],
            record["endedAt"],
            errors,
        )
        for ref in record["agentIds"]:
            require(
                f"Activity {record['id']!r} agentIds", ref, set(registries["agents"])
            )
        require(
            f"Activity {record['id']!r} protocolId",
            record["protocolId"],
            set(registries["protocols"]),
        )
        require(
            f"Activity {record['id']!r} softwareEnvironmentId",
            record.get("softwareEnvironmentId"),
            set(registries["softwareEnvironments"]),
        )
        for ref in record["inputIds"] + record["outputIds"]:
            require(f"Activity {record['id']!r}", ref)
        overlap = set(record["inputIds"]) & set(record["outputIds"])
        if overlap:
            errors.append(
                f"Activity {record['id']!r} uses the same immutable record as input "
                f"and output: {sorted(overlap)!r}."
            )
        require(
            f"Activity {record['id']!r} randomSourceId",
            record.get("randomSourceId"),
            runtime_random,
        )
        for ref in record.get("environmentObservationIds", []):
            require(
                f"Activity {record['id']!r} environmentObservationIds",
                ref,
                set(registries["observations"]),
            )
    output_producers: dict[str, list[str]] = {}
    activity_dependencies: dict[str, list[str]] = {
        identifier: [] for identifier in registries["activities"]
    }
    for producer in registries["activities"].values():
        for reference in producer["outputIds"]:
            output_producers.setdefault(reference, []).append(producer["id"])

    def available_at(reference: str) -> Fraction | None:
        """Return the latest declared time at which a scientific record exists."""
        candidates = [
            _instant(registries["activities"][producer_id]["endedAt"])
            for producer_id in output_producers.get(reference, [])
        ]
        activity = registries["activities"].get(reference)
        observation = registries["observations"].get(reference)
        calibration = registries["calibrations"].get(reference)
        analysis = registries["analyses"].get(reference)
        claim = registries["claims"].get(reference)
        review = registries["reviews"].get(reference)
        consent = registries["consents"].get(reference)
        if activity is not None:
            candidates.append(_instant(activity["endedAt"]))
        if observation is not None:
            candidates.append(_instant(observation["resultTime"]))
        if calibration is not None:
            candidates.append(_instant(calibration["performedAt"]))
        if analysis is not None:
            analysis_activity = registries["activities"].get(analysis["activityId"])
            if analysis_activity is not None:
                candidates.append(_instant(analysis_activity["endedAt"]))
        if claim is not None and claim.get("generatedById") is not None:
            claim_activity = registries["activities"].get(claim["generatedById"])
            if claim_activity is not None:
                candidates.append(_instant(claim_activity["endedAt"]))
        if review is not None:
            candidates.append(_instant(review["reviewedAt"]))
        if consent is not None:
            candidates.append(_instant(consent["recordedAt"]))
        return max(candidates) if candidates else None

    for consumer in registries["activities"].values():
        for reference in consumer["inputIds"]:
            for producer_id in output_producers.get(reference, []):
                activity_dependencies[producer_id].append(consumer["id"])
            availability = available_at(reference)
            if availability is not None and availability > _instant(
                consumer["startedAt"]
            ):
                errors.append(
                    f"Activity {consumer['id']!r} starts before input {reference!r} "
                    "is available."
                )
    _find_cycle(activity_dependencies, "Activity dependency graph", errors)
    for record in registries["protocols"].values():
        require(
            f"Protocol {record['id']!r} documentRealizationId",
            record.get("documentRealizationId"),
            realization_ids,
        )
    for record in registries["calibrations"].values():
        require(
            f"Calibration {record['id']!r} instrumentEntityId",
            record["instrumentEntityId"],
            entity_ids,
        )
        require(
            f"Calibration {record['id']!r} protocolId",
            record["protocolId"],
            set(registries["protocols"]),
        )
        for ref in record["performedByAgentIds"]:
            require(f"Calibration {record['id']!r}", ref, set(registries["agents"]))
        require(
            f"Calibration {record['id']!r} certificateRealizationId",
            record.get("certificateRealizationId"),
            realization_ids,
        )
        _time_order(
            f"Calibration {record['id']!r}",
            record["performedAt"],
            record.get("validUntil"),
            errors,
        )
    for record in registries["observations"].values():
        require(
            f"Observation {record['id']!r} featureOfInterestId",
            record["featureOfInterestId"],
            entity_ids,
        )
        require(
            f"Observation {record['id']!r} activityId",
            record["activityId"],
            set(registries["activities"]),
        )
        require(
            f"Observation {record['id']!r} protocolId",
            record["protocolId"],
            set(registries["protocols"]),
        )
        require(
            f"Observation {record['id']!r} calibrationId",
            record.get("calibrationId"),
            set(registries["calibrations"]),
        )
        require(
            f"Observation {record['id']!r} sensorId",
            record.get("sensorId"),
            sensor_ids,
        )
        for key in ("rawResultRealizationId", "processedResultRealizationId"):
            require(
                f"Observation {record['id']!r} {key}",
                record.get(key),
                realization_ids,
            )
        activity = registries["activities"].get(record["activityId"])
        if activity is not None:
            if activity["activityKind"] not in {
                "capture",
                "measurement",
                "processing",
                "simulation",
            }:
                errors.append(
                    f"Observation {record['id']!r} requires a capture, measurement, "
                    "processing, or simulation Activity."
                )
            if activity["protocolId"] != record["protocolId"]:
                errors.append(
                    f"Observation {record['id']!r} protocol differs from its Activity."
                )
            result_time = _instant(record["resultTime"])
            if (
                not _instant(activity["startedAt"])
                <= result_time
                <= _instant(activity["endedAt"])
            ):
                errors.append(
                    f"Observation {record['id']!r} resultTime is outside its Activity."
                )
            if record["id"] not in activity["outputIds"]:
                errors.append(
                    f"Observation {record['id']!r} is not listed as an output of "
                    "its Activity."
                )
            activity_io = set(activity["inputIds"] + activity["outputIds"])
            raw = record.get("rawResultRealizationId")
            processed = record.get("processedResultRealizationId")
            if raw is not None and raw not in activity_io:
                errors.append(
                    f"Observation {record['id']!r} rawResultRealizationId is absent "
                    "from its Activity inputs/outputs."
                )
            if processed is not None and processed not in activity["outputIds"]:
                errors.append(
                    f"Observation {record['id']!r} processedResultRealizationId is "
                    "not an output of its Activity."
                )
            if raw is not None and raw == processed:
                errors.append(
                    f"Observation {record['id']!r} cannot identify one realization "
                    "as both raw and processed result."
                )
        sensor = sensors.get(record.get("sensorId"))
        calibration = registries["calibrations"].get(record.get("calibrationId"))
        if sensor is not None:
            if sensor["observedProperty"] != record["observedProperty"]:
                errors.append(
                    f"Observation {record['id']!r} observedProperty differs from "
                    "its Sensor."
                )
            if sensor["protocolId"] != record["protocolId"]:
                errors.append(
                    f"Observation {record['id']!r} protocol differs from its Sensor."
                )
            if sensor.get("calibrationId") is not None and sensor.get(
                "calibrationId"
            ) != record.get("calibrationId"):
                errors.append(
                    f"Observation {record['id']!r} does not cite its Sensor's "
                    "declared calibration."
                )
            if calibration is not None:
                component = physical_components.get(sensor["componentId"])
                if (
                    component is not None
                    and calibration["instrumentEntityId"] != component["entityId"]
                ):
                    errors.append(
                        f"Observation {record['id']!r} calibration instrument differs "
                        "from its Sensor component Entity."
                    )
        if calibration is not None:
            result_time = _instant(record["resultTime"])
            if result_time < _instant(calibration["performedAt"]):
                errors.append(f"Observation {record['id']!r} predates its Calibration.")
            if calibration.get("validUntil") is not None and result_time > _instant(
                calibration["validUntil"]
            ):
                errors.append(
                    f"Observation {record['id']!r} occurs after its Calibration's "
                    "validUntil."
                )
    for record in registries["analyses"].values():
        require(
            f"Analysis {record['id']!r} activityId",
            record["activityId"],
            set(registries["activities"]),
        )
        require(
            f"Analysis {record['id']!r} softwareEnvironmentId",
            record["softwareEnvironmentId"],
            set(registries["softwareEnvironments"]),
        )
        for ref in record["inputIds"] + record["outputIds"]:
            require(f"Analysis {record['id']!r}", ref)
        for ref in record.get("validationIds", []):
            require(f"Analysis {record['id']!r} validationIds", ref)
            if ref == record["id"]:
                errors.append(f"Analysis {record['id']!r} cannot validate itself.")
        if (
            record["reproducibility"] == "seeded"
            and record.get("randomSourceId") not in runtime_random
        ):
            errors.append(
                f"Seeded analysis {record['id']!r} requires a declared random source."
            )
        if (
            record["reproducibility"] == "deterministic"
            and record.get("randomSourceId") is not None
        ):
            errors.append(
                f"Deterministic analysis {record['id']!r} must not declare randomSourceId."
            )
        environment = registries["softwareEnvironments"].get(
            record["softwareEnvironmentId"]
        )
        if (
            record["reproducibility"] in {"deterministic", "seeded"}
            and environment is not None
            and not _supports_reproducibility_claim(environment)
        ):
            errors.append(
                f"Analysis {record['id']!r} claims {record['reproducibility']!r} "
                "reproducibility, but its Software Environment supplies no exact "
                "runnable/reconstructable identity plus runtime."
            )
        activity = registries["activities"].get(record["activityId"])
        if activity is not None:
            if activity["activityKind"] not in {
                "processing",
                "simulation",
                "inference",
            }:
                errors.append(
                    f"Analysis {record['id']!r} requires a processing, simulation, "
                    "or inference Activity."
                )
            if not set(record["inputIds"]).issubset(activity["inputIds"]):
                errors.append(
                    f"Analysis {record['id']!r} inputs are not declared by its Activity."
                )
            if not set(record["outputIds"]).issubset(activity["outputIds"]):
                errors.append(
                    f"Analysis {record['id']!r} outputs are not declared by its Activity."
                )
            for reference in record["outputIds"]:
                observation = registries["observations"].get(reference)
                if (
                    observation is not None
                    and observation["activityId"] != activity["id"]
                ):
                    errors.append(
                        f"Analysis {record['id']!r} outputs Observation {reference!r}, "
                        "but that Observation names another Activity."
                    )
                claim = registries["claims"].get(reference)
                if claim is not None and claim.get("generatedById") != activity["id"]:
                    errors.append(
                        f"Analysis {record['id']!r} outputs Claim {reference!r}, but "
                        "that Claim does not name the Analysis Activity."
                    )
            if activity.get("softwareEnvironmentId") != record["softwareEnvironmentId"]:
                errors.append(
                    f"Analysis {record['id']!r} software environment differs from "
                    "its Activity."
                )
            if activity.get("randomSourceId") != record.get("randomSourceId"):
                errors.append(
                    f"Analysis {record['id']!r} random source differs from its Activity."
                )
            activity_parameters = activity.get("parameterValues", {})
            for key, value in record["parameters"].items():
                if key not in activity_parameters or activity_parameters[key] != value:
                    errors.append(
                        f"Analysis {record['id']!r} parameter {key!r} is absent or "
                        "different in its Activity."
                    )
            activity_io = set(activity["inputIds"] + activity["outputIds"])
            for reference in record.get("validationIds", []):
                if reference not in activity_io:
                    errors.append(
                        f"Analysis {record['id']!r} validation evidence {reference!r} "
                        "is absent from its Activity inputs/outputs."
                    )
                availability = available_at(reference)
                boundary = (
                    _instant(activity["startedAt"])
                    if reference in activity["inputIds"]
                    else _instant(activity["endedAt"])
                )
                if availability is not None and availability > boundary:
                    errors.append(
                        f"Analysis {record['id']!r} validation evidence "
                        f"{reference!r} is not available at its Activity boundary."
                    )
    _find_cycle(
        {
            record["id"]: [
                reference
                for reference in record["evidenceIds"]
                if reference in registries["claims"]
            ]
            for record in registries["claims"].values()
        },
        "Claim evidence graph",
        errors,
    )
    for record in registries["claims"].values():
        require(f"Claim {record['id']!r} subjectId", record["subjectId"])
        if ("objectId" in record) == ("literal" in record):
            errors.append(
                f"Claim {record['id']!r} requires exactly one of objectId or literal."
            )
        require(f"Claim {record['id']!r} objectId", record.get("objectId"))
        for ref in record["evidenceIds"]:
            require(f"Claim {record['id']!r} evidenceIds", ref)
            if ref == record["id"]:
                errors.append(f"Claim {record['id']!r} cannot cite itself as evidence.")
        require(
            f"Claim {record['id']!r} generatedById",
            record.get("generatedById"),
            set(registries["activities"]),
        )
        for ref in record.get("reviewIds", []):
            require(
                f"Claim {record['id']!r} reviewIds",
                ref,
                set(registries["reviews"]),
            )
        generating_activity = registries["activities"].get(record.get("generatedById"))
        if generating_activity is not None:
            activity_io = set(
                generating_activity["inputIds"] + generating_activity["outputIds"]
            )
            for reference in record["evidenceIds"]:
                if reference not in activity_io:
                    errors.append(
                        f"Claim {record['id']!r} evidence {reference!r} is absent "
                        "from its generating Activity inputs/outputs."
                    )
                availability = available_at(reference)
                boundary = (
                    _instant(generating_activity["startedAt"])
                    if reference in generating_activity["inputIds"]
                    else _instant(generating_activity["endedAt"])
                )
                if availability is not None and availability > boundary:
                    errors.append(
                        f"Claim {record['id']!r} evidence {reference!r} is not "
                        "available at its generating Activity boundary."
                    )
        if record["status"] == "inferred" and (
            generating_activity is None
            or generating_activity["activityKind"] != "inference"
        ):
            errors.append(
                f"Inferred Claim {record['id']!r} requires an inference Activity."
            )
        linked_reviews = [
            registries["reviews"][reference]
            for reference in record.get("reviewIds", [])
            if reference in registries["reviews"]
        ]
        for review in linked_reviews:
            if review["reviewedId"] != record["id"]:
                errors.append(
                    f"Claim {record['id']!r} cites Review {review['id']!r}, which "
                    "reviews a different target."
                )
            if review["id"] in record["evidenceIds"]:
                errors.append(
                    f"Claim {record['id']!r} cannot use its own Review as evidence."
                )
        required_decision = {"accepted": "accepted", "rejected": "rejected"}.get(
            record["status"]
        )
        if required_decision is not None and not any(
            review["decision"] == required_decision for review in linked_reviews
        ):
            errors.append(
                f"Claim {record['id']!r} status {record['status']!r} requires a "
                f"linked {required_decision} Review."
            )
        if record["status"] == "reviewed" and not any(
            review["decision"] != "not-assessed" for review in linked_reviews
        ):
            errors.append(
                f"Reviewed Claim {record['id']!r} requires at least one assessed "
                "linked Review."
            )
    for record in registries["reviews"].values():
        require(f"Review {record['id']!r} reviewedId", record["reviewedId"])
        if record["reviewedId"] == record["id"]:
            errors.append(f"Review {record['id']!r} cannot review itself.")
        require(
            f"Review {record['id']!r} reviewerAgentId",
            record["reviewerAgentId"],
            set(registries["agents"]),
        )
        claim = registries["claims"].get(record["reviewedId"])
        if claim is not None and record["id"] not in claim.get("reviewIds", []):
            errors.append(
                f"Review {record['id']!r} of Claim {claim['id']!r} is not cited by "
                "that Claim."
            )
        target_available_at = available_at(record["reviewedId"])
        if (
            target_available_at is not None
            and _instant(record["reviewedAt"]) < target_available_at
        ):
            errors.append(
                f"Review {record['id']!r} predates the availability of its target."
            )
    for record in registries["consents"].values():
        require(
            f"Consent {record['id']!r} grantedByAgentId",
            record["grantedByAgentId"],
            set(registries["agents"]),
        )
        for ref in record["appliesToIds"]:
            require(f"Consent {record['id']!r}", ref)
            if ref == record["id"]:
                errors.append(f"Consent {record['id']!r} cannot apply to itself.")
        require(
            f"Consent {record['id']!r} evidenceRealizationId",
            record.get("evidenceRealizationId"),
            realization_ids,
        )
    for record in registries["agents"].values():
        if record.get("orcid") and not _orcid_valid(record["orcid"]):
            errors.append(f"Agent {record['id']!r} has an invalid ORCID checksum.")
        if record.get("ror") and not _ror_valid(record["ror"]):
            errors.append(f"Agent {record['id']!r} has an invalid ROR checksum.")
        for reference in record.get("affiliationAgentIds", []):
            affiliation = registries["agents"].get(reference)
            if affiliation is None or affiliation["agentKind"] != "organization":
                errors.append(
                    f"Agent {record['id']!r} affiliationAgentIds must resolve to "
                    "organization Agents."
                )
            if reference == record["id"]:
                errors.append(f"Agent {record['id']!r} cannot be its own affiliation.")
    return registries


def validate_multimodal(
    manifest: dict[str, Any], known: set[str], errors: list[str]
) -> dict[str, dict[str, Any]]:
    value = manifest.get("multimodal", {})
    ids: dict[str, str] = {}
    timebases = _registry(value.get("timebases"), "multimodal.timebases", errors, ids)
    tracks = _registry(value.get("tracks"), "multimodal.tracks", errors, ids)
    mappings = _registry(
        value.get("synchronizationMappings"),
        "multimodal.synchronizationMappings",
        errors,
        ids,
    )
    annotations = _registry(
        value.get("annotations"), "multimodal.annotations", errors, ids
    )
    frames = {
        record["id"]: record
        for record in manifest.get("acoustics", {}).get("coordinateFrames", [])
    }
    frame_ids = set(frames)
    activities = {
        record["id"]: record
        for record in manifest.get("scientific", {}).get("activities", [])
    }
    activity_ids = set(activities)
    agent_ids = {
        record["id"] for record in manifest.get("scientific", {}).get("agents", [])
    }
    realizations = {record["id"]: record for record in manifest.get("realizations", [])}
    modality_kinds = {
        "audio": {"audio"},
        "video": {"video"},
        "image-sequence": {"image", "video"},
        "depth": {"depth"},
        "volumetric": {"volumetric"},
        "motion-capture": {"motion-capture"},
        "sensor": {"sensor-data"},
        "event": {"event-stream"},
        "score": {"score"},
        "annotation": {"document", "data"},
        "trajectory": {"trajectory", "motion-capture", "sensor-data"},
    }
    known_coordinate_rate_units = {
        "http://qudt.org/vocab/unit/SAMPLE": "http://qudt.org/vocab/unit/SAMPLE-PER-SEC",
        "http://qudt.org/vocab/unit/FRAME": "http://qudt.org/vocab/unit/FRAME-PER-SEC",
        "https://w3id.org/modavis/vao/vocab/unit/midi-tick": (
            "https://w3id.org/modavis/vao/vocab/unit/midi-tick-per-quarter-note"
        ),
    }
    for timebase in timebases.values():
        expected_rate_unit = known_coordinate_rate_units.get(timebase["unit"])
        if (
            expected_rate_unit is not None
            and timebase["rateUnit"] != expected_rate_unit
        ):
            errors.append(
                f"Timebase {timebase['id']!r} coordinate and rate units are "
                "incompatible."
            )
        rate = timebase["rate"]
        if (
            isinstance(rate, dict)
            and math.gcd(rate["numerator"], rate["denominator"]) != 1
        ):
            errors.append(
                f"Timebase {timebase['id']!r} exact rational rate is not in "
                "lowest terms."
            )

    def rate_value(rate: Any) -> Fraction:
        if isinstance(rate, dict):
            return Fraction(rate["numerator"], rate["denominator"])
        return _number_fraction(rate)

    for realization in realizations.values():
        technical = realization["technicalMetadata"]
        timebase = timebases.get(technical.get("timebaseId"))
        if technical.get("timebaseId") is not None and timebase is None:
            errors.append(
                f"Realization {realization['id']!r} technical timebaseId must "
                "resolve to a Timebase."
            )
        frame = frames.get(technical.get("coordinateFrameId"))
        if technical.get("coordinateFrameId") is not None and frame is None:
            errors.append(
                f"Realization {realization['id']!r} technical coordinateFrameId "
                "must resolve to a Coordinate Frame."
            )
        trajectory_track = tracks.get(technical.get("trajectoryTrackId"))
        if technical.get("trajectoryTrackId") is not None and (
            trajectory_track is None
            or trajectory_track["modality"] != "trajectory"
            or trajectory_track["realizationId"] != realization["id"]
        ):
            errors.append(
                f"Realization {realization['id']!r} technical trajectoryTrackId "
                "must resolve to a trajectory Track for that same Realization."
            )
        labels = technical.get("channelLabels")
        if labels is not None and len(labels) != technical.get("channelCount"):
            errors.append(
                f"Realization {realization['id']!r} channelLabels length does not "
                "match channelCount."
            )
        if "ambisonicsOrder" in technical:
            expected_channels = (
                (technical["ambisonicsOrder"] + 1) ** 2
                if technical["ambisonicsDimensionality"] == "3D"
                else 2 * technical["ambisonicsOrder"] + 1
            )
            if technical.get("channelCount") != expected_channels:
                errors.append(
                    f"Realization {realization['id']!r} Ambisonics order and "
                    "dimensionality require channelCount "
                    f"{expected_channels}."
                )
        if technical.get("kind") == "geometry" and frame is not None:
            if frame.get("unit") != technical.get("coordinateUnit"):
                errors.append(
                    f"Geometry Realization {realization['id']!r} coordinate unit "
                    "differs from its Coordinate Frame."
                )
            if frame["handedness"] != technical.get("handedness"):
                errors.append(
                    f"Geometry Realization {realization['id']!r} handedness differs "
                    "from its Coordinate Frame."
                )
            if frame["upAxis"] != f"+{technical.get('upAxis')}":
                errors.append(
                    f"Geometry Realization {realization['id']!r} up axis differs "
                    "from its Coordinate Frame."
                )
        if timebase is not None:
            expected_rate: Any = None
            if (
                technical.get("kind") == "audio"
                and timebase["unit"] == "http://qudt.org/vocab/unit/SAMPLE"
            ):
                expected_rate = technical.get("sampleRate")
            elif (
                technical.get("kind") == "video"
                and timebase["unit"] == "http://qudt.org/vocab/unit/FRAME"
            ):
                expected_rate = technical.get("frameRate")
            if expected_rate is not None and rate_value(timebase["rate"]) != rate_value(
                expected_rate
            ):
                errors.append(
                    f"Realization {realization['id']!r} technical rate differs "
                    "from its Timebase."
                )
        frame_rate = technical.get("frameRate")
        if (
            isinstance(frame_rate, dict)
            and math.gcd(frame_rate["numerator"], frame_rate["denominator"]) != 1
        ):
            errors.append(
                f"Realization {realization['id']!r} exact rational frameRate is "
                "not in lowest terms."
            )
    for track in tracks.values():
        track_timebase = timebases.get(track["timebaseId"])
        if track_timebase is None:
            errors.append(f"Track {track['id']!r} has unresolved timebaseId.")
        realization = realizations.get(track["realizationId"])
        if realization is None:
            errors.append(
                f"Track {track['id']!r} realizationId must resolve to a Realization."
            )
        else:
            technical = realization["technicalMetadata"]
            actual_kind = technical["kind"]
            if actual_kind not in modality_kinds[track["modality"]]:
                errors.append(
                    f"Track {track['id']!r} modality {track['modality']!r} is "
                    f"incompatible with realization technical kind {actual_kind!r}."
                )
            if (
                technical.get("timebaseId") is not None
                and technical["timebaseId"] != track["timebaseId"]
            ):
                errors.append(
                    f"Track {track['id']!r} timebase differs from its Realization."
                )
            if (
                track.get("coordinateFrameId") is not None
                and technical.get("coordinateFrameId") is not None
                and track["coordinateFrameId"] != technical["coordinateFrameId"]
            ):
                errors.append(
                    f"Track {track['id']!r} coordinate frame differs from its "
                    "Realization."
                )
            expected_rate: Any = None
            if (
                track_timebase is not None
                and actual_kind == "audio"
                and track_timebase["unit"] == "http://qudt.org/vocab/unit/SAMPLE"
            ):
                expected_rate = technical.get("sampleRate")
            elif (
                track_timebase is not None
                and actual_kind == "video"
                and track_timebase["unit"] == "http://qudt.org/vocab/unit/FRAME"
            ):
                expected_rate = technical.get("frameRate")
            if expected_rate is not None and rate_value(
                track_timebase["rate"]
            ) != rate_value(expected_rate):
                errors.append(
                    f"Track {track['id']!r} realization rate differs from its Timebase."
                )
        if track.get("coordinateFrameId") not in (None, *frame_ids):
            errors.append(f"Track {track['id']!r} has unresolved coordinateFrameId.")
    for mapping in mappings.values():
        if (
            mapping["sourceTimebaseId"] not in timebases
            or mapping["targetTimebaseId"] not in timebases
        ):
            errors.append(
                f"Synchronization mapping {mapping['id']!r} has an unresolved timebase."
            )
        if mapping["sourceTimebaseId"] == mapping["targetTimebaseId"]:
            errors.append(
                f"Synchronization mapping {mapping['id']!r} maps a timebase to itself."
            )
        if mapping["activityId"] not in activity_ids:
            errors.append(
                f"Synchronization mapping {mapping['id']!r} has unresolved activityId."
            )
        else:
            activity = activities[mapping["activityId"]]
            method_activity_kinds = {
                "shared-clock": {"capture", "measurement"},
                "timecode": {"capture", "measurement", "processing"},
                "event-matching": {"processing", "inference"},
                "cross-correlation": {"processing", "inference"},
                "manual": {"authoring", "annotation", "processing"},
                "device-timestamp": {"capture", "measurement"},
            }
            if activity["activityKind"] not in method_activity_kinds[mapping["method"]]:
                errors.append(
                    f"Synchronization mapping {mapping['id']!r} method "
                    f"{mapping['method']!r} conflicts with its Activity kind."
                )
            if mapping["id"] not in activity["outputIds"]:
                errors.append(
                    f"Synchronization mapping {mapping['id']!r} is absent from its "
                    "Activity outputs."
                )
        target_timebase = timebases.get(mapping["targetTimebaseId"])
        if target_timebase is not None and isinstance(mapping.get("jitter"), dict):
            _validate_uncertainty(
                f"Synchronization mapping {mapping['id']!r} jitter",
                mapping["jitter"],
                errors,
                (),
                target_timebase["unit"],
                matrix_integrity=False,
            )
        previous_segment: dict[str, Any] | None = None
        for segment in mapping["segments"]:
            if segment["sourceEndExclusive"] <= segment["sourceStart"]:
                errors.append(
                    f"Synchronization mapping {mapping['id']!r} has an empty segment."
                )
            if previous_segment is not None:
                previous_end = previous_segment["sourceEndExclusive"]
                if segment["sourceStart"] < previous_end:
                    errors.append(
                        f"Synchronization mapping {mapping['id']!r} has "
                        "overlapping segments."
                    )
                elif previous_segment["discontinuityAfter"] == "none":
                    if segment["sourceStart"] > previous_end:
                        errors.append(
                            f"Synchronization mapping {mapping['id']!r} has an "
                            "undeclared source-clock gap."
                        )
                    else:
                        previous_target_end = _number_fraction(
                            previous_end
                        ) * _number_fraction(
                            previous_segment["scale"]
                        ) + _number_fraction(previous_segment["offset"])
                        current_target_start = _number_fraction(
                            segment["sourceStart"]
                        ) * _number_fraction(segment["scale"]) + _number_fraction(
                            segment["offset"]
                        )
                        if previous_target_end != current_target_start:
                            errors.append(
                                f"Synchronization mapping {mapping['id']!r} jumps "
                                "at a boundary declared continuous."
                            )
            if target_timebase is not None:
                _validate_uncertainty(
                    f"Synchronization mapping {mapping['id']!r} segment residual",
                    segment["residualUncertainty"],
                    errors,
                    (),
                    target_timebase["unit"],
                    matrix_integrity=False,
                )
            previous_segment = segment
    for annotation in annotations.values():
        target = annotation["target"]
        if target["trackId"] not in tracks:
            errors.append(f"Annotation {annotation['id']!r} has unresolved trackId.")
        if (
            target.get("endExclusive") is not None
            and target.get("start") is not None
            and target["endExclusive"] <= target["start"]
        ):
            errors.append(
                f"Annotation {annotation['id']!r} has an empty temporal selector."
            )
        if annotation["createdByAgentId"] not in agent_ids:
            errors.append(
                f"Annotation {annotation['id']!r} has unresolved createdByAgentId."
            )
        activity_id = annotation.get("activityId")
        if activity_id not in (None, *activity_ids):
            errors.append(f"Annotation {annotation['id']!r} has unresolved activityId.")
        elif activity_id is not None:
            activity = activities[activity_id]
            if activity["activityKind"] not in {
                "authoring",
                "annotation",
                "processing",
                "inference",
            }:
                errors.append(
                    f"Annotation {annotation['id']!r} has an incompatible Activity kind."
                )
            if annotation["id"] not in activity["outputIds"]:
                errors.append(
                    f"Annotation {annotation['id']!r} is absent from its Activity outputs."
                )
            if annotation["createdByAgentId"] not in activity["agentIds"]:
                errors.append(
                    f"Annotation {annotation['id']!r} creator is absent from its "
                    "Activity agents."
                )
            created = _instant(annotation["createdAt"])
            if (
                not _instant(activity["startedAt"])
                <= created
                <= _instant(activity["endedAt"])
            ):
                errors.append(
                    f"Annotation {annotation['id']!r} creation time is outside its "
                    "Activity."
                )
        body = annotation.get("body")
        if isinstance(body, dict) and set(body) == {"id"} and body["id"] not in known:
            errors.append(f"Annotation {annotation['id']!r} has unresolved body id.")
    return {**timebases, **tracks, **mappings, **annotations}


def validate_physical(
    manifest: dict[str, Any],
    known: set[str],
    scientific: dict[str, dict[str, dict[str, Any]]],
    errors: list[str],
) -> None:
    value = manifest.get("physicalSystem", {})
    ids: dict[str, str] = {}
    components = _registry(
        value.get("components"), "physicalSystem.components", errors, ids
    )
    ports = _registry(value.get("ports"), "physicalSystem.ports", errors, ids)
    connections = _registry(
        value.get("connections"), "physicalSystem.connections", errors, ids
    )
    sensors = _registry(value.get("sensors"), "physicalSystem.sensors", errors, ids)
    actuators = _registry(
        value.get("actuators"), "physicalSystem.actuators", errors, ids
    )
    states = _registry(
        value.get("stateBindings"), "physicalSystem.stateBindings", errors, ids
    )
    interaction = manifest.get("interactionModel", {})
    state_ids = {x["id"] for x in interaction.get("stateVariables", [])}
    transfer_ids = {x["id"] for x in interaction.get("transferFunctions", [])}
    timing_ids = {x["id"] for x in interaction.get("timingConstraints", [])}
    entity_ids = {x["id"] for x in manifest.get("entities", [])}
    observation_ids = set(scientific["observations"])
    parent_edges: dict[str, list[str]] = {identifier: [] for identifier in components}
    for component in components.values():
        if component["entityId"] not in entity_ids:
            errors.append(
                f"Physical component {component['id']!r} has unresolved entityId."
            )
        if component.get("parentComponentId") not in (None, *components):
            errors.append(
                f"Physical component {component['id']!r} has unresolved parentComponentId."
            )
        elif component.get("parentComponentId") is not None:
            parent_edges[component["id"]].append(component["parentComponentId"])
        declared_ports = component.get("portIds")
        if declared_ports is not None:
            actual_ports = {
                identifier
                for identifier, port in ports.items()
                if port["componentId"] == component["id"]
            }
            if set(declared_ports) != actual_ports:
                errors.append(
                    f"Physical component {component['id']!r} portIds does not exactly "
                    "match the ports that name the component."
                )
    _find_cycle(parent_edges, "Physical component parent hierarchy", errors)
    for port in ports.values():
        if port["componentId"] not in components:
            errors.append(f"Physical port {port['id']!r} has unresolved componentId.")
    for connection in connections.values():
        if (
            connection["sourcePortId"] not in ports
            or connection["targetPortId"] not in ports
        ):
            errors.append(
                f"Physical connection {connection['id']!r} has an unresolved port."
            )
        else:
            source = ports[connection["sourcePortId"]]
            target = ports[connection["targetPortId"]]
            if source["direction"] not in {"output", "bidirectional"}:
                errors.append(
                    f"Physical connection {connection['id']!r} starts at a non-output port."
                )
            if target["direction"] not in {"input", "bidirectional"}:
                errors.append(
                    f"Physical connection {connection['id']!r} ends at a non-input port."
                )
            if connection.get("bidirectional") is True and (
                source["direction"] != "bidirectional"
                or target["direction"] != "bidirectional"
            ):
                errors.append(
                    f"Bidirectional physical connection {connection['id']!r} "
                    "requires two bidirectional ports."
                )
            if source["id"] == target["id"]:
                errors.append(
                    f"Physical connection {connection['id']!r} connects a port to itself."
                )
        if connection.get("delayConstraintId") not in (None, *timing_ids):
            errors.append(
                f"Physical connection {connection['id']!r} has unresolved delayConstraintId."
            )
    for sensor in sensors.values():
        if (
            sensor["componentId"] not in components
            or sensor["outputPortId"] not in ports
        ):
            errors.append(f"Sensor {sensor['id']!r} has unresolved topology.")
        elif ports[sensor["outputPortId"]]["componentId"] != sensor[
            "componentId"
        ] or ports[sensor["outputPortId"]]["direction"] not in {
            "output",
            "bidirectional",
        }:
            errors.append(
                f"Sensor {sensor['id']!r} output port is incompatible with its component."
            )
        if sensor["protocolId"] not in scientific["protocols"]:
            errors.append(f"Sensor {sensor['id']!r} has unresolved protocolId.")
        if sensor.get("calibrationId") not in (None, *scientific["calibrations"]):
            errors.append(f"Sensor {sensor['id']!r} has unresolved calibrationId.")
    for actuator in actuators.values():
        if (
            actuator["componentId"] not in components
            or actuator["inputPortId"] not in ports
        ):
            errors.append(f"Actuator {actuator['id']!r} has unresolved topology.")
        elif ports[actuator["inputPortId"]]["componentId"] != actuator[
            "componentId"
        ] or ports[actuator["inputPortId"]]["direction"] not in {
            "input",
            "bidirectional",
        }:
            errors.append(
                f"Actuator {actuator['id']!r} input port is incompatible with its component."
            )
        if actuator["protocolId"] not in scientific["protocols"]:
            errors.append(f"Actuator {actuator['id']!r} has unresolved protocolId.")
        if actuator.get("transferFunctionId") not in (None, *transfer_ids):
            errors.append(
                f"Actuator {actuator['id']!r} has unresolved transferFunctionId."
            )
    for state in states.values():
        if (
            state["stateVariableId"] not in state_ids
            or state["componentId"] not in components
        ):
            errors.append(
                f"State binding {state['id']!r} has unresolved state or component."
            )
        if state.get("observationId") not in (None, *observation_ids):
            errors.append(
                f"State binding {state['id']!r} has unresolved observationId."
            )


def validate_acoustics04(
    manifest: dict[str, Any], known: set[str], errors: list[str]
) -> None:
    value = manifest.get("acoustics")
    if not isinstance(value, dict):
        return
    frames = {record["id"]: record for record in value.get("coordinateFrames", [])}
    poses = {record["id"]: record for record in value.get("poses", [])}
    measurements = {record["id"]: record for record in value.get("measurements", [])}
    responses = {record["id"]: record for record in value.get("responseSets", [])}
    metrics = {record["id"]: record for record in value.get("metricSets", [])}
    scenes = {record["id"]: record for record in value.get("audioScenes", [])}
    render_configs = {
        record["id"]: record for record in value.get("renderConfigurations", [])
    }
    entities = {record["id"]: record for record in manifest.get("entities", [])}
    assets = {record["id"]: record for record in manifest.get("logicalAssets", [])}
    realizations = manifest.get("realizations", [])
    realizations_by_id = {record["id"]: record for record in realizations}
    realizations_by_asset: dict[str, list[dict[str, Any]]] = {
        identifier: [] for identifier in assets
    }
    for realization in realizations:
        realizations_by_asset.setdefault(realization["assetId"], []).append(realization)
    activities = {
        record["id"]: record
        for record in manifest.get("scientific", {}).get("activities", [])
    }
    calibrations = {
        record["id"]
        for record in manifest.get("scientific", {}).get("calibrations", [])
    }
    timebases = {
        record["id"] for record in manifest.get("multimodal", {}).get("timebases", [])
    }

    def asset_has_kind(identifier: str, kinds: set[str]) -> bool:
        return any(
            realization.get("technicalMetadata", {}).get("kind") in kinds
            for realization in realizations_by_asset.get(identifier, [])
        )

    def status_has_activity_kind(
        owner: str,
        status: str,
        activity_id: str,
    ) -> None:
        allowed = {
            "measured": {"capture", "measurement", "digitization"},
            "simulated": {"simulation"},
            "inferred": {"inference"},
            "learned": {"inference", "processing"},
            "authored": {"authoring", "annotation"},
            "hybrid": {"processing", "simulation", "inference", "render"},
        }
        activity = activities.get(activity_id)
        if activity is not None and activity["activityKind"] not in allowed[status]:
            errors.append(
                f"{owner} representation status {status!r} conflicts with generating "
                f"Activity kind {activity['activityKind']!r}."
            )

    frame_edges: dict[str, list[str]] = {identifier: [] for identifier in frames}
    for frame in frames.values():
        identifier = frame["id"]
        parent = frame.get("parentFrameId")
        if parent is not None:
            if parent not in frames:
                errors.append(
                    f"Coordinate frame {identifier!r} has unresolved parentFrameId."
                )
            else:
                frame_edges[identifier].append(parent)
                if frames[parent]["dimension"] != frame["dimension"]:
                    errors.append(
                        f"Coordinate frame {identifier!r} and its parent have different "
                        "dimensions."
                    )
                if "geodetic" in {
                    frames[parent]["coordinateType"],
                    frame["coordinateType"],
                }:
                    errors.append(
                        f"Coordinate frame {identifier!r} uses an affine parent edge "
                        "with a geodetic frame."
                    )
        matrix = frame.get("transformToParent")
        if (
            isinstance(matrix, list)
            and len(matrix) == 16
            and matrix[12:] != [0, 0, 0, 1]
        ):
            errors.append(
                f"Coordinate frame {identifier!r} transformToParent is not affine "
                "row-major homogeneous form."
            )
        if isinstance(matrix, list) and len(matrix) == 16:
            if frame["dimension"] == 2:
                linear = [[matrix[0], matrix[1]], [matrix[4], matrix[5]]]
                if _linear_rcond(linear) <= AFFINE_CONDITION_THRESHOLD:
                    errors.append(
                        f"Coordinate frame {identifier!r} transformToParent is singular "
                        "or numerically ill-conditioned."
                    )
                if any(
                    abs(matrix[index] - expected) > TWO_DIMENSIONAL_EMBEDDING_TOLERANCE
                    for index, expected in (
                        (2, 0),
                        (6, 0),
                        (8, 0),
                        (9, 0),
                        (10, 1),
                        (11, 0),
                    )
                ):
                    errors.append(
                        f"Two-dimensional coordinate frame {identifier!r} transform "
                        "does not preserve the canonical z=0 embedding."
                    )
            else:
                linear = [
                    [matrix[0], matrix[1], matrix[2]],
                    [matrix[4], matrix[5], matrix[6]],
                    [matrix[8], matrix[9], matrix[10]],
                ]
                if _linear_rcond(linear) <= AFFINE_CONDITION_THRESHOLD:
                    errors.append(
                        f"Coordinate frame {identifier!r} transformToParent is singular "
                        "or numerically ill-conditioned."
                    )
        if frame["coordinateType"] == "geodetic":
            units = frame.get("axisUnits", [])
            if len(units) != frame["dimension"]:
                errors.append(
                    f"Geodetic coordinate frame {identifier!r} axisUnits length does "
                    "not match dimension."
                )
        up, forward = frame["upAxis"], frame["forwardAxis"]
        if (
            up != "not-applicable"
            and forward != "not-applicable"
            and up[-1] == forward[-1]
        ):
            errors.append(
                f"Coordinate frame {identifier!r} uses collinear up and forward axes."
            )
        if frame["dimension"] == 2 and any(
            axis.endswith("Z") for axis in (up, forward)
        ):
            errors.append(
                f"Two-dimensional coordinate frame {identifier!r} cannot use a Z axis."
            )
        uncertainty = frame.get("registrationUncertainty")
        if isinstance(uncertainty, dict):
            _validate_uncertainty(
                f"Coordinate frame {identifier!r} registration",
                uncertainty,
                errors,
                (frame["dimension"],),
                frame.get("unit"),
                frame.get("axisUnits"),
                matrix_integrity=False,
            )
    _find_cycle(frame_edges, "Coordinate-frame graph", errors)

    def frame_root(identifier: Any) -> str | None:
        seen: set[str] = set()
        while identifier in frames and identifier not in seen:
            seen.add(identifier)
            parent = frames[identifier].get("parentFrameId")
            if parent is None:
                return identifier
            identifier = parent
        return None

    for pose in poses.values():
        frame = frames.get(pose["frameId"])
        local_frame = frames.get(pose.get("localFrameId"))
        if frame is None:
            errors.append(f"Pose {pose['id']!r} has unresolved frameId.")
        if pose.get("localFrameId") is not None and local_frame is None:
            errors.append(f"Pose {pose['id']!r} has unresolved localFrameId.")
        if pose["subjectId"] not in entities:
            errors.append(f"Pose {pose['id']!r} has unresolved subjectId.")
        if frame is not None and len(pose["position"]) != frame["dimension"]:
            errors.append(
                f"Pose {pose['id']!r} position dimension does not match frame."
            )
        extent = pose.get("extent")
        if (
            extent is not None
            and frame is not None
            and len(extent) != frame["dimension"]
        ):
            errors.append(f"Pose {pose['id']!r} extent dimension does not match frame.")
        if extent is not None and any(value < 0 for value in extent):
            errors.append(f"Pose {pose['id']!r} extent must be non-negative.")
        if frame is not None and frame["dimension"] == 2 and "orientationXYZW" in pose:
            errors.append(
                f"Two-dimensional pose {pose['id']!r} cannot use a quaternion."
            )
        if (
            frame is not None
            and frame["dimension"] == 3
            and "orientationRadians" in pose
        ):
            errors.append(
                f"Three-dimensional pose {pose['id']!r} cannot use orientationRadians."
            )
        quaternion = pose.get("orientationXYZW")
        has_orientation = quaternion is not None or "orientationRadians" in pose
        if has_orientation and local_frame is None:
            errors.append(
                f"Pose {pose['id']!r} orientation requires a local Coordinate Frame."
            )
        if has_orientation and frame is not None and local_frame is not None:
            if frame["dimension"] != local_frame["dimension"]:
                errors.append(
                    f"Pose {pose['id']!r} orientation frames have different dimensions."
                )
            if frame["coordinateType"] not in {"cartesian", "projected"} or local_frame[
                "coordinateType"
            ] not in {"cartesian", "projected"}:
                errors.append(
                    f"Pose {pose['id']!r} orientation requires Cartesian/projected "
                    "local and target frames."
                )
            if frame.get("unit") != local_frame.get("unit"):
                errors.append(
                    f"Pose {pose['id']!r} orientation frames require the same unit; "
                    "scale conversion must be explicit."
                )
            if (
                frame["handedness"] == "not-applicable"
                or frame["handedness"] != local_frame["handedness"]
            ):
                errors.append(
                    f"Pose {pose['id']!r} orientation frames require the same "
                    "applicable handedness; reflection must be explicit."
                )
        if (
            frame is not None
            and frame["coordinateType"] == "geodetic"
            and (quaternion is not None or "orientationRadians" in pose)
        ):
            errors.append(
                f"Pose {pose['id']!r} must express orientation in a local projected "
                "or Cartesian frame, not directly in a geodetic frame."
            )
        if (
            quaternion is not None
            and frame is not None
            and (
                frame["coordinateType"] not in {"cartesian", "projected"}
                or frame["handedness"] == "not-applicable"
            )
        ):
            errors.append(
                f"Pose {pose['id']!r} quaternion requires a Cartesian/projected "
                "frame with declared handedness."
            )
        if (
            quaternion is not None
            and abs(sum(value * value for value in quaternion) - 1.0)
            > QUATERNION_NORM_SQUARED_TOLERANCE
        ):
            errors.append(f"Pose {pose['id']!r} quaternion must have unit norm.")
        if pose["interpolation"] == "spherical-linear" and quaternion is None:
            errors.append(
                f"Pose {pose['id']!r} spherical-linear interpolation requires a quaternion."
            )
        if quaternion is not None and pose["interpolation"] in {"linear", "cubic"}:
            errors.append(
                f"Pose {pose['id']!r} quaternion orientation requires step or "
                "spherical-linear interpolation."
            )
        if "orientationRadians" in pose and pose["interpolation"] == "cubic":
            errors.append(
                f"Pose {pose['id']!r} two-dimensional orientation does not define "
                "cubic angular interpolation."
            )
        if pose["interpolation"] != "none" and "trajectoryRealizationId" not in pose:
            errors.append(
                f"Pose {pose['id']!r} interpolation requires a trajectoryRealizationId."
            )
        if frame is not None and isinstance(pose.get("positionUncertainty"), dict):
            _validate_uncertainty(
                f"Pose {pose['id']!r} position",
                pose["positionUncertainty"],
                errors,
                (frame["dimension"],),
                frame.get("unit"),
                frame.get("axisUnits"),
                matrix_integrity=False,
            )
        orientation_uncertainty = pose.get("orientationUncertainty")
        if isinstance(orientation_uncertainty, dict) and frame is not None:
            shape = _numeric_shape(orientation_uncertainty.get("value"))
            rotation_dimension = 1 if frame["dimension"] == 2 else 3
            expected = (
                (rotation_dimension, rotation_dimension)
                if orientation_uncertainty.get("kind") == "covariance"
                else ()
            )
            if (
                orientation_uncertainty.get("kind") != "registration-rms"
                and shape != expected
            ):
                errors.append(
                    f"Pose {pose['id']!r} orientation uncertainty has invalid dimension."
                )
            if orientation_uncertainty.get("unit") != "http://qudt.org/vocab/unit/RAD":
                errors.append(
                    f"Pose {pose['id']!r} orientation uncertainty must use radians."
                )
        for field in ("configurationId", "stateId"):
            if pose.get(field) not in (None, *entities):
                errors.append(f"Pose {pose['id']!r} has unresolved {field}.")
        _time_order(
            f"Pose {pose['id']!r}",
            pose.get("validFrom"),
            pose.get("validUntil"),
            errors,
        )
        trajectory = pose.get("trajectoryRealizationId")
        trajectory_record = realizations_by_id.get(trajectory)
        if trajectory is not None and trajectory_record is None:
            errors.append(
                f"Pose {pose['id']!r} has unresolved trajectoryRealizationId."
            )
        elif trajectory_record is not None and trajectory_record.get(
            "technicalMetadata", {}
        ).get("kind") not in {"trajectory", "motion-capture", "sensor-data"}:
            errors.append(
                f"Pose {pose['id']!r} trajectory realization is not trajectory-capable."
            )
        elif (
            trajectory_record is not None
            and trajectory_record.get("technicalMetadata", {}).get("coordinateFrameId")
            != pose["frameId"]
        ):
            errors.append(
                f"Pose {pose['id']!r} trajectory realization frame differs from "
                "the Pose target frame."
            )

    for binding in value.get("geometryBindings", []):
        if binding["subjectId"] not in entities:
            errors.append(
                f"Geometry binding {binding['id']!r} has unresolved subjectId."
            )
        if binding["logicalAssetId"] not in assets:
            errors.append(
                f"Geometry binding {binding['id']!r} has unresolved logicalAssetId."
            )
        elif not asset_has_kind(binding["logicalAssetId"], {"geometry"}):
            errors.append(
                f"Geometry binding {binding['id']!r} asset has no geometry realization."
            )

    def check_band_axis(owner: str, axis: dict[str, Any]) -> int:
        centers = axis["centerFrequenciesHz"]
        if centers != sorted(centers):
            errors.append(f"{owner} center frequencies must be strictly ascending.")
        lower, upper = axis.get("lowerEdgesHz"), axis.get("upperEdgesHz")
        if (lower is None) != (upper is None):
            errors.append(
                f"{owner} must provide lowerEdgesHz and upperEdgesHz together."
            )
        if lower is not None and upper is not None:
            if len(lower) != len(centers) or len(upper) != len(centers):
                errors.append(
                    f"{owner} band-edge lengths must match center frequencies."
                )
            elif any(
                not lower[index] < centers[index] < upper[index]
                for index in range(len(centers))
            ):
                errors.append(
                    f"{owner} band edges must bracket every center frequency."
                )
            elif any(lower[index] < upper[index - 1] for index in range(1, len(lower))):
                errors.append(f"{owner} acoustic bands overlap.")
        return len(centers)

    for material in value.get("materialModels", []):
        band_count = check_band_axis(
            f"Material model {material['id']!r}", material["bandAxis"]
        )
        status_has_activity_kind(
            f"Material model {material['id']!r}",
            material["representationStatus"],
            material["generatedById"],
        )
        if material["materialEntityId"] not in entities:
            errors.append(
                f"Material model {material['id']!r} has unresolved materialEntityId."
            )
        if material.get("environmentStateId") not in (None, *entities):
            errors.append(
                f"Material model {material['id']!r} has unresolved environmentStateId."
            )
        for field in ("absorption", "scattering", "transmissionLossDB"):
            if field in material and len(material[field]) != band_count:
                errors.append(
                    f"Material model {material['id']!r} {field} length does not "
                    "match its band axis."
                )
        for field in ("surfaceImpedanceAssetId",):
            if material.get(field) not in (None, *assets):
                errors.append(
                    f"Material model {material['id']!r} has unresolved {field}."
                )
        uncertainty_units = {
            "absorptionUncertainty": "http://qudt.org/vocab/unit/UNITLESS",
            "scatteringUncertainty": "http://qudt.org/vocab/unit/UNITLESS",
            "transmissionLossUncertainty": "http://qudt.org/vocab/unit/DeciB",
        }
        for field, expected_unit in uncertainty_units.items():
            uncertainty = material.get(field)
            if not isinstance(uncertainty, dict):
                continue
            _validate_uncertainty(
                f"Material model {material['id']!r} {field}",
                uncertainty,
                errors,
                (band_count,),
                expected_unit,
                matrix_integrity=False,
            )

    for measurement in measurements.values():
        _time_order(
            f"Response measurement {measurement['id']!r}",
            measurement.get("validFrom"),
            measurement.get("validUntil"),
            errors,
        )
        for field in (
            "sourceId",
            "receiverId",
            "spaceId",
            "sourceSpaceId",
            "receivingSpaceId",
            "separatingElementId",
            "configurationId",
            "stateId",
        ):
            if measurement.get(field) not in (None, *entities):
                errors.append(
                    f"Response measurement {measurement['id']!r} has unresolved {field}."
                )
        for reference in measurement.get("transmissionPathIds", []):
            if reference not in entities:
                errors.append(
                    f"Response measurement {measurement['id']!r} has unresolved "
                    f"transmissionPathId {reference!r}."
                )
        source_pose = poses.get(measurement["sourcePoseId"])
        receiver_pose = poses.get(measurement["receiverPoseId"])
        if (
            source_pose is not None
            and source_pose["subjectId"] != measurement["sourceId"]
        ):
            errors.append(
                f"Response measurement {measurement['id']!r} source pose describes "
                "a different subject."
            )
        if (
            receiver_pose is not None
            and receiver_pose["subjectId"] != measurement["receiverId"]
        ):
            errors.append(
                f"Response measurement {measurement['id']!r} receiver pose describes "
                "a different subject."
            )
        roots = {
            frame_root(item["frameId"])
            for item in (source_pose, receiver_pose)
            if item is not None
        }
        roots.discard(None)
        if len(roots) > 1:
            errors.append(
                f"Response measurement {measurement['id']!r} poses have no common "
                "coordinate-frame root."
            )

    response_fallback_edges: dict[str, list[str]] = {
        identifier: [] for identifier in responses
    }
    for response in responses.values():
        status_has_activity_kind(
            f"Response set {response['id']!r}",
            response["representationStatus"],
            response["generatedById"],
        )
        if response["responseEntityId"] not in entities:
            errors.append(
                f"Response set {response['id']!r} has unresolved responseEntityId."
            )
        if response["logicalAssetId"] not in assets:
            errors.append(
                f"Response set {response['id']!r} has unresolved logicalAssetId."
            )
        for reference in response["measurementIds"]:
            if reference not in measurements:
                errors.append(
                    f"Response set {response['id']!r} has unresolved measurementId."
                )
        if response.get("delayAssetId") not in (None, *assets):
            errors.append(
                f"Response set {response['id']!r} has unresolved delayAssetId."
            )
        for reference in response.get("calibrationIds", []):
            if reference not in calibrations:
                errors.append(
                    f"Response set {response['id']!r} has unresolved calibrationId."
                )
        interpolation = response.get("interpolation")
        if isinstance(interpolation, dict):
            if interpolation["domain"] not in known:
                errors.append(
                    f"Response set {response['id']!r} interpolation has unresolved domain."
                )
            if interpolation.get("fallbackResponseSetId") not in (None, *responses):
                errors.append(
                    f"Response set {response['id']!r} interpolation has unresolved fallback."
                )
            elif interpolation.get("fallbackResponseSetId") is not None:
                response_fallback_edges[response["id"]].append(
                    interpolation["fallbackResponseSetId"]
                )
            if interpolation.get("modelAssetId") not in (None, *assets):
                errors.append(
                    f"Response set {response['id']!r} interpolation has unresolved model asset."
                )
            for field in ("trainingInputIds", "validationInputIds"):
                for reference in interpolation.get(field, []):
                    if reference not in known:
                        errors.append(
                            f"Response set {response['id']!r} interpolation has "
                            f"unresolved {field} reference."
                        )
            if interpolation.get("qualityMetricSetId") not in (None, *metrics):
                errors.append(
                    f"Response set {response['id']!r} interpolation has unresolved metric set."
                )
        if response["representationStatus"] == "learned":
            if not isinstance(interpolation, dict) or interpolation.get(
                "method"
            ) not in {
                "neural-field",
                "hybrid",
            }:
                errors.append(
                    f"Learned response set {response['id']!r} requires a neural-field "
                    "or hybrid interpolation contract."
                )
            elif (
                interpolation.get("modelAssetId") is None
                or not interpolation.get("trainingInputIds")
                or not interpolation.get("validationInputIds")
                or interpolation.get("qualityMetricSetId") is None
                or interpolation.get("determinism") is None
            ):
                errors.append(
                    f"Learned response set {response['id']!r} lacks model, training, "
                    "validation, quality, or determinism evidence."
                )
    _find_cycle(response_fallback_edges, "Response-set fallback graph", errors)

    time_domain_response_kinds = {
        "rir",
        "brir",
        "srir",
        "hrir",
    }
    mapped_response_ids: set[str] = set()
    for realization in realizations:
        technical = realization.get("technicalMetadata", {})
        impulse = technical.get("impulseResponse")
        if not isinstance(impulse, dict):
            continue
        response = responses.get(impulse["responseSetId"])
        if response is None:
            errors.append(
                f"Realization {realization['id']!r} impulseResponse has unresolved responseSetId."
            )
            continue
        mapped_response_ids.add(response["id"])
        if realization["assetId"] != response["logicalAssetId"]:
            errors.append(
                f"Realization {realization['id']!r} impulseResponse belongs to another "
                "response-set asset."
            )
        frame_count = technical.get("frameCount")
        if frame_count is not None and impulse["sampleCount"] != frame_count:
            errors.append(
                f"Realization {realization['id']!r} impulse-response sampleCount does "
                "not match audio frameCount."
            )
        measurement_ids = [
            mapping["measurementId"] for mapping in impulse["measurementMappings"]
        ]
        if len(measurement_ids) != len(set(measurement_ids)):
            errors.append(
                f"Realization {realization['id']!r} assigns a response measurement "
                "more than once."
            )
        if set(measurement_ids) != set(response["measurementIds"]):
            errors.append(
                f"Realization {realization['id']!r} impulse-response mappings do not "
                "cover exactly the response-set measurements."
            )
        channel_count = technical["channelCount"]
        addressed_channels: set[tuple[int | None, int]] = set()
        for mapping in impulse["measurementMappings"]:
            data_index = mapping.get("dataIRIndex")
            for channel in mapping["channelIndices"]:
                address = (data_index, channel)
                if channel >= channel_count:
                    errors.append(
                        f"Realization {realization['id']!r} impulse-response mapping "
                        "selects an absent channel."
                    )
                if address in addressed_channels:
                    errors.append(
                        f"Realization {realization['id']!r} impulse-response channel "
                        "address is assigned more than once."
                    )
                addressed_channels.add(address)
            if (
                impulse["timeZeroPolicy"] == "per-measurement-delay"
                and "delaySamples" not in mapping
            ):
                errors.append(
                    f"Realization {realization['id']!r} per-measurement delay policy "
                    "requires delaySamples on every mapping."
                )
    for response in responses.values():
        if (
            response["responseKind"] in time_domain_response_kinds
            and response["id"] not in mapped_response_ids
        ):
            errors.append(
                f"Time-domain response set {response['id']!r} has no exact realization "
                "with matching impulse-response metadata."
            )

    for metric_set in metrics.values():
        band_count = check_band_axis(
            f"Metric set {metric_set['id']!r}", metric_set["bandAxis"]
        )
        metric_activity = activities.get(metric_set["generatedById"])
        metric_activity_kinds = {
            "observed": {"capture", "measurement"},
            "calculated": {"processing"},
            "simulated": {"simulation"},
            "inferred": {"inference"},
            "reviewed": {"review"},
            "accepted": {"review"},
        }
        for metric in metric_set["metrics"]:
            if (
                metric_activity is not None
                and metric_activity["activityKind"]
                not in metric_activity_kinds[metric["status"]]
            ):
                errors.append(
                    f"Metric set {metric_set['id']!r} status {metric['status']!r} "
                    "conflicts with its generating Activity kind."
                )
            if len(metric["values"]) != band_count:
                errors.append(
                    f"Metric set {metric_set['id']!r} value length does not match band axis."
                )
            if isinstance(metric.get("uncertainty"), dict):
                _validate_uncertainty(
                    f"Metric set {metric_set['id']!r} {metric['property']!r}",
                    metric["uncertainty"],
                    errors,
                    (band_count,),
                    metric["unit"],
                    matrix_integrity=False,
                )
            for field in (
                "sourceId",
                "receiverId",
                "sourceSpaceId",
                "receivingSpaceId",
                "separatingElementId",
            ):
                if metric.get(field) not in (None, *entities):
                    errors.append(
                        f"Metric set {metric_set['id']!r} has unresolved metric {field}."
                    )
        for reference in metric_set["subjectIds"]:
            if reference not in entities:
                errors.append(
                    f"Metric set {metric_set['id']!r} subjectIds must resolve to "
                    "Entities."
                )
        for reference in metric_set["inputIds"]:
            if reference not in known:
                errors.append(f"Metric set {metric_set['id']!r} has unresolved input.")

    asset_channel_limits: dict[str, int] = {}
    asset_channel_counts: dict[str, set[int]] = {}
    for realization in realizations:
        channel_count = realization.get("technicalMetadata", {}).get("channelCount")
        if isinstance(channel_count, int):
            asset = realization["assetId"]
            asset_channel_counts.setdefault(asset, set()).add(channel_count)
            asset_channel_limits[asset] = min(
                channel_count, asset_channel_limits.get(asset, channel_count)
            )
    for scene in scenes.values():
        if scene["sceneEntityId"] not in entities:
            errors.append(f"Audio scene {scene['id']!r} has unresolved sceneEntityId.")
        if scene["coordinateFrameId"] not in frames:
            errors.append(
                f"Audio scene {scene['id']!r} has unresolved coordinateFrameId."
            )
        for reference in scene["mediaAssetIds"]:
            if reference not in assets:
                errors.append(
                    f"Audio scene {scene['id']!r} has unresolved mediaAssetId."
                )
            elif not asset_has_kind(reference, {"audio"}):
                errors.append(
                    f"Audio scene {scene['id']!r} media asset has no audio realization."
                )
        if scene.get("contentTimebase") not in (None, *timebases):
            errors.append(
                f"Audio scene {scene['id']!r} has unresolved contentTimebase."
            )
        for binding in scene["bindings"]:
            if binding["entityId"] not in entities:
                errors.append(
                    f"Audio binding {binding['id']!r} has unresolved entityId."
                )
            if binding["mediaAssetId"] not in assets:
                errors.append(
                    f"Audio binding {binding['id']!r} has unresolved mediaAssetId."
                )
            elif binding["mediaAssetId"] not in scene["mediaAssetIds"]:
                errors.append(
                    f"Audio binding {binding['id']!r} references an asset outside its scene."
                )
            if binding.get("poseId") not in (None, *poses):
                errors.append(f"Audio binding {binding['id']!r} has unresolved poseId.")
            elif (
                binding.get("poseId") is not None
                and poses[binding["poseId"]]["subjectId"] != binding["entityId"]
            ):
                errors.append(
                    f"Audio binding {binding['id']!r} pose describes another entity."
                )
            elif binding.get("poseId") is not None and frame_root(
                poses[binding["poseId"]]["frameId"]
            ) != frame_root(scene["coordinateFrameId"]):
                errors.append(
                    f"Audio binding {binding['id']!r} pose is disconnected from the scene frame."
                )
            if binding.get("directivityResponseSetId") not in (None, *responses):
                errors.append(
                    f"Audio binding {binding['id']!r} has unresolved directivity response."
                )
            limit = asset_channel_limits.get(binding["mediaAssetId"])
            channel_indices = binding.get("channelIndices", [])
            if (
                channel_indices
                and len(asset_channel_counts.get(binding["mediaAssetId"], set())) > 1
            ):
                errors.append(
                    f"Audio binding {binding['id']!r} has ambiguous channel indices "
                    "across realizations with different channel counts."
                )
            if limit is not None and any(index >= limit for index in channel_indices):
                errors.append(
                    f"Audio binding {binding['id']!r} selects an absent channel."
                )
        if scene.get("metadataAssetId") not in (None, *assets):
            errors.append(
                f"Audio scene {scene['id']!r} has unresolved metadataAssetId."
            )

    fallback_edges: dict[str, list[str]] = {
        identifier: [] for identifier in render_configs
    }
    for config in render_configs.values():
        if config["sceneId"] not in scenes:
            errors.append(
                f"Render configuration {config['id']!r} has unresolved sceneId."
            )
        if config["coordinateFrameId"] not in frames:
            errors.append(
                f"Render configuration {config['id']!r} has unresolved coordinateFrameId."
            )
        if (
            config["sceneId"] in scenes
            and config["coordinateFrameId"] in frames
            and frame_root(config["coordinateFrameId"])
            != frame_root(scenes[config["sceneId"]]["coordinateFrameId"])
        ):
            errors.append(
                f"Render configuration {config['id']!r} frame is disconnected from its scene."
            )
        listener = config["listener"]
        for field, allowed in (
            ("coordinateFrameId", frames),
            ("poseId", poses),
            ("receiverId", entities),
            ("trajectoryRealizationId", realizations_by_id),
        ):
            if listener.get(field) not in (None, *allowed):
                errors.append(
                    f"Render configuration {config['id']!r} listener has unresolved {field}."
                )
        listener_pose = poses.get(listener.get("poseId"))
        if (
            listener_pose is not None
            and listener_pose["subjectId"] != listener["receiverId"]
        ):
            errors.append(
                f"Render configuration {config['id']!r} listener pose describes "
                "another receiver."
            )
        if (
            listener_pose is not None
            and listener.get("coordinateFrameId") in frames
            and frame_root(listener_pose["frameId"])
            != frame_root(listener["coordinateFrameId"])
        ):
            errors.append(
                f"Render configuration {config['id']!r} listener pose is disconnected "
                "from its listener frame."
            )
        if (
            listener.get("coordinateFrameId") in frames
            and config["coordinateFrameId"] in frames
            and frame_root(listener["coordinateFrameId"])
            != frame_root(config["coordinateFrameId"])
        ):
            errors.append(
                f"Render configuration {config['id']!r} listener frame is disconnected."
            )
        trajectory = listener.get("trajectoryRealizationId")
        if (
            trajectory is not None
            and trajectory in realizations_by_id
            and realizations_by_id[trajectory].get("technicalMetadata", {}).get("kind")
            not in {"trajectory", "motion-capture", "sensor-data"}
        ):
            errors.append(
                f"Render configuration {config['id']!r} listener trajectory "
                "realization is not trajectory-capable."
            )
        elif (
            trajectory is not None
            and trajectory in realizations_by_id
            and realizations_by_id[trajectory]
            .get("technicalMetadata", {})
            .get("coordinateFrameId")
            != listener["coordinateFrameId"]
        ):
            errors.append(
                f"Render configuration {config['id']!r} listener trajectory frame "
                "differs from the listener frame."
            )
        for field in ("headphoneCompensationAssetId", "personalizationAssetId"):
            if listener.get(field) not in (None, *assets):
                errors.append(
                    f"Render configuration {config['id']!r} listener has unresolved {field}."
                )
        for reference in config["inputIds"]:
            if reference not in known:
                errors.append(
                    f"Render configuration {config['id']!r} has unresolved input."
                )
        for feature in config["features"]:
            for reference in feature.get("inputIds", []):
                if reference not in known:
                    errors.append(
                        f"Render configuration {config['id']!r} feature has unresolved input."
                    )
        for reference in config["fallbackIds"]:
            if reference not in render_configs:
                errors.append(
                    f"Render configuration {config['id']!r} has unresolved fallback."
                )
            else:
                fallback_edges[config["id"]].append(reference)
        if config["outsideDomainPolicy"] == "fallback" and not config["fallbackIds"]:
            errors.append(
                f"Render configuration {config['id']!r} requires at least one fallback."
            )
        if config.get("validDomainId") not in (None, *entities):
            errors.append(
                f"Render configuration {config['id']!r} has unresolved validDomainId."
            )
        for level in config.get("levelsOfDetail", []):
            for reference in level["inputIds"]:
                if reference not in known:
                    errors.append(
                        f"Render configuration {config['id']!r} level of detail has "
                        "unresolved input."
                    )
    _find_cycle(fallback_edges, "Render fallback graph", errors)


def validate_cross_module_references(
    manifest: dict[str, Any], known: set[str], errors: list[str]
) -> None:
    activity_records = {
        record["id"]: record
        for record in manifest.get("scientific", {}).get("activities", [])
    }
    activities = set(activity_records)
    reviews = {
        record["id"] for record in manifest.get("scientific", {}).get("reviews", [])
    }

    def walk(value: Any, path: str, key: str | None = None) -> None:
        if key in _DECLARATION_SCAN_SKIP:
            return
        if isinstance(value, dict):
            identifier = value.get("id")
            generated = value.get("generatedById")
            if generated is not None and generated not in activities:
                errors.append(f"{path}.generatedById does not resolve to an Activity.")
            elif (
                generated is not None
                and is_identifier(identifier)
                and identifier not in activity_records[generated]["outputIds"]
            ):
                errors.append(
                    f"{path}.generatedById Activity does not declare the record as "
                    "an output."
                )
            for generated_id in value.get("generatedByIds", []):
                if generated_id not in activities:
                    errors.append(
                        f"{path}.generatedByIds does not resolve to an Activity."
                    )
                elif (
                    is_identifier(identifier)
                    and identifier not in activity_records[generated_id]["outputIds"]
                ):
                    errors.append(
                        f"{path}.generatedByIds Activity does not declare the record "
                        "as an output."
                    )
            reviewed = value.get("reviewedById")
            if reviewed is not None and reviewed not in reviews:
                errors.append(f"{path}.reviewedById does not resolve to a Review.")
            for child_key, child in value.items():
                walk(child, f"{path}.{child_key}", child_key)
        elif isinstance(value, list):
            for index, child in enumerate(value):
                walk(child, f"{path}[{index}]", key)

    walk(manifest, "$")
    transformation_statuses = {
        "converted",
        "derived",
        "simulated",
        "inferred",
        "reconstructed",
        "redacted",
        "hybrid",
    }
    compatible_activity_kinds = {
        "captured": {"capture", "measurement", "digitization"},
        "authored": {"authoring", "annotation"},
        "converted": {"processing", "digitization", "migration"},
        "derived": {"processing", "render"},
        "simulated": {"simulation"},
        "inferred": {"inference"},
        "reconstructed": {"processing"},
        "redacted": {"processing"},
        "hybrid": {"processing", "simulation", "inference", "render"},
    }
    for realization in manifest.get("realizations", []):
        provenance = realization.get("provenanceIds", [])
        if any(reference not in activities for reference in provenance):
            errors.append(
                f"Realization {realization['id']!r} provenanceIds must resolve to Activities."
            )
        generating_activities = [
            activity_records[reference]
            for reference in provenance
            if reference in activity_records
            and realization["id"] in activity_records[reference].get("outputIds", [])
        ]
        if not generating_activities:
            errors.append(
                f"Realization {realization['id']!r} must be declared as an output by "
                "at least one cited provenance Activity."
            )
        status = realization["representationStatus"].rsplit("/", 1)[-1]
        if status in compatible_activity_kinds and not any(
            activity["activityKind"] in compatible_activity_kinds[status]
            for activity in generating_activities
        ):
            errors.append(
                f"Realization {realization['id']!r} status {status!r} is not "
                "supported by a compatible generating Activity kind."
            )
        if status in transformation_statuses and not any(
            activity.get("inputIds") for activity in generating_activities
        ):
            errors.append(
                f"Realization {realization['id']!r} transformation status requires "
                "a provenance Activity with explicit inputs."
            )
    for relation in manifest.get("relations", []):
        scope = relation.get("scope")
        if not isinstance(scope, dict):
            continue
        for reference in scope.get("appliesToIds", []):
            if reference not in known:
                errors.append(
                    f"Relation {relation['id']!r} scope has unresolved appliesToId."
                )
        _time_order(
            f"Relation {relation['id']!r} scope",
            scope.get("validFrom"),
            scope.get("validUntil"),
            errors,
        )
        if (
            scope.get("start") is not None
            and scope.get("endExclusive") is not None
            and scope["endExclusive"] <= scope["start"]
        ):
            errors.append(f"Relation {relation['id']!r} has an empty scoped interval.")

    release = manifest["release"]
    if release.get("supersedesReleaseId") == release["id"]:
        errors.append("A release cannot supersede itself.")
    _time_order(
        "Manifest modification interval",
        manifest["createdAt"],
        manifest["modifiedAt"],
        errors,
    )


_LOCAL_REFERENCE_EXEMPT = {
    "scoreElementId",  # identifier inside an external score realization
    "selectionSetId",  # local grouping token, not a declared record identifier
    "softwareHeritageId",  # SWHID syntax, not a VAO record identifier
    "supersedesReleaseId",  # prior immutable release may be outside this manifest
    "variantSetId",  # local variant grouping token
}


def validate_local_references(
    manifest: dict[str, Any], known: set[str], errors: list[str]
) -> None:
    """Require every schema-named local ``*Id`` reference to resolve.

    External identities use explicit IRI-valued fields such as ``crs``,
    ``observedProperty``, classifications, and external-identifier records.
    The small exempt set contains fields whose schema intentionally defines a
    non-record token or a reference to a different release.
    """

    def walk(value: Any, path: str, key: str | None = None) -> None:
        if key in _DECLARATION_SCAN_SKIP:
            return
        if isinstance(value, dict):
            for child_key, child in value.items():
                child_path = f"{path}.{child_key}"
                if child_key not in _LOCAL_REFERENCE_EXEMPT:
                    if child_key.endswith("Id") and isinstance(child, str):
                        if child not in known:
                            errors.append(
                                f"{child_path} has unresolved local reference {child!r}."
                            )
                    elif child_key.endswith("Ids") and isinstance(child, list):
                        for index, reference in enumerate(child):
                            if isinstance(reference, str) and reference not in known:
                                errors.append(
                                    f"{child_path}[{index}] has unresolved local "
                                    f"reference {reference!r}."
                                )
                walk(child, child_path, child_key)
        elif isinstance(value, list):
            for index, child in enumerate(value):
                walk(child, f"{path}[{index}]", key)

    walk(manifest, "$")


def _state_value_valid(record: dict[str, Any], value: Any) -> bool:
    kind = record["valueType"]
    if kind == "boolean":
        valid = isinstance(value, bool)
    elif kind == "integer":
        valid = isinstance(value, int) and not isinstance(value, bool)
    elif kind == "number":
        valid = isinstance(value, (int, float)) and not isinstance(value, bool)
    else:
        valid = value in record.get("allowedValues", [])
    if not valid:
        return False
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if record.get("minimumValue") is not None and value < record["minimumValue"]:
            return False
        if record.get("maximumValue") is not None and value > record["maximumValue"]:
            return False
    return True


def _event_value_valid(record: dict[str, Any], value_present: bool, value: Any) -> bool:
    domain = record["valueDomain"]
    if domain == "none":
        return not value_present
    if not value_present:
        return False
    if domain == "boolean":
        return isinstance(value, bool)
    if domain in {"integer", "midi-key", "midi-value"}:
        valid = isinstance(value, int) and not isinstance(value, bool)
        if domain in {"midi-key", "midi-value"}:
            valid = valid and 0 <= value <= 127
        return valid
    if domain == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if domain == "enumerated":
        return value in record.get("allowedValues", [])
    return True


def _supports_reproducibility_claim(environment: dict[str, Any]) -> bool:
    """Return whether the minimum exact software-identity threshold is met."""
    if not environment.get("runtimeDescription"):
        return False
    if (
        environment.get("containerDigest") is not None
        or environment.get("identityScope") == "executable"
    ):
        return True
    dependencies = environment.get("dependencies", [])
    has_environment_lock = any(
        dependency.get("dependencyRole") == "environment-lock"
        and dependency.get("identityScope") == "environment-lock"
        for dependency in dependencies
    )
    if environment.get("identityScope") in {"source-file", "source-bundle"}:
        return has_environment_lock
    if environment.get("identityScope") == "environment-lock":
        return any(
            dependency.get("dependencyRole") == "source"
            and dependency.get("identityScope") in {"source-file", "source-bundle"}
            for dependency in dependencies
        )
    return False


def validate_runtime(manifest: dict[str, Any], errors: list[str]) -> None:
    runtime = manifest.get("runtime", {})
    model = manifest.get("interactionModel") or {}
    if model and model.get("executionSemantics") != runtime.get("executionSemantics"):
        errors.append(
            "interactionModel.executionSemantics and runtime.executionSemantics must be equal."
        )
    resolution = runtime.get("executionSemantics", {}).get("timeResolution", {})
    if isinstance(resolution, dict) and (
        isinstance(resolution.get("value"), bool)
        or not isinstance(resolution.get("value"), (int, float))
        or resolution["value"] <= 0
    ):
        errors.append("Runtime timeResolution must be a positive scalar quantity.")

    states = {record["id"]: record for record in model.get("stateVariables", [])}
    events = {record["id"]: record for record in model.get("eventTypes", [])}
    controls = {record["id"]: record for record in model.get("controls", [])}
    render_bindings = {record["id"] for record in model.get("renderBindings", [])}
    transitions = {record["id"] for record in model.get("transitions", [])}
    environments = {
        record["id"]: record
        for record in manifest.get("scientific", {}).get("softwareEnvironments", [])
    }

    random_ids: set[str] = set()
    random_sources: dict[str, dict[str, Any]] = {}
    for record in [*runtime.get("randomSources", []), *model.get("randomSources", [])]:
        if record["id"] in random_ids:
            errors.append(f"Random source {record['id']!r} is duplicated.")
        random_ids.add(record["id"])
        random_sources[record["id"]] = record

    for state in states.values():
        if not _state_value_valid(state, state["defaultValue"]):
            errors.append(
                f"State variable {state['id']!r} has an invalid defaultValue."
            )
    for transition in model.get("transitions", []):
        for condition in transition.get("conditions", []):
            state = states.get(condition["stateVariableId"])
            if state is None:
                continue
            if not _state_value_valid(state, condition["value"]):
                errors.append(
                    f"Transition {transition['id']!r} condition value is incompatible "
                    "with its state variable."
                )
            if condition["operator"] not in {"equals", "not-equals"} and state[
                "valueType"
            ] not in {"integer", "number"}:
                errors.append(
                    f"Transition {transition['id']!r} applies an ordering operator to "
                    "a non-numeric state."
                )
        for action in transition["actions"]:
            state = states.get(action["targetId"])
            operation = action["operation"]
            if state is None:
                continue
            if operation == "set-state" and (
                "value" not in action
                or not _state_value_valid(state, action.get("value"))
            ):
                errors.append(
                    f"Transition {transition['id']!r} set-state value is incompatible."
                )
            if operation == "toggle-state" and state["valueType"] != "boolean":
                errors.append(
                    f"Transition {transition['id']!r} toggles a non-boolean state."
                )
            if operation == "increment-state" and state["valueType"] not in {
                "integer",
                "number",
            }:
                errors.append(
                    f"Transition {transition['id']!r} increments a non-numeric state."
                )

    for process in model.get("processModels", []):
        if process["processKind"] == "stochastic":
            if process.get("randomSourceId") not in random_ids:
                errors.append(
                    f"Stochastic process {process['id']!r} has unresolved randomSourceId."
                )
            distribution = process.get("probabilityDistribution", {})
            candidate_count = len(process.get("actions", [])) + len(
                process.get("childProcessIds", [])
            )
            if candidate_count < 1:
                errors.append(
                    f"Stochastic process {process['id']!r} has no selectable candidate."
                )
            source = random_sources.get(process.get("randomSourceId"))
            word_range = (
                1 << (32 if source and source["algorithm"] == "pcg32" else 64)
                if source
                else None
            )
            if distribution.get("kind") == "categorical":
                parameters = distribution.get("parameters", {})
                total = sum(parameters.values())
                if total > 9_007_199_254_740_991:
                    errors.append(
                        f"Stochastic process {process['id']!r} categorical weight total "
                        "exceeds 2^53-1."
                    )
                if word_range is not None and total > word_range:
                    errors.append(
                        f"Stochastic process {process['id']!r} categorical weight total "
                        "exceeds its generator word range."
                    )
                for key in parameters:
                    bound = str(candidate_count)
                    if len(key) > len(bound) or (
                        len(key) == len(bound) and key >= bound
                    ):
                        errors.append(
                            f"Stochastic process {process['id']!r} assigns weight to "
                            f"missing candidate index {key}."
                        )
            elif word_range is not None and candidate_count > word_range:
                errors.append(
                    f"Stochastic process {process['id']!r} candidate count exceeds its "
                    "generator word range."
                )
    for renderer in runtime.get("renderers", []):
        environment = environments.get(renderer["softwareEnvironmentId"])
        if environment is None:
            errors.append(
                f"Renderer {renderer['id']!r} has unresolved softwareEnvironmentId."
            )
        elif renderer["deterministic"] and not _supports_reproducibility_claim(
            environment
        ):
            errors.append(
                f"Renderer {renderer['id']!r} claims deterministic operation, but "
                "its Software Environment supplies no exact runnable/reconstructable "
                "identity plus runtime."
            )

    for trace in runtime.get("conformanceTraces", []):
        tuples: set[tuple[int | float, int, str, int]] = set()
        for event in trace["inputEvents"]:
            order = (
                event["timestamp"],
                -event.get("priority", 0),
                event["eventTypeId"],
                event["sequence"],
            )
            if order in tuples:
                errors.append(
                    f"Conformance trace {trace['id']!r} has a non-unique event ordering tuple."
                )
            tuples.add(order)
            event_type = events.get(event["eventTypeId"])
            if event_type is None:
                errors.append(
                    f"Conformance trace {trace['id']!r} has unresolved eventTypeId."
                )
            elif not _event_value_valid(
                event_type, "value" in event, event.get("value")
            ):
                errors.append(
                    f"Conformance trace {trace['id']!r} event value violates its domain."
                )
            if event.get("controlId") not in (None, *controls):
                errors.append(
                    f"Conformance trace {trace['id']!r} has unresolved controlId."
                )
        for key, state_value in trace.get("initialState", {}).items():
            if key not in states or not _state_value_valid(states[key], state_value):
                errors.append(
                    f"Conformance trace {trace['id']!r} has invalid initial state {key!r}."
                )
        expected_state = trace["expected"]["state"]
        if set(expected_state) != set(states):
            errors.append(
                f"Conformance trace {trace['id']!r} expected state must cover every state variable exactly once."
            )
        for key, state_value in expected_state.items():
            if key not in states or not _state_value_valid(states[key], state_value):
                errors.append(
                    f"Conformance trace {trace['id']!r} has invalid expected state {key!r}."
                )
        for binding in trace["expected"]["renderBindingIds"]:
            if binding not in render_bindings:
                errors.append(
                    f"Conformance trace {trace['id']!r} has unresolved renderBindingId."
                )
        for emitted in trace["expected"]["emittedEvents"]:
            if emitted.get("sourceTransitionId") not in (None, *transitions):
                errors.append(
                    f"Conformance trace {trace['id']!r} has unresolved emitted transition."
                )
        errors.extend(vao04_runtime.verify_trace(manifest, trace))


def validate_interaction04(manifest: dict[str, Any], errors: list[str]) -> None:
    model = manifest.get("interactionModel") or {}
    entities = {x["id"] for x in manifest.get("entities", [])}
    controls = {x["id"]: x for x in model.get("controls", [])}
    events = {x["id"]: x for x in model.get("eventTypes", [])}
    routes = {x["id"] for x in model.get("routingRules", [])}
    processes = {x["id"] for x in model.get("processModels", [])}
    timings = {x["id"] for x in model.get("timingConstraints", [])}
    render_bindings = {x["id"] for x in model.get("renderBindings", [])}
    states = {x["id"]: x for x in model.get("stateVariables", [])}
    sample_mappings = {
        x["id"] for x in (manifest.get("playable") or {}).get("sampleMappings", [])
    }
    sample_variants = {
        x["id"] for x in (manifest.get("playable") or {}).get("sampleVariants", [])
    }

    def check_condition(condition: dict[str, Any], owner: str) -> None:
        state = states.get(condition["stateVariableId"])
        if state is None:
            errors.append(f"{owner} has a condition on a non-state record.")
            return
        if not _state_value_valid(state, condition["value"]):
            errors.append(f"{owner} has a condition value outside its state domain.")
        if condition["operator"] not in {"equals", "not-equals"} and state[
            "valueType"
        ] not in {"integer", "number"}:
            errors.append(f"{owner} orders a non-numeric state value.")

    def check_action(action: dict[str, Any], owner: str) -> None:
        operation = action["operation"]
        target = action["targetId"]
        if action.get("delayConstraintId") not in (None, *timings):
            errors.append(f"{owner} has an invalid delay Timing Constraint.")
        if operation in {"set-state", "toggle-state", "increment-state"}:
            state = states.get(target)
            if state is None:
                errors.append(f"{owner} state action targets a non-state record.")
                return
            if operation == "set-state" and not _state_value_valid(
                state, action.get("value")
            ):
                errors.append(f"{owner} sets a value outside its state domain.")
            if operation == "toggle-state" and state["valueType"] != "boolean":
                errors.append(f"{owner} toggles a non-boolean state.")
            if operation == "increment-state" and state["valueType"] not in {
                "integer",
                "number",
            }:
                errors.append(f"{owner} increments a non-numeric state.")
        elif operation == "emit-event" and target not in events:
            errors.append(f"{owner} emit-event target is not an Event Type.")
        elif operation == "route-event" and target not in routes:
            errors.append(f"{owner} route-event target is not a Routing Rule.")
        elif operation in {"start-process", "stop-process"} and target not in processes:
            errors.append(f"{owner} process action target is not a Process Model.")
        elif operation == "select-render-binding" and target not in render_bindings:
            errors.append(f"{owner} selection target is not a Render Binding.")

    for control in controls.values():
        if control.get("entityId") not in (None, *entities):
            errors.append(f"Control {control['id']!r} has unresolved entityId.")
        if "defaultValue" in control and not _state_value_valid(
            control, control["defaultValue"]
        ):
            errors.append(f"Control {control['id']!r} has an invalid defaultValue.")
    for state in states.values():
        if state.get("subjectEntityId") not in (None, *entities):
            errors.append(
                f"State variable {state['id']!r} has unresolved subjectEntityId."
            )
    for binding in model.get("protocolBindings", []):
        control = controls.get(binding["controlId"])
        if control is None:
            errors.append(f"Protocol binding {binding['id']!r} has invalid controlId.")
        if binding["eventTypeId"] not in events:
            errors.append(
                f"Protocol binding {binding['id']!r} has invalid eventTypeId."
            )
        if (
            "activationValue" in binding
            and "deactivationValue" in binding
            and binding["activationValue"] == binding["deactivationValue"]
        ):
            errors.append(
                f"Protocol binding {binding['id']!r} activation and deactivation "
                "values must differ."
            )

    for registry in ("transitions", "routingRules", "renderBindings"):
        for record in model.get(registry, []):
            for condition in record.get("conditions", []):
                check_condition(condition, f"{registry} record {record['id']!r}")
    for registry in ("transitions", "processModels"):
        for record in model.get(registry, []):
            for action in record.get("actions", []):
                check_action(action, f"{registry} record {record['id']!r}")
    for transition in model.get("transitions", []):
        if transition["eventTypeId"] not in events:
            errors.append(f"Transition {transition['id']!r} has invalid eventTypeId.")
        if transition.get("controlId") not in (None, *controls):
            errors.append(f"Transition {transition['id']!r} has invalid controlId.")
    route_edges: dict[str, list[str]] = {}
    for route in model.get("routingRules", []):
        if (
            route["sourceEntityId"] not in entities
            or route["targetEntityId"] not in entities
        ):
            errors.append(f"Routing rule {route['id']!r} has invalid Entity endpoint.")
        if route.get("sourceControlId") not in (None, *controls):
            errors.append(f"Routing rule {route['id']!r} has invalid sourceControlId.")
        if (
            route.get("delayConstraintId") is not None
            and route["delayConstraintId"] not in timings
        ):
            errors.append(
                f"Routing rule {route['id']!r} has unresolved delayConstraintId."
            )
        if (
            route.get("routingBehavior") in {"copies", "transposes"}
            and route.get("delayConstraintId") is None
        ):
            route_edges.setdefault(route["sourceEntityId"], []).append(
                route["targetEntityId"]
            )
            route_edges.setdefault(route["targetEntityId"], [])
    _find_cycle(route_edges, "Zero-delay routing graph", errors)
    for binding in model.get("protocolBindings", []):
        if binding["protocol"] == "MIDI-2.0":
            for key in (
                "umpGroup",
                "functionBlock",
                "umpMessageType",
                "dataResolutionBits",
            ):
                if key not in binding:
                    errors.append(f"MIDI 2.0 binding {binding['id']!r} requires {key}.")
            if binding.get("jrTimestamp") is not True:
                errors.append(
                    f"MIDI 2.0 binding {binding['id']!r} must declare JR timestamp handling."
                )
    for process in model.get("processModels", []):
        for reference in process.get("childProcessIds", []):
            if reference not in processes:
                errors.append(f"Process {process['id']!r} has invalid childProcessId.")
        if process.get("cancellationControlId") not in (None, *controls):
            errors.append(
                f"Process {process['id']!r} has invalid cancellationControlId."
            )
        if process.get("durationConstraintId") not in (None, *timings):
            errors.append(
                f"Process {process['id']!r} has invalid durationConstraintId."
            )
        if any(
            reference not in timings
            for reference in process.get("timingConstraintIds", [])
        ):
            errors.append(f"Process {process['id']!r} has invalid timingConstraintId.")
    for binding in model.get("renderBindings", []):
        if binding.get("eventTypeId") not in (None, *events):
            errors.append(f"Render binding {binding['id']!r} has invalid eventTypeId.")
        if binding.get("processModelId") not in (None, *processes):
            errors.append(
                f"Render binding {binding['id']!r} has invalid processModelId."
            )
        if any(
            reference not in sample_mappings
            for reference in binding.get("sampleMappingIds", [])
        ):
            errors.append(
                f"Render binding {binding['id']!r} has invalid sampleMappingId."
            )
        if any(
            reference not in sample_variants
            for reference in binding.get("sampleVariantIds", [])
        ):
            errors.append(
                f"Render binding {binding['id']!r} has invalid sampleVariantId."
            )
    for transfer in model.get("transferFunctions", []):
        domain = transfer.get("validDomain", [])
        if domain and any(bounds[1] <= bounds[0] for bounds in domain):
            errors.append(
                f"Transfer function {transfer['id']!r} has an empty valid domain."
            )
        if len(domain) > 1 and not transfer.get("inputKinds"):
            errors.append(
                f"Multivariate transfer function {transfer['id']!r} requires inputKinds."
            )
        dimensions = len(transfer.get("inputKinds", []))
        if dimensions:
            if len(domain) != dimensions:
                errors.append(
                    f"Multivariate transfer function {transfer['id']!r} validDomain "
                    "dimension does not match inputKinds."
                )
            for point in transfer["points"]:
                if len(point.get("inputs", [])) != dimensions:
                    errors.append(
                        f"Multivariate transfer function {transfer['id']!r} point "
                        "dimension does not match inputKinds."
                    )
        elif any("inputs" in point for point in transfer["points"]):
            errors.append(
                f"Transfer function {transfer['id']!r} uses vector inputs without inputKinds."
            )


def validate_delivery(
    manifest: dict[str, Any],
    scientific: dict[str, dict[str, dict[str, Any]]],
    errors: list[str],
    warnings: list[str],
) -> None:
    realization_ids = {x["id"] for x in manifest.get("realizations", [])}
    profile_ids = {
        record["id"]
        for registry in ("profiles", "materializableProfiles")
        for record in manifest.get(registry, [])
    }
    for realization in manifest.get("realizations", []):
        content_digests = realization.get("contentDigests", [])
        algorithms = [record["algorithm"] for record in content_digests]
        if len(algorithms) != len(set(algorithms)):
            errors.append(
                f"Realization {realization['id']!r} repeats a content-digest algorithm."
            )
        digests = {x["algorithm"]: x["value"] for x in content_digests}
        if "sha256" in digests and digests["sha256"] != realization["sha256"]:
            errors.append(
                f"Realization {realization['id']!r} has conflicting SHA-256 identities."
            )
        chunking = realization.get("chunking")
        if chunking:
            chunks = sorted(chunking["chunks"], key=lambda x: x["index"])
            if [x["index"] for x in chunks] != list(range(len(chunks))):
                errors.append(
                    f"Realization {realization['id']!r} has non-contiguous chunk indices."
                )
            if chunks:
                expected_offset = 0
                for chunk in chunks:
                    if chunk["offset"] != expected_offset:
                        errors.append(
                            f"Realization {realization['id']!r} has non-contiguous chunk byte ranges."
                        )
                    expected_offset = chunk["offset"] + chunk["length"]
                if expected_offset != realization["byteSize"]:
                    errors.append(
                        f"Realization {realization['id']!r} chunk coverage does not equal byteSize."
                    )
            elif chunking["strategy"] not in {"external-index", "zarr", "pack-shard"}:
                errors.append(
                    f"Realization {realization['id']!r} has no inline chunks for its chunking strategy."
                )
            if chunking.get("indexRealizationId") not in (None, *realization_ids):
                errors.append(
                    f"Realization {realization['id']!r} has unresolved chunk index realization."
                )
            root = chunking.get("merkleRoot")
            if root and chunks:
                algorithms = {chunk["digest"]["algorithm"] for chunk in chunks}
                if algorithms != {root["algorithm"]}:
                    errors.append(
                        f"Realization {realization['id']!r} Merkle root and chunk algorithms differ."
                    )
                elif merkle_root(chunks, root["algorithm"]) != root["value"]:
                    errors.append(
                        f"Realization {realization['id']!r} has an invalid Merkle root."
                    )
        for key in ("streamingIndexRealizationId", "authenticityEnvelopeRealizationId"):
            if realization.get(key) not in (None, *realization_ids):
                errors.append(
                    f"Realization {realization['id']!r} has unresolved {key}."
                )
    consent_ids = set(scientific["consents"])
    agent_ids = set(scientific["agents"])
    for rights in manifest.get("rights", []):
        for ref in rights.get("performerAgentIds", []) + rights.get(
            "communityAuthorityIds", []
        ):
            if ref not in agent_ids:
                errors.append(
                    f"Rights record {rights['id']!r} has unresolved agent {ref!r}."
                )
        for ref in rights.get("consentIds", []):
            if ref not in consent_ids:
                errors.append(
                    f"Rights record {rights['id']!r} has unresolved consent {ref!r}."
                )
        if rights.get(
            "privacyClassification"
        ) == "community-governed" and not rights.get("communityAuthorityIds"):
            errors.append(
                f"Community-governed rights record {rights['id']!r} requires communityAuthorityIds."
            )
        if rights.get("embargoUntil") and not rights.get("embargoRationale"):
            errors.append(
                f"Embargoed rights record {rights['id']!r} requires embargoRationale."
            )
    for group in manifest.get("assetGroups", []):
        if any(
            reference not in profile_ids
            for reference in group.get("materializesProfileIds", [])
        ):
            errors.append(
                f"Asset group {group['id']!r} materializesProfileIds must resolve "
                "to embedded Profile records."
            )


def _nested_identifiers(value: Any) -> set[str]:
    """Return identifiers declared by nested closed registries.

    Scientific activities may legitimately consume or produce records from the
    acoustics, playable, multimodal, physical, interaction, capture, and runtime
    registries. Those records are not all top-level arrays, so resolving only
    the core top-level registries incorrectly rejects valid provenance chains.
    """
    identifiers: set[str] = set()
    if isinstance(value, dict):
        identifier = value.get("id")
        if is_identifier(identifier):
            identifiers.add(identifier)
        for item in value.values():
            identifiers.update(_nested_identifiers(item))
    elif isinstance(value, list):
        for item in value:
            identifiers.update(_nested_identifiers(item))
    return identifiers


def validate_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    depth_exceeded = _json_depth_exceeded(manifest)
    if depth_exceeded:
        errors.append(
            f"Manifest exceeds the reference JSON nesting limit of {MAX_JSON_DEPTH}."
        )
    else:
        errors.extend(schema_errors(manifest, MANIFEST_SCHEMA))
        _validate_numeric_domain(manifest, errors)
    if manifest.get("$schema") != SCHEMA_URI:
        errors.append("Manifest uses the wrong immutable VAO 0.4.0 schema IRI.")
    contexts = manifest.get("@context", [])
    if not contexts or contexts[0] != CONTEXT_URI:
        errors.append(
            "Manifest does not place the immutable VAO 0.4.0 context IRI first."
        )
    if manifest.get("formatVersion") != FORMAT_VERSION:
        errors.append("Manifest formatVersion is not 0.4.0.")
    if errors:
        return {
            "valid": False,
            "formatVersion": manifest.get("formatVersion"),
            "id": manifest.get("id"),
            "releaseId": manifest.get("release", {}).get("id")
            if isinstance(manifest.get("release"), dict)
            else None,
            "logicalAssetCount": len(manifest.get("logicalAssets", []))
            if isinstance(manifest.get("logicalAssets"), list)
            else 0,
            "realizationCount": len(manifest.get("realizations", []))
            if isinstance(manifest.get("realizations"), list)
            else 0,
            "trackCount": len(manifest.get("multimodal", {}).get("tracks", []))
            if isinstance(manifest.get("multimodal"), dict)
            else 0,
            "scientificRecordCount": 0,
            "errors": sorted(set(errors)),
            "warnings": [],
        }
    try:
        base = vao03.validate_manifest(project_to_03(manifest))
        errors.extend(
            error.replace("VAO 0.3", "VAO 0.4.0").replace(
                "profile/0.3", "profile/0.4.0"
            )
            for error in base["errors"]
        )
        warnings.extend(
            warning
            for warning in base["warnings"]
            if "Acoustics 0.3 profile claim" not in warning
        )
    except (KeyError, TypeError, ValueError, RecursionError) as exc:
        errors.append(f"Cannot apply retained 0.3 semantic checks: {exc}")

    known = set(_global_identifiers(manifest, errors))
    validate_local_references(manifest, known, errors)
    _validate_measurements(manifest, errors)
    scientific = validate_scientific(manifest, known, errors)
    multimodal = validate_multimodal(manifest, known, errors)
    validate_physical(manifest, known, scientific, errors)
    validate_acoustics04(manifest, known, errors)
    validate_cross_module_references(manifest, known, errors)
    validate_interaction04(manifest, errors)
    validate_runtime(manifest, errors)
    validate_delivery(manifest, scientific, errors, warnings)
    validate_discovery(manifest, errors)

    profile_records = [
        record
        for registry in ("profiles", "materializableProfiles")
        for record in manifest.get(registry, [])
        if isinstance(record, dict)
    ]
    profiles = {record["id"] for record in profile_records}
    conforms = set(manifest.get("conformsTo", []))
    for required in (CORE_PROFILE, DYNAMIC_PROFILE):
        if required not in profiles or required not in conforms:
            errors.append(f"Every VAO 0.4.0 release must embed and claim {required}.")
    optional_requirements = [
        (SCIENTIFIC_PROFILE, any(scientific.values())),
        (MULTIMODAL_PROFILE, bool(multimodal)),
        (
            PHYSICAL_PROFILE,
            any(
                manifest.get("physicalSystem", {}).get(k)
                for k in (
                    "components",
                    "ports",
                    "connections",
                    "sensors",
                    "actuators",
                    "stateBindings",
                )
            ),
        ),
        (
            PLAYABLE_PROFILE,
            any(
                isinstance(manifest.get(key), dict)
                for key in ("playable", "interactionModel", "captureDocumentation")
            ),
        ),
        (
            SPATIAL_PROFILE,
            bool(
                isinstance(manifest.get("acoustics"), dict)
                and any(
                    manifest["acoustics"].get(key)
                    for key in ("coordinateFrames", "poses", "geometryBindings")
                )
            )
            or any(
                record.get("coordinateFrameId")
                for record in manifest.get("multimodal", {}).get("tracks", [])
            ),
        ),
        (
            ACOUSTICS_PROFILE,
            bool(
                isinstance(manifest.get("acoustics"), dict)
                and any(
                    manifest["acoustics"].get(key)
                    for key in (
                        "materialModels",
                        "measurements",
                        "responseSets",
                        "metricSets",
                        "audioScenes",
                        "renderConfigurations",
                    )
                )
            ),
        ),
        (
            RUNTIME_PROFILE,
            bool(
                manifest.get("runtime", {}).get("conformanceTraces")
                or manifest.get("runtime", {}).get("randomSources")
                or manifest.get("runtime", {}).get("renderers")
                or any(
                    process.get("processKind") == "stochastic"
                    for process in (manifest.get("interactionModel") or {}).get(
                        "processModels", []
                    )
                )
            ),
        ),
    ]
    for profile, active in optional_requirements:
        if active and (profile not in profiles or profile not in conforms):
            errors.append(f"Content requires embedded and claimed profile {profile}.")
    if ACOUSTICS_PROFILE in profiles and SPATIAL_PROFILE not in profiles:
        errors.append("The Acoustics profile requires the Spatial profile.")
    by_profile = {record["id"]: record for record in profile_records}
    for profile, required_capabilities in REQUIRED_PROFILE_CAPABILITIES.items():
        if profile in by_profile:
            missing = required_capabilities - set(
                by_profile[profile]["requiredCapabilities"]
            )
            if missing:
                errors.append(
                    f"Profile {profile} omits mandatory capabilities: "
                    + ", ".join(sorted(missing))
                    + "."
                )
    if ACOUSTICS_PROFILE in by_profile and ACOUSTIC_CAPABILITIES.isdisjoint(
        by_profile[ACOUSTICS_PROFILE]["requiredCapabilities"]
    ):
        errors.append(
            "The Acoustics profile requires at least one standard acoustic capability."
        )
    for claim in conforms:
        if claim not in profiles:
            errors.append(f"Claimed profile {claim} has no embedded profile record.")
    agent_ids = set(scientific["agents"])
    for field in ("creatorAgentIds", "contributorAgentIds"):
        for agent in manifest.get("discovery", {}).get(field, []):
            if agent not in agent_ids:
                errors.append(
                    f"Discovery {field} value {agent!r} does not resolve to an Agent."
                )

    return {
        "valid": not errors,
        "formatVersion": manifest.get("formatVersion"),
        "id": manifest.get("id"),
        "releaseId": manifest.get("release", {}).get("id")
        if isinstance(manifest.get("release"), dict)
        else None,
        "logicalAssetCount": len(manifest.get("logicalAssets", [])),
        "realizationCount": len(manifest.get("realizations", [])),
        "trackCount": len(manifest.get("multimodal", {}).get("tracks", [])),
        "scientificRecordCount": sum(
            len(x)
            for x in manifest.get("scientific", {}).values()
            if isinstance(x, list)
        ),
        "errors": sorted(set(errors)),
        "warnings": sorted(set(warnings)),
    }


def validate_carrier_parts(
    manifest_data: bytes,
    carrier_data: bytes,
    payload_names: Iterable[str],
    payload_reader: Callable[[str, int], tuple[str, int]],
) -> dict[str, Any]:
    try:
        manifest = strict_json_bytes(manifest_data, MANIFEST_NAME)
        carrier = strict_json_bytes(carrier_data, CARRIER_NAME)
    except vao03.VAO03Error as exc:
        return {
            "valid": False,
            "formatVersion": None,
            "errors": [str(exc)],
            "warnings": [],
        }
    report = validate_manifest(manifest)
    errors, warnings = list(report["errors"]), list(report["warnings"])
    errors.extend(schema_errors(carrier, CARRIER_SCHEMA))
    if carrier.get("manifestSHA256") != sha256_bytes(manifest_data):
        errors.append("Carrier manifestSHA256 does not match exact manifest bytes.")
    if carrier.get("manifestByteSize") != len(manifest_data):
        errors.append("Carrier manifestByteSize does not match exact manifest bytes.")
    if carrier.get("releaseId") != manifest.get("release", {}).get("id"):
        errors.append("Carrier releaseId does not match manifest release.id.")
    realizations = {
        x["id"]: x
        for x in manifest.get("realizations", [])
        if isinstance(x, dict) and "id" in x
    }
    groups = {
        x["id"]: x
        for x in manifest.get("assetGroups", [])
        if isinstance(x, dict) and "id" in x
    }
    payload_map: dict[str, str] = {}
    portable_payload_map: dict[str, str] = {}
    for name in payload_names:
        normalized = unicodedata.normalize("NFC", name)
        if normalized in payload_map:
            errors.append(
                f"Carrier payload paths collide after NFC normalization: {payload_map[normalized]!r}, {name!r}."
            )
        payload_map[normalized] = name
        portable = portable_carrier_path_key(name)
        if portable in portable_payload_map and portable_payload_map[portable] != name:
            errors.append(
                f"Carrier payload paths collide after NFC/case-fold normalization: "
                f"{portable_payload_map[portable]!r}, {name!r}."
            )
        portable_payload_map[portable] = name
    mapped: set[str] = set()
    embedded: set[str] = set()
    verified = 0
    for mapping in carrier.get("embeddedRealizations", []):
        rid, path = mapping.get("realizationId"), mapping.get("path")
        normalized = (
            unicodedata.normalize("NFC", path) if isinstance(path, str) else "<invalid>"
        )
        if rid in embedded:
            errors.append(f"Carrier maps realization {rid!r} more than once.")
        if normalized in mapped:
            errors.append(f"Carrier maps path {path!r} more than once.")
        embedded.add(rid)
        mapped.add(normalized)
        if rid not in realizations:
            errors.append(f"Carrier maps unknown realization {rid!r}.")
            continue
        if not is_safe_path(path, "payload"):
            errors.append(f"Carrier path {path!r} is unsafe.")
            continue
        if normalized not in payload_map:
            errors.append(f"Carrier path {path!r} is missing.")
            continue
        try:
            digest, size = payload_reader(
                payload_map[normalized], realizations[rid]["byteSize"]
            )
        except (OSError, RuntimeError, VAO04Error, zipfile.BadZipFile) as exc:
            errors.append(f"Cannot verify carrier path {path!r}: {exc}")
            continue
        verified += size
        if (
            digest != realizations[rid]["sha256"]
            or size != realizations[rid]["byteSize"]
        ):
            errors.append(
                f"Embedded realization {rid!r} fails exact byte verification."
            )
    if mapped != set(payload_map):
        errors.append("Carrier payload closure does not equal its embedded mapping.")
    for group_id in carrier.get("completeGroupIds", []):
        if group_id not in groups:
            errors.append(f"Carrier declares unknown complete group {group_id!r}.")
        else:
            required: set[str] = set()
            seen: set[str] = set()
            pending = [group_id]
            while pending:
                identifier = pending.pop()
                if identifier in seen or identifier not in groups:
                    continue
                seen.add(identifier)
                required.update(groups[identifier].get("realizationIds", []))
                pending.extend(groups[identifier].get("dependsOnGroupIds", []))
            if not required <= embedded:
                errors.append(f"Carrier complete group {group_id!r} is incomplete.")
    if carrier.get("carrierMode") == "bootstrap" and not embedded:
        errors.append("A bootstrap carrier must embed at least one realization.")
    if carrier.get("carrierMode") == "preservation-closure":
        if set(carrier.get("completeGroupIds", [])) != set(groups):
            errors.append(
                "A preservation closure must mark every asset group complete."
            )
        if set(realizations) != embedded:
            errors.append("A preservation closure must embed every realization.")
    return {
        **report,
        "valid": not errors,
        "verifiedBytes": verified,
        "errors": sorted(set(errors)),
        "warnings": sorted(set(warnings)),
    }


def validate_workspace(path: Path) -> dict[str, Any]:
    errors: list[str] = []
    if not path.is_dir():
        return {
            "valid": False,
            "errors": ["VAO workspace is not a directory."],
            "warnings": [],
        }
    normalized_names: dict[str, str] = {}
    portable_names: dict[str, str] = {}
    entry_count = 0
    total_bytes = 0
    budget_failed = False
    for item in path.rglob("*"):
        entry_count += 1
        if entry_count > MAX_ENTRIES:
            errors.append("Workspace exceeds the reference entry-count limit.")
            budget_failed = True
            break
        relative = item.relative_to(path).as_posix()
        if len(PurePosixPath(relative).parts) > MAX_PATH_SEGMENTS:
            errors.append(
                f"Workspace path exceeds the reference segment-depth limit: {relative!r}."
            )
            budget_failed = True
        normalized = normalized_carrier_path(relative)
        if normalized in normalized_names:
            errors.append(
                f"Workspace paths collide after NFC normalization: {normalized_names[normalized]!r}, {relative!r}."
            )
        normalized_names[normalized] = relative
        portable = portable_carrier_path_key(relative)
        if portable in portable_names and portable_names[portable] != relative:
            errors.append(
                f"Workspace paths collide after NFC/case-fold normalization: "
                f"{portable_names[portable]!r}, {relative!r}."
            )
        portable_names[portable] = relative
        if item.is_symlink():
            errors.append(f"Workspace symbolic link is forbidden: {relative!r}.")
            continue
        try:
            item_stat = item.stat(follow_symlinks=False)
            mode = item_stat.st_mode
        except OSError as exc:
            errors.append(f"Cannot inspect workspace entry {relative!r}: {exc}")
            continue
        if not (stat.S_ISREG(mode) or stat.S_ISDIR(mode)):
            errors.append(f"Workspace special file is forbidden: {relative!r}.")
        if stat.S_ISREG(mode):
            if item_stat.st_nlink > 1:
                errors.append(f"Workspace hard link is forbidden: {relative!r}.")
            if item_stat.st_size > MAX_ENTRY_BYTES:
                errors.append(
                    f"Workspace entry exceeds the reference size limit: {relative!r}."
                )
                budget_failed = True
            total_bytes += item_stat.st_size
            if total_bytes > MAX_TOTAL_BYTES:
                errors.append("Workspace exceeds the reference total-byte limit.")
                budget_failed = True
        root = PurePosixPath(relative).parts[0]
        if root not in {"mimetype", MANIFEST_NAME, "META-INF", "payload"}:
            errors.append(f"Unknown workspace entry {relative!r}.")
        if root in {"mimetype", MANIFEST_NAME} and relative != root:
            errors.append(f"Structural entry {root!r} must be a root file.")
        if root == "META-INF" and relative not in {"META-INF", CARRIER_NAME}:
            errors.append(f"Unknown META-INF entry {relative!r}.")
    for name in ("mimetype", MANIFEST_NAME, CARRIER_NAME):
        target = path / name
        if not target.is_file() or target.is_symlink():
            errors.append(f"Workspace is missing regular structural file {name!r}.")
    for name, limit, label in (
        (MANIFEST_NAME, MAX_MANIFEST_BYTES, "Manifest"),
        (CARRIER_NAME, MAX_DESCRIPTOR_BYTES, "Carrier descriptor"),
    ):
        target = path / name
        try:
            if (
                target.is_file()
                and not target.is_symlink()
                and target.stat().st_size > limit
            ):
                errors.append(f"{label} exceeds the reference validator size limit.")
                budget_failed = True
        except OSError as exc:
            errors.append(f"Cannot inspect workspace structural file {name!r}: {exc}")
    if budget_failed:
        return {"valid": False, "errors": sorted(set(errors)), "warnings": []}
    try:
        if (
            _read_bounded_regular(
                path / "mimetype", len(MIMETYPE.encode()), "Workspace mimetype"
            )
            != MIMETYPE.encode()
        ):
            errors.append("Workspace mimetype bytes are not exact.")
    except (OSError, VAO04Error) as exc:
        errors.append(f"Cannot read workspace mimetype: {exc}")
    try:
        manifest_data = _read_bounded_regular(
            path / MANIFEST_NAME, MAX_MANIFEST_BYTES, "Manifest"
        )
        carrier_data = _read_bounded_regular(
            path / CARRIER_NAME, MAX_DESCRIPTOR_BYTES, "Carrier descriptor"
        )
    except (OSError, VAO04Error) as exc:
        return {
            "valid": False,
            "errors": errors + [f"Cannot read structural file: {exc}"],
            "warnings": [],
        }
    payload_names = (
        [
            item.relative_to(path).as_posix()
            for item in (path / "payload").rglob("*")
            if item.is_file() and not item.is_symlink()
        ]
        if (path / "payload").is_dir()
        else []
    )

    streamed_total = 0

    def reader(name: str, expected_size: int) -> tuple[str, int]:
        nonlocal streamed_total
        remaining_budget = max(0, MAX_TOTAL_BYTES - streamed_total)
        streaming_bound = min(expected_size, MAX_ENTRY_BYTES, remaining_budget)
        with _open_regular_nofollow(path / name) as stream:
            digest, size = sha256_stream_bounded(stream, streaming_bound)
        streamed_total += size
        if streamed_total > MAX_TOTAL_BYTES:
            raise VAO04Error(
                "Workspace payload exceeds the total-byte limit while streaming."
            )
        return digest, size

    report = validate_carrier_parts(manifest_data, carrier_data, payload_names, reader)
    try:
        manifest = strict_json_bytes(manifest_data, MANIFEST_NAME)
        carrier = strict_json_bytes(carrier_data, CARRIER_NAME)
        realizations = {
            item["id"]: item
            for item in manifest.get("realizations", [])
            if isinstance(item, dict) and "id" in item
        }
        for mapping in carrier.get("embeddedRealizations", []):
            realization = realizations.get(mapping.get("realizationId"))
            target = path / str(mapping.get("path", ""))
            if realization is not None and target.is_file():
                with _open_regular_nofollow(target) as stream:
                    report["errors"].extend(validate_chunk_stream(realization, stream))
    except (OSError, vao03.VAO03Error, VAO04Error) as exc:
        report["errors"].append(f"Cannot verify embedded chunks: {exc}")
    report["errors"] = sorted(set(errors + report["errors"]))
    report["valid"] = not report["errors"]
    return report


def validate_archive(path: Path) -> dict[str, Any]:
    try:
        with zipfile.ZipFile(path, "r", allowZip64=True) as archive:
            infos = archive.infolist()
            names = [x.filename for x in infos]
            errors: list[str] = []
            if not infos:
                return {
                    "valid": False,
                    "errors": ["VAO archive is empty."],
                    "warnings": [],
                }
            if len(infos) > MAX_ENTRIES:
                errors.append(
                    "Archive exceeds the reference validator entry-count limit."
                )
            if (
                not infos
                or infos[0].filename != "mimetype"
                or infos[0].compress_type != zipfile.ZIP_STORED
            ):
                errors.append("mimetype must be the first stored ZIP entry.")
            if len(names) != len(set(names)):
                errors.append("Archive contains duplicate paths.")
            normalized_names: dict[str, str] = {}
            portable_names: dict[str, str] = {}
            total = 0
            allowed_exact = {"mimetype", MANIFEST_NAME, CARRIER_NAME}
            for info in infos:
                name = info.filename
                if not is_safe_path(name):
                    errors.append(f"Unsafe archive path {name!r}.")
                if len(PurePosixPath(name).parts) > MAX_PATH_SEGMENTS:
                    errors.append(
                        f"Archive path exceeds the reference segment-depth limit: {name!r}."
                    )
                normalized = normalized_carrier_path(name)
                if normalized in normalized_names:
                    errors.append(
                        f"Duplicate archive path after NFC normalization: {normalized_names[normalized]!r}, {name!r}."
                    )
                normalized_names[normalized] = name
                portable = portable_carrier_path_key(name)
                if portable in portable_names and portable_names[portable] != name:
                    errors.append(
                        "Duplicate archive path after NFC/case-fold normalization: "
                        f"{portable_names[portable]!r}, {name!r}."
                    )
                portable_names[portable] = name
                mode = (info.external_attr >> 16) & 0o170000
                if mode == stat.S_IFLNK:
                    errors.append(f"Archive entry {name!r} is a symbolic link.")
                elif mode and mode not in {stat.S_IFREG, stat.S_IFDIR}:
                    errors.append(f"Archive entry {name!r} is a special file.")
                if info.flag_bits & 0x1:
                    errors.append(f"Encrypted entry is forbidden: {name!r}.")
                if info.compress_type not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}:
                    errors.append(f"Unsupported compression method for {name!r}.")
                if (
                    info.compress_type == zipfile.ZIP_DEFLATED
                    and info.file_size > 0
                    and info.compress_size == 0
                ):
                    errors.append(
                        f"Compressed entry has an impossible zero compressed size: {name!r}."
                    )
                if (
                    info.compress_type == zipfile.ZIP_STORED
                    and info.file_size != info.compress_size
                ):
                    errors.append(
                        f"Stored entry has inconsistent compressed size metadata: {name!r}."
                    )
                if info.file_size > MAX_ENTRY_BYTES:
                    errors.append(
                        f"Entry exceeds the reference validator size limit: {name!r}."
                    )
                if (
                    info.file_size >= RATIO_CHECK_MIN_BYTES
                    and info.compress_size
                    and info.file_size / info.compress_size > MAX_COMPRESSION_RATIO
                ):
                    errors.append(
                        f"Entry exceeds the reference validator compression-ratio limit: {name!r}."
                    )
                total += info.file_size
                if info.is_dir():
                    if not name.startswith("payload/"):
                        errors.append(f"Unknown carrier directory {name!r}.")
                elif name not in allowed_exact and not name.startswith("payload/"):
                    errors.append(f"Unknown carrier entry {name!r}.")
            if total > MAX_TOTAL_BYTES:
                errors.append(
                    "Archive exceeds the reference validator total uncompressed-size limit."
                )
            for required in allowed_exact:
                if required not in normalized_names:
                    errors.append(f"Archive is missing required entry {required!r}.")
            if errors:
                return {"valid": False, "errors": sorted(set(errors)), "warnings": []}
            if archive.getinfo(MANIFEST_NAME).file_size > MAX_MANIFEST_BYTES:
                errors.append("Manifest exceeds the reference validator size limit.")
            if archive.getinfo(CARRIER_NAME).file_size > MAX_DESCRIPTOR_BYTES:
                errors.append(
                    "Carrier descriptor exceeds the reference validator size limit."
                )
            if archive.getinfo("mimetype").file_size != len(MIMETYPE.encode()):
                errors.append("Archive mimetype has an impossible declared size.")
            if errors:
                return {"valid": False, "errors": sorted(set(errors)), "warnings": []}
            try:
                with archive.open("mimetype", "r") as stream:
                    mimetype_data = _read_stream_bounded(
                        stream, len(MIMETYPE.encode()), "Archive mimetype"
                    )
                with archive.open(MANIFEST_NAME, "r") as stream:
                    manifest_data = _read_stream_bounded(
                        stream, MAX_MANIFEST_BYTES, "Manifest"
                    )
                with archive.open(CARRIER_NAME, "r") as stream:
                    carrier_data = _read_stream_bounded(
                        stream, MAX_DESCRIPTOR_BYTES, "Carrier descriptor"
                    )
            except (OSError, RuntimeError, VAO04Error, zipfile.BadZipFile) as exc:
                return {
                    "valid": False,
                    "errors": [f"Cannot read bounded archive structural bytes: {exc}"],
                    "warnings": [],
                }
            if mimetype_data != MIMETYPE.encode():
                errors.append("Archive mimetype bytes are not exact.")
            payload_names = [
                name
                for name in names
                if name.startswith("payload/") and not name.endswith("/")
            ]

            streamed_total = 0

            def reader(name: str, expected_size: int) -> tuple[str, int]:
                nonlocal streamed_total
                remaining_budget = max(0, MAX_TOTAL_BYTES - streamed_total)
                streaming_bound = min(expected_size, MAX_ENTRY_BYTES, remaining_budget)
                with archive.open(name, "r") as stream:
                    digest, size = sha256_stream_bounded(stream, streaming_bound)
                streamed_total += size
                if streamed_total > MAX_TOTAL_BYTES:
                    raise VAO04Error(
                        "Archive payload exceeds the total-byte limit while streaming."
                    )
                return digest, size

            report = validate_carrier_parts(
                manifest_data, carrier_data, payload_names, reader
            )
            try:
                manifest = strict_json_bytes(manifest_data, MANIFEST_NAME)
                carrier = strict_json_bytes(carrier_data, CARRIER_NAME)
                realizations = {
                    item["id"]: item
                    for item in manifest.get("realizations", [])
                    if isinstance(item, dict) and "id" in item
                }
                for mapping in carrier.get("embeddedRealizations", []):
                    realization = realizations.get(mapping.get("realizationId"))
                    name = mapping.get("path")
                    if (
                        realization is not None
                        and isinstance(name, str)
                        and name in names
                    ):
                        with archive.open(name) as stream:
                            report["errors"].extend(
                                validate_chunk_stream(realization, stream)
                            )
            except (
                KeyError,
                OSError,
                RuntimeError,
                vao03.VAO03Error,
                VAO04Error,
            ) as exc:
                report["errors"].append(f"Cannot verify embedded chunks: {exc}")
            report["errors"] = sorted(set(errors + report["errors"]))
            report["valid"] = not report["errors"]
            return report
    except (
        OSError,
        KeyError,
        RuntimeError,
        NotImplementedError,
        zipfile.BadZipFile,
    ) as exc:
        return {
            "valid": False,
            "errors": [f"Cannot read VAO 0.4.0 archive: {exc}"],
            "warnings": [],
        }


def validate(path: Path) -> dict[str, Any]:
    if path.is_dir():
        return validate_workspace(path)
    if path.suffix.lower() == ".json":
        try:
            data = _read_bounded_regular(path, MAX_MANIFEST_BYTES, "Manifest")
            return validate_manifest(strict_json_bytes(data, str(path)))
        except (OSError, vao03.VAO03Error, VAO04Error) as exc:
            return {"valid": False, "errors": [str(exc)], "warnings": []}
    return validate_archive(path)


def _read_companion_descriptor(
    path: Path, schema_path: Path
) -> tuple[dict[str, Any] | None, list[str]]:
    """Read one bounded companion descriptor under the VAO JSON domain."""
    errors: list[str] = []
    try:
        data = _read_bounded_regular(path, MAX_DESCRIPTOR_BYTES, "Companion descriptor")
        value = strict_json_bytes(data, str(path))
    except (OSError, vao03.VAO03Error, VAO04Error) as exc:
        return None, [str(exc)]
    if _json_depth_exceeded(value):
        return None, [
            f"Companion descriptor exceeds the JSON nesting limit of {MAX_JSON_DEPTH}."
        ]
    _validate_numeric_domain(value, errors)
    try:
        errors.extend(schema_errors(value, schema_path))
    except (OSError, RecursionError, ValueError) as exc:
        errors.append(f"Cannot apply companion schema: {exc}")
    return value, sorted(set(errors))


def release_semantic_errors(value: dict[str, Any]) -> list[str]:
    """Check release topology and Unicode/path invariants beyond JSON Schema."""
    errors = list(vao03.release_semantic_errors(value))
    publication = value.get("publication")
    if not isinstance(publication, dict):
        return sorted(set(errors))
    root = publication.get("rootRecord")
    members = publication.get("familyMembers")
    if not isinstance(root, dict) or not isinstance(members, list):
        return sorted(set(errors))
    records = [("rootRecord", root)] + [
        (f"familyMembers[{index}]", member.get("record", {}))
        for index, member in enumerate(members)
        if isinstance(member, dict)
    ]
    for label, record in records:
        if not isinstance(record, dict):
            continue
        normalized: dict[str, str] = {}
        portable: dict[str, str] = {}
        for item in record.get("files", []):
            name = item.get("fileIdentifier") if isinstance(item, dict) else None
            if not isinstance(name, str):
                continue
            if not is_safe_path(name):
                errors.append(f"{label} has unsafe file identifier {name!r}.")
            if PurePosixPath(name).name == "vao-release.json":
                errors.append(
                    f"{label} must not self-inventory a release descriptor named "
                    f"{name!r}."
                )
            canonical = unicodedata.normalize("NFC", name)
            previous = normalized.get(canonical)
            if previous is not None and previous != name:
                errors.append(
                    f"{label} file identifiers {previous!r} and {name!r} collide "
                    "after Unicode NFC normalization."
                )
            else:
                normalized[canonical] = name
            folded = portable_carrier_path_key(name)
            previous = portable.get(folded)
            if previous is not None and previous != name:
                errors.append(
                    f"{label} file identifiers {previous!r} and {name!r} collide "
                    "after Unicode NFC and case-fold normalization."
                )
            else:
                portable[folded] = name
    inverse_relations = {
        "hasPart": "isPartOf",
        "requires": "isRequiredBy",
        "references": "isReferencedBy",
        "isSupplementedBy": "isSupplementTo",
        "isDocumentedBy": "documents",
        "isDerivedFrom": "isSourceOf",
    }
    for index, member in enumerate(members):
        if not isinstance(member, dict):
            continue
        relation = member.get("relationFromRoot")
        inverse = member.get("inverseRelationFromMember")
        expected = inverse_relations.get(relation)
        if inverse is not None and expected is not None and inverse != expected:
            errors.append(
                f"familyMembers[{index}] inverse relation {inverse!r} does not "
                f"match {relation!r}; expected {expected!r}."
            )
    return sorted(set(errors))


def pack_semantic_errors(value: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    realization_ids: set[str] = set()
    paths: dict[str, str] = {}
    portable_paths: dict[str, str] = {}
    for index, member in enumerate(value.get("members", [])):
        if not isinstance(member, dict):
            continue
        identifier = member.get("realizationId")
        if isinstance(identifier, str):
            if identifier in realization_ids:
                errors.append(
                    f"Pack realizationId {identifier!r} occurs more than once."
                )
            realization_ids.add(identifier)
        path = member.get("path")
        if isinstance(path, str):
            if not is_safe_path(path):
                errors.append(f"Pack member path {path!r} is unsafe.")
            normalized = normalized_carrier_path(path)
            previous = paths.get(normalized)
            if previous is not None:
                errors.append(
                    f"Pack paths {previous!r} and {path!r} collide after Unicode NFC normalization."
                )
            else:
                paths[normalized] = path
            portable = portable_carrier_path_key(path)
            previous = portable_paths.get(portable)
            if previous is not None and previous != path:
                errors.append(
                    f"Pack paths {previous!r} and {path!r} collide after Unicode "
                    "NFC and case-fold normalization."
                )
            else:
                portable_paths[portable] = path
    return sorted(set(errors))


def receipt_semantic_errors(value: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    pairs: set[tuple[str, str]] = set()
    created_at = value.get("createdAt")
    for acquisition in value.get("acquisitions", []):
        if not isinstance(acquisition, dict):
            continue
        pair = (acquisition.get("realizationId"), acquisition.get("distributionId"))
        if all(isinstance(item, str) for item in pair):
            if pair in pairs:
                errors.append(
                    f"Materialization acquisition {pair!r} occurs more than once."
                )
            pairs.add(pair)
        attempted_at = acquisition.get("attemptedAt")
        verified_at = acquisition.get("verifiedAt")
        if isinstance(created_at, str) and isinstance(attempted_at, str):
            try:
                if _instant(attempted_at) > _instant(created_at):
                    errors.append(
                        f"Acquisition for {pair[0]!r} is attempted after receipt creation."
                    )
            except ValueError:
                pass
        if isinstance(verified_at, str):
            try:
                if isinstance(attempted_at, str) and _instant(verified_at) < _instant(
                    attempted_at
                ):
                    errors.append(
                        f"Acquisition for {pair[0]!r} is verified before its attempt."
                    )
                if isinstance(created_at, str) and _instant(verified_at) > _instant(
                    created_at
                ):
                    errors.append(
                        f"Acquisition for {pair[0]!r} is verified after receipt creation."
                    )
            except ValueError:
                pass
    profile_ids = [
        item["profileId"]
        for item in value.get("profileStates", [])
        if isinstance(item, dict) and isinstance(item.get("profileId"), str)
    ]
    if len(profile_ids) != len(set(profile_ids)):
        errors.append("Materialization receipt contains duplicate profile states.")
    return sorted(set(errors))


def zenodo_metadata_semantic_errors(value: dict[str, Any]) -> list[str]:
    """Apply VAO constraints to the explicitly legacy Zenodo projection."""
    errors: list[str] = []
    metadata = value.get("metadata")
    if not isinstance(metadata, dict):
        return errors
    keywords = metadata.get("keywords", [])
    if "VAO 0.4" not in keywords:
        errors.append("Legacy Zenodo metadata keywords must include 'VAO 0.4'.")
    for owner in ("creators", "contributors"):
        for index, person in enumerate(metadata.get(owner, [])):
            if not isinstance(person, dict) or not isinstance(person.get("orcid"), str):
                continue
            if not _orcid_valid("https://orcid.org/" + person["orcid"]):
                errors.append(
                    f"Legacy Zenodo {owner}[{index}] has an invalid ORCID checksum."
                )
    return sorted(set(errors))


def validate_descriptor(
    path: Path,
    schema_path: Path,
    semantic: Callable[[dict[str, Any]], list[str]] | None = None,
) -> dict[str, Any]:
    value, errors = _read_companion_descriptor(path, schema_path)
    if value is not None and semantic is not None:
        errors.extend(semantic(value))
    return {"valid": not errors, "errors": sorted(set(errors)), "warnings": []}


def validate_release_descriptor(path: Path) -> dict[str, Any]:
    return validate_descriptor(path, RELEASE_SCHEMA, release_semantic_errors)


def validate_zenodo_metadata_descriptor(path: Path) -> dict[str, Any]:
    return validate_descriptor(
        path, ZENODO_METADATA_SCHEMA, zenodo_metadata_semantic_errors
    )


def _read_manifest_for_companion(
    path: Path,
) -> tuple[dict[str, Any] | None, bytes | None, list[str]]:
    try:
        data = _read_bounded_regular(path, MAX_MANIFEST_BYTES, "Manifest")
        manifest = strict_json_bytes(data, str(path))
    except (OSError, vao03.VAO03Error, VAO04Error) as exc:
        return None, None, [str(exc)]
    report = validate_manifest(manifest)
    return manifest, data, list(report["errors"])


def _object(value: Any) -> dict[str, Any]:
    """Return an object value or an empty sentinel for defensive cross-checking."""
    return value if isinstance(value, dict) else {}


def _objects(value: Any) -> list[dict[str, Any]]:
    """Return only object members from an array-like value."""
    return (
        [item for item in value if isinstance(item, dict)]
        if isinstance(value, list)
        else []
    )


def _records_by_id(value: Any) -> dict[str, dict[str, Any]]:
    """Index well-formed record objects without assuming schema validity."""
    return {
        item["id"]: item for item in _objects(value) if isinstance(item.get("id"), str)
    }


def validate_release_manifest_set(
    release_path: Path, manifest_path: Path
) -> dict[str, Any]:
    release, errors = _read_companion_descriptor(release_path, RELEASE_SCHEMA)
    if release is not None:
        errors.extend(release_semantic_errors(release))
    manifest, manifest_data, manifest_errors = _read_manifest_for_companion(
        manifest_path
    )
    errors.extend(manifest_errors)
    if release is None or manifest is None or manifest_data is None:
        return {"valid": False, "errors": sorted(set(errors)), "warnings": []}
    release_identity = _object(manifest.get("release"))
    comparisons = {
        "vaoId": manifest.get("id"),
        "releaseId": release_identity.get("id"),
        "revision": release_identity.get("revision"),
        "contentVersion": release_identity.get("contentVersion"),
    }
    for field, expected in comparisons.items():
        if release.get(field) != expected:
            errors.append(
                f"Release descriptor {field} does not match the exact manifest."
            )
    publication = _object(release.get("publication"))
    root = _object(publication.get("rootRecord"))
    manifest_files = [
        item for item in _objects(root.get("files")) if item.get("role") == "manifest"
    ]
    if len(manifest_files) == 1:
        item = manifest_files[0]
        if item.get("byteSize") != len(manifest_data) or item.get(
            "sha256"
        ) != sha256_bytes(manifest_data):
            errors.append(
                "Publication root manifest inventory does not match the supplied exact manifest bytes."
            )
    return {"valid": not errors, "errors": sorted(set(errors)), "warnings": []}


def validate_pack_manifest_set(pack_path: Path, manifest_path: Path) -> dict[str, Any]:
    pack, errors = _read_companion_descriptor(pack_path, PACK_SCHEMA)
    if pack is not None:
        errors.extend(pack_semantic_errors(pack))
    manifest, _, manifest_errors = _read_manifest_for_companion(manifest_path)
    errors.extend(manifest_errors)
    if pack is None or manifest is None:
        return {"valid": False, "errors": sorted(set(errors)), "warnings": []}
    if pack.get("releaseId") != _object(manifest.get("release")).get("id"):
        errors.append("Pack releaseId does not match the exact manifest.")
    realizations = _records_by_id(manifest.get("realizations"))
    for member in _objects(pack.get("members")):
        realization = realizations.get(member.get("realizationId"))
        if realization is None:
            errors.append(
                f"Pack member has unknown realizationId {member.get('realizationId')!r}."
            )
            continue
        for field in ("mediaType", "byteSize", "sha256"):
            if member.get(field) != realization.get(field):
                errors.append(
                    f"Pack member {member.get('realizationId')!r} {field} does not "
                    "match the exact realization."
                )
    return {"valid": not errors, "errors": sorted(set(errors)), "warnings": []}


def _source_carrier_evidence(
    path: Path,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None, list[str]]:
    """Validate and identify the exact carrier used by a receipt."""
    if path.is_symlink():
        return (
            None,
            None,
            [f"Receipt source carrier must not be a symbolic link: {path}."],
        )
    report = validate(path)
    errors = list(report.get("errors", []))
    if not report.get("valid"):
        return None, None, errors
    try:
        if path.is_dir():
            descriptor_data = _read_bounded_regular(
                path / CARRIER_NAME, MAX_DESCRIPTOR_BYTES, "Carrier descriptor"
            )
            evidence = {
                "kind": "workspace",
                "descriptorByteSize": len(descriptor_data),
                "descriptorSHA256": sha256_bytes(descriptor_data),
            }
        else:
            with _open_regular_nofollow(path) as source:
                packed_sha256, packed_size = sha256_stream_bounded(
                    source, MAX_TOTAL_BYTES
                )
                source.seek(0)
                with zipfile.ZipFile(source, "r", allowZip64=True) as archive:
                    with archive.open(CARRIER_NAME, "r") as descriptor_stream:
                        descriptor_data = _read_stream_bounded(
                            descriptor_stream,
                            MAX_DESCRIPTOR_BYTES,
                            "Carrier descriptor",
                        )
            evidence = {
                "kind": "packed-carrier",
                "descriptorByteSize": len(descriptor_data),
                "descriptorSHA256": sha256_bytes(descriptor_data),
                "packedCarrierByteSize": packed_size,
                "packedCarrierSHA256": packed_sha256,
            }
        descriptor = strict_json_bytes(descriptor_data, CARRIER_NAME)
    except (
        OSError,
        KeyError,
        RuntimeError,
        vao03.VAO03Error,
        VAO04Error,
        zipfile.BadZipFile,
    ) as exc:
        errors.append(f"Cannot identify exact receipt source carrier: {exc}")
        return None, None, sorted(set(errors))
    return evidence, descriptor, sorted(set(errors))


def validate_receipt_manifest_set(
    receipt_path: Path, manifest_path: Path, carrier_path: Path | None = None
) -> dict[str, Any]:
    receipt, errors = _read_companion_descriptor(receipt_path, RECEIPT_SCHEMA)
    if receipt is not None:
        errors.extend(receipt_semantic_errors(receipt))
    manifest, manifest_data, manifest_errors = _read_manifest_for_companion(
        manifest_path
    )
    errors.extend(manifest_errors)
    if receipt is None or manifest is None or manifest_data is None:
        return {"valid": False, "errors": sorted(set(errors)), "warnings": []}
    if receipt.get("releaseId") != _object(manifest.get("release")).get("id"):
        errors.append("Receipt releaseId does not match the exact manifest.")
    if receipt.get("manifestSHA256") != sha256_bytes(manifest_data):
        errors.append("Receipt manifestSHA256 does not match exact manifest bytes.")
    if carrier_path is None:
        errors.append(
            "Receipt cross-validation requires the exact source carrier or workspace."
        )
    else:
        evidence, carrier, carrier_errors = _source_carrier_evidence(carrier_path)
        errors.extend(carrier_errors)
        claimed_evidence = _object(receipt.get("sourceCarrier"))
        if evidence is not None:
            for field, expected in evidence.items():
                if claimed_evidence.get(field) != expected:
                    errors.append(
                        f"Receipt sourceCarrier {field} does not match exact carrier bytes."
                    )
            if set(claimed_evidence) != set(evidence):
                errors.append(
                    "Receipt sourceCarrier evidence fields do not match its carrier kind."
                )
        if carrier is not None:
            if carrier.get("releaseId") != _object(manifest.get("release")).get("id"):
                errors.append(
                    "Receipt source carrier releaseId does not match manifest."
                )
            if carrier.get("manifestSHA256") != sha256_bytes(manifest_data):
                errors.append(
                    "Receipt source carrier does not contain the supplied exact manifest."
                )
            if carrier.get("manifestByteSize") != len(manifest_data):
                errors.append(
                    "Receipt source carrier manifestByteSize does not match supplied bytes."
                )
    realizations = _records_by_id(manifest.get("realizations"))
    distributions = _records_by_id(manifest.get("distributions"))
    for acquisition in _objects(receipt.get("acquisitions")):
        realization_id = acquisition.get("realizationId")
        distribution_id = acquisition.get("distributionId")
        realization = realizations.get(realization_id)
        distribution = distributions.get(distribution_id)
        if realization is None:
            errors.append(
                f"Receipt acquisition has unknown realizationId {realization_id!r}."
            )
        if distribution is None:
            errors.append(
                f"Receipt acquisition has unknown distributionId {distribution_id!r}."
            )
        elif realization is not None and distribution_id not in realization.get(
            "distributionIds", []
        ):
            errors.append(
                f"Receipt realization {realization_id!r} does not declare "
                f"distribution {distribution_id!r}."
            )
        if realization is None:
            continue
        observed = {
            field: acquisition[field]
            for field in ("byteSize", "sha256")
            if field in acquisition
        }
        matches = all(
            realization.get(field) == value for field, value in observed.items()
        )
        if acquisition.get("status") == "verified" and not (
            len(observed) == 2 and matches
        ):
            errors.append(
                f"Verified receipt acquisition {realization_id!r} does not match "
                "the realization byte identity."
            )
        if acquisition.get("status") == "integrity-failed" and matches:
            errors.append(
                f"Integrity-failed acquisition {realization_id!r} supplies no "
                "observed mismatch."
            )
    group_ids = set(_records_by_id(manifest.get("assetGroups")))
    selected_group_ids = receipt.get("selectedGroupIds")
    for identifier in (
        selected_group_ids if isinstance(selected_group_ids, list) else []
    ):
        if identifier not in group_ids:
            errors.append(f"Receipt selects unknown asset group {identifier!r}.")
    profile_ids = {
        item["id"]
        for registry in ("profiles", "materializableProfiles")
        for item in _objects(manifest.get(registry))
        if isinstance(item.get("id"), str)
    }
    for state in _objects(receipt.get("profileStates")):
        if state.get("profileId") not in profile_ids:
            errors.append(f"Receipt names unknown profile {state.get('profileId')!r}.")
    implementation = _object(receipt.get("implementation"))
    software_id = implementation.get("softwareEnvironmentId")
    if software_id is not None:
        scientific = _object(manifest.get("scientific"))
        environments = _records_by_id(scientific.get("softwareEnvironments"))
        environment = environments.get(software_id)
        if environment is None:
            errors.append(
                f"Receipt implementation has unknown softwareEnvironmentId {software_id!r}."
            )
        else:
            for field in (
                "name",
                "version",
                "identity",
                "identityScope",
                "identityDescription",
            ):
                if implementation.get(field) != environment.get(field):
                    errors.append(
                        f"Receipt implementation {field} does not match linked "
                        f"Software Environment {software_id!r}."
                    )
    return {"valid": not errors, "errors": sorted(set(errors)), "warnings": []}


def validate_publication_set(
    release_path: Path, metadata_paths: Iterable[Path]
) -> dict[str, Any]:
    """Validate one release descriptor and all of its legacy Zenodo projections."""
    release, errors = _read_companion_descriptor(release_path, RELEASE_SCHEMA)
    if release is None:
        return {"valid": False, "errors": errors, "warnings": []}
    errors.extend(release_semantic_errors(release))
    documents: list[dict[str, Any]] = []
    for path in metadata_paths:
        document, document_errors = _read_companion_descriptor(
            path, ZENODO_METADATA_SCHEMA
        )
        errors.extend(document_errors)
        if document is not None:
            errors.extend(zenodo_metadata_semantic_errors(document))
            documents.append(document)

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

    documents_by_id: dict[str, dict[str, Any]] = {}
    for document in documents:
        record_id = document.get("publicationRecordId")
        if record_id in documents_by_id:
            errors.append(
                f"Legacy Zenodo metadata for publication record {record_id!r} is duplicated."
            )
        elif isinstance(record_id, str):
            documents_by_id[record_id] = document
        if document.get("releaseId") != release.get("releaseId"):
            errors.append(
                f"Legacy Zenodo metadata for {record_id!r} has the wrong releaseId."
            )
        if record_id not in records:
            errors.append(
                f"Legacy Zenodo metadata names unknown publication record {record_id!r}."
            )

    zenodo_records = {
        record_id
        for record_id, record in records.items()
        if record.get("repositoryType") == vao03.ZENODO_REPOSITORY_TYPE
    }
    for record_id in sorted(zenodo_records - set(documents_by_id)):
        errors.append(
            f"Zenodo publication record {record_id!r} lacks a legacy metadata projection."
        )
    for record_id in sorted(set(documents_by_id) - zenodo_records):
        errors.append(
            f"Legacy metadata projection {record_id!r} does not describe a Zenodo record."
        )

    topology = publication.get("topology") if isinstance(publication, dict) else None
    root_id = root.get("id") if isinstance(root, dict) else None
    root_document = documents_by_id.get(root_id)
    if root_document:
        expected_role = (
            "monolithic-root" if topology == "single-record" else "family-root"
        )
        if root_document.get("recordRole") != expected_role:
            errors.append(
                f"Root legacy Zenodo metadata recordRole must be {expected_role!r}."
            )
        root_metadata = root_document.get("metadata")
        if not isinstance(root_metadata, dict) or root_metadata.get(
            "version"
        ) != release.get("contentVersion"):
            errors.append(
                "Root legacy Zenodo metadata version must equal release contentVersion."
            )

    def relation_pairs(document: dict[str, Any] | None) -> set[tuple[str, str]]:
        if not document:
            return set()
        metadata = document.get("metadata")
        related = (
            metadata.get("related_identifiers", [])
            if isinstance(metadata, dict)
            else []
        )
        return {
            (item.get("identifier"), item.get("relation"))
            for item in related
            if isinstance(item, dict)
            and isinstance(item.get("identifier"), str)
            and isinstance(item.get("relation"), str)
        }

    root_relations = relation_pairs(root_document)
    root_pid = (
        root.get("versionPersistentIdentifier") if isinstance(root, dict) else None
    )
    for member in members if isinstance(members, list) else []:
        if not isinstance(member, dict) or not isinstance(member.get("record"), dict):
            continue
        record = member["record"]
        record_id = record.get("id")
        member_document = documents_by_id.get(record_id)
        if member_document and member_document.get("recordRole") != "family-member":
            errors.append(
                f"Family-member legacy metadata {record_id!r} must use recordRole 'family-member'."
            )
        version_pid = record.get("versionPersistentIdentifier")
        relation = member.get("relationFromRoot")
        if root_document and (version_pid, relation) not in root_relations:
            errors.append(
                f"Root legacy metadata lacks {relation!r} relation to exact member PID {version_pid!r}."
            )
        concept_pid = record.get("conceptPersistentIdentifier")
        if concept_pid and (concept_pid, relation) in root_relations:
            errors.append(
                f"Root legacy metadata uses concept PID {concept_pid!r} for a family relation."
            )
        inverse = member.get("inverseRelationFromMember")
        if (
            inverse
            and member_document
            and (root_pid, inverse) not in relation_pairs(member_document)
        ):
            errors.append(
                f"Member legacy metadata {record_id!r} lacks inverse {inverse!r} "
                f"relation to exact root PID {root_pid!r}."
            )
    return {"valid": not errors, "errors": sorted(set(errors)), "warnings": []}


def pack_workspace(workspace: Path, output: Path) -> None:
    report = validate_workspace(workspace)
    if not report["valid"]:
        raise VAO04Error(
            "Cannot pack invalid VAO 0.4.0 workspace: "
            + "; ".join(report["errors"][:3])
        )
    if output.exists() or output.is_symlink():
        raise VAO04Error(f"Output already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    created = False
    try:
        manifest_data = _read_bounded_regular(
            workspace / MANIFEST_NAME, MAX_MANIFEST_BYTES, "Manifest"
        )
        carrier_data = _read_bounded_regular(
            workspace / CARRIER_NAME, MAX_DESCRIPTOR_BYTES, "Carrier descriptor"
        )
        manifest = strict_json_bytes(manifest_data, MANIFEST_NAME)
        carrier = strict_json_bytes(carrier_data, CARRIER_NAME)
        realization_sizes = {
            item["id"]: item["byteSize"]
            for item in manifest.get("realizations", [])
            if isinstance(item, dict)
            and isinstance(item.get("id"), str)
            and isinstance(item.get("byteSize"), int)
        }
        expected_sizes = {
            mapping["path"]: realization_sizes[mapping["realizationId"]]
            for mapping in carrier.get("embeddedRealizations", [])
            if isinstance(mapping, dict)
            and mapping.get("realizationId") in realization_sizes
            and isinstance(mapping.get("path"), str)
        }
        with zipfile.ZipFile(
            output, "x", compression=zipfile.ZIP_STORED, allowZip64=True
        ) as archive:
            created = True
            archive.writestr(vao03.zip_info("mimetype"), MIMETYPE.encode())
            archive.writestr(vao03.zip_info(MANIFEST_NAME), manifest_data)
            archive.writestr(vao03.zip_info(CARRIER_NAME), carrier_data)
            copied_total = 0
            for path in sorted((workspace / "payload").rglob("*")):
                if path.is_file() and not path.is_symlink():
                    name = path.relative_to(workspace).as_posix()
                    if name not in expected_sizes:
                        raise VAO04Error(
                            f"Workspace payload appeared without a carrier mapping: {name!r}."
                        )
                    with (
                        _open_regular_nofollow(path) as source,
                        archive.open(
                            vao03.zip_info(name), "w", force_zip64=True
                        ) as target,
                    ):
                        copied = _copy_stream_bounded(
                            source, target, expected_sizes[name]
                        )
                    if copied != expected_sizes[name]:
                        raise VAO04Error(
                            f"Workspace payload changed size while packing: {name!r}."
                        )
                    copied_total += copied
                    if copied_total > MAX_TOTAL_BYTES:
                        raise VAO04Error(
                            "Workspace payload exceeds the total-byte limit while packing."
                        )
            archive.comment = b"VAO/0.4.0"
        final = validate_archive(output)
        if not final["valid"]:
            raise VAO04Error(
                "Finished archive failed validation: " + "; ".join(final["errors"][:3])
            )
    except Exception:
        if created:
            output.unlink(missing_ok=True)
        raise


def _promote_legacy_activities(
    records: list[Any],
    modified_at: str,
    known: set[str],
    migrator_agent_id: str,
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
    """Promote recognizable 0.3 provenance activities into typed 0.4 records.

    VAO 0.3 deliberately allowed open paradata. A record with an activity ID,
    inputs, outputs, method, and software is sufficiently structured to retain
    its references as a VAO 0.4 Activity. The original record is still kept in
    the migration activity parameters, so promotion is additive and lossless.
    """
    agents: dict[str, dict[str, Any]] = {}
    activities: list[dict[str, Any]] = []
    protocols: dict[str, dict[str, Any]] = {}
    software_environments: dict[str, dict[str, Any]] = {}
    for record in records:
        if not isinstance(record, dict) or not is_identifier(record.get("id")):
            continue
        method = record.get("method") if isinstance(record.get("method"), dict) else {}
        software = (
            record.get("software") if isinstance(record.get("software"), dict) else {}
        )
        method_type = str(method.get("methodType", "legacy-processing"))
        activity_type = str(record.get("activityType", method_type))
        lowered = f"{method_type} {activity_type}".lower()
        activity_kind = next(
            (
                kind
                for kind in (
                    "capture",
                    "authoring",
                    "measurement",
                    "digitization",
                    "simulation",
                    "inference",
                    "annotation",
                    "review",
                    "migration",
                    "render",
                )
                if kind in lowered
            ),
            "processing",
        )
        fingerprint = hashlib.sha256(
            json_bytes({"activityType": activity_type, "method": method})
        ).hexdigest()
        protocol_id = f"urn:vao:protocol:migrated:{fingerprint}"
        protocols.setdefault(
            protocol_id,
            {
                "id": protocol_id,
                "labels": {"en": f"Migrated {method_type} protocol declaration"},
                "procedure": f"VAO 0.3 declared activity type {activity_type!r}, method {method_type!r}, and representation status {method.get('representationStatus', 'not stated')!r}.",
                "version": "legacy-0.3-declaration",
            },
        )

        software_id: str | None = None
        agent_id = migrator_agent_id
        if software:
            software_digest = hashlib.sha256(json_bytes(software)).hexdigest()
            software_id = f"urn:vao:software:migrated:{software_digest}"
            agent_id = f"urn:vao:agent:migrated-software:{software_digest}"
            name = str(software.get("name", "Unidentified legacy software"))
            version = str(software.get("version", "not stated"))
            agents.setdefault(
                agent_id,
                {
                    "id": agent_id,
                    "agentKind": "software-agent",
                    "labels": {"en": f"{name} ({version}; migrated declaration)"},
                },
            )
            software_environments.setdefault(
                software_id,
                {
                    "id": software_id,
                    "name": name,
                    "version": version,
                    "identity": {"algorithm": "sha256", "value": software_digest},
                    "identityScope": "declaration",
                    "identityDescription": "SHA-256 of the preserved VAO 0.3 software declaration; executable identity was not supplied.",
                },
            )

        inputs = [item for item in record.get("inputIds", []) if item in known]
        outputs = [item for item in record.get("outputIds", []) if item in known]
        started_at = record.get("startedAt", modified_at)
        ended_at = record.get("endedAt", started_at)
        activity: dict[str, Any] = {
            "id": record["id"],
            "activityKind": activity_kind,
            "startedAt": started_at,
            "endedAt": ended_at,
            "agentIds": [agent_id],
            "protocolId": protocol_id,
            "inputIds": inputs,
            "outputIds": outputs,
            "parameterValues": {
                "https://w3id.org/modavis/vao/ontology#legacyActivity": record,
            },
            "notes": "Promoted from a VAO 0.3 open paradata record; omitted input/output references remain preserved in legacyActivity.",
        }
        if software_id is not None:
            activity["softwareEnvironmentId"] = software_id
        activities.append(activity)
    return (
        list(agents.values()),
        activities,
        list(protocols.values()),
        list(software_environments.values()),
    )


def reference_software_environment(identifier: str) -> dict[str, Any]:
    """Describe the exact reference entry point and all behavioural dependencies."""

    def dependency(name: str, path: Path, role: str, scope: str) -> dict[str, Any]:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        return {
            "name": name,
            "dependencyRole": role,
            "identity": {"algorithm": "sha256", "value": digest},
            "identityScope": scope,
            "identityDescription": f"SHA-256 of the exact distributed file {name}.",
        }

    dependencies = [
        dependency(
            "Tools/vao03.py", Path(vao03.__file__).resolve(), "source", "source-file"
        ),
        dependency(
            "Tools/vaom.py",
            Path(vao03.vao02.__file__).resolve(),
            "source",
            "source-file",
        ),
        dependency(
            "Tools/vao04_runtime.py",
            Path(vao04_runtime.__file__).resolve(),
            "source",
            "source-file",
        ),
        dependency(
            "Tools/vao_resources.py",
            Path(vao_resources.__file__).resolve(),
            "source",
            "source-file",
        ),
        dependency(
            "Schemas/vao-release-bundle-0.4.0.json",
            SCHEMA_DIR / "vao-release-bundle-0.4.0.json",
            "normative-artifact",
            "declaration",
        ),
    ]
    lock = vao_resources.dependency_lock()
    if lock is not None:
        dependencies.append(
            dependency(
                "requirements-lock.txt",
                lock,
                "environment-lock",
                "environment-lock",
            )
        )

    return {
        "id": identifier,
        "name": "VAO 0.4 reference validator and migrator",
        "version": "0.4.0",
        "identity": {
            "algorithm": "sha256",
            "value": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        },
        "identityScope": "source-file",
        "identityDescription": (
            "SHA-256 of the exact Tools/vao04.py entry-point source; imported "
            "behavioural sources and the normative artifact-bundle declaration are "
            "pinned separately in dependencies"
            + (
                ", together with the source checkout's Python dependency lock."
                if lock is not None
                else ". No exact Python environment lock is distributed in the wheel, "
                "so this installed declaration is not sufficient for a deterministic "
                "reproducibility claim."
            )
        ),
        "dependencies": dependencies,
        "runtimeDescription": (
            "CPython >=3.11; release gate exercised on CPython 3.11 and 3.14; "
            "OS and architecture are not part of this source identity."
            + (
                ""
                if lock is not None
                else " The installed third-party environment is not exactly pinned."
            )
        ),
    }


def migrate_03_manifest(
    source: dict[str, Any], source_manifest_sha256: str
) -> dict[str, Any]:
    """Migrate a parsed manifest using the caller-supplied original-byte digest."""
    if source.get("formatVersion") != vao03.FORMAT_VERSION:
        raise VAO04Error("Migration input must be VAO 0.3.3.")
    if re.fullmatch(r"[0-9a-f]{64}", source_manifest_sha256) is None:
        raise VAO04Error(
            "Migration requires the lowercase SHA-256 of the original exact manifest bytes."
        )
    value = copy.deepcopy(source)
    value["release"]["migratedFromManifestSHA256"] = source_manifest_sha256
    value["$schema"] = SCHEMA_URI
    value["@context"] = [
        CONTEXT_URI if x == vao03.CONTEXT_URI else x for x in value["@context"]
    ]
    value["formatVersion"] = FORMAT_VERSION
    for registry in ("profiles", "materializableProfiles"):
        for profile in value[registry]:
            profile["id"] = profile["id"].replace("/0.3", f"/{FORMAT_VERSION}")
            profile["version"] = FORMAT_VERSION
    value["conformsTo"] = [
        x.replace("/0.3", f"/{FORMAT_VERSION}") if x.startswith(PROFILE_BASE) else x
        for x in value["conformsTo"]
    ]
    agent_id = "urn:vao:agent:vao04-migrator"
    protocol_id = "urn:vao:protocol:vao033-to-vao040"
    software_id = "urn:vao:software:vao04-reference"
    activity_id = (
        f"urn:vao:activity:migrate:{value['release']['migratedFromManifestSHA256']}"
    )
    legacy_paradata = value.pop("paradata", [])
    legacy_analyses = value.pop("analyses", [])
    known = _nested_identifiers(value) | {value["id"], value["release"]["id"]}
    promoted_agents, promoted_activities, promoted_protocols, promoted_software = (
        _promote_legacy_activities(
            legacy_paradata,
            value["modifiedAt"],
            known,
            agent_id,
        )
    )
    promoted_by_id = {record["id"]: record for record in promoted_activities}
    migration_realization_ids: list[str] = []
    for realization in value["realizations"]:
        inherited_provenance = [
            reference
            for reference in realization.get("provenanceIds", [])
            if reference in promoted_by_id
            and realization["id"] in promoted_by_id[reference].get("outputIds", [])
        ]
        if inherited_provenance:
            realization["provenanceIds"] = inherited_provenance
            continue
        extensions = realization.setdefault("extensions", {})
        extensions[
            "https://w3id.org/modavis/vao/ontology#sourceRepresentationStatus"
        ] = realization["representationStatus"]
        if realization.get("provenanceIds"):
            extensions["https://w3id.org/modavis/vao/ontology#sourceProvenanceIds"] = (
                realization["provenanceIds"]
            )
        realization["representationStatus"] = (
            "https://w3id.org/modavis/vao/vocab/representation-status/undetermined"
        )
        realization["provenanceIds"] = [activity_id]
        migration_realization_ids.append(realization["id"])
    legacy = {
        "https://w3id.org/modavis/vao/ontology#legacyParadata": legacy_paradata,
        "https://w3id.org/modavis/vao/ontology#legacyAnalyses": legacy_analyses,
    }
    value["scientific"] = {
        "agents": [
            {
                "id": agent_id,
                "agentKind": "software-agent",
                "labels": {"en": "VAO 0.4 reference migrator"},
            },
            *promoted_agents,
        ],
        "activities": [
            {
                "id": activity_id,
                "activityKind": "migration",
                "startedAt": value["modifiedAt"],
                "endedAt": value["modifiedAt"],
                "agentIds": [agent_id],
                "protocolId": protocol_id,
                "softwareEnvironmentId": software_id,
                "inputIds": [value["id"]],
                "outputIds": [value["release"]["id"], *migration_realization_ids],
                "parameterValues": legacy,
            },
            *promoted_activities,
        ],
        "observations": [],
        "analyses": [],
        "calibrations": [],
        "protocols": [
            {
                "id": protocol_id,
                "labels": {"en": "VAO 0.3.3 to 0.4.0 semantic migration"},
                "procedure": "Preserve exact realization identities and project closed 0.3 registries into 0.4; retain legacy open records as namespaced migration parameters.",
                "version": FORMAT_VERSION,
            },
            *promoted_protocols,
        ],
        "softwareEnvironments": [
            reference_software_environment(software_id),
            *promoted_software,
        ],
        "claims": [],
        "reviews": [],
        "consents": [],
    }
    if SCIENTIFIC_PROFILE not in {profile["id"] for profile in value["profiles"]}:
        value["profiles"].append(
            {
                "id": SCIENTIFIC_PROFILE,
                "version": FORMAT_VERSION,
                "requiredCapabilities": [
                    CAPABILITY_BASE + "typed-scientific-provenance"
                ],
            }
        )
        value["conformsTo"].append(SCIENTIFIC_PROFILE)
    value["multimodal"] = {
        "timebases": [],
        "tracks": [],
        "synchronizationMappings": [],
        "annotations": [],
    }
    value["physicalSystem"] = {
        "components": [],
        "ports": [],
        "connections": [],
        "sensors": [],
        "actuators": [],
        "stateBindings": [],
    }
    semantics = {
        "timestampOrder": "ascending",
        "simultaneousEventOrder": "priority-then-event-id",
        "transitionEvaluation": "snapshot",
        "actionExecution": "execution-group-then-array-order",
        "runToCompletion": True,
        "reentrancyPolicy": "queue",
        "lateEventPolicy": "reject",
        "timeResolution": {"value": 1, "unit": "http://qudt.org/vocab/unit/MilliSEC"},
        "maximumMicrosteps": 10000,
        "voiceAllocation": "lowest-free-then-oldest",
        "maximumVoices": 1024,
    }
    value["runtime"] = {
        "executionSemantics": semantics,
        "randomSources": [],
        "renderers": [],
        "conformanceTraces": [],
    }
    value["discovery"] = {
        "resourceType": "Dataset",
        "creatorAgentIds": [agent_id],
        "contributorAgentIds": [],
        "relatedIdentifiers": [],
        "fundingReferences": [],
        "subjects": [],
    }
    if isinstance(value.get("interactionModel"), dict):
        value["interactionModel"]["executionSemantics"] = copy.deepcopy(semantics)
        value["interactionModel"]["randomSources"] = []

    trajectory_candidates: dict[str, list[str]] = {}
    for realization in value["realizations"]:
        if realization.get("technicalMetadata", {}).get("kind") in {
            "trajectory",
            "motion-capture",
            "sensor-data",
        }:
            trajectory_candidates.setdefault(realization["assetId"], []).append(
                realization["id"]
            )

    def promote_trajectory_reference(record: dict[str, Any], owner: str) -> None:
        legacy_asset = record.pop("trajectoryAssetId", None)
        if legacy_asset is None:
            return
        candidates = trajectory_candidates.get(legacy_asset, [])
        if len(candidates) != 1:
            raise VAO04Error(
                f"Cannot migrate {owner} trajectoryAssetId {legacy_asset!r}: "
                "expected exactly one trajectory-capable realization, found "
                f"{len(candidates)}; curator selection is required."
            )
        record["trajectoryRealizationId"] = candidates[0]

    acoustics = value.get("acoustics")
    if isinstance(acoustics, dict):
        for pose in acoustics.get("poses", []):
            if "orientationXYZW" in pose or "orientationRadians" in pose:
                raise VAO04Error(
                    f"Cannot migrate oriented Pose {pose.get('id')!r}: VAO 0.3 "
                    "did not identify the local Coordinate Frame; curator selection "
                    "is required."
                )
            promote_trajectory_reference(pose, f"Pose {pose.get('id')!r}")
        for config in acoustics.get("renderConfigurations", []):
            listener = config.get("listener")
            if isinstance(listener, dict):
                promote_trajectory_reference(
                    listener, f"Render configuration {config.get('id')!r} listener"
                )
    for realization in value["realizations"]:
        realization["contentDigests"] = [
            {"algorithm": "sha256", "value": realization["sha256"]}
        ]
    return value


def migrate_03_workspace(source: Path, destination: Path) -> None:
    if not source.is_dir() or source.is_symlink():
        raise VAO04Error(
            f"Migration source is not a regular workspace directory: {source}"
        )
    for item in source.rglob("*"):
        relative = item.relative_to(source).as_posix()
        if item.is_symlink():
            raise VAO04Error(f"Migration source contains a symbolic link: {relative!r}")
        mode = item.stat(follow_symlinks=False).st_mode
        if not (stat.S_ISREG(mode) or stat.S_ISDIR(mode)):
            raise VAO04Error(f"Migration source contains a special file: {relative!r}")
        root = PurePosixPath(relative).parts[0]
        if root not in {"mimetype", MANIFEST_NAME, "META-INF", "payload"}:
            raise VAO04Error(
                f"Migration source contains an unknown entry: {relative!r}"
            )
        if root == "META-INF" and relative not in {"META-INF", CARRIER_NAME}:
            raise VAO04Error(
                f"Migration source contains an unknown META-INF entry: {relative!r}"
            )
    source_report = vao03.validate_workspace(source)
    if not source_report["valid"]:
        raise VAO04Error(
            "Migration source is not a valid VAO 0.3.3 workspace: "
            + "; ".join(source_report["errors"][:8])
        )
    if destination.exists() or destination.is_symlink():
        raise VAO04Error(f"Destination already exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.{uuid.uuid4().hex}.tmp")
    try:
        shutil.copytree(source, temporary)
        manifest, original_manifest_data = load_json(temporary / MANIFEST_NAME)
        migrated = migrate_03_manifest(
            manifest, hashlib.sha256(original_manifest_data).hexdigest()
        )
        write_json(temporary / MANIFEST_NAME, migrated)
        carrier, _ = load_json(temporary / CARRIER_NAME)
        carrier["$schema"] = f"{BASE}/schema/carrier.json"
        carrier["formatVersion"] = FORMAT_VERSION
        data = json_bytes(migrated)
        carrier["manifestSHA256"] = sha256_bytes(data)
        carrier["manifestByteSize"] = len(data)
        write_json(temporary / CARRIER_NAME, carrier)
        report = validate_workspace(temporary)
        if not report["valid"]:
            raise VAO04Error(
                "Migrated workspace failed VAO 0.4.0 validation: "
                + "; ".join(report["errors"][:8])
            )
        if destination.exists() or destination.is_symlink():
            raise VAO04Error(f"Destination appeared during migration: {destination}")
        temporary.rename(destination)
    except Exception:
        if temporary.exists() and not temporary.is_symlink():
            shutil.rmtree(temporary)
        raise


def print_report(report: dict[str, Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return
    print("VALID" if report.get("valid") else "INVALID")
    for error in report.get("errors", []):
        print(f"ERROR: {error}")
    for warning in report.get("warnings", []):
        print(f"WARNING: {warning}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    validate_cmd = sub.add_parser("validate")
    validate_cmd.add_argument("path", type=Path)
    validate_cmd.add_argument("--json", action="store_true")
    pack_cmd = sub.add_parser("pack")
    pack_cmd.add_argument("workspace", type=Path)
    pack_cmd.add_argument("output", type=Path)
    migrate_cmd = sub.add_parser("migrate-0.3")
    migrate_cmd.add_argument("source", type=Path)
    migrate_cmd.add_argument("destination", type=Path)
    descriptor_cmd = sub.add_parser("validate-descriptor")
    descriptor_cmd.add_argument(
        "kind", choices=["release", "pack", "receipt", "zenodo-metadata"]
    )
    descriptor_cmd.add_argument("path", type=Path)
    descriptor_cmd.add_argument("--json", action="store_true")
    publication_cmd = sub.add_parser("validate-publication")
    publication_cmd.add_argument("release", type=Path)
    publication_cmd.add_argument("metadata", nargs="+", type=Path)
    publication_cmd.add_argument("--json", action="store_true")
    for command, descriptor_label in (
        ("validate-release", "release"),
        ("validate-pack", "pack manifest"),
    ):
        set_cmd = sub.add_parser(command)
        set_cmd.add_argument(
            "descriptor", type=Path, help=f"path to the {descriptor_label} descriptor"
        )
        set_cmd.add_argument(
            "manifest", type=Path, help="path to exact vao-manifest.json bytes"
        )
        set_cmd.add_argument("--json", action="store_true")
    receipt_set_cmd = sub.add_parser("validate-receipt")
    receipt_set_cmd.add_argument("descriptor", type=Path)
    receipt_set_cmd.add_argument("manifest", type=Path)
    receipt_set_cmd.add_argument(
        "carrier",
        type=Path,
        help="path to the exact source workspace or packed carrier",
    )
    receipt_set_cmd.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command == "validate":
            report = validate(args.path)
            print_report(report, args.json)
            return 0 if report["valid"] else 1
        if args.command == "pack":
            pack_workspace(args.workspace, args.output)
            return 0
        if args.command == "migrate-0.3":
            migrate_03_workspace(args.source, args.destination)
            return 0
        if args.command == "validate-publication":
            report = validate_publication_set(args.release, args.metadata)
            print_report(report, args.json)
            return 0 if report["valid"] else 1
        set_validators: dict[str, Callable[..., dict[str, Any]]] = {
            "validate-release": validate_release_manifest_set,
            "validate-pack": validate_pack_manifest_set,
        }
        if args.command in set_validators:
            report = set_validators[args.command](args.descriptor, args.manifest)
            print_report(report, args.json)
            return 0 if report["valid"] else 1
        if args.command == "validate-receipt":
            report = validate_receipt_manifest_set(
                args.descriptor, args.manifest, args.carrier
            )
            print_report(report, args.json)
            return 0 if report["valid"] else 1
        schemas = {
            "pack": (PACK_SCHEMA, pack_semantic_errors),
            "receipt": (RECEIPT_SCHEMA, receipt_semantic_errors),
        }
        if args.kind == "release":
            report = validate_release_descriptor(args.path)
        elif args.kind == "zenodo-metadata":
            report = validate_zenodo_metadata_descriptor(args.path)
        else:
            schema, semantic = schemas[args.kind]
            report = validate_descriptor(args.path, schema, semantic)
        print_report(report, args.json)
        return 0 if report["valid"] else 1
    except (OSError, VAO04Error, ValueError, zipfile.BadZipFile) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
