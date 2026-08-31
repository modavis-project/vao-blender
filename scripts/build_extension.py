#!/usr/bin/env python3
"""Audit, build, validate, and checksum Blender extension release artifacts."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import platform
import shutil
import stat
import subprocess
import sys
import tempfile
import tomllib
import unicodedata
import zipfile
from pathlib import Path, PurePosixPath

ZIP_EPOCH = (1980, 1, 1, 0, 0, 0)
# One day after the ZIP epoch in UTC remains representable in every civil time
# zone. Blender's builder reads filesystem mtimes before our canonical ZIP
# normalization pass, so release input must not inherit older checkout mtimes.
ZIP_SAFE_MTIME = 315_619_200
PLATFORM_WHEEL_MARKERS = {
    "windows-x64": "win_amd64",
    "macos-arm64": "macosx_11_0_arm64",
    "linux-x64": "manylinux_2_17_x86_64",
}
PACKAGED_ROOT_FILES = {
    "CHANGELOG.md",
    "CITATION.cff",
    "LICENSE",
    "README.md",
    "RELEASE_NOTES.md",
    "SECURITY.md",
    "SUPPORT.md",
    "THIRD_PARTY_NOTICES.md",
    "__init__.py",
    "blender_manifest.toml",
}


def packaged_source_members(source_root: Path, declared_wheels: set[str]) -> set[str]:
    """Return the exact source inventory Blender is permitted to package."""
    expected_members = {name for name in PACKAGED_ROOT_FILES if (source_root / name).is_file()}
    for top_level in ("contract", "vao_blender"):
        for path in (source_root / top_level).rglob("*"):
            if path.is_symlink():
                raise RuntimeError(f"packaged source contains a symbolic link: {path}")
            if path.is_file() and "__pycache__" not in path.parts:
                expected_members.add(path.relative_to(source_root).as_posix())
    expected_members.update(declared_wheels)
    wheel_inventory = source_root / "wheels" / "WHEELS_SHA256"
    if wheel_inventory.is_file():
        expected_members.add("wheels/WHEELS_SHA256")
    return expected_members


def materialize_build_source(
    source_root: Path,
    destination: Path,
    *,
    declared_wheels: set[str],
    tracked_members: set[str],
) -> set[str]:
    """Copy exact tracked package inputs with universally ZIP-safe mtimes."""
    if destination.is_symlink() or not destination.is_dir() or any(destination.iterdir()):
        raise RuntimeError("release build-source destination must be an empty regular directory")
    expected_members = packaged_source_members(source_root, declared_wheels)
    if not expected_members.issubset(tracked_members):
        untracked = sorted(expected_members - tracked_members)
        raise RuntimeError(
            "artifact source inventory includes untracked/ignored files: " + ", ".join(untracked)
        )
    created_directories = {destination}
    for name in sorted(expected_members):
        source = source_root / name
        if source.is_symlink() or not source.is_file():
            raise RuntimeError(f"packaged source member is not a regular file: {name}")
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        created_directories.update(target.parents)
        shutil.copyfile(source, target)
        target.chmod(source.stat().st_mode & 0o777)
        os.utime(target, (ZIP_SAFE_MTIME, ZIP_SAFE_MTIME))
    for directory in sorted(created_directories, key=lambda item: len(item.parts), reverse=True):
        if directory == destination or destination in directory.parents:
            directory.chmod(0o755)
            os.utime(directory, (ZIP_SAFE_MTIME, ZIP_SAFE_MTIME))
    return expected_members


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


def git_tracked_files(root: Path) -> set[str]:
    result = subprocess.run(
        ("git", "ls-files", "-z"),
        cwd=root,
        check=True,
        capture_output=True,
    )
    try:
        output = result.stdout.decode("utf-8")
    except UnicodeError as exc:
        raise RuntimeError("release source paths must be valid UTF-8") from exc
    return {name for name in output.split("\0") if name}


def verify_clean_checkout(root: Path) -> str:
    status = git_output(root, "status", "--porcelain", "--untracked-files=all")
    if status:
        raise RuntimeError("release builds require a clean Git worktree")
    return git_output(root, "rev-parse", "HEAD")


def verify_release_checkout(root: Path, release_tag: str) -> str:
    head = verify_clean_checkout(root)

    tag_type = git_output(root, "cat-file", "-t", release_tag)
    if tag_type != "tag":
        raise RuntimeError(f"release tag must be annotated: {release_tag}")
    tag_commit = git_output(root, "rev-list", "-n", "1", release_tag)
    if tag_commit != head:
        raise RuntimeError(f"release tag {release_tag} does not point at HEAD")
    return head


def create_source_archive(
    root: Path,
    revision: str,
    release_label: str,
    destination: Path,
) -> None:
    prefix = f"vao-blender-{release_label}/"
    with destination.open("wb") as handle:
        subprocess.run(
            (
                "git",
                "archive",
                "--format=zip",
                f"--prefix={prefix}",
                revision,
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
    """Rewrite a ZIP into a platform- and zlib-independent canonical form."""
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
            destination.comment = b""
            for original in sorted(source.infolist(), key=lambda item: item.filename):
                normalized = zipfile.ZipInfo(original.filename, date_time=ZIP_EPOCH)
                normalized.compress_type = zipfile.ZIP_STORED
                normalized.create_system = 3
                normalized.create_version = 20
                normalized.extract_version = 20
                normalized.internal_attr = 0
                original_mode = original.external_attr >> 16
                permissions = 0o755 if original.is_dir() or original_mode & 0o111 else 0o644
                file_type = stat.S_IFDIR if original.is_dir() else stat.S_IFREG
                normalized.external_attr = (file_type | permissions) << 16
                normalized.comment = b""
                destination.writestr(
                    normalized,
                    source.read(original),
                    compress_type=zipfile.ZIP_STORED,
                )
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def verify_artifact_contents(
    artifact: Path,
    *,
    extension_id: str,
    version: str,
    expected_platforms: set[str],
    expected_wheels: set[str],
    split: bool,
    source_root: Path | None = None,
    tracked_members: set[str] | None = None,
) -> list[str]:
    """Check the built archive identity, platform split, and unsafe residue."""
    with zipfile.ZipFile(artifact, "r") as archive:
        entries = archive.infolist()
        names = [item.filename for item in entries]
        if len(names) != len(set(names)):
            raise RuntimeError(f"duplicate ZIP member in {artifact.name}")
        portable_names: set[str] = set()
        for item in entries:
            portable_name = unicodedata.normalize("NFC", item.filename).casefold()
            if portable_name in portable_names:
                raise RuntimeError(f"portable-name collision in {artifact.name}")
            portable_names.add(portable_name)
            unix_mode = item.external_attr >> 16
            if item.flag_bits & 0x1 or (unix_mode and stat.S_ISLNK(unix_mode)):
                raise RuntimeError(f"encrypted or symbolic-link member in {artifact.name}")
        if any(
            PurePosixPath(name).is_absolute()
            or any(part in {"", ".", ".."} for part in PurePosixPath(name).parts)
            or "\\" in name
            or name.endswith((".pyc", ".pyo"))
            or name.startswith(("build/", "dist/", "docs/", "scripts/", "tests/", "tmp/"))
            for name in names
        ):
            raise RuntimeError(f"unsafe or development-only member in {artifact.name}")
        try:
            built_manifest = tomllib.loads(archive.read("blender_manifest.toml").decode("utf-8"))
        except (KeyError, UnicodeError, tomllib.TOMLDecodeError) as exc:
            raise RuntimeError(f"cannot read built manifest from {artifact.name}") from exc
        if built_manifest.get("id") != extension_id or built_manifest.get("version") != version:
            raise RuntimeError(f"built manifest identity mismatch in {artifact.name}")
        if source_root is not None:
            try:
                source_manifest = tomllib.loads(
                    (source_root / "blender_manifest.toml").read_text(encoding="utf-8")
                )
            except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
                raise RuntimeError("cannot read the reviewed source manifest") from exc
            reviewed_built_manifest = copy.deepcopy(built_manifest)
            build = reviewed_built_manifest.get("build")
            if not isinstance(build, dict):
                raise RuntimeError(f"built manifest has no valid build table in {artifact.name}")
            generated_manifest = build.pop("generated", None)
            if split and not isinstance(generated_manifest, dict):
                raise RuntimeError(
                    f"split artifact lacks Blender's generated manifest inventory: {artifact.name}"
                )
            if reviewed_built_manifest != source_manifest:
                raise RuntimeError(
                    f"built manifest differs from reviewed source outside [build.generated]: "
                    f"{artifact.name}"
                )
        generated = built_manifest.get("build", {}).get("generated", {})
        platforms = generated.get("platforms", built_manifest.get("platforms", []))
        wheels = generated.get("wheels", built_manifest.get("wheels", []))
        if not platforms or not all(isinstance(platform, str) for platform in platforms):
            raise RuntimeError(f"artifact has no valid platform declaration in {artifact.name}")
        if split and len(platforms) != 1:
            raise RuntimeError(f"split artifact has no unique platform in {artifact.name}")
        if not split and set(platforms) != expected_platforms:
            raise RuntimeError(f"combined artifact platform inventory mismatch in {artifact.name}")
        expected_name = (
            f"{extension_id}-{version}-{platforms[0].replace('-', '_')}.zip"
            if split
            else f"{extension_id}-{version}.zip"
        )
        if artifact.name != expected_name:
            raise RuntimeError(
                f"artifact filename does not match its platform declaration: "
                f"expected {expected_name}, found {artifact.name}"
            )
        expected_native_wheels = 1 if split else len(expected_platforms)
        if len([wheel for wheel in wheels if "rpds_py-" in str(wheel)]) != expected_native_wheels:
            raise RuntimeError(f"native rpds-py wheel inventory mismatch in {artifact.name}")
        declared_wheels = {str(wheel).removeprefix("./") for wheel in wheels}
        archived_wheels = {
            name for name in names if name.startswith("wheels/") and name.endswith(".whl")
        }
        if declared_wheels != archived_wheels:
            raise RuntimeError(f"built wheel inventory mismatch in {artifact.name}")
        pure_wheels = {wheel for wheel in expected_wheels if "rpds_py-" not in wheel}
        expected_native = {
            wheel
            for wheel in expected_wheels
            if any(
                PLATFORM_WHEEL_MARKERS[platform] in wheel
                for platform in platforms
                if platform in PLATFORM_WHEEL_MARKERS
            )
        }
        if set(platforms) - PLATFORM_WHEEL_MARKERS.keys():
            raise RuntimeError(f"unknown platform in built manifest: {artifact.name}")
        if declared_wheels != pure_wheels | expected_native:
            raise RuntimeError(f"platform-specific wheel selection mismatch in {artifact.name}")
        if source_root is not None:
            expected_members = packaged_source_members(source_root, declared_wheels)
            if tracked_members is not None and not expected_members.issubset(tracked_members):
                untracked = sorted(expected_members - tracked_members)
                raise RuntimeError(
                    "artifact source inventory includes untracked/ignored files: "
                    + ", ".join(untracked)
                )
            if set(names) != expected_members:
                unexpected = sorted(set(names) - expected_members)
                missing = sorted(expected_members - set(names))
                raise RuntimeError(
                    f"artifact source inventory mismatch in {artifact.name}; "
                    f"unexpected={unexpected}, missing={missing}"
                )
            for name in sorted(expected_members - {"blender_manifest.toml"}):
                if archive.read(name) != (source_root / name).read_bytes():
                    raise RuntimeError(f"artifact member differs from reviewed source: {name}")
        return sorted(platforms)


def probe_builder(blender: Path, expected: dict[str, object]) -> dict[str, object]:
    """Reject non-canonical release builders and return deterministic provenance."""
    driver_version = platform.python_version()
    if driver_version != expected.get("driver_python_version"):
        raise RuntimeError(
            "release builder requires driver Python "
            f"{expected.get('driver_python_version')}, found {driver_version}"
        )
    marker = "VAO_BUILDER_PROVENANCE="
    expression = (
        "import bpy,json,platform,sys,zlib;"
        f"print({marker!r}+json.dumps({{"
        "'blenderVersion':'.'.join(str(item) for item in bpy.app.version),"
        "'blenderVersionTuple':list(bpy.app.version),"
        "'blenderBuildHash':bpy.app.build_hash.decode('ascii','replace'),"
        "'pythonVersion':platform.python_version(),"
        "'pythonImplementation':platform.python_implementation(),"
        "'system':platform.system(),"
        "'machine':platform.machine(),"
        "'zlibCompileVersion':zlib.ZLIB_VERSION,"
        "'zlibRuntimeVersion':zlib.ZLIB_RUNTIME_VERSION"
        "},sort_keys=True))"
    )
    try:
        result = subprocess.run(
            (
                str(blender),
                "--background",
                "--factory-startup",
                "--python-exit-code",
                "1",
                "--python-expr",
                expression,
            ),
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        detail = "\n".join(part.strip() for part in (exc.stdout, exc.stderr) if part).strip()
        if len(detail) > 4000:
            detail = detail[-4000:]
        raise RuntimeError(
            f"Blender builder provenance probe exited with status {exc.returncode}"
            + (f":\n{detail}" if detail else "")
        ) from exc
    line = next((item for item in result.stdout.splitlines() if item.startswith(marker)), None)
    if line is None:
        raise RuntimeError("Blender did not report canonical builder provenance")
    try:
        actual = json.loads(line.removeprefix(marker))
    except json.JSONDecodeError as exc:
        raise RuntimeError("Blender reported malformed builder provenance") from exc
    required = {
        "blenderVersion": expected.get("blender_version"),
        "blenderBuildHash": expected.get("blender_build_hash"),
        "pythonVersion": expected.get("blender_python_version"),
        "system": expected.get("platform_system"),
        "machine": expected.get("platform_machine"),
    }
    mismatches = {
        name: {"expected": value, "actual": actual.get(name)}
        for name, value in required.items()
        if actual.get(name) != value
    }
    if mismatches:
        raise RuntimeError(
            "release builder does not match release_metadata.toml: "
            + json.dumps(mismatches, sort_keys=True)
        )
    executable_digest = sha256(blender)
    if executable_digest != expected.get("blender_executable_sha256"):
        raise RuntimeError(
            "release Blender executable does not match the binary extracted from the pinned "
            "official archive"
        )
    return {
        **actual,
        "blenderExecutableSha256": executable_digest,
        "driverPythonImplementation": platform.python_implementation(),
        "driverPythonVersion": driver_version,
        "pinnedOfficialArchiveSha256": expected.get("official_archive_sha256"),
        "pinnedOfficialArchiveUrl": expected.get("official_archive_url"),
        "executableMatchesPinnedOfficialArchive": True,
        "archiveNormalization": "sorted ZIP_STORED entries; 1980-01-01; POSIX 0644/0755",
    }


def recover_interrupted_promotion(
    output_dir: Path,
    allowed_inventories: tuple[set[str] | tuple[set[str], str], ...],
) -> None:
    """Restore one checksum-verified backup only when the canonical path is absent."""
    backup_prefix = f".{output_dir.name}.previous-"
    backups = (
        sorted(item for item in output_dir.parent.iterdir() if item.name.startswith(backup_prefix))
        if output_dir.parent.is_dir()
        else []
    )
    if backups:
        if output_dir.exists() or output_dir.is_symlink() or len(backups) != 1:
            raise RuntimeError(
                "interrupted release replacement requires manual recovery; "
                f"preserved backups={[str(item) for item in backups]}"
            )
        backup = backups[0]
        if backup.is_symlink() or not backup.is_dir():
            raise RuntimeError("interrupted release backup is not a regular directory")
        verified = False
        for inventory in allowed_inventories:
            if isinstance(inventory, tuple):
                allowed_names, checksum_filename = inventory
            else:
                allowed_names, checksum_filename = inventory, "SHA256SUMS"
            try:
                verify_release_set(
                    backup,
                    allowed_names,
                    checksum_filename=checksum_filename,
                )
            except (OSError, RuntimeError):
                continue
            verified = True
            break
        if not verified:
            raise RuntimeError("interrupted release backup failed every owned inventory")
        os.replace(backup, output_dir)


def inspect_output_directory(output_dir: Path, *, overwrite: bool, allowed_names: set[str]) -> None:
    """Recover a verified interrupted backup, then refuse ambiguous targets."""
    recover_interrupted_promotion(output_dir, (allowed_names,))
    if output_dir.is_symlink():
        raise RuntimeError("release output directory must not be a symbolic link")
    if not output_dir.exists():
        return
    if not output_dir.is_dir():
        raise RuntimeError("release output path exists and is not a directory")
    entries = list(output_dir.iterdir())
    if not overwrite:
        raise RuntimeError("release output already exists; pass --overwrite to replace it")
    actual_names = {item.name for item in entries}
    if entries and actual_names != allowed_names:
        raise RuntimeError(
            "release output directory is not an exact owned release set; "
            f"unexpected={sorted(actual_names - allowed_names)}, "
            f"missing={sorted(allowed_names - actual_names)}"
        )
    if entries:
        verify_release_set(output_dir, allowed_names)


def verify_release_set(
    release_dir: Path,
    expected_names: set[str],
    *,
    checksum_filename: str = "SHA256SUMS",
) -> None:
    """Verify the complete promoted-file inventory and its detached checksums."""
    actual_names = {item.name for item in release_dir.iterdir()}
    if actual_names != expected_names:
        raise RuntimeError(
            "assembled release-set inventory mismatch; "
            f"unexpected={sorted(actual_names - expected_names)}, "
            f"missing={sorted(expected_names - actual_names)}"
        )
    for item in release_dir.iterdir():
        if item.is_symlink() or not item.is_file():
            raise RuntimeError(f"release-set member must be a regular file: {item.name}")
    if checksum_filename not in expected_names:
        raise RuntimeError("release-set checksum file is absent from the expected inventory")
    checksum_path = release_dir / checksum_filename
    checksum_records: dict[str, str] = {}
    for line in checksum_path.read_text(encoding="ascii").splitlines():
        match = line.split("  ", 1)
        if len(match) != 2 or len(match[0]) != 64 or match[1] in checksum_records:
            raise RuntimeError(f"{checksum_filename} contains malformed or duplicate records")
        checksum_records[match[1]] = match[0]
    expected_checksums = expected_names - {checksum_filename}
    if set(checksum_records) != expected_checksums:
        raise RuntimeError(
            f"{checksum_filename} does not exactly inventory the detached release files"
        )
    for name, expected in checksum_records.items():
        if sha256(release_dir / name) != expected:
            raise RuntimeError(f"release-set checksum mismatch: {name}")


def promote_release_directory(staging_dir: Path, output_dir: Path, *, overwrite: bool) -> None:
    """Transactionally replace a set with ordinary-error rollback and crash recovery."""
    if output_dir.exists():
        if not overwrite:
            raise RuntimeError("release output already exists")
        backup_dir = output_dir.parent / f".{output_dir.name}.previous-{os.getpid()}"
        if backup_dir.exists() or backup_dir.is_symlink():
            raise RuntimeError(f"release backup path already exists: {backup_dir}")
        os.replace(output_dir, backup_dir)
        try:
            os.replace(staging_dir, output_dir)
        except Exception:
            try:
                os.replace(backup_dir, output_dir)
            except Exception as rollback_exc:
                raise RuntimeError(
                    f"release promotion and rollback failed; previous set retained at {backup_dir}"
                ) from rollback_exc
            raise
        shutil.rmtree(backup_dir)
    else:
        os.replace(staging_dir, output_dir)


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    release = tomllib.loads((root / "release_metadata.toml").read_text(encoding="utf-8"))
    release_tag = str(release["release_tag"])
    release_label = str(release["release_label"])
    default_blender = Path(
        os.environ.get("VAO_BLENDER_BIN", "/Applications/Blender.app/Contents/MacOS/Blender")
    )
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--blender", type=Path, default=default_blender)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=root / "dist" / "release-candidate" / release_label,
    )
    parser.add_argument(
        "--release-tag",
        default=release_tag,
        help=f"Annotated tag to package (must be {release_tag}).",
    )
    parser.add_argument(
        "--staging",
        action="store_true",
        help="Build the clean current commit before its release tag exists; evidence stays unreleased.",
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
    if args.release_tag != release_tag:
        parser.error("--release-tag must match the canonical release_metadata.toml identity")
    if not args.staging and release["status"] == "unreleased":
        parser.error("final tagged builds require prerelease/published canonical metadata")

    manifest = tomllib.loads((root / "blender_manifest.toml").read_text(encoding="utf-8"))
    extension_id = str(manifest["id"])
    version = str(manifest["version"])
    if version != release["extension_version"]:
        parser.error("manifest version does not match release_metadata.toml")
    expected_prefix = f"{extension_id}-{version}"
    source_archive_name = f"vao-blender-{release_label}-source.zip"
    expected_platforms = {str(item) for item in manifest.get("platforms", [])}
    expected_wheels = {str(item).removeprefix("./") for item in manifest.get("wheels", [])}
    artifact_names = (
        {f"{expected_prefix}.zip"}
        if args.single_package
        else {
            f"{expected_prefix}-{platform_name.replace('-', '_')}.zip"
            for platform_name in expected_platforms
        }
    )
    detached_names = {
        source_archive_name,
        "SBOM.spdx.json",
        "RELEASE_NOTES.md",
        "release_metadata.toml",
        "RELEASE_EVIDENCE.json",
    }
    release_names = artifact_names | detached_names | {"SHA256SUMS"}

    if args.staging:
        release_commit = verify_clean_checkout(root)
        source_revision = release_commit
        evidence_tag = None
    else:
        release_commit = verify_release_checkout(root, args.release_tag)
        source_revision = args.release_tag
        evidence_tag = args.release_tag
    tracked_members = git_tracked_files(root)

    output_dir = args.output_dir.expanduser().absolute()
    resolved_output = output_dir.resolve(strict=False)
    resolved_root = root.resolve()
    if resolved_output == resolved_root or resolved_output in resolved_root.parents:
        parser.error("output directory must not be the repository or one of its ancestors")
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    try:
        inspect_output_directory(
            output_dir,
            overwrite=args.overwrite,
            allowed_names=release_names,
        )
    except RuntimeError as exc:
        parser.error(str(exc))

    run(sys.executable, str(root / "scripts" / "release_audit.py"))
    builder = release.get("builder")
    if not isinstance(builder, dict):
        raise RuntimeError("release_metadata.toml is missing canonical [builder] metadata")
    builder_provenance = probe_builder(args.blender, builder)
    run(str(args.blender), "--command", "extension", "validate", str(root))
    build_source_dir = Path(tempfile.mkdtemp(prefix=f".{extension_id}-build-source-"))
    staging_dir = Path(
        tempfile.mkdtemp(prefix=f".{output_dir.name}.staging-", dir=output_dir.parent)
    )
    promoted = False
    try:
        materialize_build_source(
            root,
            build_source_dir,
            declared_wheels=expected_wheels,
            tracked_members=tracked_members,
        )
        run(str(args.blender), "--command", "extension", "validate", str(build_source_dir))
        build_command = [
            str(args.blender),
            "--command",
            "extension",
            "build",
            "--source-dir",
            str(build_source_dir),
            "--output-dir",
            str(staging_dir),
        ]
        if not args.single_package:
            build_command.append("--split-platforms")
        run(*build_command)

        artifacts = sorted(staging_dir.glob(f"{expected_prefix}*.zip"))
        expected_count = 1 if args.single_package else len(expected_platforms)
        if len(artifacts) != expected_count:
            raise RuntimeError(
                f"expected {expected_count} release artifact(s), found {len(artifacts)}"
            )

        records: list[dict[str, object]] = []
        for artifact in artifacts:
            normalize_archive(artifact)
            run(str(args.blender), "--command", "extension", "validate", str(artifact))
            platforms = verify_artifact_contents(
                artifact,
                extension_id=extension_id,
                version=version,
                expected_platforms=expected_platforms,
                expected_wheels=expected_wheels,
                split=not args.single_package,
                source_root=root,
                tracked_members=tracked_members,
            )
            records.append(
                {
                    "file": artifact.name,
                    "kind": "blender-extension",
                    "platforms": platforms,
                    "bytes": artifact.stat().st_size,
                    "sha256": sha256(artifact),
                }
            )

        source_archive = staging_dir / source_archive_name
        create_source_archive(root, source_revision, release_label, source_archive)
        supporting_files = (
            (source_archive, "source"),
            (staging_dir / "SBOM.spdx.json", "release-set-sbom"),
            (staging_dir / "RELEASE_NOTES.md", "release-notes"),
            (staging_dir / "release_metadata.toml", "release-metadata"),
        )
        shutil.copyfile(root / "SBOM.spdx.json", supporting_files[1][0])
        shutil.copyfile(root / "RELEASE_NOTES.md", supporting_files[2][0])
        shutil.copyfile(root / "release_metadata.toml", supporting_files[3][0])
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

        evidence = {
            "extensionId": extension_id,
            "releaseCommit": release_commit,
            "releaseLabel": release_label,
            "releaseStatus": release["status"],
            "releaseTag": evidence_tag,
            "intendedReleaseTag": release_tag,
            "releaseDOI": release["release_doi"] or None,
            "releaseDate": release["release_date"] or None,
            "version": version,
            "blenderCompatibility": release["blender"],
            "builder": builder_provenance,
            "splitPlatforms": not args.single_package,
            "platforms": manifest.get("platforms", []),
            "standards": {
                "published": release["vao_standard"]["published"],
                "candidate": release["vao_standard"]["candidate"],
            },
            "nativeEvidenceRequired": release["native_evidence"],
            "filesExceptEvidenceAndChecksumList": records,
        }
        evidence_path = staging_dir / "RELEASE_EVIDENCE.json"
        evidence_path.write_text(
            json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        checksum_records = [
            *records,
            {
                "file": evidence_path.name,
                "kind": "release-evidence",
                "bytes": evidence_path.stat().st_size,
                "sha256": sha256(evidence_path),
            },
        ]
        checksum_records.sort(key=lambda item: str(item["file"]))
        checksum_text = "".join(f"{item['sha256']}  {item['file']}\n" for item in checksum_records)
        (staging_dir / "SHA256SUMS").write_text(checksum_text, encoding="ascii")
        verify_release_set(staging_dir, release_names)
        promote_release_directory(staging_dir, output_dir, overwrite=args.overwrite)
        promoted = True
    finally:
        if not promoted and staging_dir.exists():
            shutil.rmtree(staging_dir)
        if build_source_dir.exists():
            shutil.rmtree(build_source_dir)

    print(f"Validated {len(artifact_names)} release artifact(s) in {output_dir}")
    print((output_dir / "SHA256SUMS").read_text(encoding="ascii"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
