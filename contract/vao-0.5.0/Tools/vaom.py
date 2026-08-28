#!/usr/bin/env python3
"""Cross-platform reference manager, migrator, and validator for VAO 0.2/0.3 packages."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import mimetypes
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import sys
import uuid
import zipfile
from datetime import datetime, timezone
from typing import Any, BinaryIO, Iterable
from urllib.parse import urlsplit

import vao_resources


MIMETYPE = "application/vnd.modavis.vao+zip"
MANIFEST_NAME = "vao-manifest.json"
FORMAT_VERSION = "0.2.2"
SCHEMA_URI = "https://w3id.org/modavis/vao/0.2/schema/manifest.json"
CONTEXT_URI = "https://w3id.org/modavis/vao/0.2/context.jsonld"
CORE_PROFILE = "https://w3id.org/modavis/vao/profile/core/0.2"
RESEARCH_PROFILE = "https://w3id.org/modavis/vao/profile/research/0.2"
ORGREC_PROFILE = "https://w3id.org/modavis/vao/profile/orgrec-capture/0.2"
PLAYABLE_PROFILE = "https://w3id.org/modavis/vao/profile/playable/0.2"
SPATIAL_PROFILE = "https://w3id.org/modavis/vao/profile/spatial/0.2"
ACOUSTICS_PROFILE = "https://w3id.org/modavis/vao/profile/acoustics/0.2"
EXPERIENTIAL_PROFILE = "https://w3id.org/modavis/vao/profile/experiential/0.2"
PRESERVATION_PROFILE = "https://w3id.org/modavis/vao/profile/preservation/0.2"
STANDARD_PROFILES = {
    CORE_PROFILE,
    RESEARCH_PROFILE,
    ORGREC_PROFILE,
    PLAYABLE_PROFILE,
    SPATIAL_PROFILE,
    ACOUSTICS_PROFILE,
    EXPERIENTIAL_PROFILE,
    PRESERVATION_PROFILE,
}
APPLICATION_STATE = "https://w3id.org/modavis/vao/vocab/asset-role/application-state"
ANALYSIS_RESULT = "https://w3id.org/modavis/vao/vocab/asset-role/analysis-result"
AUDIO_DERIVATIVE = "https://w3id.org/modavis/vao/vocab/asset-role/audio-derivative"
THREE_DIMENSIONAL_MODEL = (
    "https://w3id.org/modavis/vao/vocab/asset-role/three-dimensional-model"
)
SPATIAL_MODEL = "https://w3id.org/modavis/vao/vocab/asset-role/spatial-model"
ANIMATION = "https://w3id.org/modavis/vao/vocab/asset-role/animation"
PERFORMANCE_MEDIA = "https://w3id.org/modavis/vao/vocab/asset-role/performance-media"
IMAGE_TARGET = "https://w3id.org/modavis/vao/vocab/asset-role/image-target"
TRACKING_DATA = "https://w3id.org/modavis/vao/vocab/asset-role/tracking-data"
SPATIAL_LISTENING_AUDIO = (
    "https://w3id.org/modavis/vao/vocab/asset-role/spatial-listening-audio"
)
IMPULSE_RESPONSE = "https://w3id.org/modavis/vao/vocab/asset-role/impulse-response"
ACOUSTIC_MODEL = "https://w3id.org/modavis/vao/vocab/asset-role/acoustic-model"
ACOUSTIC_SCENE_METADATA = (
    "https://w3id.org/modavis/vao/vocab/asset-role/acoustic-scene-metadata"
)
CARRIER_LABEL_IMAGE = (
    "https://w3id.org/modavis/vao/vocab/asset-role/carrier-label-image"
)
VAO_ONTOLOGY = "https://w3id.org/modavis/vao/ontology#"
VAO_VOCABULARY = "https://w3id.org/modavis/vao/vocab/"
MODAVIS_AUDIO = "https://w3id.org/modavis/ontology/audio#"
CORE_CAPABILITIES = [
    "https://w3id.org/modavis/vao/vocab/capability/core-graph",
    "https://w3id.org/modavis/vao/vocab/capability/fixity",
]
MUSICAL_INSTRUMENT = "https://w3id.org/modavis/ontology/instrument#MusicalInstrument"
SOURCE_EVIDENCE = "https://w3id.org/modavis/vao/vocab/asset-role/source-evidence"
AUTHORED_REPRESENTATION = (
    "https://w3id.org/modavis/vao/vocab/representation-status/authored"
)

GENERIC_MODEL_VIEWING = (
    "https://w3id.org/modavis/vao/vocab/capability/generic-model-viewing"
)
SYNCHRONIZED_MEDIA_ANIMATION = (
    "https://w3id.org/modavis/vao/vocab/capability/synchronized-media-animation"
)
IMAGE_TARGET_AR = "https://w3id.org/modavis/vao/vocab/capability/image-target-ar"
SURFACE_PLACEMENT_AR = (
    "https://w3id.org/modavis/vao/vocab/capability/surface-placement-ar"
)
SPATIAL_LISTENING_MAP = (
    "https://w3id.org/modavis/vao/vocab/capability/spatial-listening-map"
)
OFFLINE_ASSET_GROUPS = (
    "https://w3id.org/modavis/vao/vocab/capability/offline-asset-groups"
)
REPLACEABLE_PERFORMANCE_MEDIA = (
    "https://w3id.org/modavis/vao/vocab/capability/replaceable-performance-media"
)
SAMPLED_INSTRUMENT_PLAYBACK = (
    "https://w3id.org/modavis/vao/vocab/capability/sampled-instrument-playback"
)
SOURCE_SEGMENTATION = (
    "https://w3id.org/modavis/vao/vocab/capability/source-segmentation"
)
ACOUSTICAL_ANALYSIS = (
    "https://w3id.org/modavis/vao/vocab/capability/acoustical-analysis"
)
TUNING_MAP = "https://w3id.org/modavis/vao/vocab/capability/tuning-map"
EMPIRICAL_TIMBRE_CLASSIFICATION = (
    VAO_VOCABULARY + "capability/empirical-timbre-classification"
)
PITCH_DEPENDENT_RANK_FINGERPRINT = (
    VAO_VOCABULARY + "capability/pitch-dependent-rank-fingerprint"
)
COLLECTION_ACOUSTIC_DIAGNOSTICS = (
    VAO_VOCABULARY + "capability/collection-acoustic-diagnostics"
)
COLLECTION_ACOUSTIC_DIAGNOSTICS_ANALYSIS = (
    VAO_VOCABULARY + "analysis/evidence-qualified-collection-acoustic-diagnostics"
)
COLLECTION_EVIDENCE_SUMMARY = VAO_VOCABULARY + "analysis/collection/evidence-summary"
COLLECTION_TAKE_EVIDENCE = VAO_VOCABULARY + "analysis/collection/take-evidence"
COLLECTION_RANK_CURVES = VAO_VOCABULARY + "analysis/collection/rank-tuning-curves"
COLLECTION_RANK_STRETCH = VAO_VOCABULARY + "analysis/collection/rank-stretch"
COLLECTION_SESSION_OFFSET = VAO_VOCABULARY + "analysis/collection/session-offset"
COLLECTION_SESSION_DRIFT = VAO_VOCABULARY + "analysis/collection/session-drift"
COLLECTION_ANOMALIES = (
    VAO_VOCABULARY + "analysis/collection/acoustic-anomaly-candidates"
)
COLLECTION_SIMILARITIES = (
    VAO_VOCABULARY + "analysis/collection/acoustic-similarity-candidates"
)
MACHINE_LEARNING_MODEL = VAO_VOCABULARY + "asset-role/machine-learning-model"
SEMANTIC_BUILDING_MODEL = (
    "https://w3id.org/modavis/vao/vocab/capability/semantic-building-model"
)
MEASURED_IMPULSE_RESPONSE = (
    "https://w3id.org/modavis/vao/vocab/capability/measured-impulse-response"
)
SPATIAL_RESPONSE_FIELD = (
    "https://w3id.org/modavis/vao/vocab/capability/spatial-response-field"
)
SOURCE_DIRECTIVITY = "https://w3id.org/modavis/vao/vocab/capability/source-directivity"
ROOM_ACOUSTIC_METRICS = (
    "https://w3id.org/modavis/vao/vocab/capability/room-acoustic-metrics"
)
BUILDING_ACOUSTIC_PERFORMANCE = (
    "https://w3id.org/modavis/vao/vocab/capability/building-acoustic-performance"
)
SPATIAL_AUDIO_SCENE = (
    "https://w3id.org/modavis/vao/vocab/capability/spatial-audio-scene"
)
TRACKED_LISTENER_CONVOLUTION = (
    "https://w3id.org/modavis/vao/vocab/capability/tracked-listener-convolution"
)
TRACKED_SOURCES = "https://w3id.org/modavis/vao/vocab/capability/tracked-sources"
GEOMETRY_ACOUSTIC_RENDERING = (
    "https://w3id.org/modavis/vao/vocab/capability/geometry-acoustic-rendering"
)
HYBRID_ACOUSTIC_RENDERING = (
    "https://w3id.org/modavis/vao/vocab/capability/hybrid-acoustic-rendering"
)
LEARNED_ACOUSTIC_FIELD = (
    "https://w3id.org/modavis/vao/vocab/capability/learned-acoustic-field"
)
ACOUSTICS_CAPABILITIES = {
    SEMANTIC_BUILDING_MODEL,
    MEASURED_IMPULSE_RESPONSE,
    SPATIAL_RESPONSE_FIELD,
    SOURCE_DIRECTIVITY,
    ROOM_ACOUSTIC_METRICS,
    BUILDING_ACOUSTIC_PERFORMANCE,
    SPATIAL_AUDIO_SCENE,
    TRACKED_LISTENER_CONVOLUTION,
    TRACKED_SOURCES,
    GEOMETRY_ACOUSTIC_RENDERING,
    HYBRID_ACOUSTIC_RENDERING,
    LEARNED_ACOUSTIC_FIELD,
}
SAMPLE_PLAYBACK_PARAMETERS = MODAVIS_AUDIO + "SamplePlaybackParameters"
TUNING_MAP_TYPE = MODAVIS_AUDIO + "TuningMap"
SAMPLE_EXTRACTION_REGION = MODAVIS_AUDIO + "SampleExtractionRegion"
EXPERIENTIAL_CAPABILITIES = {
    GENERIC_MODEL_VIEWING,
    SYNCHRONIZED_MEDIA_ANIMATION,
    IMAGE_TARGET_AR,
    SURFACE_PLACEMENT_AR,
    SPATIAL_LISTENING_MAP,
    OFFLINE_ASSET_GROUPS,
    REPLACEABLE_PERFORMANCE_MEDIA,
}
SUPPORTED_CAPABILITIES = (
    set(CORE_CAPABILITIES)
    | ACOUSTICS_CAPABILITIES
    | EXPERIENTIAL_CAPABILITIES
    | {
        VAO_VOCABULARY + "capability/paradata",
        VAO_VOCABULARY + "capability/analysis",
        VAO_VOCABULARY + "capability/audio",
        VAO_VOCABULARY + "capability/preservation",
        VAO_VOCABULARY + "capability/interaction",
        VAO_VOCABULARY + "capability/playable-interaction",
        VAO_VOCABULARY + "capability/performance-control",
        VAO_VOCABULARY + "capability/sample-looping",
        VAO_VOCABULARY + "capability/spatial",
        SAMPLED_INSTRUMENT_PLAYBACK,
        SOURCE_SEGMENTATION,
        ACOUSTICAL_ANALYSIS,
        TUNING_MAP,
        EMPIRICAL_TIMBRE_CLASSIFICATION,
        PITCH_DEPENDENT_RANK_FINGERPRINT,
        COLLECTION_ACOUSTIC_DIAGNOSTICS,
    }
)

MAX_ENTRIES = 100_000
MAX_MANIFEST_BYTES = 64 * 1024 * 1024
MAX_ENTRY_BYTES = 1024**4
MAX_TOTAL_BYTES = 4 * 1024**4
CHUNK = 1024 * 1024
SCHEMA_PATH = vao_resources.schema_directory() / "vao-manifest.schema.json"
_SCHEMA_DOCUMENT: dict[str, Any] | None = None

mimetypes.add_type("model/gltf-binary", ".glb")
mimetypes.add_type("model/gltf+json", ".gltf")
mimetypes.add_type("audio/midi", ".mid")
mimetypes.add_type("audio/wav", ".wav")
mimetypes.add_type("application/ld+json", ".jsonld")


class VAOError(Exception):
    pass


def now() -> str:
    return (
        datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    )


def json_bytes(value: Any) -> bytes:
    try:
        text = json.dumps(
            value, indent=2, ensure_ascii=False, sort_keys=True, allow_nan=False
        )
    except ValueError as exc:
        raise VAOError(f"Cannot serialize non-finite JSON number: {exc}") from exc
    return (text + "\n").encode("utf-8")


def strict_json_loads(source: str) -> Any:
    def reject_constant(value: str) -> None:
        raise ValueError(f"non-finite JSON number {value!r}")

    return json.loads(source, parse_constant=reject_constant)


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = strict_json_loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise VAOError(f"Cannot read {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise VAOError(f"{path} must contain a JSON object")
    return value


def write_json(path: Path, value: Any) -> None:
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_bytes(json_bytes(value))
    os.replace(temporary, path)


def safe_archive_path(value: str, *, payload: bool = False) -> bool:
    if not value or "\\" in value or "\x00" in value or value.startswith("/"):
        return False
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in ("", ".", "..") for part in path.parts):
        return False
    if payload and (not path.parts or path.parts[0] != "payload"):
        return False
    return True


def sha256_stream(stream: BinaryIO) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    while True:
        block = stream.read(CHUNK)
        if not block:
            break
        digest.update(block)
        size += len(block)
    return digest.hexdigest(), size


def sha256_file(path: Path) -> tuple[str, int]:
    with path.open("rb") as stream:
        return sha256_stream(stream)


def asset_id_for(path: str) -> str:
    return "urn:vao:asset:" + hashlib.sha256(path.encode("utf-8")).hexdigest()


def relation_id() -> str:
    return f"urn:uuid:{uuid.uuid4()}"


def is_uri(value: Any) -> bool:
    return (
        isinstance(value, str)
        and (
            value.startswith("urn:")
            or value.startswith("http://")
            or value.startswith("https://")
        )
        and not any(c.isspace() for c in value)
    )


def normative_schema() -> dict[str, Any]:
    global _SCHEMA_DOCUMENT
    if _SCHEMA_DOCUMENT is None:
        try:
            value = strict_json_loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
            raise VAOError(
                f"Cannot load normative schema {SCHEMA_PATH}: {exc}"
            ) from exc
        if not isinstance(value, dict):
            raise VAOError(f"Normative schema {SCHEMA_PATH} is not a JSON object")
        _SCHEMA_DOCUMENT = value
    return _SCHEMA_DOCUMENT


def schema_validation_errors(instance: Any, schema: dict[str, Any]) -> list[str]:
    """Evaluate the JSON Schema keywords used by the normative VAO schema."""
    root = schema

    def resolve(reference: str) -> dict[str, Any]:
        if not reference.startswith("#/"):
            return {}
        value: Any = root
        for token in reference[2:].split("/"):
            token = token.replace("~1", "/").replace("~0", "~")
            if not isinstance(value, dict) or token not in value:
                return {}
            value = value[token]
        return value if isinstance(value, dict) else {}

    def type_matches(value: Any, expected: str) -> bool:
        return {
            "object": isinstance(value, dict),
            "array": isinstance(value, list),
            "string": isinstance(value, str),
            "integer": isinstance(value, int) and not isinstance(value, bool),
            "number": isinstance(value, (int, float)) and not isinstance(value, bool),
            "boolean": isinstance(value, bool),
            "null": value is None,
        }.get(expected, True)

    def valid_format(value: str, name: str) -> bool:
        if name == "uri":
            parsed = urlsplit(value)
            return bool(parsed.scheme) and not any(
                character.isspace() for character in value
            )
        if name == "date-time":
            if not re.match(
                r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$",
                value,
            ):
                return False
            try:
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                return False
            return parsed.tzinfo is not None
        return True

    def visit(value: Any, rule: dict[str, Any], location: str) -> list[str]:
        if "$ref" in rule:
            resolved = resolve(str(rule["$ref"]))
            if not resolved:
                return [f"{location}: unresolved schema reference {rule['$ref']!r}."]
            return visit(value, resolved, location)

        found: list[str] = []
        if "allOf" in rule:
            for branch in rule["allOf"]:
                found.extend(visit(value, branch, location))
        if "anyOf" in rule:
            matches = sum(
                not visit(value, branch, location) for branch in rule["anyOf"]
            )
            if matches < 1:
                found.append(f"{location}: must match at least one allowed shape.")
        if "oneOf" in rule:
            matches = sum(
                not visit(value, branch, location) for branch in rule["oneOf"]
            )
            if matches != 1:
                found.append(
                    f"{location}: must match exactly one allowed shape (matched {matches})."
                )
        if "not" in rule and not visit(value, rule["not"], location):
            found.append(f"{location}: matches a prohibited shape.")
        if "if" in rule:
            condition_matches = not visit(value, rule["if"], location)
            branch = rule.get("then") if condition_matches else rule.get("else")
            if isinstance(branch, dict):
                found.extend(visit(value, branch, location))
        if "const" in rule and value != rule["const"]:
            found.append(f"{location}: must equal {rule['const']!r}.")
        if "enum" in rule and value not in rule["enum"]:
            found.append(f"{location}: value is not in the allowed enumeration.")

        expected = rule.get("type")
        if isinstance(expected, str) and not type_matches(value, expected):
            return found + [f"{location}: expected {expected}."]

        if isinstance(value, str):
            if len(value) < int(rule.get("minLength", 0)):
                found.append(f"{location}: string is shorter than minLength.")
            pattern = rule.get("pattern")
            if isinstance(pattern, str) and re.search(pattern, value) is None:
                found.append(f"{location}: string does not match the required pattern.")
            format_name = rule.get("format")
            if isinstance(format_name, str) and not valid_format(value, format_name):
                found.append(f"{location}: string is not a valid {format_name}.")

        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if "minimum" in rule and value < rule["minimum"]:
                found.append(f"{location}: number is below the minimum.")
            if "maximum" in rule and value > rule["maximum"]:
                found.append(f"{location}: number is above the maximum.")
            if "exclusiveMinimum" in rule and value <= rule["exclusiveMinimum"]:
                found.append(f"{location}: number is not above the exclusive minimum.")
            if "exclusiveMaximum" in rule and value >= rule["exclusiveMaximum"]:
                found.append(f"{location}: number is not below the exclusive maximum.")

        if isinstance(value, list):
            if len(value) < int(rule.get("minItems", 0)):
                found.append(f"{location}: array is shorter than minItems.")
            if "maxItems" in rule and len(value) > int(rule["maxItems"]):
                found.append(f"{location}: array is longer than maxItems.")
            if rule.get("uniqueItems"):
                fingerprints = [
                    json.dumps(item, sort_keys=True, ensure_ascii=False)
                    for item in value
                ]
                if len(fingerprints) != len(set(fingerprints)):
                    found.append(f"{location}: array items must be unique.")
            item_rule = rule.get("items")
            if isinstance(item_rule, dict):
                for index, item in enumerate(value):
                    found.extend(visit(item, item_rule, f"{location}[{index}]"))
            contains_rule = rule.get("contains")
            if isinstance(contains_rule, dict) and not any(
                not visit(item, contains_rule, location) for item in value
            ):
                found.append(f"{location}: array does not contain a required item.")

        if isinstance(value, dict):
            if len(value) < int(rule.get("minProperties", 0)):
                found.append(f"{location}: object has fewer than minProperties.")
            if "maxProperties" in rule and len(value) > int(rule["maxProperties"]):
                found.append(f"{location}: object has more than maxProperties.")
            required = rule.get("required", [])
            for key in required:
                if key not in value:
                    found.append(f"{location}: missing required property {key!r}.")
            dependent_required = rule.get("dependentRequired", {})
            if isinstance(dependent_required, dict):
                for key, dependencies in dependent_required.items():
                    if key in value:
                        for dependency in dependencies:
                            if dependency not in value:
                                found.append(
                                    f"{location}: property {key!r} requires {dependency!r}."
                                )
            name_rule = rule.get("propertyNames")
            if isinstance(name_rule, dict):
                for key in value:
                    found.extend(visit(key, name_rule, f"{location}.<property-name>"))
            properties = rule.get("properties", {})
            if isinstance(properties, dict):
                for key, child_rule in properties.items():
                    if key in value and isinstance(child_rule, dict):
                        found.extend(visit(value[key], child_rule, f"{location}.{key}"))
                unknown = set(value) - set(properties)
                additional = rule.get("additionalProperties", True)
                if additional is False:
                    for key in sorted(unknown):
                        found.append(f"{location}: unknown property {key!r}.")
                elif isinstance(additional, dict):
                    for key in sorted(unknown):
                        found.extend(visit(value[key], additional, f"{location}.{key}"))
        return found

    return visit(instance, schema, "$")


def iter_payload_files(workspace: Path) -> list[str]:
    payload = workspace / "payload"
    if not payload.exists():
        return []
    return sorted(
        path.relative_to(workspace).as_posix()
        for path in payload.rglob("*")
        if path.is_file() and not path.is_symlink()
    )


def validate_manifest(
    manifest: dict[str, Any],
    *,
    payload_names: Iterable[str] | None = None,
    payload_reader: Any | None = None,
) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    verified_bytes = 0

    def non_finite_paths(value: Any, location: str = "$") -> list[str]:
        if isinstance(value, float) and not math.isfinite(value):
            return [location]
        if isinstance(value, list):
            return [
                path
                for index, item in enumerate(value)
                for path in non_finite_paths(item, f"{location}[{index}]")
            ]
        if isinstance(value, dict):
            return [
                path
                for key, item in value.items()
                for path in non_finite_paths(item, f"{location}.{key}")
            ]
        return []

    for path in non_finite_paths(manifest):
        errors.append(f"Manifest contains a non-finite JSON number at {path}.")

    try:
        errors.extend(schema_validation_errors(manifest, normative_schema()))
    except VAOError as exc:
        errors.append(str(exc))

    required = [
        "@context",
        "type",
        "formatVersion",
        "id",
        "revision",
        "createdAt",
        "modifiedAt",
        "title",
        "conformsTo",
        "profiles",
        "modavisBinding",
        "primaryEntityId",
        "focusEntityIds",
        "entities",
        "relations",
        "assets",
        "paradata",
        "analyses",
        "rights",
        "integrity",
    ]
    for key in required:
        if key not in manifest:
            errors.append(f"Manifest is missing required field {key!r}.")

    if manifest.get("type") != "VirtualAcousticObject":
        errors.append("Manifest type must be VirtualAcousticObject.")
    version = manifest.get("formatVersion")
    if not isinstance(version, str) or not version.startswith("0.2."):
        errors.append(f"Unsupported VAO format version {version!r}.")
    if not is_uri(manifest.get("id")):
        errors.append("VAO id must be an absolute HTTP(S) IRI or URN.")
    if not isinstance(manifest.get("revision"), int) or manifest.get("revision", 0) < 1:
        errors.append("revision must be a positive integer.")
    if not isinstance(manifest.get("title"), dict) or not manifest.get("title"):
        errors.append("title must contain at least one localized string.")

    binding = manifest.get("modavisBinding")
    if not isinstance(binding, dict):
        errors.append("modavisBinding must be an object.")
    else:
        for key in (
            "ontologyIRI",
            "ontologyVersion",
            "ontologyStatus",
            "mappingVersion",
        ):
            if not binding.get(key):
                errors.append(f"modavisBinding is missing {key}.")
        if binding.get("ontologyStatus") not in (
            "development",
            "released",
            "embedded-snapshot",
        ):
            errors.append("modavisBinding.ontologyStatus is not recognized.")
        if binding.get("ontologyStatus") == "released":
            for key in ("ontologyVersionIRI", "mappingIRI"):
                if not is_uri(binding.get(key)):
                    errors.append(
                        f"released modavisBinding requires an absolute {key}."
                    )
        vocabulary_iri = binding.get("vocabularyReleaseIRI")
        vocabulary_hash = binding.get("vocabularyManifestSHA256")
        if vocabulary_iri is not None and not is_uri(vocabulary_iri):
            errors.append(
                "modavisBinding.vocabularyReleaseIRI must be an absolute IRI."
            )
        if vocabulary_iri is not None and not (
            isinstance(vocabulary_hash, str)
            and len(vocabulary_hash) == 64
            and all(
                character in "0123456789abcdefABCDEF" for character in vocabulary_hash
            )
        ):
            errors.append(
                "modavisBinding.vocabularyReleaseIRI requires a SHA-256 manifest pin."
            )
        if vocabulary_hash is not None and vocabulary_iri is None:
            errors.append(
                "modavisBinding.vocabularyManifestSHA256 requires vocabularyReleaseIRI."
            )

    entities = (
        manifest.get("entities") if isinstance(manifest.get("entities"), list) else []
    )
    relations = (
        manifest.get("relations") if isinstance(manifest.get("relations"), list) else []
    )
    assets = manifest.get("assets") if isinstance(manifest.get("assets"), list) else []
    paradata = (
        manifest.get("paradata") if isinstance(manifest.get("paradata"), list) else []
    )
    analyses = (
        manifest.get("analyses") if isinstance(manifest.get("analyses"), list) else []
    )
    rights = manifest.get("rights") if isinstance(manifest.get("rights"), list) else []

    if not entities:
        errors.append("At least one entity is required.")
    if not assets:
        errors.append(
            "The core VAO profile requires at least one indexed payload asset."
        )
    if not rights:
        errors.append(
            "At least one rights record is required; unknown rights must be stated explicitly."
        )

    registries = {
        "entity": entities,
        "relation": relations,
        "asset": assets,
        "paradata": paradata,
        "analysis": analyses,
    }
    all_ids: dict[str, str] = {}
    for label, records in registries.items():
        for index, record in enumerate(records):
            if not isinstance(record, dict):
                errors.append(f"{label}[{index}] must be an object.")
                continue
            identifier = record.get("id")
            if not is_uri(identifier):
                errors.append(f"{label}[{index}] has an invalid or missing id.")
                continue
            if identifier in all_ids:
                errors.append(
                    f"Duplicate identifier {identifier!r} in {all_ids[identifier]} and {label}."
                )
            else:
                all_ids[identifier] = label

    acoustics = (
        manifest.get("acoustics")
        if isinstance(manifest.get("acoustics"), dict)
        else None
    )
    acoustic_collections = (
        "coordinateFrames",
        "poses",
        "geometryBindings",
        "materialModels",
        "responseSets",
        "metricSets",
        "audioScenes",
        "renderConfigurations",
    )
    if acoustics is not None:
        for collection in acoustic_collections:
            for index, record in enumerate(acoustics.get(collection, [])):
                if not isinstance(record, dict):
                    continue
                identifier = record.get("id")
                if not is_uri(identifier):
                    errors.append(
                        f"acoustics.{collection}[{index}] has an invalid or missing id."
                    )
                elif identifier in all_ids:
                    errors.append(
                        f"Duplicate identifier {identifier!r} in {all_ids[identifier]} and acoustics.{collection}."
                    )
                else:
                    all_ids[identifier] = f"acoustics.{collection}"

    entity_ids = {record.get("id") for record in entities if isinstance(record, dict)}
    entities_by_id = {
        record.get("id"): record for record in entities if isinstance(record, dict)
    }
    primary = manifest.get("primaryEntityId")
    primary_records = [
        record
        for record in entities
        if isinstance(record, dict) and record.get("id") == primary
    ]
    if len(primary_records) != 1:
        errors.append("primaryEntityId must resolve to exactly one entity.")
    focus_ids = manifest.get("focusEntityIds")
    if not isinstance(focus_ids, list) or not focus_ids:
        errors.append("focusEntityIds must be a non-empty array.")
        focus_ids = []
    else:
        if primary not in focus_ids:
            errors.append("focusEntityIds must include primaryEntityId.")
        for reference in focus_ids:
            if reference not in entity_ids:
                errors.append(
                    f"focusEntityIds contains unresolved entity {reference!r}."
                )

    for index, entity in enumerate(entities):
        if not isinstance(entity, dict):
            continue
        if not isinstance(entity.get("types"), list) or not entity.get("types"):
            errors.append(
                f"Entity {entity.get('id', index)!r} requires at least one type IRI."
            )
        elif any(
            not isinstance(value, str) or not value.startswith(("http://", "https://"))
            for value in entity["types"]
        ):
            errors.append(
                f"Entity {entity.get('id', index)!r} contains a non-IRI type."
            )
        if not isinstance(entity.get("labels"), dict) or not entity.get("labels"):
            errors.append(
                f"Entity {entity.get('id', index)!r} requires a localized label."
            )

    for relation in relations:
        if not isinstance(relation, dict):
            continue
        subject = relation.get("subjectId")
        if subject not in all_ids:
            errors.append(
                f"Relation {relation.get('id')!r} has an unresolved subject {subject!r}."
            )
        if not isinstance(relation.get("predicate"), str) or not relation[
            "predicate"
        ].startswith(("http://", "https://")):
            errors.append(
                f"Relation {relation.get('id')!r} has an invalid predicate IRI."
            )
        has_object = "objectId" in relation
        has_literal = "literal" in relation
        if has_object == has_literal:
            errors.append(
                f"Relation {relation.get('id')!r} must have exactly one of objectId or literal."
            )
        if has_object and not is_uri(relation.get("objectId")):
            errors.append(
                f"Relation {relation.get('id')!r} has an invalid object identifier."
            )
        for reference in relation.get("evidenceIds", []) + relation.get(
            "generatedByIds", []
        ):
            if reference not in all_ids:
                errors.append(
                    f"Relation {relation.get('id')!r} has unresolved local reference {reference!r}."
                )

    asset_paths: set[str] = set()
    for index, asset in enumerate(assets):
        if not isinstance(asset, dict):
            continue
        label = asset.get("id", index)
        path = asset.get("path")
        if not isinstance(path, str) or not safe_archive_path(path, payload=True):
            errors.append(f"Asset {label!r} has an unsafe payload path.")
            continue
        if path in asset_paths:
            errors.append(f"Duplicate asset path {path!r}.")
        asset_paths.add(path)
        if not isinstance(asset.get("byteSize"), int) or asset.get("byteSize", -1) < 0:
            errors.append(f"Asset {label!r} has an invalid byteSize.")
        digest = asset.get("sha256")
        if (
            not isinstance(digest, str)
            or len(digest) != 64
            or any(c not in "0123456789abcdef" for c in digest)
        ):
            errors.append(f"Asset {label!r} has an invalid SHA-256.")
        if not isinstance(asset.get("mediaType"), str) or "/" not in asset.get(
            "mediaType", ""
        ):
            errors.append(f"Asset {label!r} has an invalid media type.")
        if not isinstance(asset.get("roles"), list) or not asset.get("roles"):
            errors.append(f"Asset {label!r} requires at least one role.")
        about = asset.get("aboutEntityIds")
        if not isinstance(about, list) or not about:
            errors.append(f"Asset {label!r} requires at least one subject entity.")
        else:
            for reference in about:
                if reference not in entity_ids:
                    errors.append(
                        f"Asset {label!r} refers to unknown entity {reference!r}."
                    )

        if payload_reader is not None and isinstance(digest, str):
            try:
                actual_digest, actual_size = payload_reader(path)
                verified_bytes += actual_size
                if actual_digest != digest:
                    errors.append(f"Asset hash mismatch for {path!r}.")
                if actual_size != asset.get("byteSize"):
                    errors.append(f"Asset byte-size mismatch for {path!r}.")
            except (KeyError, OSError, RuntimeError, zipfile.BadZipFile) as exc:
                errors.append(f"Cannot verify asset {path!r}: {exc}")

    if payload_names is not None:
        names = set(payload_names)
        for path in sorted(asset_paths - names):
            errors.append(f"Indexed asset is missing from payload: {path!r}.")
        for path in sorted(names - asset_paths):
            errors.append(f"Payload file is not indexed: {path!r}.")

    for activity in paradata:
        if not isinstance(activity, dict):
            continue
        if not activity.get("activityType") or not str(
            activity.get("activityType")
        ).startswith(("http://", "https://")):
            errors.append(f"Paradata {activity.get('id')!r} has no activity-type IRI.")
        software = activity.get("software")
        if (
            not isinstance(software, dict)
            or not software.get("name")
            or not software.get("version")
        ):
            errors.append(
                f"Paradata {activity.get('id')!r} requires software name and version."
            )
        for reference in activity.get("inputIds", []) + activity.get("outputIds", []):
            if reference not in all_ids:
                errors.append(
                    f"Paradata {activity.get('id')!r} has unresolved local reference {reference!r}."
                )

    assets_by_id = {
        asset.get("id"): asset for asset in assets if isinstance(asset, dict)
    }
    for record in analyses:
        if not isinstance(record, dict):
            continue
        for reference in record.get("inputIds", []) + record.get("outputIds", []):
            if reference not in all_ids:
                errors.append(
                    f"Analysis {record.get('id')!r} has unresolved local reference {reference!r}."
                )
        if (
            record.get("paradataId") is not None
            and record.get("paradataId") not in all_ids
        ):
            errors.append(
                f"Analysis {record.get('id')!r} has unresolved paradata reference."
            )
        for observation in record.get("observations", []):
            if not isinstance(observation, dict):
                continue
            if observation.get("unit") in {
                "http://qudt.org/vocab/unit/Centi",
                "https://qudt.org/vocab/unit/Centi",
            }:
                errors.append(
                    f"Analysis {record.get('id')!r} uses QUDT Centi, which is not a cent unit; "
                    f"use {VAO_VOCABULARY + 'unit/cent'!r}."
                )
            for key in ("subjectId", "sourceRegionId", "valueAssetId"):
                reference = observation.get(key)
                if reference is not None and reference not in all_ids:
                    errors.append(
                        f"Analysis {record.get('id')!r} observation has unresolved {key} {reference!r}."
                    )
            source_region = observation.get("sourceRegionId")
            if (
                source_region is not None
                and entities_by_id.get(source_region, {}).get("kind") != "signalRegion"
            ):
                errors.append(
                    f"Analysis {record.get('id')!r} observation sourceRegionId is not a signal region."
                )
            value_asset = observation.get("valueAssetId")
            if value_asset is not None and value_asset not in assets_by_id:
                errors.append(
                    f"Analysis {record.get('id')!r} observation valueAssetId is not an indexed asset."
                )
            channels = observation.get("channelIndices")
            if channels is not None and (
                not isinstance(channels, list)
                or not channels
                or any(
                    not isinstance(channel, int)
                    or isinstance(channel, bool)
                    or channel < 0
                    for channel in channels
                )
                or len(set(channels)) != len(channels)
            ):
                errors.append(
                    f"Analysis {record.get('id')!r} observation has invalid channel indices."
                )
            time_range = observation.get("timeRange")
            if isinstance(time_range, dict):
                if time_range.get("endSeconds", 0) < time_range.get("startSeconds", 0):
                    errors.append(
                        f"Analysis {record.get('id')!r} observation has an inverted time range."
                    )
                if "startFrameInclusive" in time_range:
                    start = time_range.get("startFrameInclusive")
                    end = time_range.get("endFrameExclusive")
                    rate = time_range.get("sampleRate")
                    clock = time_range.get("clockAssetId")
                    if (
                        not isinstance(start, int)
                        or isinstance(start, bool)
                        or start < 0
                        or not isinstance(end, int)
                        or isinstance(end, bool)
                        or end <= start
                        or not isinstance(rate, (int, float))
                        or isinstance(rate, bool)
                        or rate <= 0
                        or clock not in assets_by_id
                    ):
                        errors.append(
                            f"Analysis {record.get('id')!r} observation has an invalid exact-frame clock."
                        )

    rights_targets = {
        target
        for record in rights
        if isinstance(record, dict)
        for target in record.get("appliesToIds", [])
    }
    if manifest.get("id") not in rights_targets:
        errors.append("At least one rights record must apply to the VAO id.")

    integrity = manifest.get("integrity")
    if not isinstance(integrity, dict):
        errors.append("integrity must be an object.")
    else:
        if integrity.get("algorithm") != "sha256":
            errors.append("VAO 0.2 requires sha256 payload fixity.")
        if integrity.get("assetCount") != len(assets):
            errors.append("integrity.assetCount does not match the asset index.")
        declared_total = sum(
            asset.get("byteSize", 0)
            for asset in assets
            if isinstance(asset, dict) and isinstance(asset.get("byteSize"), int)
        )
        if integrity.get("totalPayloadBytes") != declared_total:
            errors.append("integrity.totalPayloadBytes does not match the asset index.")

    profile_records = [
        profile for profile in manifest.get("profiles", []) if isinstance(profile, dict)
    ]
    profile_ids = {profile.get("id") for profile in profile_records}
    if len(profile_ids) != len(profile_records):
        errors.append("Profile identifiers must be unique.")
    conforms_to = set(manifest.get("conformsTo", []))
    for profile in profile_records:
        profile_id = profile.get("id")
        if profile_id not in conforms_to:
            errors.append(
                f"Declared profile {profile_id!r} must also occur in conformsTo."
            )
        if profile_id in STANDARD_PROFILES and profile.get("version") != "0.2":
            errors.append(
                f"Standard VAO 0.2 profile {profile_id!r} must declare version '0.2'."
            )
    for profile_id in STANDARD_PROFILES.intersection(conforms_to):
        if profile_id not in profile_ids:
            errors.append(
                f"conformsTo claim {profile_id!r} requires a matching profile record."
            )
    declared_capabilities = {
        capability
        for profile in profile_records
        for capability in profile.get("requiredCapabilities", [])
        if isinstance(capability, str)
    }
    if CORE_PROFILE not in profile_ids:
        errors.append("Every VAO 0.2 package must claim the core profile.")
    if CORE_PROFILE not in manifest.get("conformsTo", []):
        errors.append("conformsTo must include the core profile URI.")
    if (
        EXPERIENTIAL_PROFILE in manifest.get("conformsTo", [])
        and EXPERIENTIAL_PROFILE not in profile_ids
    ):
        errors.append(
            "The experiential conformsTo claim requires an experiential profile record."
        )
    if RESEARCH_PROFILE in profile_ids and not paradata:
        errors.append("The research profile requires processing/capture paradata.")
    generated_outputs = {
        reference
        for activity in paradata
        if isinstance(activity, dict)
        for reference in activity.get("outputIds", [])
    }
    if RESEARCH_PROFILE in profile_ids:
        for record in analyses:
            if isinstance(record, dict) and not record.get("paradataId"):
                errors.append(
                    f"Research-profile analysis {record.get('id')!r} requires paradataId."
                )
        for asset in assets:
            if not isinstance(asset, dict):
                continue
            if (
                set(asset.get("roles", [])) & {ANALYSIS_RESULT, AUDIO_DERIVATIVE}
                and asset.get("id") not in generated_outputs
            ):
                errors.append(
                    f"Research-profile derivative asset {asset.get('id')!r} is not a paradata output."
                )
    if ORGREC_PROFILE in profile_ids:
        if RESEARCH_PROFILE not in profile_ids:
            errors.append("The OrgRec capture profile requires the research profile.")
        project_assets = [
            asset
            for asset in assets
            if isinstance(asset, dict)
            and asset.get("path") == "payload/orgrec/project.json"
            and APPLICATION_STATE in asset.get("roles", [])
        ]
        if len(project_assets) != 1:
            errors.append(
                "The OrgRec capture profile requires exactly one application-state payload/orgrec/project.json asset."
            )

    if PLAYABLE_PROFILE in profile_ids:
        interactions = [
            entity
            for entity in entities
            if isinstance(entity, dict) and entity.get("kind") == "interaction"
        ]
        if not interactions:
            errors.append(
                "The playable profile requires at least one interaction entity."
            )
        outgoing = {VAO_ONTOLOGY + "activates", VAO_ONTOLOGY + "modulates"}
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
                if VAO_ONTOLOGY + local_name not in properties:
                    errors.append(
                        f"Playable interaction {interaction.get('id')!r} is missing {local_name}."
                    )
            if not any(
                isinstance(relation, dict)
                and relation.get("subjectId") == interaction.get("id")
                and relation.get("predicate") in outgoing
                for relation in relations
            ):
                errors.append(
                    f"Playable interaction {interaction.get('id')!r} has no activates/modulates relation."
                )

    loop_sets = [
        entity
        for entity in entities
        if isinstance(entity, dict) and entity.get("kind") == "loopPointSet"
    ]
    signal_regions = {
        entity.get("id"): entity
        for entity in entities
        if isinstance(entity, dict) and entity.get("kind") == "signalRegion"
    }
    assets_by_id = {
        asset.get("id"): asset for asset in assets if isinstance(asset, dict)
    }
    for loop_set in loop_sets:
        identifier = loop_set.get("id")
        properties = (
            loop_set.get("properties")
            if isinstance(loop_set.get("properties"), dict)
            else {}
        )
        rate = properties.get(MODAVIS_AUDIO + "sampleRate")
        total = properties.get(MODAVIS_AUDIO + "totalFrames")
        digest = properties.get(MODAVIS_AUDIO + "sourceAudioSHA256")
        if (
            not isinstance(rate, (int, float))
            or isinstance(rate, bool)
            or rate <= 0
            or not isinstance(total, int)
            or isinstance(total, bool)
            or total <= 0
            or not isinstance(digest, str)
            or not re.fullmatch(r"[0-9a-f]{64}", digest)
        ):
            errors.append(
                f"Loop point set {identifier!r} has invalid source clock or fixity."
            )
            continue
        region_ids = [
            relation.get("objectId")
            for relation in relations
            if isinstance(relation, dict)
            and relation.get("subjectId") == identifier
            and relation.get("predicate") == MODAVIS_AUDIO + "hasLoopRegion"
        ]
        if len(region_ids) != 1 or region_ids[0] not in signal_regions:
            errors.append(
                f"Loop point set {identifier!r} must resolve exactly one signal region."
            )
            continue
        region = signal_regions[region_ids[0]]
        region_properties = (
            region.get("properties")
            if isinstance(region.get("properties"), dict)
            else {}
        )
        start = region_properties.get(MODAVIS_AUDIO + "startFrameInclusive")
        end = region_properties.get(MODAVIS_AUDIO + "endFrameExclusive")
        crossfade = region_properties.get(MODAVIS_AUDIO + "crossfadeFrames")
        frame_values_are_int = all(
            isinstance(value, int) and not isinstance(value, bool)
            for value in (start, end, crossfade)
        )
        if (
            not frame_values_are_int
            or start < 0
            or end <= start
            or end > total
            or crossfade < 0
            or crossfade * 2 >= end - start
        ):
            errors.append(
                f"Signal loop region {region.get('id')!r} has invalid half-open frame coordinates."
            )
        if region_properties.get(
            MODAVIS_AUDIO + "exitPolicy"
        ) != "envelopeRelease" and not isinstance(
            region_properties.get(MODAVIS_AUDIO + "releaseStartFrame"), int
        ):
            errors.append(
                f"Signal loop region {region.get('id')!r} requires a recorded release start for its exit policy."
            )
        signal_links = [
            relation.get("objectId")
            for relation in relations
            if isinstance(relation, dict)
            and relation.get("subjectId") == identifier
            and relation.get("predicate") == MODAVIS_AUDIO + "appliesToSignal"
        ]
        for asset_id in signal_links:
            asset = assets_by_id.get(asset_id)
            if isinstance(asset, dict) and asset.get("sha256") != digest:
                errors.append(
                    f"Loop point set {identifier!r} source hash does not match its linked audio asset."
                )
        if properties.get(MODAVIS_AUDIO + "status") == "accepted":
            loop_interactions = [
                entity
                for entity in entities
                if isinstance(entity, dict)
                and entity.get("kind") == "interaction"
                and any(
                    isinstance(relation, dict)
                    and relation.get("subjectId") == entity.get("id")
                    and relation.get("predicate") == MODAVIS_AUDIO + "usesLoopPointSet"
                    and relation.get("objectId") == identifier
                    for relation in relations
                )
            ]
            if not loop_interactions:
                errors.append(
                    f"Accepted loop point set {identifier!r} has no playable interaction."
                )
            for interaction in loop_interactions:
                if not any(
                    isinstance(relation, dict)
                    and relation.get("subjectId") == interaction.get("id")
                    and relation.get("predicate") == VAO_ONTOLOGY + "usesSample"
                    for relation in relations
                ):
                    errors.append(
                        f"Loop interaction {interaction.get('id')!r} has no usesSample relation."
                    )

    entities_by_id = {
        entity.get("id"): entity for entity in entities if isinstance(entity, dict)
    }

    def active_targets(subject_id: str, predicate: str) -> list[str]:
        return [
            relation.get("objectId")
            for relation in relations
            if isinstance(relation, dict)
            and relation.get("subjectId") == subject_id
            and relation.get("predicate") == predicate
            and relation.get("status") not in {"rejected", "superseded"}
            and isinstance(relation.get("objectId"), str)
        ]

    if SAMPLED_INSTRUMENT_PLAYBACK in declared_capabilities:
        if PLAYABLE_PROFILE not in profile_ids:
            errors.append(
                "The sampled-instrument-playback capability requires the playable profile."
            )
        mappings = [
            entity
            for entity in entities
            if isinstance(entity, dict)
            and entity.get("kind") == "parameterSet"
            and SAMPLE_PLAYBACK_PARAMETERS in entity.get("types", [])
        ]
        if not mappings:
            errors.append(
                "The sampled-instrument-playback capability requires sample playback parameters."
            )
        for mapping in mappings:
            identifier = mapping.get("id")
            properties = (
                mapping.get("properties")
                if isinstance(mapping.get("properties"), dict)
                else {}
            )
            required_numbers = (
                "rootKeyNumber",
                "minimumKeyNumber",
                "maximumKeyNumber",
                "minimumVelocity",
                "maximumVelocity",
                "targetFrequencyHz",
                "gainDB",
            )
            if any(
                not isinstance(properties.get(MODAVIS_AUDIO + name), (int, float))
                or isinstance(properties.get(MODAVIS_AUDIO + name), bool)
                for name in required_numbers
            ):
                errors.append(
                    f"Sample playback parameters {identifier!r} are missing numeric key, velocity, frequency, or gain values."
                )
                continue
            root_key = properties[MODAVIS_AUDIO + "rootKeyNumber"]
            minimum_key = properties[MODAVIS_AUDIO + "minimumKeyNumber"]
            maximum_key = properties[MODAVIS_AUDIO + "maximumKeyNumber"]
            minimum_velocity = properties[MODAVIS_AUDIO + "minimumVelocity"]
            maximum_velocity = properties[MODAVIS_AUDIO + "maximumVelocity"]
            target_frequency = properties[MODAVIS_AUDIO + "targetFrequencyHz"]
            if not (0 <= minimum_key <= root_key <= maximum_key <= 127):
                errors.append(
                    f"Sample playback parameters {identifier!r} have an invalid key range."
                )
            if not (0 <= minimum_velocity <= maximum_velocity <= 127):
                errors.append(
                    f"Sample playback parameters {identifier!r} have an invalid velocity range."
                )
            if target_frequency <= 0:
                errors.append(
                    f"Sample playback parameters {identifier!r} require a positive target frequency."
                )
            pitch_mode = properties.get(MODAVIS_AUDIO + "pitchTrackingMode")
            if pitch_mode not in {
                "preserveRecordedPitch",
                "resampleToTarget",
                "disabled",
            }:
                errors.append(
                    f"Sample playback parameters {identifier!r} have an invalid pitch-tracking mode."
                )
            source_frequency = properties.get(MODAVIS_AUDIO + "sourceFundamentalHz")
            if pitch_mode == "resampleToTarget" and (
                not isinstance(source_frequency, (int, float))
                or isinstance(source_frequency, bool)
                or source_frequency <= 0
            ):
                errors.append(
                    f"Sample playback parameters {identifier!r} require a measured source fundamental for resampling."
                )
            envelope = properties.get(MODAVIS_AUDIO + "envelope")
            if (
                not isinstance(envelope, dict)
                or not isinstance(envelope.get("attackSeconds"), (int, float))
                or not isinstance(envelope.get("releaseSeconds"), (int, float))
                or not isinstance(envelope.get("sustainLevel"), (int, float))
                or envelope.get("attackSeconds", -1) < 0
                or envelope.get("releaseSeconds", -1) < 0
                or not 0 <= envelope.get("sustainLevel", -1) <= 1
                or envelope.get("curve") not in {"linear", "equalPower", "natural"}
            ):
                errors.append(
                    f"Sample playback parameters {identifier!r} have an invalid envelope."
                )
            if properties.get(MODAVIS_AUDIO + "status") not in {"reviewed", "accepted"}:
                errors.append(
                    f"Sample playback parameters {identifier!r} must be reviewed or accepted for playable conformance."
                )
            interactions = [
                entity
                for entity in entities
                if isinstance(entity, dict)
                and entity.get("kind") == "interaction"
                and identifier
                in active_targets(
                    entity.get("id"), MODAVIS_AUDIO + "usesPlaybackParameters"
                )
            ]
            if not interactions:
                errors.append(
                    f"Sample playback parameters {identifier!r} are not used by a playable interaction."
                )
            for interaction in interactions:
                sample_ids = active_targets(
                    interaction.get("id"), VAO_ONTOLOGY + "usesSample"
                )
                if (
                    len(sample_ids) != 1
                    or sample_ids[0] not in assets_by_id
                    or not str(
                        assets_by_id[sample_ids[0]].get("mediaType", "")
                    ).startswith("audio/")
                ):
                    errors.append(
                        f"Sampled interaction {interaction.get('id')!r} must resolve exactly one audio sample."
                    )

    if TUNING_MAP in declared_capabilities:
        maps = [
            entity
            for entity in entities
            if isinstance(entity, dict)
            and entity.get("kind") == "parameterSet"
            and TUNING_MAP_TYPE in entity.get("types", [])
        ]
        if not maps:
            errors.append("The tuning-map capability requires a tuning map entity.")
        for tuning_map in maps:
            properties = (
                tuning_map.get("properties")
                if isinstance(tuning_map.get("properties"), dict)
                else {}
            )
            reference = properties.get(MODAVIS_AUDIO + "referenceA4Hz")
            reference_key = properties.get(MODAVIS_AUDIO + "referenceKeyNumber")
            entries = properties.get(MODAVIS_AUDIO + "tuningEntries")
            if (
                not isinstance(reference, (int, float))
                or isinstance(reference, bool)
                or reference <= 0
                or not isinstance(reference_key, int)
                or isinstance(reference_key, bool)
                or not 0 <= reference_key <= 127
                or not isinstance(entries, list)
                or not entries
            ):
                errors.append(
                    f"Tuning map {tuning_map.get('id')!r} has invalid reference data or no entries."
                )
                continue
            keys: set[int] = set()
            for entry in entries:
                key = entry.get("keyNumber") if isinstance(entry, dict) else None
                frequency = (
                    entry.get("targetFrequencyHz") if isinstance(entry, dict) else None
                )
                if (
                    not isinstance(key, int)
                    or isinstance(key, bool)
                    or not 0 <= key <= 127
                    or key in keys
                    or not isinstance(frequency, (int, float))
                    or isinstance(frequency, bool)
                    or frequency <= 0
                ):
                    errors.append(
                        f"Tuning map {tuning_map.get('id')!r} has an invalid or duplicate entry."
                    )
                    break
                keys.add(key)
                component = entry.get("componentId")
                if component is not None and component not in entities_by_id:
                    errors.append(
                        f"Tuning map {tuning_map.get('id')!r} entry has an unresolved component."
                    )
            if not any(
                tuning_map.get("id") in active_targets(subject.get("id"), predicate)
                for subject in entities
                if isinstance(subject, dict)
                for predicate in (
                    MODAVIS_AUDIO + "hasTuningMap",
                    MODAVIS_AUDIO + "usesTuningMap",
                )
            ):
                errors.append(
                    f"Tuning map {tuning_map.get('id')!r} is not linked to an instrument or interaction."
                )

    if SOURCE_SEGMENTATION in declared_capabilities:
        extraction_regions = [
            entity
            for entity in entities
            if isinstance(entity, dict)
            and entity.get("kind") == "signalRegion"
            and SAMPLE_EXTRACTION_REGION in entity.get("types", [])
        ]
        if not extraction_regions:
            errors.append(
                "The source-segmentation capability requires a sample extraction region."
            )
        for region in extraction_regions:
            properties = (
                region.get("properties")
                if isinstance(region.get("properties"), dict)
                else {}
            )
            start = properties.get(MODAVIS_AUDIO + "startFrameInclusive")
            end = properties.get(MODAVIS_AUDIO + "endFrameExclusive")
            total = properties.get(MODAVIS_AUDIO + "totalFrames")
            rate = properties.get(MODAVIS_AUDIO + "sampleRate")
            digest = properties.get(MODAVIS_AUDIO + "sourceAudioSHA256")
            if (
                not isinstance(start, int)
                or isinstance(start, bool)
                or start < 0
                or not isinstance(end, int)
                or isinstance(end, bool)
                or end <= start
                or not isinstance(total, int)
                or isinstance(total, bool)
                or end > total
                or not isinstance(rate, (int, float))
                or isinstance(rate, bool)
                or rate <= 0
                or not isinstance(digest, str)
                or not re.fullmatch(r"[0-9a-f]{64}", digest)
            ):
                errors.append(
                    f"Sample extraction region {region.get('id')!r} has invalid source coordinates or fixity."
                )
                continue
            source_ids = active_targets(
                region.get("id"), MODAVIS_AUDIO + "appliesToSignal"
            )
            if (
                len(source_ids) != 1
                or source_ids[0] not in assets_by_id
                or assets_by_id[source_ids[0]].get("sha256") != digest
            ):
                errors.append(
                    f"Sample extraction region {region.get('id')!r} does not resolve its fixed source audio."
                )
            derived = [
                relation
                for relation in relations
                if isinstance(relation, dict)
                and relation.get("predicate") == MODAVIS_AUDIO + "extractedFromRegion"
                and relation.get("objectId") == region.get("id")
                and relation.get("status") not in {"rejected", "superseded"}
            ]
            if not derived:
                errors.append(
                    f"Sample extraction region {region.get('id')!r} has no derived sample or take."
                )

    if ACOUSTICAL_ANALYSIS in declared_capabilities and not analyses:
        errors.append(
            "The acoustical-analysis capability requires at least one analysis record."
        )

    if EMPIRICAL_TIMBRE_CLASSIFICATION in declared_capabilities:
        records = [
            record
            for record in analyses
            if isinstance(record, dict)
            and record.get("analysisType")
            == VAO_VOCABULARY + "analysis/empirical-hierarchical-timbre-classification"
        ]
        model_assets = [
            asset
            for asset in assets
            if isinstance(asset, dict)
            and MACHINE_LEARNING_MODEL in asset.get("roles", [])
        ]
        if not records:
            errors.append(
                "The empirical-timbre-classification capability requires a hierarchical classification analysis."
            )
        if not model_assets:
            errors.append(
                "The empirical-timbre-classification capability requires an indexed machine-learning model asset."
            )
        model_ids = {asset.get("id") for asset in model_assets}
        expected_concepts = {
            VAO_VOCABULARY + "timbre-family/" + family
            for family in ("flute", "diapason", "string", "reed")
        }
        paradata_by_id = {
            activity.get("id"): activity
            for activity in paradata
            if isinstance(activity, dict)
        }
        for record in records:
            activity = paradata_by_id.get(record.get("paradataId"), {})
            method = (
                activity.get("method")
                if isinstance(activity.get("method"), dict)
                else {}
            )
            if (
                method.get("methodType") != "machine-learning-inference"
                or method.get("representationStatus") != "learned"
            ):
                errors.append(
                    f"Empirical timbre analysis {record.get('id')!r} requires learned machine-learning-inference paradata."
                )
            if model_ids.isdisjoint(activity.get("inputIds", [])):
                errors.append(
                    f"Empirical timbre analysis {record.get('id')!r} does not identify its model asset as an input."
                )
            observations = record.get("observations", [])
            distribution_record = next(
                (
                    item
                    for item in observations
                    if isinstance(item, dict)
                    and item.get("property")
                    == VAO_VOCABULARY + "analysis/timbre/calibrated-family-distribution"
                ),
                None,
            )
            distribution = (
                distribution_record.get("value")
                if isinstance(distribution_record, dict)
                else None
            )
            if not isinstance(distribution, list):
                errors.append(
                    f"Empirical timbre analysis {record.get('id')!r} has no calibrated family distribution."
                )
            else:
                probabilities = [
                    item.get("calibratedProbability")
                    for item in distribution
                    if isinstance(item, dict)
                ]
                concepts = [
                    item.get("concept")
                    for item in distribution
                    if isinstance(item, dict)
                ]
                if (
                    len(probabilities) != 4
                    or set(concepts) != expected_concepts
                    or any(
                        not isinstance(value, (int, float))
                        or isinstance(value, bool)
                        or not math.isfinite(value)
                        or not 0 <= value <= 1
                        for value in probabilities
                    )
                    or abs(sum(probabilities) - 1) > 1e-6
                ):
                    errors.append(
                        f"Empirical timbre analysis {record.get('id')!r} must contain exactly the governed four-family finite probabilities summing to one."
                    )
            decision_record = next(
                (
                    item
                    for item in observations
                    if isinstance(item, dict)
                    and item.get("property")
                    == VAO_VOCABULARY + "analysis/timbre/classification-decision"
                ),
                None,
            )
            decision = (
                decision_record.get("value")
                if isinstance(decision_record, dict)
                else None
            )
            if not isinstance(decision, dict) or not isinstance(
                decision.get("abstained"), bool
            ):
                errors.append(
                    f"Empirical timbre analysis {record.get('id')!r} has no typed classification decision."
                )
            elif (
                not isinstance(decision.get("outOfDistribution"), bool)
                or not isinstance(
                    decision.get("outOfDistributionDistance"), (int, float)
                )
                or isinstance(decision.get("outOfDistributionDistance"), bool)
                or not math.isfinite(decision["outOfDistributionDistance"])
                or decision["outOfDistributionDistance"] < 0
            ):
                errors.append(
                    f"Empirical timbre analysis {record.get('id')!r} requires a typed non-negative OOD decision and distance."
                )
            elif (
                not decision["abstained"]
                and decision.get("selectedConcept") not in expected_concepts
            ):
                errors.append(
                    f"Non-abstained empirical timbre analysis {record.get('id')!r} requires a selected governed family concept."
                )

    if PITCH_DEPENDENT_RANK_FINGERPRINT in declared_capabilities:
        records = [
            record
            for record in analyses
            if isinstance(record, dict)
            and record.get("analysisType")
            == VAO_VOCABULARY + "analysis/pitch-dependent-rank-fingerprint"
        ]
        if not records:
            errors.append(
                "The pitch-dependent-rank-fingerprint capability requires a rank-fingerprint analysis."
            )
        paradata_by_id = {
            activity.get("id"): activity
            for activity in paradata
            if isinstance(activity, dict)
        }
        for record in records:
            activity = paradata_by_id.get(record.get("paradataId"))
            if not isinstance(activity, dict):
                errors.append(
                    f"Rank fingerprint {record.get('id')!r} requires resolvable method paradata."
                )
            else:
                method = (
                    activity.get("method")
                    if isinstance(activity.get("method"), dict)
                    else {}
                )
                if method.get("methodType") != "metric-calculation":
                    errors.append(
                        f"Rank fingerprint {record.get('id')!r} requires metric-calculation paradata."
                    )
                seed = method.get("randomSeed")
                if not isinstance(seed, (int, str)) or isinstance(seed, bool):
                    errors.append(
                        f"Rank fingerprint {record.get('id')!r} requires a typed deterministic random seed."
                    )
                parameters = (
                    activity.get("parameters")
                    if isinstance(activity.get("parameters"), dict)
                    else {}
                )
                if not isinstance(
                    parameters.get("parameterSHA256"), str
                ) or not re.fullmatch(r"[0-9a-f]{64}", parameters["parameterSHA256"]):
                    errors.append(
                        f"Rank fingerprint {record.get('id')!r} requires a lowercase SHA-256 parameter fingerprint."
                    )
            observations = record.get("observations", [])
            trajectory_record = next(
                (
                    item
                    for item in observations
                    if isinstance(item, dict)
                    and item.get("property")
                    == VAO_VOCABULARY + "analysis/timbre/pitch-trajectory"
                ),
                None,
            )
            trajectory = (
                trajectory_record.get("value")
                if isinstance(trajectory_record, dict)
                else None
            )
            adjacent_pairs = set()
            if not isinstance(trajectory, list):
                errors.append(
                    f"Rank fingerprint {record.get('id')!r} has no pitch trajectory."
                )
            else:
                keys = [
                    item.get("keyNumber")
                    for item in trajectory
                    if isinstance(item, dict)
                ]
                if (
                    not keys
                    or len(keys) != len(trajectory)
                    or any(
                        not isinstance(key, int) or isinstance(key, bool)
                        for key in keys
                    )
                    or len(set(keys)) != len(keys)
                    or keys != sorted(keys)
                ):
                    errors.append(
                        f"Rank fingerprint {record.get('id')!r} trajectory keys must be non-empty, typed, unique, and ascending."
                    )
                for point in trajectory:
                    centroid = (
                        point.get("normalizedSpectralCentroid")
                        if isinstance(point, dict)
                        else None
                    )
                    slope = (
                        point.get("weightedAverageSlopeDBPerOctave")
                        if isinstance(point, dict)
                        else None
                    )
                    partials = (
                        point.get("relativePartialLevelsDB")
                        if isinstance(point, dict)
                        else None
                    )
                    if (
                        not isinstance(centroid, (int, float))
                        or isinstance(centroid, bool)
                        or not math.isfinite(centroid)
                        or not isinstance(slope, (int, float))
                        or isinstance(slope, bool)
                        or not math.isfinite(slope)
                        or not isinstance(partials, list)
                    ):
                        errors.append(
                            f"Rank fingerprint {record.get('id')!r} contains an incomplete or non-finite trajectory point."
                        )
                        break
                adjacent_pairs = set(zip(keys, keys[1:]))
            transition_record = next(
                (
                    item
                    for item in observations
                    if isinstance(item, dict)
                    and item.get("property")
                    == VAO_VOCABULARY
                    + "analysis/timbre/construction-transition-candidates"
                ),
                None,
            )
            transitions = (
                transition_record.get("value")
                if isinstance(transition_record, dict)
                else None
            )
            if not isinstance(transitions, list):
                errors.append(
                    f"Rank fingerprint {record.get('id')!r} has no transition-candidate observation."
                )
            else:
                for transition in transitions:
                    lower = (
                        transition.get("lowerKeyNumber")
                        if isinstance(transition, dict)
                        else None
                    )
                    upper = (
                        transition.get("upperKeyNumber")
                        if isinstance(transition, dict)
                        else None
                    )
                    delta = (
                        transition.get("bicImprovement")
                        if isinstance(transition, dict)
                        else None
                    )
                    p_value = (
                        transition.get("familyWisePermutationPValue")
                        if isinstance(transition, dict)
                        else None
                    )
                    effect = (
                        transition.get("standardizedEffectSize")
                        if isinstance(transition, dict)
                        else None
                    )
                    strength = (
                        transition.get("evidenceStrength")
                        if isinstance(transition, dict)
                        else None
                    )
                    interpretation = (
                        transition.get("interpretation")
                        if isinstance(transition, dict)
                        else None
                    )
                    if (
                        not isinstance(lower, int)
                        or isinstance(lower, bool)
                        or not isinstance(upper, int)
                        or isinstance(upper, bool)
                        or lower >= upper
                        or not isinstance(delta, (int, float))
                        or isinstance(delta, bool)
                        or delta < 0
                        or not isinstance(p_value, (int, float))
                        or isinstance(p_value, bool)
                        or not 0 <= p_value <= 1
                        or not isinstance(effect, (int, float))
                        or isinstance(effect, bool)
                        or not math.isfinite(effect)
                        or effect < 0
                        or not isinstance(strength, str)
                        or not strength
                        or not isinstance(interpretation, str)
                        or not interpretation
                        or (lower, upper) not in adjacent_pairs
                    ):
                        errors.append(
                            f"Rank fingerprint {record.get('id')!r} contains an invalid construction-transition candidate."
                        )
                        break

    if COLLECTION_ACOUSTIC_DIAGNOSTICS in declared_capabilities:
        research_capabilities = {
            capability
            for profile in profile_records
            if profile.get("id") == RESEARCH_PROFILE
            for capability in profile.get("requiredCapabilities", [])
            if isinstance(capability, str)
        }
        if COLLECTION_ACOUSTIC_DIAGNOSTICS not in research_capabilities:
            errors.append(
                "The collection-acoustic-diagnostics capability must be declared by the research profile."
            )
        if ACOUSTICAL_ANALYSIS not in research_capabilities:
            errors.append(
                "The collection-acoustic-diagnostics capability requires acoustical-analysis in the research profile."
            )
        records = [
            record
            for record in analyses
            if isinstance(record, dict)
            and record.get("analysisType") == COLLECTION_ACOUSTIC_DIAGNOSTICS_ANALYSIS
        ]
        if not records:
            errors.append(
                "The collection-acoustic-diagnostics capability requires an evidence-qualified collection analysis."
            )
        paradata_by_id = {
            activity.get("id"): activity
            for activity in paradata
            if isinstance(activity, dict)
        }
        required_properties = {
            COLLECTION_EVIDENCE_SUMMARY,
            COLLECTION_TAKE_EVIDENCE,
            COLLECTION_RANK_CURVES,
            COLLECTION_RANK_STRETCH,
            COLLECTION_SESSION_OFFSET,
            COLLECTION_SESSION_DRIFT,
            COLLECTION_ANOMALIES,
            COLLECTION_SIMILARITIES,
        }

        def finite_number(value: Any) -> bool:
            return (
                isinstance(value, (int, float))
                and not isinstance(value, bool)
                and math.isfinite(value)
            )

        for record in records:
            activity = paradata_by_id.get(record.get("paradataId"))
            if not isinstance(activity, dict):
                errors.append(
                    f"Collection diagnostics {record.get('id')!r} requires resolvable method paradata."
                )
                continue
            method = (
                activity.get("method")
                if isinstance(activity.get("method"), dict)
                else {}
            )
            if (
                method.get("methodType") != "metric-calculation"
                or method.get("representationStatus") != "inferred"
            ):
                errors.append(
                    f"Collection diagnostics {record.get('id')!r} requires inferred metric-calculation paradata."
                )
            parameters = (
                activity.get("parameters")
                if isinstance(activity.get("parameters"), dict)
                else {}
            )
            parameter_hash = parameters.get(VAO_ONTOLOGY + "parameterSHA256")
            if not isinstance(parameter_hash, str) or not re.fullmatch(
                r"[0-9a-f]{64}", parameter_hash
            ):
                errors.append(
                    f"Collection diagnostics {record.get('id')!r} requires a lowercase SHA-256 parameter fingerprint."
                )
            parameter_names = (
                "minimumAggregateQualityScore",
                "moderateQualityScore",
                "highQualityScore",
                "minimumAnomalyGroupSize",
                "anomalyWarningScore",
                "anomalyCriticalScore",
                "similarityThreshold",
                "minimumSimilarityHarmonics",
                "maximumSimilarityCandidates",
                "minimumDriftRepeatedTargets",
                "minimumDriftPairComparisons",
                "minimumDriftSpanHours",
            )
            if any(VAO_ONTOLOGY + name not in parameters for name in parameter_names):
                errors.append(
                    f"Collection diagnostics {record.get('id')!r} has an incomplete parameter set."
                )
            parameter = lambda name: parameters.get(VAO_ONTOLOGY + name)
            minimum_quality = parameter("minimumAggregateQualityScore")
            moderate_quality = parameter("moderateQualityScore")
            high_quality = parameter("highQualityScore")
            anomaly_group = parameter("minimumAnomalyGroupSize")
            warning_score = parameter("anomalyWarningScore")
            critical_score = parameter("anomalyCriticalScore")
            similarity_threshold = parameter("similarityThreshold")
            similarity_harmonics = parameter("minimumSimilarityHarmonics")
            maximum_candidates = parameter("maximumSimilarityCandidates")
            repeated_targets = parameter("minimumDriftRepeatedTargets")
            pair_comparisons = parameter("minimumDriftPairComparisons")
            drift_span = parameter("minimumDriftSpanHours")
            if not (
                finite_number(minimum_quality)
                and finite_number(moderate_quality)
                and finite_number(high_quality)
                and 0 <= minimum_quality <= moderate_quality <= high_quality <= 1
                and isinstance(anomaly_group, int)
                and not isinstance(anomaly_group, bool)
                and anomaly_group >= 3
                and finite_number(warning_score)
                and warning_score > 0
                and finite_number(critical_score)
                and critical_score >= warning_score
                and finite_number(similarity_threshold)
                and 0 <= similarity_threshold <= 1
                and isinstance(similarity_harmonics, int)
                and not isinstance(similarity_harmonics, bool)
                and similarity_harmonics >= 3
                and isinstance(maximum_candidates, int)
                and not isinstance(maximum_candidates, bool)
                and maximum_candidates > 0
                and isinstance(repeated_targets, int)
                and not isinstance(repeated_targets, bool)
                and repeated_targets > 0
                and isinstance(pair_comparisons, int)
                and not isinstance(pair_comparisons, bool)
                and pair_comparisons > 0
                and finite_number(drift_span)
                and drift_span >= 0
            ):
                errors.append(
                    f"Collection diagnostics {record.get('id')!r} has invalid parameter values."
                )
                continue
            observations = record.get("observations", [])
            properties = [
                item.get("property") for item in observations if isinstance(item, dict)
            ]
            if set(properties) != required_properties or len(properties) != len(
                set(properties)
            ):
                errors.append(
                    f"Collection diagnostics {record.get('id')!r} must contain each governed observation exactly once."
                )
                continue
            observation_by_property = {
                item.get("property"): item
                for item in observations
                if isinstance(item, dict)
            }
            expected_aggregations = {
                COLLECTION_RANK_CURVES: VAO_VOCABULARY
                + "aggregation/quality-weighted-median",
                COLLECTION_RANK_STRETCH: VAO_VOCABULARY
                + "aggregation/siegel-repeated-median",
                COLLECTION_SESSION_OFFSET: VAO_VOCABULARY + "aggregation/median",
                COLLECTION_SESSION_DRIFT: VAO_VOCABULARY
                + "aggregation/within-target-median-slope",
                COLLECTION_ANOMALIES: VAO_VOCABULARY
                + "aggregation/robust-multivariate-distance",
                COLLECTION_SIMILARITIES: VAO_VOCABULARY
                + "aggregation/harmonic-aligned-cosine",
            }
            if any(item.get("status") != "inferred" for item in observations) or any(
                observation_by_property[key].get("aggregation") != aggregation
                for key, aggregation in expected_aggregations.items()
            ):
                errors.append(
                    f"Collection diagnostics {record.get('id')!r} uses invalid status or aggregation semantics."
                )
            observation_subjects = {
                item.get("subjectId") for item in observations if isinstance(item, dict)
            }
            if (
                len(observation_subjects) != 1
                or None in observation_subjects
                or not observation_subjects <= entity_ids
            ):
                errors.append(
                    f"Collection diagnostics {record.get('id')!r} observations must share one resolved subject."
                )
            expected_units = {
                COLLECTION_RANK_CURVES: VAO_VOCABULARY + "unit/cent",
                COLLECTION_RANK_STRETCH: VAO_VOCABULARY + "unit/cent-per-octave",
                COLLECTION_SESSION_OFFSET: VAO_VOCABULARY + "unit/cent",
                COLLECTION_SESSION_DRIFT: VAO_VOCABULARY + "unit/cent-per-hour",
            }
            if any(
                observation_by_property[key].get("unit") != unit
                for key, unit in expected_units.items()
            ):
                errors.append(
                    f"Collection diagnostics {record.get('id')!r} uses an invalid governed unit."
                )
            summary = observation_by_property[COLLECTION_EVIDENCE_SUMMARY].get("value")
            count_keys = (
                "eligibleTakeCount",
                "analyzedTakeCount",
                "aggregateTakeCount",
                "highQualityCount",
                "moderateQualityCount",
                "limitedQualityCount",
                "excludedCount",
            )
            if (
                not isinstance(summary, dict)
                or any(
                    not isinstance(summary.get(key), int)
                    or isinstance(summary.get(key), bool)
                    or summary[key] < 0
                    for key in count_keys
                )
                or not finite_number(summary.get("aggregateCoverage"))
            ):
                errors.append(
                    f"Collection diagnostics {record.get('id')!r} has an invalid evidence summary."
                )
                continue
            eligible = summary["eligibleTakeCount"]
            analyzed = summary["analyzedTakeCount"]
            aggregate = summary["aggregateTakeCount"]
            tier_total = (
                summary["highQualityCount"]
                + summary["moderateQualityCount"]
                + summary["limitedQualityCount"]
            )
            coverage = summary["aggregateCoverage"]
            if (
                analyzed > eligible
                or aggregate > analyzed
                or tier_total != aggregate
                or tier_total + summary["excludedCount"] != eligible
                or not 0 <= coverage <= 1
                or abs(coverage - (aggregate / eligible if eligible else 0)) > 1e-9
            ):
                errors.append(
                    f"Collection diagnostics {record.get('id')!r} has an inconsistent evidence summary."
                )
                continue
            ledger = observation_by_property[COLLECTION_TAKE_EVIDENCE].get("value")
            if not isinstance(ledger, list) or len(ledger) != eligible:
                errors.append(
                    f"Collection diagnostics {record.get('id')!r} evidence ledger does not match its eligible count."
                )
                continue
            ledger_take_ids: set[str] = set()
            for entry in ledger:
                take_id = entry.get("takeId") if isinstance(entry, dict) else None
                rank_id = entry.get("rankGroupId") if isinstance(entry, dict) else None
                key = entry.get("keyNumber") if isinstance(entry, dict) else None
                quality = entry.get("qualityScore") if isinstance(entry, dict) else None
                tier = entry.get("tier") if isinstance(entry, dict) else None
                included = (
                    entry.get("includedInAggregates")
                    if isinstance(entry, dict)
                    else None
                )
                if (
                    take_id not in entity_ids
                    or take_id in ledger_take_ids
                    or rank_id not in entity_ids
                    or not isinstance(key, int)
                    or isinstance(key, bool)
                    or not 0 <= key <= 127
                    or not finite_number(quality)
                    or not 0 <= quality <= 1
                    or tier not in {"high", "moderate", "limited", "excluded"}
                    or not isinstance(included, bool)
                    or included != (tier != "excluded")
                ):
                    errors.append(
                        f"Collection diagnostics {record.get('id')!r} has an invalid or duplicate take-evidence entry."
                    )
                    break
                ledger_take_ids.add(take_id)
            if ledger_take_ids != set(record.get("inputIds", [])):
                errors.append(
                    f"Collection diagnostics {record.get('id')!r} inputs must equal its assessed take ledger."
                )
            if ledger_take_ids != set(activity.get("inputIds", [])) or record.get(
                "id"
            ) not in activity.get("outputIds", []):
                errors.append(
                    f"Collection diagnostics {record.get('id')!r} paradata lineage must use the assessed ledger and generate the analysis."
                )
            curves = observation_by_property[COLLECTION_RANK_CURVES].get("value")
            if not isinstance(curves, list):
                errors.append(
                    f"Collection diagnostics {record.get('id')!r} rank curves must be an array."
                )
            else:
                rank_ids: set[str] = set()
                for curve in curves:
                    rank_id = (
                        curve.get("rankGroupId") if isinstance(curve, dict) else None
                    )
                    points = curve.get("points") if isinstance(curve, dict) else None
                    grouping = (
                        curve.get("groupingBasis") if isinstance(curve, dict) else None
                    )
                    if (
                        rank_id not in entity_ids
                        or rank_id in rank_ids
                        or not isinstance(grouping, str)
                        or not grouping
                        or not isinstance(points, list)
                        or not points
                    ):
                        errors.append(
                            f"Collection diagnostics {record.get('id')!r} has an invalid or duplicate rank curve."
                        )
                        continue
                    rank_ids.add(rank_id)
                    prior_key = -1
                    for point in points:
                        key = (
                            point.get("keyNumber") if isinstance(point, dict) else None
                        )
                        median = (
                            point.get("medianDeviationCents")
                            if isinstance(point, dict)
                            else None
                        )
                        mad = (
                            point.get("medianAbsoluteDeviationCents")
                            if isinstance(point, dict)
                            else None
                        )
                        count = (
                            point.get("evidenceCount")
                            if isinstance(point, dict)
                            else None
                        )
                        if (
                            not isinstance(key, int)
                            or isinstance(key, bool)
                            or not prior_key < key <= 127
                            or not finite_number(median)
                            or not finite_number(mad)
                            or mad < 0
                            or not isinstance(count, int)
                            or isinstance(count, bool)
                            or count <= 0
                        ):
                            errors.append(
                                f"Collection diagnostics {record.get('id')!r} rank keys must be ascending and carry finite non-negative evidence."
                            )
                            break
                        prior_key = key
            stretches = observation_by_property[COLLECTION_RANK_STRETCH].get("value")
            if not isinstance(stretches, list):
                errors.append(
                    f"Collection diagnostics {record.get('id')!r} rank stretches must be an array."
                )
            else:
                stretch_rank_ids: set[str] = set()
                for stretch in stretches:
                    rank_id = (
                        stretch.get("rankGroupId")
                        if isinstance(stretch, dict)
                        else None
                    )
                    value = (
                        stretch.get("stretchCentsPerOctave")
                        if isinstance(stretch, dict)
                        else None
                    )
                    method = (
                        stretch.get("method") if isinstance(stretch, dict) else None
                    )
                    count = (
                        stretch.get("evidenceCount")
                        if isinstance(stretch, dict)
                        else None
                    )
                    if (
                        rank_id not in entity_ids
                        or rank_id in stretch_rank_ids
                        or not finite_number(value)
                        or not isinstance(method, str)
                        or not method
                        or not isinstance(count, int)
                        or isinstance(count, bool)
                        or count <= 0
                    ):
                        errors.append(
                            f"Collection diagnostics {record.get('id')!r} has an invalid or duplicate rank-stretch entry."
                        )
                        break
                    stretch_rank_ids.add(rank_id)
            offsets = observation_by_property[COLLECTION_SESSION_OFFSET].get("value")
            if not isinstance(offsets, list):
                errors.append(
                    f"Collection diagnostics {record.get('id')!r} session offsets must be an array."
                )
            else:
                offset_session_ids: set[str] = set()
                for offset in offsets:
                    session_id = (
                        offset.get("sessionId") if isinstance(offset, dict) else None
                    )
                    value = (
                        offset.get("medianDeviationCents")
                        if isinstance(offset, dict)
                        else None
                    )
                    count = (
                        offset.get("evidenceCount")
                        if isinstance(offset, dict)
                        else None
                    )
                    if (
                        session_id not in entity_ids
                        or session_id in offset_session_ids
                        or not finite_number(value)
                        or not isinstance(count, int)
                        or isinstance(count, bool)
                        or count <= 0
                    ):
                        errors.append(
                            f"Collection diagnostics {record.get('id')!r} has an invalid or duplicate session-offset entry."
                        )
                        break
                    offset_session_ids.add(session_id)
            drifts = observation_by_property[COLLECTION_SESSION_DRIFT].get("value")
            if not isinstance(drifts, list):
                errors.append(
                    f"Collection diagnostics {record.get('id')!r} session drift must be an array."
                )
            else:
                session_ids: set[str] = set()
                for drift in drifts:
                    session_id = (
                        drift.get("sessionId") if isinstance(drift, dict) else None
                    )
                    value = (
                        drift.get("driftCentsPerHour")
                        if isinstance(drift, dict)
                        else None
                    )
                    applicability = (
                        drift.get("applicability") if isinstance(drift, dict) else None
                    )
                    repeated = (
                        drift.get("repeatedTargetCount")
                        if isinstance(drift, dict)
                        else None
                    )
                    comparisons = (
                        drift.get("pairComparisonCount")
                        if isinstance(drift, dict)
                        else None
                    )
                    duration = (
                        drift.get("durationHours") if isinstance(drift, dict) else None
                    )
                    if (
                        session_id not in entity_ids
                        or session_id in session_ids
                        or applicability not in {"applicable", "indeterminate"}
                        or not isinstance(repeated, int)
                        or isinstance(repeated, bool)
                        or repeated < 0
                        or not isinstance(comparisons, int)
                        or isinstance(comparisons, bool)
                        or comparisons < 0
                        or (
                            value is not None
                            and (
                                not finite_number(value)
                                or applicability != "applicable"
                                or repeated < repeated_targets
                                or comparisons < pair_comparisons
                                or not finite_number(duration)
                                or duration < drift_span
                            )
                        )
                        or (value is None and applicability != "indeterminate")
                    ):
                        errors.append(
                            f"Collection diagnostics {record.get('id')!r} has an invalid or duplicate session-drift entry."
                        )
                        continue
                    session_ids.add(session_id)
            anomalies = observation_by_property[COLLECTION_ANOMALIES].get("value")
            if not isinstance(anomalies, list):
                errors.append(
                    f"Collection diagnostics {record.get('id')!r} anomalies must be an array."
                )
            else:
                anomaly_take_ids: set[str] = set()
                for candidate in anomalies:
                    take_id = (
                        candidate.get("takeId") if isinstance(candidate, dict) else None
                    )
                    score = (
                        candidate.get("robustDistance")
                        if isinstance(candidate, dict)
                        else None
                    )
                    quality = (
                        candidate.get("qualityScore")
                        if isinstance(candidate, dict)
                        else None
                    )
                    severity = (
                        candidate.get("severity")
                        if isinstance(candidate, dict)
                        else None
                    )
                    if (
                        take_id not in ledger_take_ids
                        or take_id in anomaly_take_ids
                        or not finite_number(score)
                        or score < 0
                        or not finite_number(quality)
                        or not 0 <= quality <= 1
                        or severity not in {"warning", "critical"}
                        or score < warning_score
                        or severity
                        != ("critical" if score >= critical_score else "warning")
                    ):
                        errors.append(
                            f"Collection diagnostics {record.get('id')!r} has an invalid or duplicate anomaly candidate."
                        )
                        break
                    anomaly_take_ids.add(take_id)
            similarities = observation_by_property[COLLECTION_SIMILARITIES].get("value")
            if not isinstance(similarities, list):
                errors.append(
                    f"Collection diagnostics {record.get('id')!r} similarities must be an array."
                )
            else:
                if len(similarities) > maximum_candidates:
                    errors.append(
                        f"Collection diagnostics {record.get('id')!r} exceeds its declared similarity-candidate cap."
                    )
                pairs: set[tuple[str, str]] = set()
                for candidate in similarities:
                    first = (
                        candidate.get("firstTakeId")
                        if isinstance(candidate, dict)
                        else None
                    )
                    second = (
                        candidate.get("secondTakeId")
                        if isinstance(candidate, dict)
                        else None
                    )
                    similarity = (
                        candidate.get("cosineSimilarity")
                        if isinstance(candidate, dict)
                        else None
                    )
                    count = (
                        candidate.get("sharedPartialCount")
                        if isinstance(candidate, dict)
                        else None
                    )
                    interpretation = (
                        candidate.get("interpretation")
                        if isinstance(candidate, dict)
                        else None
                    )
                    pair = (first, second)
                    if (
                        first not in ledger_take_ids
                        or second not in ledger_take_ids
                        or not first < second
                        or pair in pairs
                        or not finite_number(similarity)
                        or not similarity_threshold <= similarity <= 1
                        or not isinstance(count, int)
                        or isinstance(count, bool)
                        or count < similarity_harmonics
                        or not isinstance(interpretation, str)
                        or "candidate" not in interpretation.casefold()
                    ):
                        errors.append(
                            f"Collection diagnostics {record.get('id')!r} has an invalid, duplicate, or identity-overstating similarity candidate."
                        )
                        break
                    pairs.add(pair)

    acoustic_profiles = [
        profile for profile in profile_records if profile.get("id") == ACOUSTICS_PROFILE
    ]
    acoustic_declared_capabilities = {
        capability
        for profile in acoustic_profiles
        for capability in profile.get("requiredCapabilities", [])
        if isinstance(capability, str)
    }
    if ACOUSTICS_PROFILE in profile_ids:
        if len(acoustic_profiles) != 1:
            errors.append("The acoustics profile must be declared exactly once.")
        if SPATIAL_PROFILE not in profile_ids:
            errors.append("The acoustics profile requires the spatial profile.")
        if ACOUSTICS_PROFILE not in manifest.get("conformsTo", []):
            errors.append(
                "conformsTo must include the acoustics profile URI when that profile is claimed."
            )
        if acoustics is None:
            errors.append(
                "The acoustics profile requires the closed top-level acoustics object."
            )
        if not acoustic_declared_capabilities.intersection(ACOUSTICS_CAPABILITIES):
            errors.append(
                "The acoustics profile requires at least one standard acoustic capability."
            )

    if acoustics is not None:
        frames = acoustics.get("coordinateFrames", [])
        poses = acoustics.get("poses", [])
        geometry_bindings = acoustics.get("geometryBindings", [])
        material_models = acoustics.get("materialModels", [])
        response_sets = acoustics.get("responseSets", [])
        metric_sets = acoustics.get("metricSets", [])
        audio_scenes = acoustics.get("audioScenes", [])
        render_configurations = acoustics.get("renderConfigurations", [])
        frame_by_id = {
            item.get("id"): item for item in frames if isinstance(item, dict)
        }
        pose_by_id = {item.get("id"): item for item in poses if isinstance(item, dict)}
        response_by_id = {
            item.get("id"): item for item in response_sets if isinstance(item, dict)
        }
        metric_by_id = {
            item.get("id"): item for item in metric_sets if isinstance(item, dict)
        }
        scene_by_id = {
            item.get("id"): item for item in audio_scenes if isinstance(item, dict)
        }
        paradata_by_id = {
            item.get("id"): item for item in paradata if isinstance(item, dict)
        }

        def require_reference(
            owner: str, key: str, reference: Any, allowed: set[str] | None = None
        ) -> None:
            if reference is None:
                return
            registry = allowed if allowed is not None else set(all_ids)
            if reference not in registry:
                errors.append(f"{owner}.{key} has unresolved reference {reference!r}.")

        def generated_by(owner: str, identifier: Any) -> dict[str, Any] | None:
            activity = paradata_by_id.get(identifier)
            if activity is None:
                errors.append(f"{owner}.generatedById must resolve to paradata.")
            return activity

        def matrix_is_invertible(values: Any) -> bool:
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
            matrix = [
                list(map(float, values[row * 4 : (row + 1) * 4])) for row in range(4)
            ]
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

        parent_by_frame: dict[str, str] = {}
        for frame in frames:
            if not isinstance(frame, dict):
                continue
            identifier = frame.get("id")
            parent = frame.get("parentFrameId")
            transform = frame.get("transformToParent")
            if parent is not None:
                require_reference(
                    f"Coordinate frame {identifier!r}",
                    "parentFrameId",
                    parent,
                    set(frame_by_id),
                )
                if transform is None:
                    errors.append(
                        f"Coordinate frame {identifier!r} with a parent requires transformToParent."
                    )
                elif not matrix_is_invertible(transform):
                    errors.append(
                        f"Coordinate frame {identifier!r} transformToParent is not a finite invertible 4x4 matrix."
                    )
                if isinstance(identifier, str) and isinstance(parent, str):
                    parent_by_frame[identifier] = parent
            elif transform is not None:
                errors.append(
                    f"Coordinate frame {identifier!r} cannot have transformToParent without parentFrameId."
                )
            if (
                frame.get("dimension") == 2
                and frame.get("handedness") != "not-applicable"
            ):
                errors.append(
                    f"Two-dimensional coordinate frame {identifier!r} must use handedness 'not-applicable'."
                )
        for identifier in parent_by_frame:
            visited: set[str] = set()
            cursor = identifier
            while cursor in parent_by_frame:
                if cursor in visited:
                    errors.append(
                        f"Coordinate-frame parent graph contains a cycle at {identifier!r}."
                    )
                    break
                visited.add(cursor)
                cursor = parent_by_frame[cursor]

        for pose in poses:
            if not isinstance(pose, dict):
                continue
            identifier = pose.get("id")
            require_reference(
                f"Pose {identifier!r}", "subjectId", pose.get("subjectId"), entity_ids
            )
            require_reference(
                f"Pose {identifier!r}", "frameId", pose.get("frameId"), set(frame_by_id)
            )
            frame = frame_by_id.get(pose.get("frameId"), {})
            position = pose.get("position")
            if (
                isinstance(position, list)
                and frame
                and len(position) != frame.get("dimension")
            ):
                errors.append(
                    f"Pose {identifier!r} dimension does not match its coordinate frame."
                )
            orientation = pose.get("orientationXYZW")
            if isinstance(orientation, list) and len(orientation) == 4:
                norm = math.sqrt(sum(float(value) ** 2 for value in orientation))
                if not math.isfinite(norm) or abs(norm - 1.0) > 1e-5:
                    errors.append(
                        f"Pose {identifier!r} orientationXYZW must be a normalized XYZW quaternion."
                    )
            if (
                pose.get("validFrom")
                and pose.get("validUntil")
                and pose["validUntil"] < pose["validFrom"]
            ):
                errors.append(f"Pose {identifier!r} has an inverted validity interval.")
            for key in (
                "configurationId",
                "stateId",
                "trajectoryAssetId",
                "generatedById",
            ):
                require_reference(f"Pose {identifier!r}", key, pose.get(key))

        for binding_record in geometry_bindings:
            if not isinstance(binding_record, dict):
                continue
            identifier = binding_record.get("id")
            require_reference(
                f"Geometry binding {identifier!r}",
                "subjectId",
                binding_record.get("subjectId"),
                entity_ids,
            )
            require_reference(
                f"Geometry binding {identifier!r}",
                "assetId",
                binding_record.get("assetId"),
                set(assets_by_id),
            )
            require_reference(
                f"Geometry binding {identifier!r}",
                "frameId",
                binding_record.get("frameId"),
                set(frame_by_id),
            )
            require_reference(
                f"Geometry binding {identifier!r}",
                "generatedById",
                binding_record.get("generatedById"),
                set(paradata_by_id),
            )
            selector = binding_record.get("selector", {})
            asset = assets_by_id.get(binding_record.get("assetId"), {})
            selector_type = (
                selector.get("selectorType") if isinstance(selector, dict) else None
            )
            if selector_type == "gltf-node-index" and asset.get("mediaType") not in {
                "model/gltf+json",
                "model/gltf-binary",
            }:
                errors.append(
                    f"Geometry binding {identifier!r} uses a glTF selector on a non-glTF asset."
                )
            if selector_type == "gltf-node-index" and not isinstance(
                selector.get("value"), int
            ):
                errors.append(
                    f"Geometry binding {identifier!r} glTF node selector must be an integer index; glTF names are not identifiers."
                )
            if selector_type == "usd-prim-path" and not str(
                selector.get("value", "")
            ).startswith("/"):
                errors.append(
                    f"Geometry binding {identifier!r} USD prim selector must be an absolute prim path."
                )

        for material in material_models:
            if not isinstance(material, dict):
                continue
            identifier = material.get("id")
            require_reference(
                f"Material model {identifier!r}",
                "materialEntityId",
                material.get("materialEntityId"),
                entity_ids,
            )
            activity = generated_by(
                f"Material model {identifier!r}", material.get("generatedById")
            )
            if activity is not None and activity.get("method", {}).get(
                "methodType"
            ) not in {
                "material-characterization",
                "simulation",
                "manual-authoring",
                "machine-learning-inference",
            }:
                errors.append(
                    f"Material model {identifier!r} paradata does not declare a material method."
                )
            bands = material.get("bandAxis", {}).get("centerFrequenciesHz", [])
            if any(b <= 0 for b in bands) or any(
                left >= right for left, right in zip(bands, bands[1:])
            ):
                errors.append(
                    f"Material model {identifier!r} frequencies must be positive and strictly ascending."
                )
            for key in ("absorption", "scattering", "transmissionLossDB"):
                if key in material and len(material[key]) != len(bands):
                    errors.append(
                        f"Material model {identifier!r} {key} length must match its frequency axis."
                    )
            require_reference(
                f"Material model {identifier!r}",
                "surfaceImpedanceAssetId",
                material.get("surfaceImpedanceAssetId"),
                set(assets_by_id),
            )
            require_reference(
                f"Material model {identifier!r}",
                "environmentStateId",
                material.get("environmentStateId"),
                entity_ids,
            )

        for response in response_sets:
            if not isinstance(response, dict):
                continue
            identifier = response.get("id")
            require_reference(
                f"Response set {identifier!r}",
                "responseEntityId",
                response.get("responseEntityId"),
                entity_ids,
            )
            require_reference(
                f"Response set {identifier!r}",
                "assetId",
                response.get("assetId"),
                set(assets_by_id),
            )
            activity = generated_by(
                f"Response set {identifier!r}", response.get("generatedById")
            )
            status = response.get("representationStatus")
            method_type = (
                activity.get("method", {}).get("methodType") if activity else None
            )
            if status == "measured" and method_type not in {
                "measurement",
                "deconvolution",
            }:
                errors.append(
                    f"Measured response set {identifier!r} requires measurement/deconvolution method paradata."
                )
            asset = assets_by_id.get(response.get("assetId"), {})
            if IMPULSE_RESPONSE not in asset.get("roles", []) and response.get(
                "responseKind"
            ) not in {"hrtf", "directivity", "sound-field"}:
                errors.append(
                    f"Response set {identifier!r} asset must carry the impulse-response role."
                )
            encoding = response.get("encoding")
            if encoding == "AES69-SOFA" and not str(
                asset.get("path", "")
            ).lower().endswith(".sofa"):
                errors.append(
                    f"AES69-SOFA response set {identifier!r} must reference a .sofa asset."
                )
            if encoding in {"WAV", "FLAC"} and (
                len(response.get("measurements", [])) != 1
                or response.get("interpolation") is not None
            ):
                errors.append(
                    f"{encoding} response set {identifier!r} is limited to one fixed source-receiver pair without interpolation; use SOFA for spatial sets."
                )
            for measurement in response.get("measurements", []):
                if not isinstance(measurement, dict):
                    continue
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
                    require_reference(
                        f"Response set {identifier!r} measurement",
                        key,
                        measurement.get(key),
                        entity_ids,
                    )
                require_reference(
                    f"Response set {identifier!r} measurement",
                    "sourcePoseId",
                    measurement.get("sourcePoseId"),
                    set(pose_by_id),
                )
                require_reference(
                    f"Response set {identifier!r} measurement",
                    "receiverPoseId",
                    measurement.get("receiverPoseId"),
                    set(pose_by_id),
                )
                for path_id in measurement.get("transmissionPathIds", []):
                    require_reference(
                        f"Response set {identifier!r} measurement",
                        "transmissionPathIds",
                        path_id,
                        entity_ids,
                    )
            interpolation = response.get("interpolation")
            if isinstance(interpolation, dict):
                require_reference(
                    f"Response set {identifier!r} interpolation",
                    "domain",
                    interpolation.get("domain"),
                    entity_ids,
                )
                for key in ("fallbackResponseSetId",):
                    require_reference(
                        f"Response set {identifier!r} interpolation",
                        key,
                        interpolation.get(key),
                        set(response_by_id),
                    )
                require_reference(
                    f"Response set {identifier!r} interpolation",
                    "modelAssetId",
                    interpolation.get("modelAssetId"),
                    set(assets_by_id),
                )
                for key in ("trainingInputIds", "validationInputIds"):
                    for reference in interpolation.get(key, []):
                        require_reference(
                            f"Response set {identifier!r} interpolation", key, reference
                        )
                require_reference(
                    f"Response set {identifier!r} interpolation",
                    "qualityMetricSetId",
                    interpolation.get("qualityMetricSetId"),
                    set(metric_by_id),
                )
                if interpolation.get("method") == "neural-field":
                    for key in (
                        "modelAssetId",
                        "trainingInputIds",
                        "validationInputIds",
                        "qualityMetricSetId",
                        "fallbackResponseSetId",
                    ):
                        if not interpolation.get(key):
                            errors.append(
                                f"Neural-field response set {identifier!r} requires {key}."
                            )
                    model_id = interpolation.get("modelAssetId")
                    model_asset = assets_by_id.get(model_id, {})
                    if ACOUSTIC_MODEL not in model_asset.get("roles", []):
                        errors.append(
                            f"Neural-field response set {identifier!r} model asset requires the acoustic-model role."
                        )
                    if method_type != "machine-learning-inference" or model_id not in (
                        activity or {}
                    ).get("inputIds", []):
                        errors.append(
                            f"Neural-field response set {identifier!r} requires machine-learning-inference paradata that uses its fixed model asset."
                        )
                    if not any(
                        candidate.get("method", {}).get("methodType")
                        == "machine-learning-training"
                        and model_id in candidate.get("outputIds", [])
                        for candidate in paradata
                        if isinstance(candidate, dict)
                    ):
                        errors.append(
                            f"Neural-field response set {identifier!r} model asset requires machine-learning-training provenance."
                        )
                    fallback = response_by_id.get(
                        interpolation.get("fallbackResponseSetId"), {}
                    )
                    if fallback.get("representationStatus") in {"learned", "hybrid"}:
                        errors.append(
                            f"Neural-field response set {identifier!r} fallback must be non-learned."
                        )
                    determinism = interpolation.get("determinism")
                    if determinism is None or (
                        determinism == "seeded" and "seed" not in interpolation
                    ):
                        errors.append(
                            f"Neural-field response set {identifier!r} requires determinism and a seed when seeded."
                        )

        for metric_set in metric_sets:
            if not isinstance(metric_set, dict):
                continue
            identifier = metric_set.get("id")
            activity = generated_by(
                f"Metric set {identifier!r}", metric_set.get("generatedById")
            )
            if (
                activity is not None
                and activity.get("method", {}).get("methodType") != "metric-calculation"
            ):
                errors.append(
                    f"Metric set {identifier!r} paradata must declare metric-calculation."
                )
            for key in ("subjectIds", "inputIds"):
                for reference in metric_set.get(key, []):
                    require_reference(f"Metric set {identifier!r}", key, reference)
            bands = metric_set.get("bandAxis", {}).get("centerFrequenciesHz", [])
            if any(b <= 0 for b in bands) or any(
                left >= right for left, right in zip(bands, bands[1:])
            ):
                errors.append(
                    f"Metric set {identifier!r} frequencies must be positive and strictly ascending."
                )
            for metric in metric_set.get("metrics", []):
                if not isinstance(metric, dict):
                    continue
                if len(metric.get("values", [])) != len(bands):
                    errors.append(
                        f"Metric {metric.get('property')!r} in {identifier!r} must align with its frequency axis."
                    )
                if "uncertainties" in metric and len(metric["uncertainties"]) != len(
                    bands
                ):
                    errors.append(
                        f"Metric uncertainties in {identifier!r} must align with its frequency axis."
                    )
                for key in (
                    "sourceId",
                    "receiverId",
                    "sourceSpaceId",
                    "receivingSpaceId",
                    "separatingElementId",
                ):
                    require_reference(
                        f"Metric set {identifier!r}", key, metric.get(key), entity_ids
                    )

        for scene in audio_scenes:
            if not isinstance(scene, dict):
                continue
            identifier = scene.get("id")
            require_reference(
                f"Audio scene {identifier!r}",
                "sceneEntityId",
                scene.get("sceneEntityId"),
                entity_ids,
            )
            require_reference(
                f"Audio scene {identifier!r}",
                "coordinateFrameId",
                scene.get("coordinateFrameId"),
                set(frame_by_id),
            )
            for reference in scene.get("mediaAssetIds", []):
                require_reference(
                    f"Audio scene {identifier!r}",
                    "mediaAssetIds",
                    reference,
                    set(assets_by_id),
                )
            require_reference(
                f"Audio scene {identifier!r}",
                "metadataAssetId",
                scene.get("metadataAssetId"),
                set(assets_by_id),
            )
            require_reference(
                f"Audio scene {identifier!r}",
                "generatedById",
                scene.get("generatedById"),
                set(paradata_by_id),
            )
            if scene.get("representationType") == "ITU-ADM-BW64" and not any(
                str(assets_by_id.get(reference, {}).get("path", ""))
                .lower()
                .endswith((".wav", ".bw64"))
                for reference in scene.get("mediaAssetIds", [])
            ):
                errors.append(
                    f"ITU-ADM-BW64 audio scene {identifier!r} requires a BW64/WAVE asset carrying ADM metadata."
                )
            for binding_record in scene.get("bindings", []):
                if not isinstance(binding_record, dict):
                    continue
                for key, registry in (
                    ("entityId", entity_ids),
                    ("mediaAssetId", set(assets_by_id)),
                    ("poseId", set(pose_by_id)),
                    ("directivityResponseSetId", set(response_by_id)),
                ):
                    require_reference(
                        f"Audio scene {identifier!r} binding",
                        key,
                        binding_record.get(key),
                        registry,
                    )

        for configuration in render_configurations:
            if not isinstance(configuration, dict):
                continue
            identifier = configuration.get("id")
            require_reference(
                f"Render configuration {identifier!r}",
                "sceneId",
                configuration.get("sceneId"),
                set(scene_by_id),
            )
            require_reference(
                f"Render configuration {identifier!r}",
                "coordinateFrameId",
                configuration.get("coordinateFrameId"),
                set(frame_by_id),
            )
            for key in ("inputIds", "fallbackIds"):
                for reference in configuration.get(key, []):
                    require_reference(
                        f"Render configuration {identifier!r}", key, reference
                    )
            listener = configuration.get("listener", {})
            for key, registry in (
                ("receiverId", entity_ids),
                ("coordinateFrameId", set(frame_by_id)),
                ("poseId", set(pose_by_id)),
                ("trajectoryAssetId", set(assets_by_id)),
                ("personalizationAssetId", set(assets_by_id)),
                ("headphoneCompensationAssetId", set(assets_by_id)),
            ):
                require_reference(
                    f"Render configuration {identifier!r} listener",
                    key,
                    listener.get(key),
                    registry,
                )
            require_reference(
                f"Render configuration {identifier!r}",
                "validDomainId",
                configuration.get("validDomainId"),
                entity_ids,
            )
            if configuration.get(
                "outsideDomainPolicy"
            ) == "fallback" and not configuration.get("fallbackIds"):
                errors.append(
                    f"Render configuration {identifier!r} selects fallback policy without a fallback."
                )
            if configuration.get("strategy") == "learned-field" and not any(
                response_by_id.get(reference, {}).get("interpolation", {}).get("method")
                == "neural-field"
                for reference in configuration.get("inputIds", [])
            ):
                errors.append(
                    f"Learned-field render configuration {identifier!r} requires a neural-field response input."
                )

        if SPATIAL_PROFILE in profile_ids and not frames:
            errors.append(
                "The spatial profile requires at least one explicit coordinate frame."
            )
        if SEMANTIC_BUILDING_MODEL in acoustic_declared_capabilities:
            kinds = {
                entity.get("kind") for entity in entities if isinstance(entity, dict)
            }
            if not {"building", "space", "boundary"}.issubset(kinds):
                errors.append(
                    "The semantic-building-model capability requires building, space, and boundary entities."
                )
            if not any(
                binding.get("role") == "authoritative-semantic"
                for binding in geometry_bindings
                if isinstance(binding, dict)
            ):
                errors.append(
                    "The semantic-building-model capability requires an authoritative semantic geometry binding."
                )
        if MEASURED_IMPULSE_RESPONSE in acoustic_declared_capabilities and not any(
            response.get("representationStatus") == "measured"
            for response in response_sets
            if isinstance(response, dict)
        ):
            errors.append(
                "The measured-impulse-response capability requires a measured response set."
            )
        if SPATIAL_RESPONSE_FIELD in acoustic_declared_capabilities and not any(
            response.get("interpolation")
            for response in response_sets
            if isinstance(response, dict)
        ):
            errors.append(
                "The spatial-response-field capability requires an interpolation contract."
            )
        if SOURCE_DIRECTIVITY in acoustic_declared_capabilities and not any(
            response.get("responseKind") == "directivity"
            for response in response_sets
            if isinstance(response, dict)
        ):
            errors.append(
                "The source-directivity capability requires a directivity response set."
            )
        if ROOM_ACOUSTIC_METRICS in acoustic_declared_capabilities and not metric_sets:
            errors.append("The room-acoustic-metrics capability requires a metric set.")
        if BUILDING_ACOUSTIC_PERFORMANCE in acoustic_declared_capabilities and not any(
            metric.get("sourceSpaceId")
            and metric.get("receivingSpaceId")
            and metric.get("separatingElementId")
            for metric_set in metric_sets
            if isinstance(metric_set, dict)
            for metric in metric_set.get("metrics", [])
            if isinstance(metric, dict)
        ):
            errors.append(
                "The building-acoustic-performance capability requires source room, receiving room, and separating element on a metric."
            )
        if SPATIAL_AUDIO_SCENE in acoustic_declared_capabilities and not audio_scenes:
            errors.append("The spatial-audio-scene capability requires an audio scene.")
        if TRACKED_LISTENER_CONVOLUTION in acoustic_declared_capabilities and not any(
            configuration.get("strategy")
            in {"tracked-convolution", "response-interpolation"}
            and configuration.get("listener", {}).get("mode")
            in {"tracked-3dof", "tracked-6dof"}
            for configuration in render_configurations
            if isinstance(configuration, dict)
        ):
            errors.append(
                "The tracked-listener-convolution capability requires a tracked listener render configuration."
            )
        if TRACKED_SOURCES in acoustic_declared_capabilities and not any(
            feature.get("feature") == "source-tracking"
            and feature.get("mode") != "disabled"
            and feature.get("inputIds")
            for configuration in render_configurations
            if isinstance(configuration, dict)
            for feature in configuration.get("features", [])
            if isinstance(feature, dict)
        ):
            errors.append(
                "The tracked-sources capability requires a non-disabled source-tracking feature with explicit inputs."
            )
        if GEOMETRY_ACOUSTIC_RENDERING in acoustic_declared_capabilities:
            if not any(
                configuration.get("strategy") in {"geometry-acoustics", "hybrid"}
                for configuration in render_configurations
                if isinstance(configuration, dict)
            ):
                errors.append(
                    "The geometry-acoustic-rendering capability requires a geometry or hybrid render configuration."
                )
            if not material_models:
                errors.append(
                    "The geometry-acoustic-rendering capability requires acoustic material models."
                )
        if HYBRID_ACOUSTIC_RENDERING in acoustic_declared_capabilities and not any(
            configuration.get("strategy") == "hybrid"
            for configuration in render_configurations
            if isinstance(configuration, dict)
        ):
            errors.append(
                "The hybrid-acoustic-rendering capability requires a hybrid render configuration."
            )
        if LEARNED_ACOUSTIC_FIELD in acoustic_declared_capabilities and not any(
            response.get("representationStatus") in {"learned", "hybrid"}
            and response.get("interpolation", {}).get("method") == "neural-field"
            for response in response_sets
            if isinstance(response, dict)
        ):
            errors.append(
                "The learned-acoustic-field capability requires a learned/hybrid neural-field response set."
            )

    if SPATIAL_PROFILE in profile_ids:
        if acoustics is None:
            errors.append(
                "The spatial profile requires the top-level acoustics object."
            )
        elif not acoustics.get("poses") and not acoustics.get("geometryBindings"):
            errors.append(
                "The spatial profile requires at least one pose or geometry binding."
            )

    if EXPERIENTIAL_PROFILE in profile_ids:
        experiential_profiles = [
            profile
            for profile in manifest.get("profiles", [])
            if isinstance(profile, dict) and profile.get("id") == EXPERIENTIAL_PROFILE
        ]
        if len(experiential_profiles) != 1:
            errors.append("The experiential profile must be declared exactly once.")
            declared_experiential_capabilities: set[str] = set()
        else:
            capabilities = experiential_profiles[0].get("requiredCapabilities", [])
            declared_experiential_capabilities = {
                value for value in capabilities if isinstance(value, str)
            }
        if EXPERIENTIAL_PROFILE not in manifest.get("conformsTo", []):
            errors.append(
                "conformsTo must include the experiential profile URI when that profile is claimed."
            )
        known_capabilities = (
            declared_experiential_capabilities & EXPERIENTIAL_CAPABILITIES
        )
        if not known_capabilities:
            errors.append(
                "The experiential profile requires at least one standard experiential capability."
            )

        entities_by_id = {
            entity.get("id"): entity for entity in entities if isinstance(entity, dict)
        }

        def active_targets(subject_id: str, predicate: str) -> list[str]:
            return [
                relation.get("objectId")
                for relation in relations
                if isinstance(relation, dict)
                and relation.get("subjectId") == subject_id
                and relation.get("predicate") == predicate
                and relation.get("status") not in {"rejected", "superseded"}
                and isinstance(relation.get("objectId"), str)
            ]

        def valid_dimensions(value: Any, *, depth_required: bool) -> bool:
            if not isinstance(value, dict) or not is_uri(value.get("unit")):
                return False
            names = (
                ("width", "height", "depth") if depth_required else ("width", "height")
            )
            return all(
                isinstance(value.get(name), (int, float))
                and not isinstance(value.get(name), bool)
                and value[name] > 0
                for name in names
            )

        def valid_coordinate_metadata(asset: dict[str, Any]) -> bool:
            properties = (
                asset.get("properties")
                if isinstance(asset.get("properties"), dict)
                else {}
            )
            return (
                isinstance(properties.get(VAO_ONTOLOGY + "coordinateSystem"), str)
                and bool(properties[VAO_ONTOLOGY + "coordinateSystem"].strip())
                and is_uri(properties.get(VAO_ONTOLOGY + "coordinateUnit"))
                and properties.get(VAO_ONTOLOGY + "handedness") in {"left", "right"}
                and properties.get(VAO_ONTOLOGY + "upAxis") in {"X", "Y", "Z"}
                and valid_dimensions(
                    properties.get(VAO_ONTOLOGY + "physicalDimensions"),
                    depth_required=True,
                )
            )

        def experience_entities(capability: str) -> list[dict[str, Any]]:
            return [
                entity
                for entity in entities
                if isinstance(entity, dict)
                and entity.get("kind") == "experience"
                and isinstance(entity.get("properties"), dict)
                and entity["properties"].get(VAO_ONTOLOGY + "experienceCapability")
                == capability
            ]

        def validate_presents(
            experience: dict[str, Any], allowed_kinds: set[str], capability_label: str
        ) -> None:
            targets = active_targets(experience.get("id"), VAO_ONTOLOGY + "presents")
            if not any(
                target in entities_by_id
                and entities_by_id[target].get("kind") in allowed_kinds
                for target in targets
            ):
                errors.append(
                    f"Experiential {capability_label} experience {experience.get('id')!r} has no valid presents relation."
                )

        def model_assets(
            experience: dict[str, Any], capability_label: str
        ) -> list[dict[str, Any]]:
            targets = active_targets(experience.get("id"), VAO_ONTOLOGY + "usesModel")
            models = [
                assets_by_id[target]
                for target in targets
                if target in assets_by_id
                and set(assets_by_id[target].get("roles", []))
                & {THREE_DIMENSIONAL_MODEL, SPATIAL_MODEL}
            ]
            if not models:
                errors.append(
                    f"Experiential {capability_label} experience {experience.get('id')!r} has no usesModel relation to a model asset."
                )
            for asset in models:
                if not valid_coordinate_metadata(asset):
                    errors.append(
                        f"Experiential model asset {asset.get('id')!r} lacks valid coordinates or physical dimensions."
                    )
            return models

        for capability in sorted(known_capabilities):
            matching_experiences = experience_entities(capability)
            if not matching_experiences:
                errors.append(
                    f"Experiential capability {capability!r} has no matching experience entity."
                )
                continue

            if capability in {
                GENERIC_MODEL_VIEWING,
                IMAGE_TARGET_AR,
                SURFACE_PLACEMENT_AR,
                SPATIAL_LISTENING_MAP,
            }:
                if (
                    SPATIAL_PROFILE not in profile_ids
                    or SPATIAL_PROFILE not in manifest.get("conformsTo", [])
                ):
                    errors.append(
                        f"Experiential capability {capability!r} requires the spatial profile."
                    )

            for experience in matching_experiences:
                identifier = experience.get("id")
                properties = (
                    experience.get("properties")
                    if isinstance(experience.get("properties"), dict)
                    else {}
                )

                if capability == GENERIC_MODEL_VIEWING:
                    validate_presents(
                        experience,
                        {"instrument", "spatialRegion"},
                        "generic-model-viewing",
                    )
                    model_assets(experience, "generic-model-viewing")

                elif capability == SYNCHRONIZED_MEDIA_ANIMATION:
                    validate_presents(
                        experience, {"instrument"}, "synchronized-media-animation"
                    )
                    performance_ids = active_targets(
                        identifier, VAO_ONTOLOGY + "hasPerformance"
                    )
                    performances = [
                        entities_by_id[target]
                        for target in performance_ids
                        if target in entities_by_id
                        and entities_by_id[target].get("kind") == "performance"
                    ]
                    if not performances:
                        errors.append(
                            f"Synchronized experience {identifier!r} has no hasPerformance relation to a performance entity."
                        )
                    for performance in performances:
                        performance_properties = (
                            performance.get("properties")
                            if isinstance(performance.get("properties"), dict)
                            else {}
                        )
                        clock = performance_properties.get(
                            VAO_ONTOLOGY + "timelineClock"
                        )
                        clock_valid = (
                            isinstance(clock, dict)
                            and is_uri(clock.get("timeUnit"))
                            and isinstance(clock.get("duration"), (int, float))
                            and not isinstance(clock.get("duration"), bool)
                            and clock["duration"] > 0
                            and (
                                "offset" not in clock
                                or (
                                    isinstance(clock.get("offset"), (int, float))
                                    and not isinstance(clock.get("offset"), bool)
                                    and clock["offset"] >= 0
                                )
                            )
                        )
                        if not clock_valid:
                            errors.append(
                                f"Performance {performance.get('id')!r} has an invalid timelineClock."
                            )
                        media = [
                            assets_by_id[target]
                            for target in active_targets(
                                performance.get("id"), VAO_ONTOLOGY + "usesMedia"
                            )
                            if target in assets_by_id
                            and PERFORMANCE_MEDIA
                            in assets_by_id[target].get("roles", [])
                            and str(
                                assets_by_id[target].get("mediaType", "")
                            ).startswith(("audio/", "video/"))
                        ]
                        if not media:
                            errors.append(
                                f"Performance {performance.get('id')!r} has no usesMedia relation to performance media."
                            )
                        animations = [
                            assets_by_id[target]
                            for target in active_targets(
                                performance.get("id"), VAO_ONTOLOGY + "drivesAnimation"
                            )
                            if target in assets_by_id
                            and ANIMATION in assets_by_id[target].get("roles", [])
                        ]
                        if not animations:
                            errors.append(
                                f"Performance {performance.get('id')!r} has no drivesAnimation relation to an animation asset."
                            )
                        triggers = active_targets(
                            performance.get("id"), VAO_ONTOLOGY + "triggeredBy"
                        )
                        if triggers:
                            if (
                                PLAYABLE_PROFILE not in profile_ids
                                or PLAYABLE_PROFILE
                                not in manifest.get("conformsTo", [])
                            ):
                                errors.append(
                                    f"Triggered performance {performance.get('id')!r} requires the playable profile."
                                )
                            for target in triggers:
                                if (
                                    target not in entities_by_id
                                    or entities_by_id[target].get("kind")
                                    != "interaction"
                                ):
                                    errors.append(
                                        f"Performance {performance.get('id')!r} has triggeredBy target that is not an interaction."
                                    )

                elif capability == IMAGE_TARGET_AR:
                    validate_presents(
                        experience, {"instrument", "spatialRegion"}, "image-target-ar"
                    )
                    model_assets(experience, "image-target-ar")
                    target_assets = [
                        assets_by_id[target]
                        for target in active_targets(
                            identifier, VAO_ONTOLOGY + "usesTarget"
                        )
                        if target in assets_by_id
                        and IMAGE_TARGET in assets_by_id[target].get("roles", [])
                        and str(assets_by_id[target].get("mediaType", "")).startswith(
                            "image/"
                        )
                    ]
                    if not target_assets:
                        errors.append(
                            f"Image-target AR experience {identifier!r} has no image target asset."
                        )
                    for asset in target_assets:
                        asset_properties = (
                            asset.get("properties")
                            if isinstance(asset.get("properties"), dict)
                            else {}
                        )
                        if not valid_dimensions(
                            asset_properties.get(VAO_ONTOLOGY + "physicalDimensions"),
                            depth_required=False,
                        ):
                            errors.append(
                                f"Image target {asset.get('id')!r} lacks valid physical dimensions."
                            )
                    for target in active_targets(
                        identifier, VAO_ONTOLOGY + "usesTrackingData"
                    ):
                        if (
                            target not in assets_by_id
                            or TRACKING_DATA
                            not in assets_by_id[target].get("roles", [])
                        ):
                            errors.append(
                                f"Image-target AR experience {identifier!r} has invalid tracking-data target {target!r}."
                            )

                elif capability == SURFACE_PLACEMENT_AR:
                    validate_presents(
                        experience,
                        {"instrument", "spatialRegion"},
                        "surface-placement-ar",
                    )
                    model_assets(experience, "surface-placement-ar")
                    policy = properties.get(VAO_ONTOLOGY + "placementPolicy")
                    if not (
                        isinstance(policy, dict)
                        and policy.get("surfaceAlignment")
                        in {"horizontal", "vertical", "any"}
                        and policy.get("modelAnchor") in {"origin", "base-center"}
                        and isinstance(policy.get("allowUniformScale"), bool)
                    ):
                        errors.append(
                            f"Surface-placement experience {identifier!r} has an invalid placementPolicy."
                        )

                elif capability == SPATIAL_LISTENING_MAP:
                    validate_presents(
                        experience, {"place", "spatialRegion"}, "spatial-listening-map"
                    )
                    point_ids = active_targets(
                        identifier, VAO_ONTOLOGY + "hasListeningPoint"
                    )
                    points = [
                        entities_by_id[target]
                        for target in point_ids
                        if target in entities_by_id
                        and entities_by_id[target].get("kind") == "spatialRegion"
                    ]
                    if not points:
                        errors.append(
                            f"Spatial-listening experience {identifier!r} has no listening point."
                        )
                    for point in points:
                        point_properties = (
                            point.get("properties")
                            if isinstance(point.get("properties"), dict)
                            else {}
                        )
                        position = point_properties.get(VAO_ONTOLOGY + "position")
                        coordinates_valid = (
                            isinstance(
                                point_properties.get(VAO_ONTOLOGY + "coordinateSystem"),
                                str,
                            )
                            and bool(
                                point_properties[
                                    VAO_ONTOLOGY + "coordinateSystem"
                                ].strip()
                            )
                            and is_uri(
                                point_properties.get(VAO_ONTOLOGY + "coordinateUnit")
                            )
                            and point_properties.get(VAO_ONTOLOGY + "handedness")
                            in {"left", "right"}
                            and point_properties.get(VAO_ONTOLOGY + "upAxis")
                            in {"X", "Y", "Z"}
                        )
                        position_valid = (
                            isinstance(position, dict)
                            and all(
                                isinstance(position.get(axis), (int, float))
                                and not isinstance(position.get(axis), bool)
                                for axis in ("x", "y", "z")
                            )
                            and is_uri(position.get("unit"))
                            and position.get("unit")
                            == point_properties.get(VAO_ONTOLOGY + "coordinateUnit")
                        )
                        if not coordinates_valid or not position_valid:
                            errors.append(
                                f"Listening point {point.get('id')!r} lacks valid coordinate/position metadata."
                            )
                        listening_audio = [
                            assets_by_id[target]
                            for target in active_targets(
                                point.get("id"), VAO_ONTOLOGY + "usesMedia"
                            )
                            if target in assets_by_id
                            and SPATIAL_LISTENING_AUDIO
                            in assets_by_id[target].get("roles", [])
                            and str(
                                assets_by_id[target].get("mediaType", "")
                            ).startswith("audio/")
                        ]
                        if not listening_audio:
                            errors.append(
                                f"Listening point {point.get('id')!r} has no spatial-listening audio asset."
                            )

                elif capability == OFFLINE_ASSET_GROUPS:
                    validate_presents(
                        experience, {"instrument"}, "offline-asset-groups"
                    )
                    group_ids = active_targets(
                        identifier, VAO_ONTOLOGY + "offersAssetGroup"
                    )
                    groups = [
                        entities_by_id[target]
                        for target in group_ids
                        if target in entities_by_id
                        and entities_by_id[target].get("kind") == "assetGroup"
                    ]
                    if not groups:
                        errors.append(
                            f"Offline experience {identifier!r} has no asset group."
                        )
                    for group in groups:
                        group_properties = (
                            group.get("properties")
                            if isinstance(group.get("properties"), dict)
                            else {}
                        )
                        policy = group_properties.get(VAO_ONTOLOGY + "assetGroupPolicy")
                        if not (
                            isinstance(policy, dict)
                            and policy.get("availability")
                            in {"offline-optional", "offline-required"}
                            and policy.get("selection") in {"independent", "exclusive"}
                            and isinstance(policy.get("defaultSelected"), bool)
                        ):
                            errors.append(
                                f"Asset group {group.get('id')!r} has an invalid assetGroupPolicy."
                            )
                        members = active_targets(
                            group.get("id"), VAO_ONTOLOGY + "includesAsset"
                        )
                        if not members:
                            errors.append(
                                f"Asset group {group.get('id')!r} includes no assets."
                            )
                        for target in members:
                            if target not in assets_by_id:
                                errors.append(
                                    f"Asset group {group.get('id')!r} includes non-asset target {target!r}."
                                )

                elif capability == REPLACEABLE_PERFORMANCE_MEDIA:
                    validate_presents(
                        experience, {"instrument"}, "replaceable-performance-media"
                    )
                    if properties.get(VAO_ONTOLOGY + "selectionPolicy") != "exclusive":
                        errors.append(
                            f"Replaceable-media experience {identifier!r} must use exclusive selection."
                        )

                    configuration_ids = active_targets(
                        identifier, VAO_ONTOLOGY + "offersConfiguration"
                    )
                    configurations = [
                        entities_by_id[target]
                        for target in configuration_ids
                        if target in entities_by_id
                        and entities_by_id[target].get("kind") == "configuration"
                    ]
                    if len(configurations) < 2:
                        errors.append(
                            f"Replaceable-media experience {identifier!r} requires at least two configurations."
                        )

                    carrier_ids: list[str] = []
                    performance_ids: set[str] = set()
                    for configuration in configurations:
                        carriers = [
                            target
                            for target in active_targets(
                                configuration.get("id"), VAO_ONTOLOGY + "usesCarrier"
                            )
                            if target in entities_by_id
                            and entities_by_id[target].get("kind") == "digitalObject"
                        ]
                        if len(carriers) != 1:
                            errors.append(
                                f"Replaceable-media configuration {configuration.get('id')!r} must use exactly one carrier."
                            )
                            continue
                        carrier_id = carriers[0]
                        carrier_ids.append(carrier_id)
                        labels = [
                            assets_by_id[target]
                            for target in active_targets(
                                carrier_id, VAO_ONTOLOGY + "hasLabelImage"
                            )
                            if target in assets_by_id
                            and CARRIER_LABEL_IMAGE
                            in assets_by_id[target].get("roles", [])
                            and str(
                                assets_by_id[target].get("mediaType", "")
                            ).startswith("image/")
                        ]
                        if not labels:
                            errors.append(
                                f"Replaceable-media carrier {carrier_id!r} has no label image."
                            )
                        carrier_performances = [
                            target
                            for target in active_targets(
                                carrier_id, VAO_ONTOLOGY + "hasPerformance"
                            )
                            if target in entities_by_id
                            and entities_by_id[target].get("kind") == "performance"
                        ]
                        if not carrier_performances:
                            errors.append(
                                f"Replaceable-media carrier {carrier_id!r} has no performance."
                            )
                        performance_ids.update(carrier_performances)

                    if len(carrier_ids) != len(set(carrier_ids)):
                        errors.append(
                            "Replaceable-media configurations must resolve distinct carriers."
                        )

                    for performance_id in sorted(performance_ids):
                        performance = entities_by_id[performance_id]
                        performance_properties = (
                            performance.get("properties")
                            if isinstance(performance.get("properties"), dict)
                            else {}
                        )
                        clock = performance_properties.get(
                            VAO_ONTOLOGY + "timelineClock"
                        )
                        if not (
                            isinstance(clock, dict)
                            and is_uri(clock.get("timeUnit"))
                            and isinstance(clock.get("duration"), (int, float))
                            and not isinstance(clock.get("duration"), bool)
                            and clock["duration"] > 0
                            and (
                                "offset" not in clock
                                or (
                                    isinstance(clock.get("offset"), (int, float))
                                    and not isinstance(clock.get("offset"), bool)
                                    and clock["offset"] >= 0
                                )
                            )
                        ):
                            errors.append(
                                f"Replaceable-media performance {performance_id!r} has an invalid timelineClock."
                            )
                        transport = performance_properties.get(
                            VAO_ONTOLOGY + "transportPolicy"
                        )
                        if not (
                            isinstance(transport, dict)
                            and set(transport)
                            == {"masterClock", "start", "pause", "stop", "seek"}
                            and transport.get("masterClock") == "audio"
                            and transport.get("start") == "explicit"
                            and transport.get("pause") == "hold"
                            and transport.get("stop") == "reset"
                            and transport.get("seek") in {"allowed", "forbidden"}
                        ):
                            errors.append(
                                f"Replaceable-media performance {performance_id!r} has an invalid transportPolicy."
                            )
                        media = [
                            assets_by_id[target]
                            for target in active_targets(
                                performance_id, VAO_ONTOLOGY + "usesMedia"
                            )
                            if target in assets_by_id
                            and PERFORMANCE_MEDIA
                            in assets_by_id[target].get("roles", [])
                            and str(
                                assets_by_id[target].get("mediaType", "")
                            ).startswith("audio/")
                        ]
                        if not media:
                            errors.append(
                                f"Replaceable-media performance {performance_id!r} has no audio master media."
                            )
                        target_ids = set(
                            active_targets(performance_id, VAO_ONTOLOGY + "targets")
                        )
                        if not target_ids or any(
                            target not in entities_by_id for target in target_ids
                        ):
                            errors.append(
                                f"Replaceable-media performance {performance_id!r} has invalid target entities."
                            )
                        animations = [
                            assets_by_id[target]
                            for target in active_targets(
                                performance_id, VAO_ONTOLOGY + "drivesAnimation"
                            )
                            if target in assets_by_id
                            and ANIMATION in assets_by_id[target].get("roles", [])
                        ]
                        if not animations:
                            errors.append(
                                f"Replaceable-media performance {performance_id!r} has no animation asset."
                            )
                        for animation in animations:
                            animation_properties = (
                                animation.get("properties")
                                if isinstance(animation.get("properties"), dict)
                                else {}
                            )
                            bindings = animation_properties.get(
                                VAO_ONTOLOGY + "animationBindings"
                            )
                            layers = (
                                bindings.get("layers")
                                if isinstance(bindings, dict)
                                else None
                            )
                            bindings_valid = (
                                isinstance(bindings, dict)
                                and set(bindings) == {"blendPolicy", "layers"}
                                and bindings.get("blendPolicy")
                                in {"parallel", "ordered"}
                                and isinstance(layers, list)
                                and bool(layers)
                            )
                            if bindings_valid:
                                for layer in layers:
                                    layer_targets = (
                                        layer.get("targetEntityIds")
                                        if isinstance(layer, dict)
                                        else None
                                    )
                                    if not (
                                        isinstance(layer, dict)
                                        and set(layer) == {"clip", "targetEntityIds"}
                                        and isinstance(layer.get("clip"), str)
                                        and bool(layer["clip"].strip())
                                        and isinstance(layer_targets, list)
                                        and bool(layer_targets)
                                        and all(
                                            is_uri(target)
                                            and target in entities_by_id
                                            and target in target_ids
                                            for target in layer_targets
                                        )
                                    ):
                                        bindings_valid = False
                                        break
                            if not bindings_valid:
                                errors.append(
                                    f"Replaceable-media animation {animation.get('id')!r} has invalid animationBindings."
                                )

                    interaction_ids = active_targets(
                        identifier, VAO_ONTOLOGY + "hasInteraction"
                    )
                    interactions = [
                        entities_by_id[target]
                        for target in interaction_ids
                        if target in entities_by_id
                        and entities_by_id[target].get("kind") == "interaction"
                    ]
                    if not interactions:
                        errors.append(
                            f"Replaceable-media experience {identifier!r} has no declarative interaction."
                        )
                    allowed_actions = {
                        "select",
                        "install",
                        "eject",
                        "play",
                        "pause",
                        "stop",
                        "seek",
                        "restart",
                    }
                    required_actions = {"select", "install", "eject", "play", "stop"}
                    found_actions: set[str] = set()
                    expected_target_kinds = {
                        "select": {"configuration"},
                        "install": {"digitalObject"},
                        "eject": {"digitalObject"},
                        "play": {"performance"},
                        "pause": {"performance"},
                        "stop": {"performance"},
                        "seek": {"performance"},
                        "restart": {"performance"},
                    }
                    for interaction in interactions:
                        interaction_properties = (
                            interaction.get("properties")
                            if isinstance(interaction.get("properties"), dict)
                            else {}
                        )
                        sequence = interaction_properties.get(
                            VAO_ONTOLOGY + "actionSequence"
                        )
                        if not isinstance(sequence, list) or not sequence:
                            errors.append(
                                f"Replaceable-media interaction {interaction.get('id')!r} has no actionSequence."
                            )
                            continue
                        for action_record in sequence:
                            action = (
                                action_record.get("action")
                                if isinstance(action_record, dict)
                                else None
                            )
                            target = (
                                action_record.get("targetId")
                                if isinstance(action_record, dict)
                                else None
                            )
                            if not (
                                isinstance(action_record, dict)
                                and set(action_record) == {"action", "targetId"}
                                and action in allowed_actions
                                and target in entities_by_id
                                and entities_by_id[target].get("kind")
                                in expected_target_kinds[action]
                            ):
                                errors.append(
                                    f"Replaceable-media interaction {interaction.get('id')!r} has a prohibited or invalid action."
                                )
                                continue
                            found_actions.add(action)
                    if not required_actions <= found_actions:
                        missing = ", ".join(sorted(required_actions - found_actions))
                        errors.append(
                            f"Replaceable-media action sequences are missing required actions: {missing}."
                        )

    if PRESERVATION_PROFILE in profile_ids:
        for asset in assets:
            if not isinstance(asset, dict):
                continue
            if not asset.get("originalFilename"):
                errors.append(
                    f"Preservation asset {asset.get('id')!r} has no originalFilename."
                )
            if not asset.get("createdAt"):
                errors.append(
                    f"Preservation asset {asset.get('id')!r} has no createdAt."
                )
            if (
                set(asset.get("roles", [])) & {ANALYSIS_RESULT, AUDIO_DERIVATIVE}
                and asset.get("id") not in generated_outputs
            ):
                errors.append(
                    f"Preservation derivative asset {asset.get('id')!r} is not a paradata output."
                )
        for index, record in enumerate(rights):
            if (
                isinstance(record, dict)
                and not str(record.get("accessCondition", "")).strip()
            ):
                errors.append(
                    f"Preservation rights record {index} has no access condition."
                )

    folded: dict[str, str] = {}
    for path in asset_paths:
        old = folded.setdefault(path.casefold(), path)
        if old != path:
            message = f"Payload paths collide when case-folded: {old!r} and {path!r}."
            if PRESERVATION_PROFILE in profile_ids:
                errors.append(message)
            else:
                warnings.append(message)

    return {
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "assetCount": len(assets),
        "verifiedBytes": verified_bytes,
        "formatVersion": manifest.get("formatVersion"),
        "id": manifest.get("id"),
        "claimedCapabilities": sorted(declared_capabilities),
        "supportedCapabilities": sorted(declared_capabilities & SUPPORTED_CAPABILITIES),
        "unsupportedCapabilities": sorted(
            declared_capabilities - SUPPORTED_CAPABILITIES
        ),
    }


def validate_workspace(path: Path) -> dict[str, Any]:
    errors: list[str] = []
    mimetype_path = path / "mimetype"
    if not mimetype_path.is_file() or mimetype_path.read_bytes() != MIMETYPE.encode(
        "utf-8"
    ):
        errors.append("Workspace mimetype is missing or invalid.")
    try:
        manifest = load_json(path / MANIFEST_NAME)
    except VAOError as exc:
        return {
            "valid": False,
            "errors": errors + [str(exc)],
            "warnings": [],
            "assetCount": 0,
            "verifiedBytes": 0,
        }
    payload_names = iter_payload_files(path)

    def reader(name: str) -> tuple[str, int]:
        return sha256_file(path / PurePosixPath(name))

    report = validate_manifest(
        manifest, payload_names=payload_names, payload_reader=reader
    )
    report["errors"] = errors + report["errors"]
    report["valid"] = not report["errors"]
    report["container"] = "workspace"
    return report


def validate_archive(path: Path) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    try:
        with zipfile.ZipFile(path, "r", allowZip64=True) as archive:
            infos = archive.infolist()
            if len(infos) > MAX_ENTRIES:
                errors.append(
                    f"Archive has {len(infos)} entries; local safety limit is {MAX_ENTRIES}."
                )
            names = [info.filename for info in infos]
            if len(names) != len(set(names)):
                errors.append("Archive contains duplicate entry paths.")
            if not infos or infos[0].filename != "mimetype":
                errors.append("mimetype must be the first archive entry.")
            elif infos[0].compress_type != zipfile.ZIP_STORED:
                errors.append("mimetype must be stored without compression.")
            for info in infos:
                if not safe_archive_path(info.filename.rstrip("/")):
                    errors.append(f"Unsafe archive path {info.filename!r}.")
                mode = info.external_attr >> 16
                if mode and stat.S_ISLNK(mode):
                    errors.append(f"Links are prohibited: {info.filename!r}.")
                if info.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
                    errors.append(
                        f"Unsupported compression method for {info.filename!r}."
                    )
                if info.file_size > MAX_ENTRY_BYTES:
                    errors.append(
                        f"Entry exceeds the local safety limit: {info.filename!r}."
                    )
            total = sum(info.file_size for info in infos)
            if total > MAX_TOTAL_BYTES:
                errors.append(
                    "Expanded archive exceeds the local total-size safety limit."
                )
            try:
                if archive.read("mimetype") != MIMETYPE.encode("utf-8"):
                    errors.append("mimetype content is invalid.")
            except KeyError:
                errors.append("Archive has no mimetype entry.")
            try:
                manifest_info = archive.getinfo(MANIFEST_NAME)
                if manifest_info.file_size > MAX_MANIFEST_BYTES:
                    errors.append("Manifest exceeds the local 64 MiB safety limit.")
                    manifest = {}
                else:
                    manifest = strict_json_loads(
                        archive.read(manifest_info).decode("utf-8")
                    )
                    if not isinstance(manifest, dict):
                        raise ValueError("manifest root is not an object")
            except (KeyError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
                errors.append(f"Cannot read {MANIFEST_NAME}: {exc}")
                manifest = {}

            payload_names = [
                info.filename
                for info in infos
                if not info.is_dir() and info.filename.startswith("payload/")
            ]
            unknown_roots = [
                info.filename
                for info in infos
                if not info.is_dir()
                and info.filename not in ("mimetype", MANIFEST_NAME)
                and not info.filename.startswith(("payload/", "META-INF/"))
            ]
            for name in unknown_roots:
                errors.append(f"Unknown root archive entry {name!r}.")

            def reader(name: str) -> tuple[str, int]:
                with archive.open(name, "r") as stream:
                    return sha256_stream(stream)

            semantic = validate_manifest(
                manifest, payload_names=payload_names, payload_reader=reader
            )
            errors.extend(semantic["errors"])
            warnings.extend(semantic["warnings"])
            semantic.update(
                {
                    "valid": not errors,
                    "errors": errors,
                    "warnings": warnings,
                    "container": "zip64"
                    if any(info.file_size >= 0xFFFFFFFF for info in infos)
                    else "zip",
                }
            )
            return semantic
    except (OSError, zipfile.BadZipFile, RuntimeError) as exc:
        return {
            "valid": False,
            "errors": [f"Cannot read VAO archive: {exc}"],
            "warnings": [],
            "assetCount": 0,
            "verifiedBytes": 0,
        }


def validate(path: Path) -> dict[str, Any]:
    if path.is_dir():
        return validate_workspace(path)
    return validate_archive(path)


def refresh_asset_metadata(workspace: Path, manifest: dict[str, Any]) -> None:
    for asset in manifest.get("assets", []):
        if not isinstance(asset, dict) or not safe_archive_path(
            str(asset.get("path", "")), payload=True
        ):
            continue
        path = workspace / PurePosixPath(asset["path"])
        if not path.is_file() or path.is_symlink():
            continue
        digest, size = sha256_file(path)
        asset["sha256"] = digest
        asset["byteSize"] = size
    manifest.setdefault("integrity", {})["algorithm"] = "sha256"
    manifest["integrity"]["assetCount"] = len(manifest.get("assets", []))
    manifest["integrity"]["totalPayloadBytes"] = sum(
        asset.get("byteSize", 0)
        for asset in manifest.get("assets", [])
        if isinstance(asset, dict)
    )
    manifest["modifiedAt"] = now()


def migrate_01_manifest(manifest: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Deterministically migrate the closed VAO 0.1 contract to VAO 0.2."""
    if not str(manifest.get("formatVersion", "")).startswith("0.1."):
        raise VAOError("The migration input must be a VAO 0.1.x manifest.")
    notes: list[str] = []
    migrated = json.loads(json.dumps(manifest))
    primary = migrated.pop("rootEntityId", None)
    if not is_uri(primary):
        raise VAOError("The VAO 0.1 rootEntityId is missing or invalid.")
    migrated["$schema"] = SCHEMA_URI
    migrated["@context"] = [
        CONTEXT_URI
        if value == "https://w3id.org/modavis/vao/0.1/context.jsonld"
        else value
        for value in migrated.get("@context", [])
    ]
    migrated["formatVersion"] = FORMAT_VERSION
    migrated["primaryEntityId"] = primary
    migrated["focusEntityIds"] = [primary]
    profile_map = {
        "https://w3id.org/modavis/vao/profile/core/0.1": CORE_PROFILE,
        "https://w3id.org/modavis/vao/profile/research/0.1": RESEARCH_PROFILE,
        "https://w3id.org/modavis/vao/profile/orgrec-capture/0.1": ORGREC_PROFILE,
        "https://w3id.org/modavis/vao/profile/playable/0.1": PLAYABLE_PROFILE,
        "https://w3id.org/modavis/vao/profile/spatial/0.1": SPATIAL_PROFILE,
        "https://w3id.org/modavis/vao/profile/experiential/0.1": EXPERIENTIAL_PROFILE,
        "https://w3id.org/modavis/vao/profile/preservation/0.1": PRESERVATION_PROFILE,
    }
    migrated["conformsTo"] = [
        profile_map.get(value, value) for value in migrated.get("conformsTo", [])
    ]
    for profile in migrated.get("profiles", []):
        if isinstance(profile, dict):
            profile["id"] = profile_map.get(profile.get("id"), profile.get("id"))
            if profile.get("id") in profile_map.values():
                profile["version"] = "0.2"
    binding = migrated.get("modavisBinding")
    if isinstance(binding, dict) and binding.get("mappingVersion") in {
        "vao-modavis-mapping/0.1",
        "vao-modavis-mapping/0.1.1",
        "vao-modavis-mapping/0.1.2",
    }:
        binding["mappingVersion"] = "vao-modavis-mapping/0.2.2"
        notes.append(
            "The MODAVIS mapping identifier was advanced; review the still-development ontology binding."
        )

    if SPATIAL_PROFILE in {
        profile.get("id")
        for profile in migrated.get("profiles", [])
        if isinstance(profile, dict)
    }:
        frames: list[dict[str, Any]] = []
        poses: list[dict[str, Any]] = []
        regions = [
            entity
            for entity in migrated.get("entities", [])
            if isinstance(entity, dict) and entity.get("kind") == "spatialRegion"
        ]
        for index, region in enumerate(regions):
            properties = (
                region.get("properties")
                if isinstance(region.get("properties"), dict)
                else {}
            )
            frame_id = f"urn:vao:migration:frame:{index}"
            unit = properties.get(
                VAO_ONTOLOGY + "coordinateUnit", "http://qudt.org/vocab/unit/M"
            )
            handedness = properties.get(VAO_ONTOLOGY + "handedness", "right")
            up = str(properties.get(VAO_ONTOLOGY + "upAxis", "Y"))
            frames.append(
                {
                    "id": frame_id,
                    "dimension": 3,
                    "coordinateType": "cartesian",
                    "unit": unit,
                    "handedness": handedness
                    if handedness in {"left", "right"}
                    else "right",
                    "upAxis": up if up.startswith(("+", "-")) else "+" + up,
                    "forwardAxis": "-Z",
                    "notes": "Migrated from VAO 0.1 spatialRegion properties; forward axis requires curatorial review.",
                }
            )
            position = properties.get(VAO_ONTOLOGY + "position")
            if isinstance(position, dict) and all(
                isinstance(position.get(axis), (int, float)) for axis in ("x", "y", "z")
            ):
                poses.append(
                    {
                        "id": f"urn:vao:migration:pose:{index}",
                        "subjectId": region.get("id"),
                        "frameId": frame_id,
                        "position": [position["x"], position["y"], position["z"]],
                        "interpolation": "none",
                    }
                )
            else:
                notes.append(
                    f"Spatial region {region.get('id')!r} has no migratable position; add a pose or geometry binding."
                )
        migrated["acoustics"] = {
            "coordinateFrames": frames,
            "poses": poses,
            "geometryBindings": [],
            "materialModels": [],
            "responseSets": [],
            "metricSets": [],
            "audioScenes": [],
            "renderConfigurations": [],
        }
    migrated["modifiedAt"] = now()
    migrated["revision"] = int(migrated.get("revision", 0)) + 1
    return migrated, notes


