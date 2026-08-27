"""Deterministic immutable graph construction."""

from __future__ import annotations

from collections import defaultdict
from types import MappingProxyType
from typing import Any

from .model import AssetRecord, EntityNode, GraphIndex, RelationEdge, freeze


def build_graph(manifest: dict[str, Any]) -> GraphIndex:
    entities: dict[str, EntityNode] = {}
    for raw in sorted(manifest.get("entities", []), key=lambda item: item["id"]):
        entities[raw["id"]] = EntityNode(
            id=raw["id"],
            kind=raw["kind"],
            types=tuple(raw.get("types", [])),
            labels=freeze(raw.get("labels", {})),
            properties=freeze(raw.get("properties", {})),
        )

    assets: dict[str, AssetRecord] = {}
    for raw in sorted(manifest.get("assets", []), key=lambda item: item["id"]):
        assets[raw["id"]] = AssetRecord(
            id=raw["id"],
            path=raw["path"],
            media_type=raw["mediaType"],
            byte_size=raw["byteSize"],
            sha256=raw["sha256"],
            roles=tuple(raw.get("roles", [])),
            about_entity_ids=tuple(raw.get("aboutEntityIds", [])),
            original_filename=raw.get("originalFilename", ""),
            representation_status=raw.get("representationStatus", ""),
            properties=freeze(raw.get("properties", {})),
        )

    relations: dict[str, RelationEdge] = {}
    outgoing: dict[str, list[RelationEdge]] = defaultdict(list)
    incoming: dict[str, list[RelationEdge]] = defaultdict(list)
    for raw in sorted(manifest.get("relations", []), key=lambda item: item["id"]):
        edge = RelationEdge(
            id=raw["id"],
            subject_id=raw["subjectId"],
            predicate=raw["predicate"],
            object_id=raw.get("objectId", ""),
            literal=freeze(raw.get("literal")),
            status=raw.get("status", ""),
            properties=freeze(raw.get("properties", {})),
        )
        relations[edge.id] = edge
        outgoing[edge.subject_id].append(edge)
        if edge.object_id:
            incoming[edge.object_id].append(edge)

    def frozen_index(index: dict[str, list[RelationEdge]]) -> MappingProxyType:
        return MappingProxyType(
            {
                identifier: tuple(sorted(edges, key=lambda edge: (edge.predicate, edge.id)))
                for identifier, edges in sorted(index.items())
            }
        )

    return GraphIndex(
        entities=MappingProxyType(entities),
        assets=MappingProxyType(assets),
        relations=MappingProxyType(relations),
        outgoing=frozen_index(outgoing),
        incoming=frozen_index(incoming),
    )
