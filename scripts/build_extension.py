#!/usr/bin/env python3
"""Audit, build, validate, and checksum Blender extension release artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import tomllib
import zipfile
from pathlib import Path

ZIP_EPOCH = (1980, 1, 1, 0, 0, 0)
DEFAULT_RELEASE_TAG = "v0.3.0-rc.1"
RELEASE_DOI = "10.5281/zenodo.22134389"
STANDARD_DOI = "10.5281/zenodo.22122774"
STANDARD_RELEASE = "v0.4.0"
STANDARD_SOURCE_SHA256 = "2acbda0a257c7f71e2b57e01617678745de2ecf11197b4687aa623f71d23955d"


def run(*args: str) -> None:
    subprocess.run(args, check=True)


def git_output(root: Path, *args: str) -> str:
    return subprocess.run(
        ("git", *args),
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def verify_release_checkout(root: Path, release_tag: str) -> str:
    status = git_output(root, "status", "--porcelain", "--untracked-files=all")
    if status:
        raise RuntimeError("release builds require a clean Git worktree")

    head = git_output(root, "rev-parse", "HEAD")
    tag_type = git_output(root, "cat-file", "-t", release_tag)
    if tag_type != "tag":
        raise RuntimeError(f"release tag must be annotated: {release_tag}")
    tag_commit = git_output(root, "rev-list", "-n", "1", release_tag)
    if tag_commit != head:
        raise RuntimeError(f"release tag {release_tag} does not point at HEAD")
    return head


def create_source_archive(root: Path, release_tag: str, destination: Path) -> None:
    prefix = f"vao-blender-{release_tag.removeprefix('v')}/"
    with destination.open("wb") as handle:
        subprocess.run(
            (
                "git",
                "archive",
                "--format=zip",
                f"--prefix={prefix}",
                release_tag,
            ),
            cwd=root,
            check=True,
            stdout=handle,
        )
    normalize_archive(destination)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def normalize_archive(path: Path) -> None:
    """Rewrite a Blender-built ZIP into a byte-reproducible canonical form."""
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".normalizing", dir=path.parent
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        with (
            zipfile.ZipFile(path, "r", allowZip64=True) as source,
            zipfile.ZipFile(
                temporary,
                "w",
                allowZip64=True,
            ) as destination,
        ):
            destination.comment = source.comment
            for original in sorted(source.infolist(), key=lambda item: item.filename):
                normalized = zipfile.ZipInfo(original.filename, date_time=ZIP_EPOCH)
                normalized.compress_type = original.compress_type
                normalized.create_system = original.create_system
                normalized.create_version = original.create_version
                normalized.extract_version = original.extract_version
                normalized.internal_attr = original.internal_attr
                normalized.external_attr = original.external_attr
                normalized.comment = original.comment
                destination.writestr(
                    normalized,
                    source.read(original),
                    compress_type=original.compress_type,
                    compresslevel=9,
                )
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    default_blender = Path(
        os.environ.get("VAO_BLENDER_BIN", "/Applications/Blender.app/Contents/MacOS/Blender")
    )
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--blender", type=Path, default=default_blender)
    parser.add_argument("--output-dir", type=Path, default=root / "dist" / "release-candidate")
    parser.add_argument(
        "--release-tag",
        default=DEFAULT_RELEASE_TAG,
        help=f"Annotated tag to package (default: {DEFAULT_RELEASE_TAG}).",
    )
    parser.add_argument(
        "--single-package",
        action="store_true",
        help="Build one multi-platform package instead of the default split artifacts.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace artifacts for the current extension version in the output directory.",
    )
    args = parser.parse_args()

    if not args.blender.is_file():
        parser.error(f"Blender executable not found: {args.blender}")

    manifest = tomllib.loads((root / "blender_manifest.toml").read_text(encoding="utf-8"))
    extension_id = str(manifest["id"])
    version = str(manifest["version"])
    expected_prefix = f"{extension_id}-{version}"
    release_label = args.release_tag.removeprefix("v")
    source_archive_name = f"vao-blender-{release_label}-source.zip"

    release_commit = verify_release_checkout(root, args.release_tag)

    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    existing = sorted(output_dir.glob(f"{expected_prefix}*.zip"))
    metadata_files = [
        output_dir / source_archive_name,
        output_dir / "SBOM.spdx.json",
        output_dir / "RELEASE_NOTES.md",
        output_dir / "SHA256SUMS",
        output_dir / "RELEASE_EVIDENCE.json",
    ]
    if (existing or any(path.exists() for path in metadata_files)) and not args.overwrite:
        parser.error("release artifacts already exist; pass --overwrite to replace this version")
    if args.overwrite:
        for path in [*existing, *metadata_files]:
            if path.exists():
                path.unlink()

    run(sys.executable, str(root / "scripts" / "release_audit.py"))
    run(str(args.blender), "--command", "extension", "validate", str(root))
    build_command = [
        str(args.blender),
        "--command",
        "extension",
        "build",
        "--source-dir",
        str(root),
        "--output-dir",
        str(output_dir),
    ]
    if not args.single_package:
        build_command.append("--split-platforms")
    run(*build_command)

    artifacts = sorted(output_dir.glob(f"{expected_prefix}*.zip"))
    expected_count = 1 if args.single_package else len(manifest.get("platforms", []))
    if len(artifacts) != expected_count:
        raise RuntimeError(f"expected {expected_count} release artifact(s), found {len(artifacts)}")

    records: list[dict[str, object]] = []
    for artifact in artifacts:
        normalize_archive(artifact)
        run(str(args.blender), "--command", "extension", "validate", str(artifact))
        records.append(
            {
                "file": artifact.name,
                "kind": "blender-extension",
                "bytes": artifact.stat().st_size,
                "sha256": sha256(artifact),
            }
        )

    source_archive = output_dir / source_archive_name
    create_source_archive(root, args.release_tag, source_archive)
    supporting_files = (
        (source_archive, "source"),
        (output_dir / "SBOM.spdx.json", "sbom"),
        (output_dir / "RELEASE_NOTES.md", "release-notes"),
    )
    shutil.copyfile(root / "SBOM.spdx.json", supporting_files[1][0])
    shutil.copyfile(root / "RELEASE_NOTES.md", supporting_files[2][0])
    for artifact, kind in supporting_files:
        records.append(
            {
                "file": artifact.name,
                "kind": kind,
                "bytes": artifact.stat().st_size,
                "sha256": sha256(artifact),
            }
        )
    records.sort(key=lambda item: str(item["file"]))

    checksum_text = "".join(f"{item['sha256']}  {item['file']}\n" for item in records)
    (output_dir / "SHA256SUMS").write_text(checksum_text, encoding="ascii")
    evidence = {
        "extensionId": extension_id,
        "releaseCommit": release_commit,
        "releaseTag": args.release_tag,
        "releaseDOI": RELEASE_DOI,
        "version": version,
        "splitPlatforms": not args.single_package,
        "platforms": manifest.get("platforms", []),
        "standard": {
            "doi": STANDARD_DOI,
            "release": STANDARD_RELEASE,
            "sourceArchiveSha256": STANDARD_SOURCE_SHA256,
        },
        "artifacts": records,
    }
    (output_dir / "RELEASE_EVIDENCE.json").write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    print(f"Validated {len(artifacts)} release artifact(s) in {output_dir}")
    print(checksum_text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
