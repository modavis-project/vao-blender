#!/usr/bin/env python3
"""Verify release identity, contracts, dependencies, evidence, and public docs."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import subprocess
import sys
import tomllib
from pathlib import Path, PurePosixPath
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PROJECT_TITLE = "VAO Blender: A Blender Extension for Virtual Acoustic Objects"
REQUIRED_PUBLIC_FILES = (
    ".github/workflows/native-release-evidence.yml",
    ".zenodo.json",
    "release_metadata.toml",
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
ACTIVE_RELEASE_DOCS = (
    "README.md",
    "RELEASE_NOTES.md",
    "docs/INSTALLATION.md",
    "docs/PUBLICATION.md",
    "docs/RELEASE.md",
)
CREATOR = {
    "affiliation": (
        "Digital Humanities (Image/Object), Friedrich Schiller University Jena; "
        "Research Group DIGITAL ORGANOLOGY, Leipzig University"
    ),
    "name": "Ukolov, Dominik",
    "orcid": "0000-0002-7904-3892",
}
CFF_AUTHOR = {
    "affiliation": CREATOR["affiliation"],
    "family-names": "Ukolov",
    "given-names": "Dominik",
    "orcid": f"https://orcid.org/{CREATOR['orcid']}",
}
PLATFORM_WHEEL_MARKERS = {
    "windows-x64": "win_amd64",
    "macos-arm64": "macosx_11_0_arm64",
    "linux-x64": "manylinux_2_17_x86_64",
}
BINARY_ATTRIBUTE_PATTERNS = (
    "*.blend",
    "*.blend1",
    "*.glb",
    "*.gz",
    "*.ico",
    "*.jpeg",
    "*.jpg",
    "*.mp3",
    "*.ogg",
    "*.pdf",
    "*.png",
    "*.tar",
    "*.vao",
    "*.wav",
    "*.whl",
    "*.xz",
    "*.zip",
)
BINARY_SOURCE_SUFFIXES = {pattern.removeprefix("*") for pattern in BINARY_ATTRIBUTE_PATTERNS}
INTENTIONALLY_REMOVED_SOURCE_MEMBERS = {
    "wheels/rpds_py-2026.6.3-cp313-cp313-macosx_10_12_x86_64.whl"
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def parse_checksum_file(path: Path) -> dict[str, str]:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"checksum inventory must be a regular file: {path}")
    entries: dict[str, str] = {}
    for line_number, raw in enumerate(path.read_text(encoding="ascii").splitlines(), 1):
        if not raw.strip():
            continue
        match = re.fullmatch(r"([0-9a-f]{64})  (.+)", raw)
        if not match:
            raise ValueError(f"{path}:{line_number}: invalid checksum line")
        digest, name = match.groups()
        normalized = name.removeprefix("./")
        member = PurePosixPath(normalized)
        if member.is_absolute() or any(part in {"", ".", ".."} for part in member.parts):
            raise ValueError(f"{path}:{line_number}: unsafe checksum path {name!r}")
        if normalized in entries:
            raise ValueError(f"{path}:{line_number}: duplicate path {normalized!r}")
        entries[normalized] = digest
    return entries


def load_release_metadata() -> dict[str, Any]:
    metadata = tomllib.loads((ROOT / "release_metadata.toml").read_text(encoding="utf-8"))
    required_strings = (
        "extension_version",
        "release_label",
        "release_tag",
        "status",
        "release_doi",
        "release_date",
        "repository",
    )
    for field in required_strings:
        if not isinstance(metadata.get(field), str):
            raise ValueError(f"release_metadata.toml {field!r} must be a string")

    extension_version = metadata["extension_version"]
    release_label = metadata["release_label"]
    semver_component = r"(?:0|[1-9]\d*)"
    if not re.fullmatch(
        rf"{semver_component}(?:\.{semver_component}){{2}}(?:-rc\.[1-9]\d*)?",
        extension_version,
    ):
        raise ValueError("extension_version must be a strict stable or numbered-RC SemVer")
    if release_label != extension_version:
        raise ValueError("release_label and Blender extension_version must be identical")
    if metadata["release_tag"] != f"v{release_label}":
        raise ValueError("release_tag must be 'v' followed by release_label")
    if metadata["status"] not in {"unreleased", "prerelease", "published"}:
        raise ValueError("release status must be unreleased, prerelease, or published")
    is_release_candidate = "-rc." in release_label
    if metadata["status"] == "prerelease" and not is_release_candidate:
        raise ValueError("prerelease status requires a numbered RC release_label")
    if metadata["status"] == "published" and is_release_candidate:
        raise ValueError("published status requires the stable extension release_label")
    if metadata["status"] in {"prerelease", "published"} and not metadata["release_doi"]:
        raise ValueError("a prerelease or published release must declare its own DOI")
    if metadata["status"] == "unreleased" and metadata["release_doi"]:
        raise ValueError("an unreleased version must not borrow or predict a DOI")
    if metadata["status"] == "unreleased" and metadata["release_date"]:
        raise ValueError("an unreleased version must not claim a publication date")
    if metadata["status"] != "unreleased" and not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}", metadata["release_date"]
    ):
        raise ValueError("a prerelease or published release must declare an ISO release date")
    if metadata["release_doi"] and not re.fullmatch(
        r"10\.\d{4,9}/[-._;()/:A-Za-z0-9]+", metadata["release_doi"]
    ):
        raise ValueError("release_doi is not a syntactically valid DOI")
    if metadata["release_date"]:
        try:
            dt.date.fromisoformat(metadata["release_date"])
        except ValueError as exc:
            raise ValueError("release_date is not a real calendar date") from exc
    if not re.fullmatch(r"https://github\.com/[^/]+/[^/]+", metadata["repository"]):
        raise ValueError("repository must be a canonical HTTPS GitHub repository URL")

    previous = metadata.get("previous_release")
    if not isinstance(previous, dict):
        raise ValueError("release_metadata.toml is missing [previous_release]")
    if not all(
        isinstance(previous.get(name), str) and previous[name] for name in ("label", "doi", "tag")
    ):
        raise ValueError("[previous_release] must provide a label, DOI, and tag")
    if previous["tag"] != f"v{previous['label']}":
        raise ValueError("previous release tag and label are inconsistent")
    if previous["doi"] == metadata["release_doi"] and metadata["release_doi"]:
        raise ValueError("the current release must not reuse the previous release DOI")
    blender = metadata.get("blender")
    if not isinstance(blender, dict) or not isinstance(blender.get("platforms"), list):
        raise ValueError("release_metadata.toml is missing [blender] compatibility metadata")
    if not all(
        isinstance(blender.get(name), str) and blender[name]
        for name in ("version_min", "version_max_exclusive", "python", "python_abi")
    ):
        raise ValueError("[blender] compatibility fields must be non-empty strings")
    if not all(isinstance(item, str) and item for item in blender["platforms"]):
        raise ValueError("[blender] platforms must be non-empty strings")
    if len(blender["platforms"]) != len(set(blender["platforms"])):
        raise ValueError("[blender] platforms contain duplicates")
    expected_platforms = ["windows-x64", "macos-arm64", "linux-x64"]
    if blender["platforms"] != expected_platforms:
        raise ValueError(
            "[blender] platforms must exactly match the audited official-host release targets"
        )
    if blender["python_abi"] != "cp" + blender["python"].replace(".", ""):
        raise ValueError("[blender] Python version and ABI are inconsistent")
    builder = metadata.get("builder")
    builder_fields = (
        "blender_version",
        "blender_python_version",
        "driver_python_version",
        "platform_system",
        "platform_machine",
        "official_archive_url",
        "official_archive_sha256",
        "blender_build_hash",
        "blender_executable_sha256",
    )
    if not isinstance(builder, dict) or not all(
        isinstance(builder.get(name), str) and builder[name] for name in builder_fields
    ):
        raise ValueError("release_metadata.toml is missing complete [builder] provenance")
    expected_archive_url = (
        "https://download.blender.org/release/Blender5.2/"
        f"blender-{builder['blender_version']}-linux-x64.tar.xz"
    )
    if builder["official_archive_url"] != expected_archive_url:
        raise ValueError("[builder] official Blender archive URL is not canonical")
    expected_builder = {
        "blender_version": "5.2.1",
        "blender_python_version": "3.13.13",
        "driver_python_version": "3.13.13",
        "platform_system": "Linux",
        "platform_machine": "x86_64",
        "official_archive_url": expected_archive_url,
        "official_archive_sha256": "a31f524fa99a527d3d52b7f5aaa68c34e1a19d5a1c9473f79c5cc610fd5b10e9",
        "blender_build_hash": "9e2066aef7ef",
        "blender_executable_sha256": "c2fd82553c979a7f6ba85202c487aa1173c90db588a67d74d70cc7b0c2bea01c",
    }
    if builder != expected_builder:
        raise ValueError("[builder] does not match the audited official Blender 5.2.1 builder")
    if not builder["blender_python_version"].startswith(blender["python"] + "."):
        raise ValueError("[builder] Blender Python series conflicts with compatibility metadata")
    if builder["platform_system"] != "Linux" or builder["platform_machine"] != "x86_64":
        raise ValueError("[builder] release platform must be canonical Linux x86_64")
    citation = metadata.get("citation")
    if not isinstance(citation, dict) or citation != {
        "cff_version": "1.2.0",
        "schema_url": (
            "https://raw.githubusercontent.com/citation-file-format/"
            "citation-file-format/396f738fb025b1d8acdb02a56ffc923f95dc8999/schema.json"
        ),
        "schema_sha256": "0b8d22140da702d766df318dcff3a91af2f39521298dcf36d76315fd99cc169b",
    }:
        raise ValueError("[citation] must pin the official CFF 1.2.0 schema exactly")
    spdx = metadata.get("spdx")
    if not isinstance(spdx, dict) or spdx != {
        "version": "2.3",
        "schema_url": (
            "https://raw.githubusercontent.com/spdx/spdx-spec/"
            "aadf3b0b8dbbabdb4d880b0fc714255fea436ff7/schemas/spdx-schema.json"
        ),
        "schema_sha256": "239208b7ac287b3cf5d9a9af23f9d69863971102a5e1587a27a398b43490b89b",
    }:
        raise ValueError("[spdx] must pin the official SPDX 2.3 JSON schema exactly")
    native_evidence = metadata.get("native_evidence")
    expected_native_evidence = {
        "blender_versions": ["5.1.2", "5.2.1"],
        "platforms": blender["platforms"],
        "required_tests": [
            "installed-extension-smoke",
            "lifecycle",
            "detached-reopen",
            "vao-0.3.2",
            "vao-0.4.0",
            "vao-0.5.0",
            "audio-policy",
        ],
        "attestation_filename": "NATIVE_TEST_EVIDENCE.json",
        "publication_checksums_filename": "PUBLICATION_SHA256SUMS",
        "hosts": [
            {
                "blender_version": version,
                "platform": platform_name,
                "archive_url": url,
                "archive_sha256": archive_sha256,
                "build_hash": build_hash,
                "python_version": python_version,
                "system": system,
                "machine": machine,
                "runner_image": runner_image,
            }
            for (
                version,
                platform_name,
                url,
                archive_sha256,
                build_hash,
                python_version,
                system,
                machine,
                runner_image,
            ) in (
                (
                    "5.1.2",
                    "windows-x64",
                    "https://download.blender.org/release/Blender5.1/blender-5.1.2-windows-x64.zip",
                    "345bedea7b0acf7cc9666423d8553f9129622aea34ded65c23e8cb70f83f14ff",
                    "ec6e62d40fa9",
                    "3.13.9",
                    "Windows",
                    "AMD64",
                    "windows-2025",
                ),
                (
                    "5.1.2",
                    "macos-arm64",
                    "https://download.blender.org/release/Blender5.1/blender-5.1.2-macos-arm64.dmg",
                    "f104ffee2ba6aee32328e5c203b7e4608d8a1745f7bbcf2766f3b9777e8fbe17",
                    "ec6e62d40fa9",
                    "3.13.9",
                    "Darwin",
                    "arm64",
                    "macos-15",
                ),
                (
                    "5.1.2",
                    "linux-x64",
                    "https://download.blender.org/release/Blender5.1/blender-5.1.2-linux-x64.tar.xz",
                    "aaccb355f50183979b698bcce7467103a76261b5fa59f4972295842662a285fb",
                    "ec6e62d40fa9",
                    "3.13.9",
                    "Linux",
                    "x86_64",
                    "ubuntu-24.04",
                ),
                (
                    "5.2.1",
                    "windows-x64",
                    "https://download.blender.org/release/Blender5.2/blender-5.2.1-windows-x64.zip",
                    "0e631dad7d0cad6d5d18abdd2e2550f6c0213215334eda00ddbd3d22b96ecb2c",
                    "9e2066aef7ef",
                    "3.13.13",
                    "Windows",
                    "AMD64",
                    "windows-2025",
                ),
                (
                    "5.2.1",
                    "macos-arm64",
                    "https://download.blender.org/release/Blender5.2/blender-5.2.1-macos-arm64.dmg",
                    "6409e21de80994db5f4c4a34486b6fd43cea21085b912f7491c53e923acb65a3",
                    "9e2066aef7ef",
                    "3.13.13",
                    "Darwin",
                    "arm64",
                    "macos-15",
                ),
                (
                    "5.2.1",
                    "linux-x64",
                    "https://download.blender.org/release/Blender5.2/blender-5.2.1-linux-x64.tar.xz",
                    "a31f524fa99a527d3d52b7f5aaa68c34e1a19d5a1c9473f79c5cc610fd5b10e9",
                    "9e2066aef7ef",
                    "3.13.13",
                    "Linux",
                    "x86_64",
                    "ubuntu-24.04",
                ),
            )
        ],
    }
    if native_evidence != expected_native_evidence:
        raise ValueError("[native_evidence] does not define the exact detached publication gate")
    standard = metadata.get("vao_standard")
    if not isinstance(standard, dict) or not all(
        isinstance(standard.get(name), dict) for name in ("published", "candidate")
    ):
        raise ValueError("release_metadata.toml must define published and candidate standards")
    for kind, fields in {
        "published": ("version", "doi", "release_url", "source_sha256"),
        "candidate": (
            "version",
            "commit",
            "tree_url",
            "release_bundle_sha256",
        ),
    }.items():
        record = standard[kind]
        if not all(isinstance(record.get(name), str) and record[name] for name in fields):
            raise ValueError(f"[vao_standard.{kind}] metadata is incomplete")
    for digest in (
        standard["published"]["source_sha256"],
        standard["candidate"]["release_bundle_sha256"],
    ):
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ValueError("standard bundle checksums must be lowercase SHA-256 values")
    if not re.fullmatch(r"[0-9a-f]{40}", standard["candidate"]["commit"]):
        raise ValueError("candidate standard commit must be a full Git SHA-1")
    return metadata


def verify_manifest_policy(manifest: dict[str, object], release: dict[str, Any]) -> None:
    blender = release["blender"]
    expected_fields = {
        "blender_version_min": blender["version_min"],
        "blender_version_max": blender["version_max_exclusive"],
    }
    for field, expected in expected_fields.items():
        if manifest.get(field) != expected:
            raise ValueError(f"blender_manifest.toml {field} must be {expected!r}")
    platforms = manifest.get("platforms", [])
    if set(platforms) != set(blender["platforms"]) or len(platforms) != len(blender["platforms"]):
        raise ValueError("blender_manifest.toml platform inventory is inconsistent")
    native_wheels = [str(item) for item in manifest.get("wheels", []) if "rpds_py-" in str(item)]
    if len(native_wheels) != len(blender["platforms"]):
        raise ValueError("manifest must declare one native rpds-py wheel per platform")
    if any(
        f"-{blender['python_abi']}-{blender['python_abi']}-" not in item for item in native_wheels
    ):
        raise ValueError("native wheels do not match the declared Blender Python ABI")
    for platform in blender["platforms"]:
        marker = PLATFORM_WHEEL_MARKERS.get(platform)
        if marker is None or sum(marker in wheel for wheel in native_wheels) != 1:
            raise ValueError(f"native wheel inventory does not exactly cover {platform}")
    exclusions = set(manifest.get("build", {}).get("paths_exclude_pattern", []))  # type: ignore[union-attr]
    required_exclusions = {
        ".*",
        "__pycache__/",
        "build/",
        "dist/",
        "docs/",
        "scripts/",
        "tests/",
        "tmp/",
        "*.blend",
        "*.vao",
        "SBOM.spdx.json",
    }
    if not required_exclusions.issubset(exclusions):
        raise ValueError("blender_manifest.toml is missing release-safety build exclusions")


def verify_wheels(
    manifest: dict[str, object],
) -> tuple[int, dict[str, tuple[str, str, str]]]:
    wheel_dir = ROOT / "wheels"
    recorded = parse_checksum_file(wheel_dir / "WHEELS_SHA256")
    actual = {path.name for path in wheel_dir.glob("*.whl")}
    declared = {Path(str(item)).name for item in manifest.get("wheels", [])}  # type: ignore[arg-type]
    if actual != set(recorded):
        raise ValueError("WHEELS_SHA256 does not exactly inventory wheels/*.whl")
    if actual != declared:
        raise ValueError("blender_manifest.toml does not exactly declare wheels/*.whl")
    expected_packages: dict[str, tuple[str, str, str]] = {}
    for name, expected in sorted(recorded.items()):
        wheel_path = wheel_dir / name
        if wheel_path.is_symlink() or not wheel_path.is_file():
            raise ValueError(f"wheel must be a regular file: {name}")
        if sha256(wheel_path) != expected:
            raise ValueError(f"wheel failed SHA-256 verification: {name}")
        parts = name.split("-")
        if len(parts) < 5:
            raise ValueError(f"wheel filename is malformed: {name}")
        package_name = parts[0].replace("_", "-").lower()
        expected_packages[name] = (package_name, parts[1], expected)
    return len(actual), expected_packages


def verify_contract_inventory(version: str) -> int:
    contract_root = ROOT / "contract" / f"vao-{version}"
    inventory_path = contract_root / "CONTRACT_FILES_SHA256"
    recorded = parse_checksum_file(inventory_path)
    actual = {
        path.relative_to(contract_root).as_posix()
        for path in contract_root.rglob("*")
        if path.is_file() and path != inventory_path and "__pycache__" not in path.parts
    }
    if any(path.is_symlink() for path in contract_root.rglob("*")):
        raise ValueError(f"VAO {version} vendored contract must not contain symbolic links")
    if actual != set(recorded):
        missing = sorted(actual - set(recorded))
        stale = sorted(set(recorded) - actual)
        raise ValueError(f"VAO {version} inventory mismatch; missing={missing}, stale={stale}")
    for name, expected in recorded.items():
        if sha256(contract_root / name) != expected:
            raise ValueError(f"VAO {version} vendored file failed SHA-256 verification: {name}")
    return len(actual)


def require_tokens(label: str, text: str, tokens: tuple[str, ...]) -> None:
    for token in tokens:
        if token not in text:
            raise ValueError(f"{label} is missing release metadata: {token}")


def verify_cross_platform_checkout_policy() -> None:
    """Keep tagged source bytes invariant across hosted runner operating systems."""
    attributes_path = ROOT / ".gitattributes"
    if attributes_path.is_symlink() or not attributes_path.is_file():
        raise ValueError("release source requires a regular .gitattributes file")
    try:
        attributes_bytes = attributes_path.read_bytes()
        attributes = attributes_bytes.decode("utf-8")
    except (OSError, UnicodeError) as exc:
        raise ValueError(".gitattributes must be readable UTF-8") from exc
    if b"\r" in attributes_bytes:
        raise ValueError(".gitattributes itself must use LF line endings")
    rules = {
        line.strip()
        for line in attributes.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    required_rules = {"* text=auto eol=lf"} | {
        f"{pattern} binary -eol" for pattern in BINARY_ATTRIBUTE_PATTERNS
    }
    if not required_rules.issubset(rules):
        raise ValueError(
            ".gitattributes must force LF text checkouts and exempt every audited binary type"
        )

    try:
        result = subprocess.run(
            (
                "git",
                "ls-files",
                "--cached",
                "--others",
                "--exclude-standard",
                "-z",
            ),
            cwd=ROOT,
            check=True,
            capture_output=True,
        )
        names = result.stdout.decode("utf-8").removesuffix("\0").split("\0")
    except (OSError, UnicodeError, subprocess.CalledProcessError) as exc:
        raise ValueError("release audit could not inventory source line endings") from exc
    if ".gitattributes" not in names:
        raise ValueError(".gitattributes is absent from the auditable source inventory")
    for name in names:
        path = ROOT / name
        # Pre-commit release audits intentionally run with the unsupported Intel
        # wheel removed from the working tree while it is still present in the
        # index. The final clean-tag gate separately rejects any unresolved Git
        # deletion, so only inspect members that belong to the candidate tree.
        if not path.exists() and not path.is_symlink():
            if name in INTENTIONALLY_REMOVED_SOURCE_MEMBERS:
                continue
            raise ValueError(f"release source inventory has an unexpected deletion: {name}")
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"release source inventory contains a non-regular member: {name}")
        if PurePosixPath(name).suffix.lower() in BINARY_SOURCE_SUFFIXES:
            continue
        data = path.read_bytes()
        if b"\x00" not in data and b"\r" in data:
            raise ValueError(f"release text source must use LF line endings: {name}")


def verify_workflows(release: dict[str, Any]) -> None:
    workflow_dir = ROOT / ".github" / "workflows"
    for workflow in sorted(workflow_dir.glob("*.yml")):
        text = workflow.read_text(encoding="utf-8")
        if re.search(r"^\s*runs-on:\s*[^\n]*-latest\s*$", text, flags=re.MULTILINE):
            raise ValueError(f"{workflow.relative_to(ROOT)} uses a moving latest runner image")
        action_references = re.findall(r"^\s*(?:-\s*)?uses:\s*([^\s#]+)", text, flags=re.MULTILINE)
        for reference in action_references:
            if not re.fullmatch(r"[^@\s]+@[0-9a-f]{40}", reference):
                raise ValueError(
                    f"{workflow.relative_to(ROOT)} has a mutable action reference: {reference}"
                )

    native_path = workflow_dir / "native-release-evidence.yml"
    native = native_path.read_text(encoding="utf-8")
    require_tokens(
        str(native_path.relative_to(ROOT)),
        native,
        (
            "workflow_dispatch:",
            "permissions:\n  contents: read",
            "scripts/prepare_native_blender.py",
            "scripts/run_native_release_cell.py",
            '--blender-executable-sha256 "${{ steps.blender.outputs.blender_executable_sha256 }}"',
            "Revalidate citation and SBOM against pinned official schemas",
            "scripts/native_evidence.py merge",
            "scripts/native_evidence.py assemble",
            "scripts/native_evidence.py verify",
            "/attempts/${{ github.run_attempt }}",
            "base-release-attempt-${{ github.run_attempt }}",
            "native-cell-attempt-${{ github.run_attempt }}-*",
            "Upload complete non-published publication set",
        ),
    )
    matrix = re.findall(
        r'^\s{10}- blender: "([^"]+)"\n'
        r"\s{12}platform: ([^\s]+)\n"
        r"\s{12}runner: ([^\s]+)$",
        native,
        flags=re.MULTILINE,
    )
    expected_matrix = [
        (host["blender_version"], host["platform"], host["runner_image"])
        for host in release["native_evidence"]["hosts"]
    ]
    if matrix != expected_matrix:
        raise ValueError("native release workflow matrix does not exactly match host policy")
    forbidden = ("contents: write", "id-token: write", "gh release", "zenodo")
    if any(token in native.lower() for token in forbidden):
        raise ValueError("native release workflow contains a publication capability")


def verify_citation(release: dict[str, Any]) -> None:
    """Validate the JSON-form YAML 1.2 citation document structurally."""
    try:
        citation = json.loads((ROOT / "CITATION.cff").read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("CITATION.cff must be valid JSON-form YAML 1.2") from exc
    if not isinstance(citation, dict):
        raise ValueError("CITATION.cff must contain one mapping")
    release_label = release["release_label"]
    repository = release["repository"]
    required_top = {
        "cff-version",
        "message",
        "title",
        "type",
        "version",
        "license",
        "abstract",
        "keywords",
        "repository-code",
        "authors",
        "preferred-citation",
        "references",
    }
    publication_fields = {"doi", "date-released"} if release["release_doi"] else set()
    if set(citation) != required_top | publication_fields:
        raise ValueError("CITATION.cff has missing or unexpected top-level fields")
    expected_identity = {
        "cff-version": release["citation"]["cff_version"],
        "title": PROJECT_TITLE,
        "type": "software",
        "version": release_label,
        "license": "GPL-3.0-or-later",
        "repository-code": repository,
        "authors": [CFF_AUTHOR],
    }
    for name, expected in expected_identity.items():
        if citation.get(name) != expected:
            raise ValueError(f"CITATION.cff {name!r} is inconsistent")
    keywords = citation.get("keywords")
    if (
        not isinstance(keywords, list)
        or len(keywords) < 5
        or len(keywords) != len(set(keywords))
        or not all(isinstance(item, str) and item for item in keywords)
    ):
        raise ValueError("CITATION.cff keywords are incomplete or malformed")
    preferred = citation.get("preferred-citation")
    expected_preferred = {
        "type": "software",
        "title": PROJECT_TITLE,
        "authors": [CFF_AUTHOR],
        "version": release_label,
        "repository-code": repository,
    }
    if release["release_doi"]:
        expected_preferred.update(
            {"doi": release["release_doi"], "date-released": release["release_date"]}
        )
        if (
            citation.get("doi") != release["release_doi"]
            or citation.get("date-released") != release["release_date"]
        ):
            raise ValueError("CITATION.cff publication fields are inconsistent")
    if preferred != expected_preferred:
        raise ValueError("CITATION.cff preferred citation is inconsistent")
    references = citation.get("references")
    if not isinstance(references, list) or len(references) != 3:
        raise ValueError("CITATION.cff must identify exactly three release/standard references")
    by_title = {item.get("title"): item for item in references if isinstance(item, dict)}
    if len(by_title) != len(references):
        raise ValueError("CITATION.cff references must be mappings with unique titles")
    previous = release["previous_release"]
    previous_reference = by_title.get(PROJECT_TITLE, {})
    expected_previous = {
        "type": "software",
        "version": previous["label"],
        "doi": previous["doi"],
        "url": f"{repository}/releases/tag/{previous['tag']}",
    }
    if any(previous_reference.get(name) != value for name, value in expected_previous.items()):
        raise ValueError("CITATION.cff previous-release reference is inconsistent")
    standard_note = (
        "Specifications and documentation are CC-BY-4.0; reference software is Apache-2.0."
    )
    for kind, title in (
        ("published", "Virtual Acoustic Object (VAO) Standard 0.4.0"),
        ("candidate", "Virtual Acoustic Object (VAO) Standard 0.5.0 candidate"),
    ):
        standard = release["vao_standard"][kind]
        reference = by_title.get(title, {})
        expected_url = standard.get("release_url") or standard.get("tree_url")
        if (
            reference.get("version") != standard["version"]
            or reference.get("url") != expected_url
            or reference.get("notes") != standard_note
            or "license" in reference
        ):
            raise ValueError(f"CITATION.cff {kind} VAO Standard reference is inconsistent")
    if release["status"] == "unreleased" and ("doi" in citation or "date-released" in citation):
        raise ValueError("unreleased CITATION.cff metadata must not claim publication")


def verify_public_metadata(manifest: dict[str, object], release: dict[str, Any]) -> None:
    repository = release["repository"]
    release_label = release["release_label"]
    release_url = f"{repository}/releases/tag/{release['release_tag']}"
    previous = release["previous_release"]
    published = release["vao_standard"]["published"]
    candidate = release["vao_standard"]["candidate"]

    state_surface_names = (
        "README.md",
        "RELEASE_NOTES.md",
        "docs/INSTALLATION.md",
        "docs/RELEASE.md",
        "docs/PUBLICATION.md",
    )
    state_surfaces = {
        name: (ROOT / name).read_text(encoding="utf-8") for name in state_surface_names
    }
    readme = state_surfaces["README.md"]
    if not readme.startswith(f"# {PROJECT_TITLE}\n"):
        raise ValueError("README.md project title is inconsistent")
    require_tokens(
        "README.md",
        readme,
        (
            release_label,
            repository,
            published["release_url"],
            published["doi"],
            candidate["commit"],
            candidate["tree_url"],
        ),
    )
    if release["release_doi"]:
        require_tokens(
            "README.md",
            readme,
            (release["release_doi"], release["release_date"]),
        )

    status = release["status"]
    expected_marker = f"Current release state: **{status}**."
    for relative, surface in state_surfaces.items():
        if expected_marker not in surface:
            raise ValueError(f"{relative} does not carry the canonical current-state marker")
        for other_status in {"unreleased", "prerelease", "published"} - {status}:
            stale_marker = f"Current release state: **{other_status}**."
            if stale_marker in surface:
                raise ValueError(f"{relative} retains the stale state marker {other_status!r}")
    expected_badge = f"release-{release_label.replace('-', '--')}%20{status}-"
    if expected_badge not in readme:
        raise ValueError("README.md release badge does not match the canonical release state")
    notes_status = f"Status: **{status}**."
    if notes_status not in state_surfaces["RELEASE_NOTES.md"]:
        raise ValueError("RELEASE_NOTES.md status does not match release_metadata.toml")

    unreleased_claims = {
        "README.md": (
            f"No `{release['release_tag']}` tag, canonical release",
            f"Version {release_label} is unreleased and has no DOI yet.",
        ),
        "RELEASE_NOTES.md": (
            "prepared for a staged release candidate; no tag, canonical artifact set, DOI,",
            "This candidate has no DOI yet.",
        ),
        "docs/INSTALLATION.md": (
            "candidate; no current download or publication is claimed yet.",
            "candidate remains\nunreleased until",
        ),
        "docs/RELEASE.md": ("No current-release DOI, publication date,",),
        "docs/PUBLICATION.md": ("but its status is `unreleased` and it has no DOI.",),
    }
    for relative, claims in unreleased_claims.items():
        surface = state_surfaces[relative]
        for claim in claims:
            if status == "unreleased" and claim not in surface:
                raise ValueError(f"{relative} is missing its explicit unreleased-state claim")
            if status != "unreleased" and claim in surface:
                raise ValueError(f"{relative} retains a false unreleased-state claim")
    if status != "unreleased":
        for relative in (
            "README.md",
            "RELEASE_NOTES.md",
            "docs/RELEASE.md",
            "docs/PUBLICATION.md",
        ):
            require_tokens(
                relative,
                state_surfaces[relative],
                (release["release_doi"], release["release_date"]),
            )

    stale_artifact = f"vao_blender-{previous['label'].split('-')[0]}-"
    for relative in ACTIVE_RELEASE_DOCS:
        text = (ROOT / relative).read_text(encoding="utf-8")
        if stale_artifact in text or previous["tag"] in text:
            raise ValueError(f"{relative} still presents previous-release artifacts as current")
    versioned_output = f"dist/release-candidate/{release_label}"
    artifact_prefix = f"vao_blender-{release_label}-"
    active_requirements = {
        "README.md": (
            f"candidate is {release_label}",
            artifact_prefix + "windows_x64.zip",
            artifact_prefix + "macos_arm64.zip",
            artifact_prefix + "linux_x64.zip",
            versioned_output,
            "native-release-evidence.yml",
        ),
        "RELEASE_NOTES.md": (
            f"# VAO Blender {release_label}",
            "Status: **unreleased**"
            if release["status"] == "unreleased"
            else f"Status: **{release['status']}**",
            "| 5.1.2 | Windows x64 |",
            "| 5.1.2 | macOS ARM64 |",
            "| 5.1.2 | Linux x64 |",
            "| 5.2.1 | Windows x64 |",
            "| 5.2.1 | macOS ARM64 |",
            "| 5.2.1 | Linux x64 |",
            release["native_evidence"]["attestation_filename"],
            "native-release-evidence.yml",
        ),
        "docs/INSTALLATION.md": (artifact_prefix + "<platform>.zip", versioned_output),
        "docs/PUBLICATION.md": (
            release["release_tag"],
            release_label,
            release["native_evidence"]["attestation_filename"],
            "scripts/native_evidence.py merge",
            "native-release-evidence.yml",
        ),
        "docs/RELEASE.md": (
            release["release_tag"],
            versioned_output,
            release["native_evidence"]["attestation_filename"],
            "scripts/native_evidence.py merge",
            "native-release-evidence.yml",
        ),
    }
    for relative, tokens in active_requirements.items():
        require_tokens(relative, state_surfaces[relative], tokens)

    verify_citation(release)

    zenodo = json.loads((ROOT / ".zenodo.json").read_text(encoding="utf-8"))
    expected_zenodo = {
        "access_right": "open",
        "language": "eng",
        "license": "gpl-3.0-or-later",
        "title": PROJECT_TITLE,
        "upload_type": "software",
        "version": release_label,
    }
    for key, expected in expected_zenodo.items():
        if zenodo.get(key) != expected:
            raise ValueError(f".zenodo.json {key!r} must be {expected!r}")
    if zenodo.get("creators") != [CREATOR]:
        raise ValueError(".zenodo.json creator metadata is incomplete or unexpected")
    if len(zenodo.get("keywords", [])) < 6:
        raise ValueError(".zenodo.json must provide complete discovery keywords")
    if not str(zenodo.get("description", "")).startswith("<p>VAO Blender"):
        raise ValueError(".zenodo.json must provide the full software description")
    if "doi" in zenodo:
        raise ValueError(".zenodo.json must not declare a Zenodo-reserved DOI as an existing DOI")
    if release["release_doi"] and release["release_doi"] in json.dumps(zenodo, sort_keys=True):
        raise ValueError(
            ".zenodo.json must leave the current reserved DOI to the manual draft record"
        )
    if release["status"] == "unreleased":
        if zenodo.get("publication_date"):
            raise ValueError("unreleased Zenodo metadata must not claim a DOI or publication date")
        if "Unreleased" not in str(zenodo.get("notes", "")):
            raise ValueError(".zenodo.json must identify the metadata as unreleased")
    else:
        if zenodo.get("publication_date") != release["release_date"]:
            raise ValueError(".zenodo.json publication date is inconsistent")
        zenodo_notes = str(zenodo.get("notes", ""))
        if (
            "unreleased" in zenodo_notes.lower()
            or "no doi" in zenodo_notes.lower()
            or release["status"] not in zenodo_notes.lower()
        ):
            raise ValueError(".zenodo.json notes retain a stale or missing release-state claim")
    identifiers = {
        item.get("identifier")
        for item in zenodo.get("related_identifiers", [])
        if isinstance(item, dict)
    }
    required_identifiers = {
        release_url,
        f"https://doi.org/{previous['doi']}",
        f"https://doi.org/{published['doi']}",
        published["release_url"],
        candidate["tree_url"],
    }
    if not required_identifiers.issubset(identifiers):
        raise ValueError(".zenodo.json is missing release-history or standard relationships")
    release_relationships = [
        item
        for item in zenodo.get("related_identifiers", [])
        if isinstance(item, dict) and item.get("identifier") == release_url
    ]
    if release_relationships != [
        {
            "identifier": release_url,
            "relation": "isIdenticalTo",
            "resource_type": "software",
        }
    ]:
        raise ValueError(".zenodo.json must identify the exact intended GitHub release")

    if manifest.get("website") != repository:
        raise ValueError("blender_manifest.toml website must identify this repository")


def verify_sbom(
    release: dict[str, Any],
    expected_dependencies: dict[str, tuple[str, str, str]],
) -> None:
    sbom = json.loads((ROOT / "SBOM.spdx.json").read_text(encoding="utf-8"))
    if sbom.get("spdxVersion") != f"SPDX-{release['spdx']['version']}":
        raise ValueError("SBOM.spdx.json is not SPDX 2.3")
    release_label = release["release_label"]
    repository = release["repository"]
    release_url = f"{repository}/releases/tag/{release['release_tag']}"
    if sbom.get("documentNamespace") != f"{repository}/spdx/v{release_label}":
        raise ValueError("SBOM document namespace does not identify this release")
    if sbom.get("name") != f"VAO-Blender-{release_label}-SBOM":
        raise ValueError("SBOM document name does not identify this release")
    document_comment = str(sbom.get("comment", ""))
    if (
        "Standalone release-set SBOM" not in document_comment
        or "not embedded" not in document_comment
    ):
        raise ValueError("SBOM must identify its standalone release-set scope")

    packages = sbom.get("packages", [])
    if not isinstance(packages, list):
        raise ValueError("SBOM packages must be an array")
    by_id = {package.get("SPDXID"): package for package in packages if isinstance(package, dict)}
    if len(by_id) != len(packages):
        raise ValueError("SBOM package SPDX identifiers must be unique and non-empty")
    root = by_id.get("SPDXRef-Package-VAO-Blender")
    if (
        not root
        or root.get("name") != "VAO Blender"
        or root.get("versionInfo") != release_label
        or root.get("downloadLocation") != release_url
        or root.get("licenseDeclared") != "GPL-3.0-or-later"
        or "complete three-platform release set" not in str(root.get("comment", ""))
    ):
        raise ValueError("SBOM root package does not identify the release candidate")
    if sbom.get("documentDescribes") != ["SPDXRef-Package-VAO-Blender"]:
        raise ValueError("SBOM documentDescribes must identify exactly the extension package")

    for kind, spdx_id in (
        ("published", "SPDXRef-Package-VAO-Standard-040"),
        ("candidate", "SPDXRef-Package-VAO-Standard-050-Candidate"),
    ):
        standard = release["vao_standard"][kind]
        package = by_id.get(spdx_id)
        if not package or package.get("versionInfo") != standard["version"]:
            raise ValueError(f"SBOM is missing the VAO {standard['version']} contract package")
        if package.get("licenseDeclared") != "CC-BY-4.0 AND Apache-2.0":
            raise ValueError(f"SBOM VAO {standard['version']} licence expression is incomplete")
        expected_location = standard.get("release_url") or standard.get("tree_url")
        if package.get("downloadLocation") != expected_location:
            raise ValueError(f"SBOM VAO {standard['version']} source location is inconsistent")
    published_package = by_id["SPDXRef-Package-VAO-Standard-040"]
    published_hashes = {
        item.get("checksumValue")
        for item in published_package.get("checksums", [])
        if isinstance(item, dict) and item.get("algorithm") == "SHA256"
    }
    if (
        published_hashes != {release["vao_standard"]["published"]["source_sha256"]}
        or published_package.get("packageFileName") != "vao-standard-0.4.0.zip"
    ):
        raise ValueError("SBOM published VAO source-archive checksum is inconsistent")
    candidate_package = by_id["SPDXRef-Package-VAO-Standard-050-Candidate"]
    if candidate_package.get("checksums") or release["vao_standard"]["candidate"][
        "commit"
    ] not in str(candidate_package.get("sourceInfo", "")):
        raise ValueError("SBOM candidate tree must be commit-bound without a false blob checksum")
    bundle_package = by_id.get("SPDXRef-Package-VAO-Standard-050-Release-Bundle")
    candidate = release["vao_standard"]["candidate"]
    bundle_checksums = (
        bundle_package.get("checksums", []) if isinstance(bundle_package, dict) else []
    )
    bundle_hashes = {
        item.get("checksumValue")
        for item in bundle_checksums
        if isinstance(item, dict) and item.get("algorithm") == "SHA256"
    }
    expected_bundle_url = (
        "https://raw.githubusercontent.com/modavis-project/vao-standard/"
        f"{candidate['commit']}/Schemas/vao-release-bundle-0.5.0.json"
    )
    if (
        not bundle_package
        or bundle_package.get("versionInfo") != candidate["version"]
        or bundle_package.get("packageFileName") != "Schemas/vao-release-bundle-0.5.0.json"
        or bundle_package.get("downloadLocation") != expected_bundle_url
        or bundle_package.get("licenseDeclared") != "CC-BY-4.0"
        or bundle_hashes != {candidate["release_bundle_sha256"]}
    ):
        raise ValueError("SBOM candidate release-bundle file identity is inconsistent")

    excluded = {
        "SPDXRef-Package-VAO-Blender",
        "SPDXRef-Package-VAO-Standard-040",
        "SPDXRef-Package-VAO-Standard-050-Candidate",
        "SPDXRef-Package-VAO-Standard-050-Release-Bundle",
    }
    dependencies: dict[str, tuple[str, str, str]] = {}
    dependency_ids: set[str] = set()
    for package in packages:
        spdx_id = package["SPDXID"]
        if spdx_id in excluded:
            continue
        filename = package.get("packageFileName")
        name = str(package.get("name", "")).replace("_", "-").lower()
        version = str(package.get("versionInfo", ""))
        if (
            not isinstance(filename, str)
            or filename not in expected_dependencies
            or filename in dependencies
            or not name
            or not version
        ):
            raise ValueError("SBOM wheel package identity is missing, duplicated, or unexpected")
        checksums = {
            checksum.get("checksumValue")
            for checksum in package.get("checksums", [])
            if isinstance(checksum, dict) and checksum.get("algorithm") == "SHA256"
        }
        if len(checksums) != 1 or any(
            not re.fullmatch(r"[0-9a-f]{64}", str(item)) for item in checksums
        ):
            raise ValueError(f"SBOM wheel package {filename} must have one SHA-256")
        dependencies[filename] = (name, version, str(next(iter(checksums))))
        dependency_ids.add(str(spdx_id))
    if dependencies != expected_dependencies:
        raise ValueError("SBOM dependencies do not exactly identify the vendored wheel inventory")
    relationships = {
        (
            item.get("spdxElementId"),
            item.get("relationshipType"),
            item.get("relatedSpdxElement"),
        )
        for item in sbom.get("relationships", [])
        if isinstance(item, dict)
    }
    required_relationships = {
        ("SPDXRef-Package-VAO-Blender", "DEPENDS_ON", item) for item in dependency_ids
    } | {
        (
            "SPDXRef-Package-VAO-Blender",
            "CONTAINS",
            "SPDXRef-Package-VAO-Standard-040",
        ),
        (
            "SPDXRef-Package-VAO-Blender",
            "CONTAINS",
            "SPDXRef-Package-VAO-Standard-050-Candidate",
        ),
        (
            "SPDXRef-Package-VAO-Standard-050-Candidate",
            "CONTAINS",
            "SPDXRef-Package-VAO-Standard-050-Release-Bundle",
        ),
    }
    if not required_relationships.issubset(relationships):
        raise ValueError("SBOM dependency or vendored-standard relationships are incomplete")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()

    verify_cross_platform_checkout_policy()
    release = load_release_metadata()
    manifest = tomllib.loads((ROOT / "blender_manifest.toml").read_text(encoding="utf-8"))
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    package_versions = []
    for path in (ROOT / "__init__.py", ROOT / "vao_blender" / "__init__.py"):
        source = path.read_text(encoding="utf-8")
        match = re.search(r'^__version__ = "([^"]+)"$', source, re.MULTILINE)
        package_versions.append(match.group(1) if match else "")
    expected_extension_version = release["extension_version"]
    extension_versions = {str(manifest.get("version")), *package_versions}
    if extension_versions != {expected_extension_version}:
        raise ValueError(
            "Blender/package versions must all match release_metadata.toml: "
            f"expected={expected_extension_version!r}, actual={sorted(extension_versions)}"
        )
    expected_project_version = expected_extension_version.replace("-rc.", "rc")
    if str(project["project"]["version"]) != expected_project_version:
        raise ValueError(
            "pyproject version must be the PEP 440 spelling of extension_version: "
            f"expected={expected_project_version!r}"
        )

    missing_docs = [name for name in REQUIRED_PUBLIC_FILES if not (ROOT / name).is_file()]
    if missing_docs:
        raise ValueError(f"required public repository files are missing: {missing_docs}")

    verify_public_metadata(manifest, release)
    verify_workflows(release)
    verify_manifest_policy(manifest, release)
    wheel_count, expected_dependencies = verify_wheels(manifest)
    verify_sbom(release, expected_dependencies)

    sys.path.insert(0, str(ROOT))
    from vao_blender.core.contract import (
        RELEASE_BUNDLE_04_SHA256,
        RELEASE_BUNDLE_05_SHA256,
        STANDARD_05_COMMIT,
        verify_contracts,
    )

    published = release["vao_standard"]["published"]
    candidate = release["vao_standard"]["candidate"]
    if (
        published.get("version") != "0.4.0"
        or published.get("source_sha256") != RELEASE_BUNDLE_04_SHA256
    ):
        raise ValueError("release metadata does not match the pinned published VAO 0.4.0 bundle")
    if (
        candidate.get("version") != "0.5.0"
        or candidate.get("commit") != STANDARD_05_COMMIT
        or candidate.get("release_bundle_sha256") != RELEASE_BUNDLE_05_SHA256
    ):
        raise ValueError("release metadata does not match the pinned VAO 0.5.0 candidate")

    verify_contracts()
    contract_04_count = verify_contract_inventory("0.4.0")
    contract_05_count = verify_contract_inventory("0.5.0")
    print(
        "Release audit passed: "
        f"extension={release['extension_version']}, label={release['release_label']}, "
        f"status={release['status']}, wheels={wheel_count}, "
        f"VAO-0.4.0-files={contract_04_count}, VAO-0.5.0-files={contract_05_count}, "
        f"public-docs={len(REQUIRED_PUBLIC_FILES)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