def command_migrate(args: argparse.Namespace) -> int:
    source = Path(args.source)
    destination = Path(args.destination)
    if (
        source.is_symlink()
        or not source.is_dir()
        or not (source / MANIFEST_NAME).is_file()
    ):
        raise VAOError("Migration source must be an unpacked VAO 0.1 workspace.")
    if destination.exists():
        raise VAOError(f"Migration destination already exists: {destination}")
    try:
        destination.resolve(strict=False).relative_to(source.resolve())
    except ValueError:
        pass
    else:
        raise VAOError("Migration destination must not be inside the source workspace.")

    entry_count = 0
    total_bytes = 0
    for directory, child_directories, filenames in os.walk(source, followlinks=False):
        for name in child_directories + filenames:
            candidate = Path(directory) / name
            metadata = candidate.lstat()
            if stat.S_ISLNK(metadata.st_mode) or not (
                stat.S_ISDIR(metadata.st_mode) or stat.S_ISREG(metadata.st_mode)
            ):
                raise VAOError(
                    f"Migration source contains a prohibited link or special file: {candidate}"
                )
            if stat.S_ISREG(metadata.st_mode):
                entry_count += 1
                total_bytes += metadata.st_size
                if metadata.st_size > MAX_ENTRY_BYTES:
                    raise VAOError(
                        f"Migration source entry exceeds the local safety limit: {candidate}"
                    )
    if entry_count > MAX_ENTRIES or total_bytes > MAX_TOTAL_BYTES:
        raise VAOError(
            "Migration source exceeds local entry-count or total-size safety limits."
        )

    source_manifest_path = source / MANIFEST_NAME
    if source_manifest_path.stat().st_size > MAX_MANIFEST_BYTES:
        raise VAOError(
            "Migration source manifest exceeds the local 64 MiB safety limit."
        )
    source_manifest_bytes = source_manifest_path.read_bytes()
    source_manifest_digest = hashlib.sha256(source_manifest_bytes).hexdigest()
    source_manifest = load_json(source_manifest_path)
    migrated, notes = migrate_01_manifest(source_manifest)
    shutil.copytree(source, destination, symlinks=False)
    try:
        snapshot_relative = (
            f"payload/migration/source-manifest-{source_manifest_digest[:16]}.json"
        )
        snapshot_path = destination / PurePosixPath(snapshot_relative)
        snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        snapshot_path.write_bytes(source_manifest_bytes)
        snapshot_asset_id = asset_id_for(snapshot_relative)
        if snapshot_asset_id in manifest_ids(migrated):
            raise VAOError(
                "Migration source-manifest asset identifier collides with an existing record."
            )
        migrated.setdefault("assets", []).append(
            {
                "id": snapshot_asset_id,
                "path": snapshot_relative,
                "mediaType": "application/json",
                "byteSize": len(source_manifest_bytes),
                "sha256": source_manifest_digest,
                "roles": [SOURCE_EVIDENCE],
                "representationStatus": AUTHORED_REPRESENTATION,
                "aboutEntityIds": [migrated["primaryEntityId"]],
                "originalFilename": MANIFEST_NAME,
                "createdAt": source_manifest.get(
                    "modifiedAt",
                    source_manifest.get("createdAt", migrated["modifiedAt"]),
                ),
                "encoding": "UTF-8",
                "properties": {
                    VAO_ONTOLOGY + "sourceFormatVersion": source_manifest.get(
                        "formatVersion"
                    ),
                    VAO_ONTOLOGY + "sourceManifestSHA256": source_manifest_digest,
                },
            }
        )
        migration_activity_id = f"urn:vao:migration:0.1-to-0.2:{source_manifest_digest}"
        if migration_activity_id in manifest_ids(migrated):
            raise VAOError(
                "Migration activity identifier collides with an existing record."
            )
        migrated.setdefault("paradata", []).append(
            {
                "id": migration_activity_id,
                "activityType": VAO_ONTOLOGY + "MigrationActivity",
                "startedAt": migrated["modifiedAt"],
                "endedAt": migrated["modifiedAt"],
                "software": {
                    "name": "VAOM",
                    "version": FORMAT_VERSION,
                    "uri": "https://w3id.org/modavis/vao/tools/vaom",
                },
                "inputIds": [snapshot_asset_id],
                "outputIds": [],
                "parameters": {
                    VAO_ONTOLOGY + "sourceFormatVersion": source_manifest.get(
                        "formatVersion"
                    ),
                    VAO_ONTOLOGY + "targetFormatVersion": FORMAT_VERSION,
                    VAO_ONTOLOGY + "sourceManifestSHA256": source_manifest_digest,
                    VAO_ONTOLOGY + "mappingVersion": migrated.get(
                        "modavisBinding", {}
                    ).get("mappingVersion"),
                    VAO_ONTOLOGY + "migrationNotes": notes,
                },
                "notes": "Evidence-preserving copy migration. The source workspace was not modified; review reported migration notes before release.",
            }
        )
        (destination / "mimetype").write_bytes(MIMETYPE.encode("utf-8"))
        refresh_asset_metadata(destination, migrated)
        write_json(destination / MANIFEST_NAME, migrated)
        report = validate_workspace(destination)
    except Exception:
        shutil.rmtree(destination, ignore_errors=True)
        raise
    for note in notes:
        print(f"migration note: {note}", file=sys.stderr)
    print(destination)
    if not report["valid"]:
        print_report(report, False)
        return 1
    return 0


