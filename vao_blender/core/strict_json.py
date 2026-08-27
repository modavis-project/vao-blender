"""Strict JSON decoding: UTF-8, duplicate keys, and finite numbers only."""

from __future__ import annotations

import json
from typing import Any


class StrictJSONError(ValueError):
    pass


def _object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise StrictJSONError(f"duplicate JSON object key: {key!r}")
        result[key] = value
    return result


def loads(data: bytes | str) -> Any:
    if isinstance(data, bytes):
        try:
            source = data.decode("utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            raise StrictJSONError(f"JSON is not strict UTF-8: {exc}") from exc
    else:
        source = data
    try:
        return json.loads(
            source,
            object_pairs_hook=_object,
            parse_constant=lambda value: (_ for _ in ()).throw(
                StrictJSONError(f"non-finite JSON number: {value}")
            ),
        )
    except StrictJSONError:
        raise
    except (ValueError, TypeError) as exc:
        raise StrictJSONError(str(exc)) from exc
