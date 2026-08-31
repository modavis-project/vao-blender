#!/usr/bin/env python3
"""Create or verify detached native-test evidence for an immutable release set."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
DETACHED_SOURCE_MEMBERS = frozenset(
    {
        ".gitattributes",
        "SBOM.spdx.json",
        "RELEASE_NOTES.md",
        "blender_manifest.toml",
        "release_metadata.toml",
    }
)

from scripts.build_extension import (  # noqa: E402
    create_source_archive,
    git_tracked_files,
    promote_release_directory,
    recover_interrupted_promotion,
    verify_artifact_contents,
    verify_release_checkout,
    verify_release_set,
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def parse_checksums(path: Path) -> dict[str, str]:
    if path.is_symlink() or not path.is_file():
        raise RuntimeError(f"checksum inventory must be a regular file: {path}")
    records: dict[str, str] = {}
    for line_number, line in enumerate(path.read_text(encoding="ascii").splitlines(), 1):
        match = re.fullmatch(r"([0-9a-f]{64})  ([^/][^\r\n]*)", line)
        if not match or "/" in match.group(2) or "\\" in match.group(2):
            raise RuntimeError(f"{path.name}:{line_number}: invalid checksum record")
        digest, name = match.groups()
        if name in records:
            raise RuntimeError(f"{path.name}:{line_number}: duplicate checksum record")
        records[name] = digest
    return records


def release_context() -> dict[str, Any]:
    release = tomllib.loads((ROOT / "release_metadata.toml").read_text(encoding="utf-8"))
    manifest = tomllib.loads((ROOT / "blender_manifest.toml").read_text(encoding="utf-8"))
    config = release["native_evidence"]
    artifact_names = {
        platform_name: (
            f"{manifest['id']}-{manifest['version']}-{platform_name.replace('-', '_')}.zip"
        )
        for platform_name in config["platforms"]
    }
    base_names = set(artifact_names.values()) | {
        f"vao-blender-{release['release_label']}-source.zip",
        "SBOM.spdx.json",
        "RELEASE_NOTES.md",
        "release_metadata.toml",
        "RELEASE_EVIDENCE.json",
        "SHA256SUMS",
    }
    return {
        "release": release,
        "manifest": manifest,
        "config": config,
        "artifact_names": artifact_names,
        "base_names": base_names,
    }


def source_checkout_state(release_tag: str) -> tuple[str, bool]:
    """Re-establish the clean annotated-tag binding for detached attestation."""
    try:
        return verify_release_checkout(ROOT, release_tag), True
    except (OSError, subprocess.CalledProcessError, RuntimeError) as exc:
        raise RuntimeError(
            "native evidence requires the clean exact annotated release-tag checkout"
        ) from exc


def _same_file_bytes(left: Path, right: Path) -> bool:
    if left.stat().st_size != right.stat().st_size:
        return False
    with left.open("rb") as left_stream, right.open("rb") as right_stream:
        while True:
            left_block = left_stream.read(1024 * 1024)
            right_block = right_stream.read(1024 * 1024)
            if left_block != right_block:
                return False
            if not left_block:
                return True


def verify_tagged_source_binding(
    release_dir: Path,
    *,
    context: dict[str, Any],
    checksums: dict[str, str],
) -> None:
    """Rebuild and revalidate every source-derived release member at the tag."""
    release = context["release"]
    manifest = context["manifest"]
    expected_platforms = {str(item) for item in manifest.get("platforms", [])}
    expected_wheels = {str(item).removeprefix("./") for item in manifest.get("wheels", [])}
    if set(context["artifact_names"]) != expected_platforms:
        raise RuntimeError("native evidence platform inventory differs from the tagged manifest")

    tracked_members = git_tracked_files(ROOT)
    if not DETACHED_SOURCE_MEMBERS.issubset(tracked_members):
        missing = sorted(DETACHED_SOURCE_MEMBERS - tracked_members)
        raise RuntimeError(
            "detached release metadata is not fully tracked at the release tag: "
            + ", ".join(missing)
        )
    for platform_name, artifact_name in context["artifact_names"].items():
        artifact = release_dir / artifact_name
        if checksums.get(artifact_name) != sha256(artifact):
            raise RuntimeError(f"tagged platform artifact checksum mismatch: {artifact_name}")
        validated_platforms = verify_artifact_contents(
            artifact,
            extension_id=str(manifest["id"]),
            version=str(manifest["version"]),
            expected_platforms=expected_platforms,
            expected_wheels=expected_wheels,
            split=True,
            source_root=ROOT,
            tracked_members=tracked_members,
        )
        if validated_platforms != [platform_name]:
            raise RuntimeError(f"tagged platform artifact identity mismatch: {artifact_name}")

    for filename in ("SBOM.spdx.json", "RELEASE_NOTES.md", "release_metadata.toml"):
        source = ROOT / filename
        detached = release_dir / filename
        if source.is_symlink() or not source.is_file():
            raise RuntimeError(f"tagged source member must be a regular file: {filename}")
        if checksums.get(filename) != sha256(detached) or not _same_file_bytes(source, detached):
            raise RuntimeError(f"detached {filename} differs from the exact tagged source checkout")

    source_archive_name = f"vao-blender-{release['release_label']}-source.zip"
    detached_source_archive = release_dir / source_archive_name
    with tempfile.TemporaryDirectory(prefix="vao-native-tagged-source-") as directory:
        reconstructed = Path(directory) / source_archive_name
        create_source_archive(
            ROOT,
            str(release["release_tag"]),
            str(release["release_label"]),
            reconstructed,
        )
        if checksums.get(source_archive_name) != sha256(reconstructed) or not _same_file_bytes(
            reconstructed, detached_source_archive
        ):
            raise RuntimeError(
                "detached source archive differs from the reconstructed exact tagged source"
            )


def validate_final_release_evidence(
    release_dir: Path,
    *,
    context: dict[str, Any],
    evidence: dict[str, Any],
    checksums: dict[str, str],
) -> None:
    """Bind native evidence to the exact final, tagged, canonical base release."""
    source_metadata = ROOT / "release_metadata.toml"
    detached_metadata = release_dir / "release_metadata.toml"
    if detached_metadata.read_bytes() != source_metadata.read_bytes():
        raise RuntimeError("detached release metadata differs from the attesting source checkout")
    try:
        detached_release = tomllib.loads(detached_metadata.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
        raise RuntimeError("detached release metadata is not valid UTF-8 TOML") from exc
    release = context["release"]
    if detached_release != release:
        raise RuntimeError("detached release metadata is not the canonical release identity")
    if (
        release.get("status") != "prerelease"
        or release.get("release_tag") != f"v{release.get('release_label')}"
        or not release.get("release_doi")
        or not release.get("release_date")
    ):
        raise RuntimeError(
            "native evidence may only certify a final prerelease base with its real tag, DOI, and date"
        )

    commit, clean = source_checkout_state(release["release_tag"])
    if not clean or evidence.get("releaseCommit") != commit:
        raise RuntimeError(
            "native evidence requires a clean checkout at the exact base-release commit"
        )
    expected_identity = {
        "extensionId": context["manifest"]["id"],
        "version": context["manifest"]["version"],
        "releaseLabel": release["release_label"],
        "releaseStatus": release["status"],
        "releaseTag": release["release_tag"],
        "intendedReleaseTag": release["release_tag"],
        "releaseDOI": release["release_doi"],
        "releaseDate": release["release_date"],
        "blenderCompatibility": release["blender"],
        "platforms": release["blender"]["platforms"],
        "standards": release["vao_standard"],
        "nativeEvidenceRequired": release["native_evidence"],
        "splitPlatforms": True,
    }
    mismatches = {
        name: {"expected": value, "actual": evidence.get(name)}
        for name, value in expected_identity.items()
        if evidence.get(name) != value
    }
    if mismatches:
        raise RuntimeError(
            "base release evidence is not final or canonical: "
            + json.dumps(mismatches, sort_keys=True)
        )

    builder_metadata = release["builder"]
    builder = evidence.get("builder")
    expected_builder = {
        "blenderVersion": builder_metadata["blender_version"],
        "blenderVersionTuple": [
            int(item) for item in builder_metadata["blender_version"].split(".")
        ],
        "blenderBuildHash": builder_metadata["blender_build_hash"],
        "pythonVersion": builder_metadata["blender_python_version"],
        "pythonImplementation": "CPython",
        "system": builder_metadata["platform_system"],
        "machine": builder_metadata["platform_machine"],
        "blenderExecutableSha256": builder_metadata["blender_executable_sha256"],
        "driverPythonVersion": builder_metadata["driver_python_version"],
        "driverPythonImplementation": "CPython",
        "pinnedOfficialArchiveSha256": builder_metadata["official_archive_sha256"],
        "pinnedOfficialArchiveUrl": builder_metadata["official_archive_url"],
        "executableMatchesPinnedOfficialArchive": True,
        "archiveNormalization": ("sorted ZIP_STORED entries; 1980-01-01; POSIX 0644/0755"),
    }
    if not isinstance(builder, dict) or any(
        builder.get(name) != value for name, value in expected_builder.items()
    ):
        raise RuntimeError("base release evidence has non-canonical builder provenance")

    records = evidence.get("filesExceptEvidenceAndChecksumList")
    if not isinstance(records, list):
        raise RuntimeError("base release evidence has no artifact inventory")
    by_name: dict[str, dict[str, Any]] = {}
    artifact_platforms = {
        filename: platform_name for platform_name, filename in context["artifact_names"].items()
    }
    for record in records:
        expected_fields = {"file", "kind", "bytes", "sha256"}
        if isinstance(record, dict) and record.get("file") in artifact_platforms:
            expected_fields.add("platforms")
        if (
            not isinstance(record, dict)
            or set(record) != expected_fields
            or not isinstance(record.get("file"), str)
            or record["file"] in by_name
        ):
            raise RuntimeError("base release evidence has a malformed artifact inventory")
        if record["file"] in artifact_platforms and record["platforms"] != [
            artifact_platforms[record["file"]]
        ]:
            raise RuntimeError("base release evidence has a mismatched artifact platform")
        by_name[record["file"]] = record
    expected_record_names = context["base_names"] - {"SHA256SUMS", "RELEASE_EVIDENCE.json"}
    if set(by_name) != expected_record_names:
        raise RuntimeError("base release evidence artifact inventory is incomplete")
    for name, record in by_name.items():
        member = release_dir / name
        if (
            record["bytes"] != member.stat().st_size
            or record["sha256"] != checksums.get(name)
            or record["sha256"] != sha256(member)
        ):
            raise RuntimeError(f"base release evidence artifact record is inconsistent: {name}")
    verify_tagged_source_binding(
        release_dir,
        context=context,
        checksums=checksums,
    )


def verify_checksum_inventory(
    release_dir: Path,
    checksum_name: str,
    expected_names: set[str],
) -> dict[str, str]:
    records = parse_checksums(release_dir / checksum_name)
    if set(records) != expected_names:
        raise RuntimeError(
            f"{checksum_name} inventory mismatch; "
            f"unexpected={sorted(set(records) - expected_names)}, "
            f"missing={sorted(expected_names - set(records))}"
        )
    for name, expected in records.items():
        member = release_dir / name
        if member.is_symlink() or not member.is_file() or sha256(member) != expected:
            raise RuntimeError(f"{checksum_name} verification failed: {name}")
    return records


def load_base_release(
    release_dir: Path,
    context: dict[str, Any],
    *,
    allow_publication_members: bool = False,
) -> tuple[dict, dict]:
    if allow_publication_members:
        checksums = verify_checksum_inventory(
            release_dir,
            "SHA256SUMS",
            context["base_names"] - {"SHA256SUMS"},
        )
    else:
        verify_release_set(release_dir, context["base_names"])
        checksums = parse_checksums(release_dir / "SHA256SUMS")
    evidence = json.loads((release_dir / "RELEASE_EVIDENCE.json").read_text(encoding="utf-8"))
    if not isinstance(evidence, dict):
        raise RuntimeError("RELEASE_EVIDENCE.json must contain a JSON object")
    commit = evidence.get("releaseCommit")
    if not isinstance(commit, str) or not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise RuntimeError("RELEASE_EVIDENCE.json has no valid release commit")
    validate_final_release_evidence(
        release_dir,
        context=context,
        evidence=evidence,
        checksums=checksums,
    )
    return evidence, checksums


def _valid_timestamp(value: object) -> bool:
    if not isinstance(value, str) or not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", value
    ):
        return False
    try:
        dt.datetime.fromisoformat(value.removesuffix("Z") + "+00:00")
    except ValueError:
        return False
    return True


def validate_cells(
    data: dict[str, Any],
    *,
    context: dict[str, Any],
    release_commit: str,
    artifact_checksums: dict[str, str],
) -> list[dict[str, Any]]:
    if set(data) != {"schemaVersion", "releaseCommit", "cells"}:
        raise RuntimeError("native evidence input has missing or unexpected top-level fields")
    if data["schemaVersion"] != 1 or data["releaseCommit"] != release_commit:
        raise RuntimeError("native evidence input is not bound to this release commit")
    cells = data.get("cells")
    if not isinstance(cells, list):
        raise RuntimeError("native evidence cells must be an array")
    config = context["config"]
    expected_cells = {
        (blender_version, platform_name)
        for blender_version in config["blender_versions"]
        for platform_name in config["platforms"]
    }
    exact_fields = {
        "blenderVersion",
        "platform",
        "status",
        "runUrl",
        "observedAt",
        "sourceCommit",
        "artifactFile",
        "artifactSha256",
        "blenderArchiveUrl",
        "blenderArchiveSha256",
        "blenderBuildHash",
        "blenderPythonVersion",
        "blenderExecutableSha256",
        "hostSystem",
        "hostMachine",
        "runnerImage",
        "runnerImageVersion",
        "tests",
    }
    normalized: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    required_tests = list(config["required_tests"])
    host_policies = {(item["blender_version"], item["platform"]): item for item in config["hosts"]}
    if set(host_policies) != expected_cells or len(host_policies) != len(config["hosts"]):
        raise RuntimeError("native host policy does not exactly cover the evidence cells")
    run_url_pattern = re.compile(
        re.escape(context["release"]["repository"]) + r"/actions/runs/[1-9]\d*/attempts/[1-9]\d*"
    )
    run_urls: set[str] = set()
    for cell in cells:
        if not isinstance(cell, dict) or set(cell) != exact_fields:
            raise RuntimeError("native evidence cell has missing or unexpected fields")
        key = (cell["blenderVersion"], cell["platform"])
        if key not in expected_cells or key in seen:
            raise RuntimeError(f"native evidence has an unexpected or duplicate cell: {key}")
        seen.add(key)
        platform_name = cell["platform"]
        host_policy = host_policies[key]
        expected_artifact = context["artifact_names"][platform_name]
        expected_digest = artifact_checksums.get(expected_artifact)
        if (
            cell["status"] != "pass"
            or not isinstance(cell["runUrl"], str)
            or not run_url_pattern.fullmatch(cell["runUrl"])
            or not _valid_timestamp(cell["observedAt"])
            or cell["sourceCommit"] != release_commit
            or cell["artifactFile"] != expected_artifact
            or cell["artifactSha256"] != expected_digest
            or cell["blenderArchiveUrl"] != host_policy["archive_url"]
            or cell["blenderArchiveSha256"] != host_policy["archive_sha256"]
            or cell["blenderBuildHash"] != host_policy["build_hash"]
            or cell["blenderPythonVersion"] != host_policy["python_version"]
            or not isinstance(cell["blenderExecutableSha256"], str)
            or not re.fullmatch(r"[0-9a-f]{64}", cell["blenderExecutableSha256"])
            or cell["hostSystem"] != host_policy["system"]
            or cell["hostMachine"] != host_policy["machine"]
            or cell["runnerImage"] != host_policy["runner_image"]
            or not isinstance(cell["runnerImageVersion"], str)
            or not re.fullmatch(r"[A-Za-z0-9._+-]{1,128}", cell["runnerImageVersion"])
            or not isinstance(cell["tests"], list)
            or cell["tests"] != required_tests
        ):
            raise RuntimeError(f"native evidence cell failed immutable pass validation: {key}")
        run_urls.add(cell["runUrl"])
        normalized.append(
            {
                **cell,
                "tests": required_tests,
            }
        )
    if seen != expected_cells:
        raise RuntimeError(f"native evidence is missing cells: {sorted(expected_cells - seen)}")
    if len(run_urls) != 1:
        raise RuntimeError("native evidence cells must come from one workflow run attempt")
    order = {
        (blender_version, platform_name): index
        for index, (blender_version, platform_name) in enumerate(
            (blender_version, platform_name)
            for blender_version in config["blender_versions"]
            for platform_name in config["platforms"]
        )
    }
    return sorted(
        normalized,
        key=lambda cell: order[(cell["blenderVersion"], cell["platform"])],
    )


def template(release_dir: Path) -> dict[str, Any]:
    context = release_context()
    evidence, checksums = load_base_release(release_dir, context)
    cells = []
    host_policies = {
        (item["blender_version"], item["platform"]): item for item in context["config"]["hosts"]
    }
    for blender_version in context["config"]["blender_versions"]:
        for platform_name in context["config"]["platforms"]:
            artifact = context["artifact_names"][platform_name]
            host_policy = host_policies[(blender_version, platform_name)]
            cells.append(
                {
                    "blenderVersion": blender_version,
                    "platform": platform_name,
                    "status": "pending",
                    "runUrl": "",
                    "observedAt": "",
                    "sourceCommit": evidence["releaseCommit"],
                    "artifactFile": artifact,
                    "artifactSha256": checksums[artifact],
                    "blenderArchiveUrl": host_policy["archive_url"],
                    "blenderArchiveSha256": host_policy["archive_sha256"],
                    "blenderBuildHash": host_policy["build_hash"],
                    "blenderPythonVersion": host_policy["python_version"],
                    "blenderExecutableSha256": "",
                    "hostSystem": host_policy["system"],
                    "hostMachine": host_policy["machine"],
                    "runnerImage": host_policy["runner_image"],
                    "runnerImageVersion": "",
                    "tests": context["config"]["required_tests"],
                }
            )
    return {
        "schemaVersion": 1,
        "releaseCommit": evidence["releaseCommit"],
        "cells": cells,
    }


def merge_cells(release_dir: Path, input_dir: Path) -> dict[str, Any]:
    """Merge six independently produced cell objects after full validation."""
    context = release_context()
    evidence, checksums = load_base_release(release_dir, context)
    if input_dir.is_symlink() or not input_dir.is_dir():
        raise RuntimeError("native cell input must be a non-symbolic-link directory")
    members = list(input_dir.iterdir())
    if not members or any(
        item.is_symlink() or not item.is_file() or item.suffix != ".json" for item in members
    ):
        raise RuntimeError("native cell input directory must contain only regular JSON files")
    cells: list[dict[str, Any]] = []
    for path in sorted(members):
        try:
            cell = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"native cell is not valid UTF-8 JSON: {path.name}") from exc
        if not isinstance(cell, dict):
            raise RuntimeError(f"native cell must be a JSON object: {path.name}")
        cells.append(cell)
    normalized = validate_cells(
        {
            "schemaVersion": 1,
            "releaseCommit": evidence["releaseCommit"],
            "cells": cells,
        },
        context=context,
        release_commit=evidence["releaseCommit"],
        artifact_checksums=checksums,
    )
    return {
        "schemaVersion": 1,
        "releaseCommit": evidence["releaseCommit"],
        "cells": normalized,
    }


def publication_names(context: dict[str, Any]) -> set[str]:
    return context["base_names"] | {
        context["config"]["attestation_filename"],
        context["config"]["publication_checksums_filename"],
    }


def verify_publication(release_dir: Path) -> None:
    context = release_context()
    expected_names = publication_names(context)
    recover_interrupted_promotion(
        release_dir,
        (
            context["base_names"],
            (expected_names, context["config"]["publication_checksums_filename"]),
        ),
    )
    actual_names = {item.name for item in release_dir.iterdir()}
    if actual_names != expected_names:
        raise RuntimeError("publication release-set inventory is incomplete or contains extras")
    for member in release_dir.iterdir():
        if member.is_symlink() or not member.is_file():
            raise RuntimeError(f"publication member must be a regular file: {member.name}")
    evidence, base_records = load_base_release(
        release_dir,
        context,
        allow_publication_members=True,
    )
    attestation_name = context["config"]["attestation_filename"]
    attestation = json.loads((release_dir / attestation_name).read_text(encoding="utf-8"))
    expected_attestation_fields = {
        "schemaVersion",
        "type",
        "extensionId",
        "version",
        "releaseLabel",
        "releaseCommit",
        "baseChecksumsFile",
        "baseChecksumsSha256",
        "cells",
    }
    if set(attestation) != expected_attestation_fields:
        raise RuntimeError("native test attestation has missing or unexpected fields")
    if (
        attestation["schemaVersion"] != 1
        or attestation["type"] != "VAO Blender native installed-extension test attestation"
        or attestation["extensionId"] != context["manifest"]["id"]
        or attestation["version"] != context["manifest"]["version"]
        or attestation["releaseLabel"] != context["release"]["release_label"]
        or attestation["releaseCommit"] != evidence["releaseCommit"]
        or attestation["baseChecksumsFile"] != "SHA256SUMS"
        or attestation["baseChecksumsSha256"] != sha256(release_dir / "SHA256SUMS")
    ):
        raise RuntimeError("native test attestation identity is inconsistent")
    validate_cells(
        {
            "schemaVersion": attestation["schemaVersion"],
            "releaseCommit": attestation["releaseCommit"],
            "cells": attestation["cells"],
        },
        context=context,
        release_commit=evidence["releaseCommit"],
        artifact_checksums=base_records,
    )
    publication_checksum_name = context["config"]["publication_checksums_filename"]
    verify_checksum_inventory(
        release_dir,
        publication_checksum_name,
        expected_names - {publication_checksum_name},
    )


def assemble(release_dir: Path, input_path: Path, *, overwrite: bool) -> None:
    context = release_context()
    recover_interrupted_promotion(
        release_dir,
        (
            context["base_names"],
            (
                publication_names(context),
                context["config"]["publication_checksums_filename"],
            ),
        ),
    )
    if release_dir.is_symlink() or not release_dir.is_dir():
        raise RuntimeError("release directory must be an existing non-symbolic-link directory")
    actual_names = {item.name for item in release_dir.iterdir()}
    allow_publication_members = False
    if actual_names == publication_names(context):
        if not overwrite:
            raise RuntimeError("native publication evidence already exists; pass --overwrite")
        verify_publication(release_dir)
        allow_publication_members = True
    elif actual_names == context["base_names"]:
        pass
    else:
        raise RuntimeError("release directory is neither an exact base nor publication release set")
    evidence, base_records = load_base_release(
        release_dir,
        context,
        allow_publication_members=allow_publication_members,
    )
    try:
        input_data = json.loads(input_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("native evidence input is not valid UTF-8 JSON") from exc
    if not isinstance(input_data, dict):
        raise RuntimeError("native evidence input must be a JSON object")
    cells = validate_cells(
        input_data,
        context=context,
        release_commit=evidence["releaseCommit"],
        artifact_checksums=base_records,
    )
    attestation = {
        "schemaVersion": 1,
        "type": "VAO Blender native installed-extension test attestation",
        "extensionId": context["manifest"]["id"],
        "version": context["manifest"]["version"],
        "releaseLabel": context["release"]["release_label"],
        "releaseCommit": evidence["releaseCommit"],
        "baseChecksumsFile": "SHA256SUMS",
        "baseChecksumsSha256": sha256(release_dir / "SHA256SUMS"),
        "cells": cells,
    }
    staging = Path(
        tempfile.mkdtemp(prefix=f".{release_dir.name}.native-evidence-", dir=release_dir.parent)
    )
    promoted = False
    try:
        for name in context["base_names"]:
            shutil.copyfile(release_dir / name, staging / name)
        attestation_name = context["config"]["attestation_filename"]
        (staging / attestation_name).write_text(
            json.dumps(attestation, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        publication_checksum_name = context["config"]["publication_checksums_filename"]
        checksum_names = publication_names(context) - {publication_checksum_name}
        checksum_text = "".join(
            f"{sha256(staging / name)}  {name}\n" for name in sorted(checksum_names)
        )
        (staging / publication_checksum_name).write_text(checksum_text, encoding="ascii")
        verify_publication(staging)
        promote_release_directory(staging, release_dir, overwrite=True)
        promoted = True
    finally:
        if not promoted and staging.exists():
            shutil.rmtree(staging)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in ("template", "verify"):
        command = subparsers.add_parser(name)
        command.add_argument("--release-dir", type=Path, required=True)
    merge_parser = subparsers.add_parser("merge")
    merge_parser.add_argument("--release-dir", type=Path, required=True)
    merge_parser.add_argument("--input-dir", type=Path, required=True)
    assemble_parser = subparsers.add_parser("assemble")
    assemble_parser.add_argument("--release-dir", type=Path, required=True)
    assemble_parser.add_argument("--input", type=Path, required=True)
    assemble_parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    release_dir = args.release_dir.expanduser().absolute()
    if args.command == "template":
        print(json.dumps(template(release_dir), indent=2, sort_keys=True))
    elif args.command == "merge":
        print(
            json.dumps(
                merge_cells(release_dir, args.input_dir.expanduser().absolute()),
                indent=2,
                sort_keys=True,
            )
        )
    elif args.command == "verify":
        verify_publication(release_dir)
        print(f"Native publication evidence verified: {release_dir}")
    else:
        assemble(release_dir, args.input.expanduser().absolute(), overwrite=args.overwrite)
        print(f"Native publication evidence assembled: {release_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
