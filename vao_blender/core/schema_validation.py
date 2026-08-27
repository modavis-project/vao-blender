"""Offline validation against the checksum-pinned VAO JSON Schemas.

The extension prefers ``jsonschema`` when the optional bundled dependency is
available. A closed-schema validator covering every keyword used by the pinned
manifest schema is retained so source checkouts and constrained Blender builds
still reject malformed packages rather than silently skipping the schema stage.
"""

from __future__ import annotations

import json
import math
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator
from urllib.parse import urlparse

from .diagnostics import Diagnostic, Severity, Stage, ordered

CONTRACT_ROOT = Path(__file__).resolve().parents[2] / "contract" / "vao-0.2.2"
SCHEMA_PATH = CONTRACT_ROOT / "vao-manifest.schema.json"


def load_schema(path: Path = SCHEMA_PATH) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as stream:
        return json.load(stream)


def _pointer(parts: tuple[str | int, ...]) -> str:
    if not parts:
        return ""
    escaped = [str(part).replace("~", "~0").replace("/", "~1") for part in parts]
    return "/" + "/".join(escaped)


def _type_matches(value: Any, kind: str) -> bool:
    return {
        "object": isinstance(value, dict),
        "array": isinstance(value, list),
        "string": isinstance(value, str),
        "integer": isinstance(value, int) and not isinstance(value, bool),
        "number": isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value),
        "boolean": isinstance(value, bool),
        "null": value is None,
    }.get(kind, False)


def _resolve(root: dict[str, Any], reference: str) -> dict[str, Any]:
    if not reference.startswith("#/"):
        raise ValueError(f"non-local schema reference is not supported offline: {reference}")
    current: Any = root
    for component in reference[2:].split("/"):
        current = current[component.replace("~1", "/").replace("~0", "~")]
    return current


def _format_valid(value: str, name: str) -> bool:
    if name in {"uri", "uri-reference"}:
        parsed = urlparse(value)
        return bool(parsed.scheme) if name == "uri" else not any(ord(char) < 32 for char in value)
    if name == "date-time":
        try:
            datetime.fromisoformat(value.replace("Z", "+00:00"))
            return "T" in value
        except ValueError:
            return False
    return True