def command_init(args: argparse.Namespace) -> int:
    if not is_uri(args.entity_type):
        raise VAOError("--entity-type must be an absolute HTTP(S) IRI or URN.")
    if args.classification is not None and not is_uri(args.classification):
        raise VAOError("--classification must be an absolute HTTP(S) IRI or URN.")
    workspace = Path(args.workspace)
    if workspace.exists():
        raise VAOError(f"Destination already exists: {workspace}")
    root_id = f"urn:uuid:{uuid.uuid4()}"
    vao_id = f"urn:uuid:{uuid.uuid4()}"
    created = now()
    payload_path = "payload/provenance/README.txt"
    asset_id = asset_id_for(payload_path)
    workspace.mkdir(parents=True)
    try:
        (workspace / "payload/provenance").mkdir(parents=True)
        (workspace / "mimetype").write_bytes(MIMETYPE.encode("utf-8"))
        note = (
            "This file was created by VAOM as explicit source evidence for the initial VAO workspace.\n"
            "Replace or supplement it with documented instrument assets before publication.\n"
        )
        (workspace / payload_path).write_text(note, encoding="utf-8")
        digest, size = sha256_file(workspace / payload_path)
        manifest = {
            "$schema": SCHEMA_URI,
            "@context": [CONTEXT_URI],
            "type": "VirtualAcousticObject",
            "formatVersion": FORMAT_VERSION,
            "id": vao_id,
            "revision": 1,
            "createdAt": created,
            "modifiedAt": created,
            "title": {"und": args.title},
            "description": {"und": "Virtual Acoustic Object 0.2 authoring workspace."},
            "conformsTo": [CORE_PROFILE],
            "profiles": [
                {
                    "id": CORE_PROFILE,
                    "version": "0.2",
                    "requiredCapabilities": CORE_CAPABILITIES,
                }
            ],
            "modavisBinding": {
                "ontologyIRI": "https://w3id.org/modavis/ontology",
                "ontologyVersion": "0.2.0-dev",
                "ontologyStatus": "development",
                "mappingVersion": "vao-modavis-mapping/0.2.2",
                "notes": "The bound ontology version is a development contract; pin a released mapping before publication.",
            },
            "primaryEntityId": root_id,
            "focusEntityIds": [root_id],
            "entities": [
                {
                    "id": root_id,
                    "kind": args.entity_kind,
                    "types": [args.entity_type],
                    "labels": {"und": args.title},
                    "classifications": (
                        [{"id": args.classification}] if args.classification else []
                    ),
                    "externalIdentifiers": [],
                    "properties": {},
                }
            ],
            "relations": [
                {
                    "id": relation_id(),
                    "subjectId": root_id,
                    "predicate": "https://w3id.org/modavis/vao/ontology#hasRepresentation",
                    "objectId": asset_id,
                    "status": "asserted",
                }
            ],
            "assets": [
                {
                    "id": asset_id,
                    "path": payload_path,
                    "mediaType": "text/plain",
                    "byteSize": size,
                    "sha256": digest,
                    "roles": [SOURCE_EVIDENCE],
                    "representationStatus": AUTHORED_REPRESENTATION,
                    "aboutEntityIds": [root_id],
                    "originalFilename": "README.txt",
                    "createdAt": created,
                    "encoding": "UTF-8",
                    "properties": {},
                }
            ],
            "paradata": [],
            "analyses": [],
            "rights": [
                {
                    "appliesToIds": [vao_id],
                    "statement": {
                        "und": "Rights information has not been supplied; no permission is inferred."
                    },
                    "accessCondition": "Unspecified",
                }
            ],
            "integrity": {
                "algorithm": "sha256",
                "assetCount": 1,
                "totalPayloadBytes": size,
            },
            "extensions": {},
        }
        write_json(workspace / MANIFEST_NAME, manifest)
    except Exception:
        shutil.rmtree(workspace, ignore_errors=True)
        raise
    print(root_id)
    return 0


