"""Verified glTF inspection and stable node-index import derivative helpers."""

from __future__ import annotations

import json
import os
import struct
import tempfile
from pathlib import Path

from .strict_json import StrictJSONError, loads

GLB_MAGIC = b"glTF"
JSON_CHUNK = 0x4E4F534A
COPY_CHUNK_SIZE = 4 * 1024 * 1024
MAX_JSON_CHUNK_SIZE = 64 * 1024 * 1024


class GLTFError(RuntimeError):
    pass


def inject_glb_node_indices(source: Path, destination: Path) -> int:
    """Inject stable node indices into a temporary GLB while copying binary chunks unchanged."""
    source = Path(source)
    destination = Path(destination)
    source_size = source.stat().st_size
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None

    try:
        with source.open("rb") as incoming:
            header = incoming.read(12)
            if len(header) != 12 or header[:4] != GLB_MAGIC:
                raise GLTFError("asset is not a GLB container")
            version, declared_length = struct.unpack_from("<II", header, 4)
            if version != 2 or declared_length != source_size:
                raise GLTFError("GLB header version/length is invalid")

            with tempfile.NamedTemporaryFile(
                mode="w+b",
                prefix=f".{destination.name}.",
                suffix=".tmp",
                dir=destination.parent,
                delete=False,
            ) as outgoing:
                temporary_path = Path(outgoing.name)
                outgoing.write(struct.pack("<4sII", GLB_MAGIC, 2, 0))
                offset = 12
                json_seen = False
                node_count = 0

                while offset < source_size:
                    chunk_header = incoming.read(8)
                    if len(chunk_header) != 8:
                        raise GLTFError("truncated GLB chunk header")
                    length, kind = struct.unpack("<II", chunk_header)
                    offset += 8
                    if length % 4 or length > source_size - offset:
                        raise GLTFError("invalid GLB chunk length")

                    if kind == JSON_CHUNK:
                        if json_seen:
                            raise GLTFError("GLB contains multiple JSON chunks")
                        if length > MAX_JSON_CHUNK_SIZE:
                            raise GLTFError("GLB JSON chunk exceeds the 64 MiB safety limit")
                        json_seen = True
                        payload = incoming.read(length)
                        if len(payload) != length:
                            raise GLTFError("truncated GLB JSON chunk")
                        payload, node_count = _indexed_json(payload)
                        outgoing.write(struct.pack("<II", len(payload), kind))
                        outgoing.write(payload)
                    else:
                        outgoing.write(chunk_header)
                        _copy_exact(incoming, outgoing, length)
                    offset += length

                if not json_seen:
                    raise GLTFError("GLB has no JSON chunk")
                rebuilt_length = outgoing.tell()
                if rebuilt_length > 0xFFFFFFFF:
                    raise GLTFError("rebuilt GLB exceeds the container size limit")
                outgoing.seek(8)
                outgoing.write(struct.pack("<I", rebuilt_length))
                outgoing.flush()
                os.fsync(outgoing.fileno())

        temporary_path.replace(destination)
        temporary_path = None
        return node_count
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _indexed_json(payload: bytes) -> tuple[bytes, int]:
    try:
        document = loads(payload.rstrip(b" \t\r\n\x00"))
    except StrictJSONError as exc:
        raise GLTFError(f"GLB JSON is invalid: {exc}") from exc
    if not isinstance(document, dict):
        raise GLTFError("GLB JSON root is not an object")
    for collection_name in ("buffers", "images"):
        records = document.get(collection_name, [])
        if not isinstance(records, list):
            raise GLTFError(f"GLB {collection_name} is not an array")
        for record in records:
            if not isinstance(record, dict):
                raise GLTFError(f"GLB {collection_name} entry is not an object")
            uri = record.get("uri")
            if uri is not None and (not isinstance(uri, str) or not uri.startswith("data:")):
                raise GLTFError(
                    "external glTF resource URIs are forbidden; VAO-Blender performs no fetch"
                )
    nodes = document.get("nodes", [])
    if not isinstance(nodes, list):
        raise GLTFError("GLB nodes is not an array")
    for index, node in enumerate(nodes):
        if not isinstance(node, dict):
            raise GLTFError("GLB node is not an object")
        extras = node.get("extras")
        if extras is None:
            extras = {}
            node["extras"] = extras
        if not isinstance(extras, dict):
            raise GLTFError("GLB node extras is not an object")
        extras["vao_blender_node_index"] = index
    rebuilt = json.dumps(
        document, ensure_ascii=False, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    rebuilt += b" " * ((-len(rebuilt)) % 4)
    return rebuilt, len(nodes)


def _copy_exact(incoming, outgoing, length: int) -> None:
    remaining = length
    while remaining:
        chunk = incoming.read(min(remaining, COPY_CHUNK_SIZE))
        if not chunk:
            raise GLTFError("truncated GLB binary chunk")
        outgoing.write(chunk)
        remaining -= len(chunk)
