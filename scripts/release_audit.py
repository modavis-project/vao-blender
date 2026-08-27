#!/usr/bin/env python3
"""Verify release metadata, vendored contracts, dependency wheels, and docs."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROJECT_TITLE = "VAO Blender: A Blender Extension for Virtual Acoustic Objects"
RELEASE_VERSION = "0.3.0-rc.1"
RELEASE_DOI = "10.5281/zenodo.22134389"
REPOSITORY_URL = "https://github.com/modavis-project/vao-blender"
RELEASE_URL = f"{REPOSITORY_URL}/releases/tag/v0.3.0-rc.1"
STANDARD_RELEASE_URL = "https://github.com/modavis-project/vao-standard/tree/v0.4.0"
STANDARD_DOI = "10.5281/zenodo.22122774"
REQUIRED_PUBLIC_FILES = (
    ".zenodo.json",
    "README.md",
    "CHANGELOG.md",
    "CONTRIBUTING.md",
    "CODE_OF_CONDUCT.md",
    "SECURITY.md",
    "SUPPORT.md",
    "LICENSE",
    "RELEASE_NOTES.md",
    "THIRD_PARTY_NOTICES.md",
    "CITATION.cff",
    "SBOM.spdx.json",
    "docs/COMPATIBILITY.md",
    "docs/CONFORMANCE.md",
    "docs/INSTALLATION.md",
    "docs/PRIVACY.md",
    "docs/PUBLICATION.md",
    "docs/RELEASE.md",
    "docs/TROUBLESHOOTING.md",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def parse_checksum_file(path: Path) -> dict[str, str]:
    entries: dict[str, str] = {}
    for line_number, raw in enumerate(path.read_text(encoding="ascii").splitlines(), 1):
        if not raw.strip():
            continue
        match = re.fullmatch(r"([0-9a-f]{64})  (.+)", raw)
        if not match:
            raise ValueError(f"{path}:{line_number}: invalid checksum line")
        digest, name = match.groups()
        if name in entries:
            raise ValueError(f"{path}:{line_number}: duplicate path {name!r}")
        entries[name] = digest
    return entries


def verify_wheels(manifest: dict[str, object]) -> int:
    wheel_dir = ROOT / "wheels"
    recorded = parse_checksum_file(wheel_dir / "WHEELS_SHA256")
    actual = {path.name for path in wheel_dir.glob("*.whl")}
    declared = {Path(str(item)).name for item in manifest.get("wheels", [])}  # type: ignore[arg-type]
    if actual != set(recorded):
        raise ValueError("WHEELS_SHA256 does not exactly inventory wheels/*.whl")
    if actual != declared:
        raise ValueError("blender_manifest.toml does not exactly declare wheels/*.whl")
    for name, expected in sorted(recorded.items()):
        if sha256(wheel_dir / name) != expected:
            raise ValueError(f"wheel failed SHA-256 verification: {name}")
    return len(actual)


def verify_contract_inventory() -> int:
    contract_root = ROOT / "contract" / "vao-0.4.0"
    inventory_path = contract_root / "CONTRACT_FILES_SHA256"
    recorded = parse_checksum_file(inventory_path)
    actual = {
        path.relative_to(contract_root).as_posix()
        for path in contract_root.rglob("*")
        if path.is_file() and path != inventory_path
    }
    normalized = {name.removeprefix("./") for name in recorded}
    if actual != normalized:
        missing = sorted(actual - normalized)
        stale = sorted(normalized - actual)
        raise ValueError(f"VAO 0.4.0 inventory mismatch; missing={missing}, stale={stale}")
    for name, expected in recorded.items():
        relative = name.removeprefix("./")
        if sha256(contract_root / relative) != expected:
            raise ValueError(f"VAO 0.4.0 vendored file failed SHA-256 verification: {relative}")
    return len(actual)


def verify_release_metadata(manifest: dict[str, object]) -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    if not readme.startswith(f"# {PROJECT_TITLE}\n"):
        raise ValueError("README.md project title is inconsistent")
    for required in (RELEASE_DOI, REPOSITORY_URL, STANDARD_RELEASE_URL, STANDARD_DOI):
        if required not in readme:
            raise ValueError(f"README.md is missing release reference: {required}")

    citation = (ROOT / "CITATION.cff").read_text(encoding="utf-8")
    required_citation_lines = (
        f'title: "{PROJECT_TITLE}"',
        f"version: {RELEASE_VERSION}",
        f'doi: "{RELEASE_DOI}"',
        f'repository-code: "{REPOSITORY_URL}"',
        f'doi: "{STANDARD_DOI}"',
    )
    for line in required_citation_lines:
        if line not in citation:
            raise ValueError(f"CITATION.cff is missing release metadata: {line}")

    zenodo = json.loads((ROOT / ".zenodo.json").read_text(encoding="utf-8"))
    expected_zenodo = {
        "access_right": "open",
        "language": "eng",
        "license": "gpl-3.0-or-later",
        "publication_date": "2026-08-27",
        "title": PROJECT_TITLE,
        "upload_type": "software",
        "version": RELEASE_VERSION,
    }
    for key, expected in expected_zenodo.items():
        if zenodo.get(key) != expected:
            raise ValueError(f".zenodo.json {key!r} must be {expected!r}")
    if zenodo.get("doi"):
        raise ValueError("Zenodo release DOI must not be declared as an external DOI")
    expected_creators = [
        {
            "affiliation": (
                "Digital Humanities (Image/Object), Friedrich Schiller University Jena; "
                "Research Group DIGITAL ORGANOLOGY, Leipzig University"
            ),
            "name": "Ukolov, Dominik",
            "orcid": "0000-0002-7904-3892",
        }
    ]
    if zenodo.get("creators") != expected_creators:
        raise ValueError(".zenodo.json creator metadata is incomplete or unexpected")
    if len(zenodo.get("keywords", [])) < 6:
        raise ValueError(".zenodo.json must provide complete discovery keywords")
    if not str(zenodo.get("description", "")).startswith("<p>VAO Blender"):
        raise ValueError(".zenodo.json must provide the full software description")
    if "Release candidate" not in str(zenodo.get("notes", "")):
        raise ValueError(".zenodo.json must disclose the release-candidate test scope")
    identifiers = {
        item.get("identifier")
        for item in zenodo.get("related_identifiers", [])
        if isinstance(item, dict)
    }
    required_identifiers = {
        RELEASE_URL,
        f"https://doi.org/{STANDARD_DOI}",
        STANDARD_RELEASE_URL,
    }
    if not required_identifiers.issubset(identifiers):
        raise ValueError(".zenodo.json is missing repository or standard relationships")
    release_relationships = [
        item
        for item in zenodo.get("related_identifiers", [])
        if isinstance(item, dict) and item.get("identifier") == RELEASE_URL
    ]
    if release_relationships != [
        {
            "identifier": RELEASE_URL,
            "relation": "isIdenticalTo",
            "resource_type": "software",
        }
    ]:
        raise ValueError(".zenodo.json must identify the exact GitHub release")

    if manifest.get("website") != REPOSITORY_URL:
        raise ValueError("blender_manifest.toml website must identify this repository")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()

    manifest = tomllib.loads((ROOT / "blender_manifest.toml").read_text(encoding="utf-8"))
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    package_source = (ROOT / "vao_blender" / "__init__.py").read_text(encoding="utf-8")
    version_match = re.search(r'^__version__ = "([^"]+)"$', package_source, re.MULTILINE)
    versions = {
        str(manifest.get("version")),
        str(project["project"]["version"]),
        version_match.group(1) if version_match else "",
    }
    if len(versions) != 1 or "" in versions:
        raise ValueError(f"release versions are inconsistent: {sorted(versions)}")

    missing_docs = [name for name in REQUIRED_PUBLIC_FILES if not (ROOT / name).is_file()]
    if missing_docs:
        raise ValueError(f"required public repository files are missing: {missing_docs}")

    verify_release_metadata(manifest)

    sbom = json.loads((ROOT / "SBOM.spdx.json").read_text(encoding="utf-8"))
    if sbom.get("spdxVersion") != "SPDX-2.3":
        raise ValueError("SBOM.spdx.json is not SPDX 2.3")
    root_packages = [
        package
        for package in sbom.get("packages", [])
        if package.get("SPDXID") == "SPDXRef-Package-VAO-Blender"
    ]
    if len(root_packages) != 1 or root_packages[0].get("versionInfo") != RELEASE_VERSION:
        raise ValueError("SBOM root package does not identify the release candidate")

    sys.path.insert(0, str(ROOT))
    from vao_blender.core.contract import verify_contracts

    verify_contracts()
    wheel_count = verify_wheels(manifest)
    contract_count = verify_contract_inventory()
    version = next(iter(versions))
    print(
        f"Release audit passed: version={version}, wheels={wheel_count}, "
        f"VAO-0.4.0-files={contract_count}, public-docs={len(REQUIRED_PUBLIC_FILES)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