def _fallback_errors(
    value: Any,
    schema: dict[str, Any] | bool,
    root: dict[str, Any],
    path: tuple[str | int, ...] = (),
) -> Iterator[tuple[str, str]]:
    if schema is True:
        return
    if schema is False:
        yield _pointer(path), "value is disallowed by the schema"
        return
    if "$ref" in schema:
        yield from _fallback_errors(value, _resolve(root, schema["$ref"]), root, path)
        return

    if "allOf" in schema:
        for subschema in schema["allOf"]:
            yield from _fallback_errors(value, subschema, root, path)
    if "anyOf" in schema:
        branches = [list(_fallback_errors(value, item, root, path)) for item in schema["anyOf"]]
        if all(branch for branch in branches):
            yield _pointer(path), "value does not match any permitted schema branch"
    if "oneOf" in schema:
        matches = sum(
            not list(_fallback_errors(value, item, root, path)) for item in schema["oneOf"]
        )
        if matches != 1:
            yield _pointer(path), f"value matches {matches} oneOf branches; exactly one is required"
    if "not" in schema and not list(_fallback_errors(value, schema["not"], root, path)):
        yield _pointer(path), "value matches a prohibited schema"
    if "if" in schema:
        condition_matches = not list(_fallback_errors(value, schema["if"], root, path))
        branch = schema.get("then") if condition_matches else schema.get("else")
        if branch is not None:
            yield from _fallback_errors(value, branch, root, path)

    expected = schema.get("type")
    if expected:
        kinds = [expected] if isinstance(expected, str) else expected
        if not any(_type_matches(value, kind) for kind in kinds):
            yield _pointer(path), f"expected type {expected!r}, got {type(value).__name__}"
            return

    if "const" in schema and value != schema["const"]:
        yield _pointer(path), f"expected constant {schema['const']!r}"
    if "enum" in schema and value not in schema["enum"]:
        yield _pointer(path), "value is outside the permitted enumeration"

    if isinstance(value, dict):
        required = schema.get("required", [])
        for key in required:
            if key not in value:
                yield _pointer(path), f"required property {key!r} is missing"
        if len(value) < schema.get("minProperties", 0):
            yield _pointer(path), "object has too few properties"
        properties = schema.get("properties", {})
        additional = schema.get("additionalProperties", True)
        for key, item in value.items():
            child_schema = properties.get(key, additional)
            if child_schema is False:
                yield _pointer(path + (key,)), "additional property is not permitted"
            elif child_schema is not True:
                yield from _fallback_errors(item, child_schema, root, path + (key,))
            if "propertyNames" in schema:
                yield from _fallback_errors(key, schema["propertyNames"], root, path + (key,))
        for trigger, dependencies in schema.get("dependentRequired", {}).items():
            if trigger in value:
                for dependency in dependencies:
                    if dependency not in value:
                        yield (
                            _pointer(path),
                            (f"property {trigger!r} requires property {dependency!r}"),
                        )

    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0):
            yield _pointer(path), "array has too few items"
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            yield _pointer(path), "array has too many items"
        if schema.get("uniqueItems"):
            markers = [json.dumps(item, sort_keys=True, separators=(",", ":")) for item in value]
            if len(markers) != len(set(markers)):
                yield _pointer(path), "array items are not unique"
        item_schema = schema.get("items")
        if item_schema is not None:
            for index, item in enumerate(value):
                yield from _fallback_errors(item, item_schema, root, path + (index,))
        if "contains" in schema and not any(
            not list(_fallback_errors(item, schema["contains"], root, path + (index,)))
            for index, item in enumerate(value)
        ):
            yield _pointer(path), "array does not contain a required matching item"

    if isinstance(value, str):
        if len(value) < schema.get("minLength", 0):
            yield _pointer(path), "string is shorter than minLength"
        if "pattern" in schema and re.search(schema["pattern"], value) is None:
            yield _pointer(path), f"string does not match pattern {schema['pattern']!r}"
        if "format" in schema and not _format_valid(value, schema["format"]):
            yield _pointer(path), f"string is not a valid {schema['format']}"

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            yield _pointer(path), f"number is below minimum {schema['minimum']}"
        if "maximum" in schema and value > schema["maximum"]:
            yield _pointer(path), f"number is above maximum {schema['maximum']}"
        if "exclusiveMinimum" in schema and value <= schema["exclusiveMinimum"]:
            yield _pointer(path), f"number is not above {schema['exclusiveMinimum']}"


def validate_schema_document(
    value: dict[str, Any],
    schema_path: Path,
    *,
    diagnostic_code: str = "VAO-SCH-001",
) -> tuple[Diagnostic, ...]:
    """Validate one closed JSON document without network schema resolution."""
    schema = load_schema(schema_path)
    errors: list[tuple[str, str]]
    try:
        from jsonschema import Draft202012Validator, FormatChecker  # type: ignore

        validator = Draft202012Validator(schema, format_checker=FormatChecker())
        errors = [
            (_pointer(tuple(error.absolute_path)), error.message)
            for error in validator.iter_errors(value)
        ]
    except ImportError:
        errors = list(_fallback_errors(value, schema, schema))
    return ordered(
        Diagnostic(
            code=diagnostic_code,
            severity=Severity.ERROR,
            stage=Stage.SCHEMA,
            message=message,
            pointer=pointer,
        )
        for pointer, message in errors
    )


def validate_schema(manifest: dict[str, Any]) -> tuple[Diagnostic, ...]:
    """Validate the pinned VAO 0.2.2 manifest schema."""
    return validate_schema_document(manifest, SCHEMA_PATH)