def command_add(args: argparse.Namespace) -> int:
    workspace = Path(args.workspace)
    source = Path(args.source)
    if not workspace.is_dir() or not source.is_file():
        raise VAOError("Workspace or source file does not exist.")
    manifest = load_json(workspace / MANIFEST_NAME)
    about = args.about or manifest.get("primaryEntityId")
    entity_ids = {
        entity.get("id")
        for entity in manifest.get("entities", [])
        if isinstance(entity, dict)
    }
    if about not in entity_ids:
        raise VAOError(f"Unknown subject entity: {about}")
    if not is_uri(args.role) or not is_uri(args.representation_status):
        raise VAOError("Asset role and representation status must be absolute IRIs.")
    safe_name = source.name.replace("\\", "_").replace("/", "_")
    relative = f"payload/assets/{safe_name}"
    existing = {
        asset.get("path")
        for asset in manifest.get("assets", [])
        if isinstance(asset, dict)
    }
    counter = 2
    while relative in existing or (workspace / relative).exists():
        relative = f"payload/assets/{source.stem}-{counter}{source.suffix}"
        counter += 1
    target = workspace / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    digest, size = sha256_file(target)
    identifier = asset_id_for(relative)
    media_type = (
        args.media_type
        or mimetypes.guess_type(source.name)[0]
        or "application/octet-stream"
    )
    manifest.setdefault("assets", []).append(
        {
            "id": identifier,
            "path": relative,
            "mediaType": media_type,
            "byteSize": size,
            "sha256": digest,
            "roles": [args.role],
            "representationStatus": args.representation_status,
            "aboutEntityIds": [about],
            "originalFilename": source.name,
            "createdAt": now(),
            "properties": {},
        }
    )
    manifest.setdefault("relations", []).append(
        {
            "id": relation_id(),
            "subjectId": about,
            "predicate": "https://w3id.org/modavis/vao/ontology#hasRepresentation",
            "objectId": identifier,
            "status": "asserted",
        }
    )
    manifest["revision"] = int(manifest.get("revision", 0)) + 1
    refresh_asset_metadata(workspace, manifest)
    write_json(workspace / MANIFEST_NAME, manifest)
    report = validate_workspace(workspace)
    if not report["valid"]:
        raise VAOError(
            "Asset was added, but workspace validation failed: "
            + "; ".join(report["errors"][:3])
        )
    print(identifier)
    return 0


