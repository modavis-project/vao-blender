"""Strict JSON decoding: UTF-8, duplicate keys, and finite numbers only."""

from __future__ import annotations

import json
from typing import Any


class StrictJSONError(ValueError):
    pass


MAX_JSON_DEPTH = 128


def _object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise StrictJSONError(f"duplicate JSON object key: {key!r}")
        result[key] = value
    return result


def _check_depth(value: Any, *, maximum: int = MAX_JSON_DEPTH) -> None:
    """Reject structures deep enough to exhaust recursive downstream consumers."""
    pending: list[tuple[Any, int]] = [(value, 1)]
    while pending:
        current, depth = pending.pop()
        if depth > maximum:
            raise StrictJSONError(f"JSON nesting exceeds the supported depth of {maximum}")
        if not isinstance(current, (dict, list)):
            continue
        children = current.values() if isinstance(current, dict) else current
        pending.extend((child, depth + 1) for child in children)


def loads(data: bytes | str) -> Any:
    if isinstance(data, bytes):
        try:
            source = data.decode("utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            raise StrictJSONError(f"JSON is not strict UTF-8: {exc}") from exc
    else:
        source = data
    try:
        value = json.loads(
            source,
            object_pairs_hook=_object,
            parse_constant=lambda value: (_ for _ in ()).throw(
                StrictJSONError(f"non-finite JSON number: {value}")
            ),
        )
        _check_depth(value)
        return value
    except StrictJSONError:
        raise
    except (ValueError, TypeError, RecursionError) as exc:
        raise StrictJSONError(str(exc)) from exc
