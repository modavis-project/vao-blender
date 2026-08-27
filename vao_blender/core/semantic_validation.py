"""VAO graph, reference, integrity, rights, and profile semantic checks."""

from __future__ import annotations

import re
from typing import Any

from .diagnostics import Diagnostic, Severity, Stage, ordered

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
ACTIVE_STATUSES = {"accepted", "asserted"}


def validate_semantics(manifest: dict[str, Any]) -> tuple[Diagnostic, ...]:
    found: list[Diagnostic] = []

    def error(code: str, message: str, pointer: str = "", *ids: str) -> None:
        found.append(
            Diagnostic(
                code=code,
                severity=Severity.ERROR,
                stage=Stage.SEMANTIC,
                message=message,
                pointer=pointer,
                related_ids=tuple(ids),
            )
        )

    package_id = manifest.get("id", "")
    entities = manifest.get("entities", [])
    assets = manifest.get("assets", [])
    relations = manifest.get("relations", [])

    categories = {
        "entity": [
            (item.get("id", ""), f"/entities/{index}/id") for index, item in enumerate(entities)
        ],
        "asset": [(item.get("id", ""), f"/assets/{index}/id") for index, item in enumerate(assets)],
        "relation": [
            (item.get("id", ""), f"/relations/{index}/id") for index, item in enumerate(relations)
        ],
        "paradata": [
            (item.get("id", ""), f"/paradata/{index}/id")
            for index, item in enumerate(manifest.get("paradata", []))
        ],
        "analysis": [
            (item.get("id", ""), f"/analyses/{index}/id")
            for index, item in enumerate(manifest.get("analyses", []))
        ],
    }
    for collection, records in manifest.get("acoustics", {}).items():
        if isinstance(records, list):
            categories[f"acoustics.{collection}"] = [
                (item.get("id", ""), f"/acoustics/{collection}/{index}/id")
                for index, item in enumerate(records)
                if isinstance(item, dict) and "id" in item
            ]
    all_ids: dict[str, tuple[str, str]] = {}
    for category, entries in categories.items():
        local: set[str] = set()
        for identifier, pointer in entries:
            if identifier in local:
                error("VAO-SEM-001", f"duplicate {category} id {identifier!r}", pointer, identifier)
            local.add(identifier)
            if identifier in all_ids:
                previous_category, _ = all_ids[identifier]
                error(
                    "VAO-SEM-002",
                    f"id {identifier!r} is reused by {previous_category} and {category}",
                    pointer,
                    identifier,
                )
            all_ids[identifier] = (category, pointer)

    entity_ids = {item.get("id", "") for item in entities}
    local_ids = set(all_ids)
    graph_target_ids = local_ids
    primary = manifest.get("primaryEntityId", "")
    if primary not in entity_ids:
        error(
            "VAO-SEM-003",
            "primaryEntityId does not resolve to an entity",
            "/primaryEntityId",
            primary,
        )
    if primary not in manifest.get("focusEntityIds", []):
        error(
            "VAO-SEM-018", "focusEntityIds must include primaryEntityId", "/focusEntityIds", primary
        )
    for index, identifier in enumerate(manifest.get("focusEntityIds", [])):
        if identifier not in entity_ids:
            error(
                "VAO-SEM-004",
                "focusEntityIds entry does not resolve to an entity",
                f"/focusEntityIds/{index}",
                identifier,
            )

    for index, relation in enumerate(relations):
        subject = relation.get("subjectId", "")
        if subject not in graph_target_ids:
            error(
                "VAO-SEM-005",
                "relation subjectId is dangling",
                f"/relations/{index}/subjectId",
                relation.get("id", ""),
                subject,
            )
        # Object identifiers may intentionally be external IRIs. Predicates
        # whose executable semantics require a local object are resolved by
        # their profile validator/compiler, never by guessing here.
        if relation.get("status") not in {"asserted", "accepted", "rejected", "hypothesis"}:
            error(
                "VAO-SEM-007",
                "relation status is not recognized",
                f"/relations/{index}/status",
                relation.get("id", ""),
            )

    paths: dict[str, int] = {}
    total_bytes = 0
    for index, asset in enumerate(assets):
        path = asset.get("path", "")
        if path in paths:
            error(
                "VAO-SEM-008",
                f"multiple assets index payload path {path!r}",
                f"/assets/{index}/path",
                asset.get("id", ""),
            )
        paths[path] = index
        total_bytes += asset.get("byteSize", 0)
        if not SHA256_RE.fullmatch(asset.get("sha256", "")):
            error(
                "VAO-SEM-009",
                "asset sha256 must be lowercase hexadecimal",
                f"/assets/{index}/sha256",
                asset.get("id", ""),
            )
        for about_index, identifier in enumerate(asset.get("aboutEntityIds", [])):
            if identifier not in entity_ids:
                error(
                    "VAO-SEM-010",
                    "asset aboutEntityIds entry is dangling",
                    f"/assets/{index}/aboutEntityIds/{about_index}",
                    asset.get("id", ""),
                    identifier,
                )

    integrity = manifest.get("integrity", {})
    if integrity.get("algorithm") != "sha256":
        error("VAO-SEM-011", "only sha256 integrity is supported", "/integrity/algorithm")
    if integrity.get("assetCount") != len(assets):
        error("VAO-SEM-012", "integrity.assetCount does not match assets", "/integrity/assetCount")
    if integrity.get("totalPayloadBytes") != total_bytes:
        error(
            "VAO-SEM-013",
            "integrity.totalPayloadBytes does not equal the indexed asset total",
            "/integrity/totalPayloadBytes",
        )

    rights = manifest.get("rights", [])
    if not any(package_id in record.get("appliesToIds", []) for record in rights):
        error("VAO-SEM-019", "at least one rights record must apply to the VAO id", "/rights")
    for index, record in enumerate(rights):
        for item_index, identifier in enumerate(record.get("appliesToIds", [])):
            if identifier not in graph_target_ids and identifier != package_id:
                error(
                    "VAO-SEM-014",
                    "rights applicability identifier is dangling",
                    f"/rights/{index}/appliesToIds/{item_index}",
                    identifier,
                )

    profile_ids = [profile.get("id", "") for profile in manifest.get("profiles", [])]
    if len(profile_ids) != len(set(profile_ids)):
        error("VAO-SEM-020", "profile identifiers must be unique", "/profiles")
    conforms_to = set(manifest.get("conformsTo", []))
    for profile_index, profile in enumerate(manifest.get("profiles", [])):
        capabilities = profile.get("requiredCapabilities", [])
        if len(capabilities) != len(set(capabilities)):
            error(
                "VAO-SEM-015",
                "profile requiredCapabilities contains duplicates",
                f"/profiles/{profile_index}/requiredCapabilities",
                profile.get("id", ""),
            )
        if profile.get("id") not in conforms_to:
            error(
                "VAO-SEM-021",
                "every claimed profile must appear in conformsTo",
                f"/profiles/{profile_index}/id",
                profile.get("id", ""),
            )

    return ordered(found)


def rights_require_acknowledgement(manifest: dict[str, Any]) -> bool:
    """Conservatively gate media use when permission is unknown or restricted."""
    rights = manifest.get("rights", [])
    if not rights:
        return True
    for record in rights:
        license_value = str(record.get("license", "")).strip().lower()
        access = str(record.get("accessCondition", "")).strip().lower()
        if not license_value or any(
            token in access
            for token in ("restricted", "unknown", "pending", "prohibited", "not established")
        ):
            return True
    return False