def manifest_ids(manifest: dict[str, Any]) -> set[str]:
    result: set[str] = set()
    for registry in ("entities", "relations", "assets", "paradata", "analyses"):
        for record in manifest.get(registry, []):
            if isinstance(record, dict) and isinstance(record.get("id"), str):
                result.add(record["id"])
    return result


def save_workspace_manifest(workspace: Path, manifest: dict[str, Any]) -> None:
    manifest["revision"] = int(manifest.get("revision", 0)) + 1
    manifest["modifiedAt"] = now()
    payload_names = iter_payload_files(workspace)

    def reader(name: str) -> tuple[str, int]:
        return sha256_file(workspace / PurePosixPath(name))

    report = validate_manifest(
        manifest, payload_names=payload_names, payload_reader=reader
    )
    if not report["valid"]:
        raise VAOError(
            "Change would invalidate the workspace: " + "; ".join(report["errors"][:5])
        )
    write_json(workspace / MANIFEST_NAME, manifest)


def command_entity(args: argparse.Namespace) -> int:
    workspace = Path(args.workspace)
    if not workspace.is_dir():
        raise VAOError(f"Workspace does not exist: {workspace}")
    manifest = load_json(workspace / MANIFEST_NAME)
    identifier = args.id or f"urn:uuid:{uuid.uuid4()}"
    if not is_uri(identifier):
        raise VAOError("Entity id must be an absolute HTTP(S) IRI or URN.")
    if identifier in manifest_ids(manifest):
        raise VAOError(f"Identifier is already used: {identifier}")
    if any(not value.startswith(("http://", "https://")) for value in args.types):
        raise VAOError("Entity types must be absolute HTTP(S) ontology IRIs.")
    entity: dict[str, Any] = {
        "id": identifier,
        "kind": args.kind,
        "types": args.types,
        "labels": {args.language: args.label},
        "externalIdentifiers": [],
        "properties": {},
    }
    if args.classification:
        entity["classifications"] = [{"id": value} for value in args.classification]
    manifest.setdefault("entities", []).append(entity)
    save_workspace_manifest(workspace, manifest)
    print(identifier)
    return 0


def command_link(args: argparse.Namespace) -> int:
    workspace = Path(args.workspace)
    if not workspace.is_dir():
        raise VAOError(f"Workspace does not exist: {workspace}")
    manifest = load_json(workspace / MANIFEST_NAME)
    known = manifest_ids(manifest)
    if args.subject not in known:
        raise VAOError(f"Unknown local subject: {args.subject}")
    if not args.predicate.startswith(("http://", "https://")):
        raise VAOError("Predicate must be an absolute HTTP(S) ontology IRI.")
    relation: dict[str, Any] = {
        "id": args.id or relation_id(),
        "subjectId": args.subject,
        "predicate": args.predicate,
        "status": args.status,
    }
    if relation["id"] in known or not is_uri(relation["id"]):
        raise VAOError("Relation id is invalid or already used.")
    if args.object is not None:
        if not is_uri(args.object):
            raise VAOError("Object must be an absolute HTTP(S) IRI or URN.")
        relation["objectId"] = args.object
    else:
        literal: dict[str, Any] = {"value": args.value}
        if args.datatype:
            literal["datatype"] = args.datatype
        if args.language:
            literal["language"] = args.language
        if args.unit:
            literal["unit"] = args.unit
        relation["literal"] = literal
    if args.evidence:
        relation["evidenceIds"] = args.evidence
    if args.generated_by:
        relation["generatedByIds"] = args.generated_by
    manifest.setdefault("relations", []).append(relation)
    save_workspace_manifest(workspace, manifest)
    print(relation["id"])
    return 0


def zip_info(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_STORED
    info.create_system = 3
    info.external_attr = (stat.S_IFREG | 0o644) << 16
    info.flag_bits |= 0x800
    return info


def command_pack(args: argparse.Namespace) -> int:
    workspace = Path(args.workspace)
    output = Path(args.output)
    if not workspace.is_dir():
        raise VAOError(f"Workspace does not exist: {workspace}")
    if output.exists():
        raise VAOError(f"Output already exists: {output}")
    manifest = load_json(workspace / MANIFEST_NAME)
    refresh_asset_metadata(workspace, manifest)
    write_json(workspace / MANIFEST_NAME, manifest)
    report = validate_workspace(workspace)
    if not report["valid"]:
        raise VAOError(
            "Workspace validation failed: " + "; ".join(report["errors"][:5])
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(
            output, "x", compression=zipfile.ZIP_STORED, allowZip64=True
        ) as archive:
            archive.writestr(zip_info("mimetype"), MIMETYPE.encode("utf-8"))
            archive.writestr(zip_info(MANIFEST_NAME), json_bytes(manifest))
            for asset in sorted(manifest["assets"], key=lambda value: value["path"]):
                archive.write(
                    workspace / PurePosixPath(asset["path"]),
                    asset["path"],
                    compress_type=zipfile.ZIP_STORED,
                )
            archive.comment = b"VAO/0.2"
        final_report = validate_archive(output)
        if not final_report["valid"]:
            output.unlink(missing_ok=True)
            raise VAOError(
                "Created archive failed validation: "
                + "; ".join(final_report["errors"][:5])
            )
    except Exception:
        output.unlink(missing_ok=True)
        raise
    print(output)
    return 0


def command_unpack(args: argparse.Namespace) -> int:
    source = Path(args.source)
    destination = Path(args.destination)
    report = validate_archive(source)
    if not report["valid"]:
        raise VAOError("VAO validation failed: " + "; ".join(report["errors"][:5]))
    if destination.exists():
        if not args.force:
            raise VAOError(f"Destination already exists: {destination}")
        if destination.is_symlink() or not destination.is_dir():
            raise VAOError("--force accepts only an existing ordinary directory.")
        shutil.rmtree(destination)
    destination.mkdir(parents=True)
    try:
        with zipfile.ZipFile(source, "r", allowZip64=True) as archive:
            for info in archive.infolist():
                if info.is_dir():
                    continue
                target = destination.joinpath(*PurePosixPath(info.filename).parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                with (
                    archive.open(info, "r") as input_stream,
                    target.open("xb") as output_stream,
                ):
                    shutil.copyfileobj(input_stream, output_stream, length=CHUNK)
    except Exception:
        shutil.rmtree(destination, ignore_errors=True)
        raise
    print(destination)
    return 0


def print_report(report: dict[str, Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True))
        return
    state = "VALID" if report.get("valid") else "INVALID"
    print(
        f"{state}: VAO {report.get('formatVersion', 'unknown')} {report.get('id', '')}".rstrip()
    )
    if report.get("formatVersion") == "0.3.3":
        print(
            f"Logical assets: {report.get('logicalAssetCount', 0)}; realizations: {report.get('realizationCount', 0)}; verified bytes: {report.get('verifiedBytes', 0)}"
        )
    else:
        print(
            f"Assets: {report.get('assetCount', 0)}; verified bytes: {report.get('verifiedBytes', 0)}"
        )
    for warning in report.get("warnings", []):
        print(f"warning: {warning}")
    for error in report.get("errors", []):
        print(f"error: {error}")


def command_validate(args: argparse.Namespace) -> int:
    path = Path(args.path)
    try:
        import vao03

        if vao03.detect_version(path) == vao03.FORMAT_VERSION:
            report = vao03.validate(path)
            print_report(report, args.json)
            return 0 if report["valid"] else 1
    except ImportError:
        pass
    report = validate(path)
    print_report(report, args.json)
    return 0 if report["valid"] else 1


def command_inspect(args: argparse.Namespace) -> int:
    path = Path(args.path)
    try:
        import vao03

        if vao03.detect_version(path) == vao03.FORMAT_VERSION:
            report = vao03.validate(path)
            manifest = vao03.load_json(path / MANIFEST_NAME)[0] if path.is_dir() else {}
            if not path.is_dir():
                with zipfile.ZipFile(path, "r", allowZip64=True) as archive:
                    manifest = vao03.strict_json_bytes(
                        archive.read(MANIFEST_NAME), MANIFEST_NAME
                    )
            summary = {
                "validation": report,
                "title": manifest.get("title"),
                "primaryEntityId": manifest.get("primaryEntityId"),
                "profiles": [
                    p.get("id")
                    for p in manifest.get("profiles", [])
                    if isinstance(p, dict)
                ],
                "materializableProfiles": [
                    p.get("id")
                    for p in manifest.get("materializableProfiles", [])
                    if isinstance(p, dict)
                ],
                "logicalAssetCount": len(manifest.get("logicalAssets", [])),
                "realizationCount": len(manifest.get("realizations", [])),
                "distributionCount": len(manifest.get("distributions", [])),
                "assetGroupCount": len(manifest.get("assetGroups", [])),
            }
            if args.json:
                print(json.dumps(summary, indent=2, ensure_ascii=False, sort_keys=True))
            else:
                print_report(report, False)
                print(f"Title: {manifest.get('title', {})}")
                print(
                    f"Logical assets: {summary['logicalAssetCount']}; realizations: {summary['realizationCount']}; distributions: {summary['distributionCount']}; groups: {summary['assetGroupCount']}"
                )
                print("Embedded profiles: " + ", ".join(summary["profiles"]))
                print(
                    "Materializable profiles: "
                    + ", ".join(summary["materializableProfiles"])
                )
            return 0 if report["valid"] else 1
    except ImportError:
        pass
    report = validate(path)
    manifest: dict[str, Any] = {}
    if path.is_dir():
        try:
            manifest = load_json(path / MANIFEST_NAME)
        except VAOError:
            pass
    else:
        try:
            with zipfile.ZipFile(path, "r", allowZip64=True) as archive:
                manifest = strict_json_loads(
                    archive.read(MANIFEST_NAME).decode("utf-8")
                )
        except Exception:
            pass
    summary = {
        "validation": report,
        "title": manifest.get("title"),
        "primaryEntityId": manifest.get("primaryEntityId"),
        "focusEntityIds": manifest.get("focusEntityIds"),
        "profiles": [
            profile.get("id")
            for profile in manifest.get("profiles", [])
            if isinstance(profile, dict)
        ],
        "entityCount": len(manifest.get("entities", [])),
        "relationCount": len(manifest.get("relations", [])),
        "paradataCount": len(manifest.get("paradata", [])),
        "analysisCount": len(manifest.get("analyses", [])),
        "mediaTypes": sorted(
            {
                asset.get("mediaType")
                for asset in manifest.get("assets", [])
                if isinstance(asset, dict) and asset.get("mediaType")
            }
        ),
    }
    if args.json:
        print(json.dumps(summary, indent=2, ensure_ascii=False, sort_keys=True))
    else:
        print_report(report, False)
        print(f"Title: {manifest.get('title', {})}")
        print(
            f"Entities: {summary['entityCount']}; relations: {summary['relationCount']}; paradata: {summary['paradataCount']}; analyses: {summary['analysisCount']}"
        )
        print("Profiles: " + ", ".join(summary["profiles"]))
        print("Media types: " + ", ".join(summary["mediaTypes"]))
    return 0 if report["valid"] else 1


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        prog="vaom",
        description="Virtual Acoustic Object Manager (VAO 0.2 compatibility and VAO 0.3)",
    )
    result.add_argument(
        "--version",
        action="version",
        version="VAOM 0.3.3 (with VAO 0.2.2 compatibility)",
    )
    subcommands = result.add_subparsers(dest="command", required=True)

    init = subcommands.add_parser("init", help="create a VAO authoring workspace")
    init.add_argument("workspace")
    init.add_argument("--title", required=True)
    init.add_argument(
        "--entity-kind",
        default="instrument",
        help="primary entity kind (default: instrument)",
    )
    init.add_argument(
        "--entity-type",
        default=MUSICAL_INSTRUMENT,
        help="primary entity ontology class IRI",
    )
    init.add_argument(
        "--classification", help="optional primary entity classification IRI"
    )
    init.set_defaults(function=command_init)

    add = subcommands.add_parser("add", help="copy, index, and link an asset")
    add.add_argument("workspace")
    add.add_argument("source")
    add.add_argument(
        "--role", default=SOURCE_EVIDENCE, help="absolute VAO asset-role URI"
    )
    add.add_argument(
        "--representation-status",
        required=True,
        help="absolute representation-status concept IRI",
    )
    add.add_argument(
        "--about", help="subject entity id; defaults to the primary entity"
    )
    add.add_argument("--media-type")
    add.set_defaults(function=command_add)

    entity = subcommands.add_parser("entity", help="add a typed node to the VAO graph")
    entity.add_argument("workspace")
    entity.add_argument("--label", required=True)
    entity.add_argument(
        "--kind",
        required=True,
        choices=[
            "instrument",
            "component",
            "componentCollection",
            "configuration",
            "state",
            "performance",
            "event",
            "activity",
            "agent",
            "place",
            "building",
            "storey",
            "space",
            "zone",
            "boundary",
            "opening",
            "material",
            "source",
            "acousticEmitter",
            "acousticReceiver",
            "receiverArray",
            "coordinateFrame",
            "acousticResponse",
            "audioScene",
            "renderConfiguration",
            "sensor",
            "equipment",
            "sourceSnapshot",
            "sourceFragment",
            "assertion",
            "evidenceSupport",
            "annotation",
            "digitalObject",
            "measurement",
            "analysis",
            "parameterSet",
            "spatialRegion",
            "interaction",
            "experience",
            "assetGroup",
            "loopPointSet",
            "signalRegion",
            "other",
        ],
    )
    entity.add_argument(
        "--type",
        dest="types",
        action="append",
        required=True,
        help="ontology class IRI; repeatable",
    )
    entity.add_argument(
        "--classification",
        action="append",
        help="classification concept IRI; repeatable",
    )
    entity.add_argument("--language", default="und")
    entity.add_argument(
        "--id", help="absolute IRI or URN; a UUID URN is generated by default"
    )
    entity.set_defaults(function=command_entity)

    link = subcommands.add_parser("link", help="add an evidence-capable graph relation")
    link.add_argument("workspace")
    link.add_argument("subject")
    link.add_argument("predicate")
    target = link.add_mutually_exclusive_group(required=True)
    target.add_argument("--object", help="resource IRI or URN")
    target.add_argument("--value", help="literal string value")
    link.add_argument("--datatype", help="literal datatype IRI")
    link.add_argument("--language", help="literal language tag")
    link.add_argument("--unit", help="literal unit IRI")
    link.add_argument(
        "--status",
        choices=["asserted", "accepted", "rejected", "superseded", "inferred"],
        default="asserted",
    )
    link.add_argument(
        "--evidence", action="append", help="local evidence id; repeatable"
    )
    link.add_argument(
        "--generated-by", action="append", help="local activity id; repeatable"
    )
    link.add_argument(
        "--id", help="relation IRI or URN; a UUID URN is generated by default"
    )
    link.set_defaults(function=command_link)

    validate_command = subcommands.add_parser(
        "validate", help="validate a VAO workspace or archive"
    )
    validate_command.add_argument("path")
    validate_command.add_argument("--json", action="store_true")
    validate_command.set_defaults(function=command_validate)

    inspect = subcommands.add_parser("inspect", help="summarize and validate a VAO")
    inspect.add_argument("path")
    inspect.add_argument("--json", action="store_true")
    inspect.set_defaults(function=command_inspect)

    migrate = subcommands.add_parser(
        "migrate-0.1", help="copy and migrate an unpacked VAO 0.1 workspace to 0.2.2"
    )
    migrate.add_argument("source")
    migrate.add_argument("destination")
    migrate.set_defaults(function=command_migrate)

    pack = subcommands.add_parser("pack", help="build a validated .vao file")
    pack.add_argument("workspace")
    pack.add_argument("output")
    pack.set_defaults(function=command_pack)

    unpack = subcommands.add_parser(
        "unpack", help="validate and safely extract a .vao file"
    )
    unpack.add_argument("source")
    unpack.add_argument("destination")
    unpack.add_argument(
        "--force",
        action="store_true",
        help="replace an existing ordinary destination directory",
    )
    unpack.set_defaults(function=command_unpack)

    migrate_02 = subcommands.add_parser(
        "migrate-0.2",
        help="migrate a validated VAO 0.2.2 workspace to a new VAO 0.3.3 workspace",
    )
    migrate_02.add_argument("source")
    migrate_02.add_argument("destination")
    migrate_02.set_defaults(function=lambda args: _vao03_migrate(args))

    pack_03 = subcommands.add_parser(
        "pack-0.3", help="build a validated VAO 0.3 carrier"
    )
    pack_03.add_argument("workspace")
    pack_03.add_argument("output")
    pack_03.set_defaults(function=lambda args: _vao03_pack(args))

    receipt_03 = subcommands.add_parser(
        "receipt-0.3", help="write a verified local VAO 0.3 materialization receipt"
    )
    receipt_03.add_argument("workspace")
    receipt_03.add_argument("output")
    receipt_03.set_defaults(function=lambda args: _vao03_receipt(args))
    return result


def _vao03_migrate(args: argparse.Namespace) -> int:
    import vao03

    report = vao03.migrate_02(Path(args.source), Path(args.destination))
    print(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True))
    return 0


def _vao03_pack(args: argparse.Namespace) -> int:
    import vao03

    vao03.pack_workspace(Path(args.workspace), Path(args.output))
    print(args.output)
    return 0


def _vao03_receipt(args: argparse.Namespace) -> int:
    import vao03

    vao03.create_receipt(Path(args.workspace), Path(args.output))
    print(args.output)
    return 0


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        return int(args.function(args))
    except (VAOError, OSError, zipfile.BadZipFile, ValueError) as exc:
        print(f"vaom: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
