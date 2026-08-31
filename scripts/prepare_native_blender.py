#!/usr/bin/env python3
"""Fetch, verify, extract, and probe one pinned official native Blender host."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import stat
import subprocess
import tarfile
import tempfile
import tomllib
import unicodedata
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MAX_ARCHIVE_BYTES = 1024 * 1024 * 1024
MAX_ARCHIVE_MEMBERS = 200_000
MAX_ARCHIVE_MEMBER_BYTES = 2 * 1024 * 1024 * 1024
MAX_ARCHIVE_EXPANDED_BYTES = 8 * 1024 * 1024 * 1024


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def host_policy(version: str, platform_name: str) -> tuple[dict[str, Any], dict[str, Any]]:
    release = tomllib.loads((ROOT / "release_metadata.toml").read_text(encoding="utf-8"))
    matches = [
        item
        for item in release["native_evidence"]["hosts"]
        if item["blender_version"] == version and item["platform"] == platform_name
    ]
    if len(matches) != 1:
        raise RuntimeError("requested Blender/native-platform pair is not uniquely pinned")
    return release, matches[0]


def download(policy: dict[str, Any], destination: Path) -> Path:
    url = policy["archive_url"]
    archive = destination.parent / Path(url).name
    if archive.exists() or archive.is_symlink():
        raise RuntimeError(f"refusing existing native-host archive path: {archive}")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{archive.name}.download-", dir=archive.parent
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    request = urllib.request.Request(url, headers={"User-Agent": "VAO-Blender-release-gate/1"})
    try:
        with urllib.request.urlopen(request, timeout=60) as response, temporary.open("wb") as out:
            declared = response.headers.get("Content-Length")
            if declared and int(declared) > MAX_ARCHIVE_BYTES:
                raise RuntimeError("official Blender archive exceeds the release-gate limit")
            total = 0
            for block in iter(lambda: response.read(1024 * 1024), b""):
                total += len(block)
                if total > MAX_ARCHIVE_BYTES:
                    raise RuntimeError("official Blender archive exceeds the release-gate limit")
                out.write(block)
        if sha256(temporary) != policy["archive_sha256"]:
            raise RuntimeError("official Blender archive failed its pinned SHA-256")
        os.replace(temporary, archive)
    finally:
        if temporary.exists():
            temporary.unlink()
    return archive


def safe_archive_name(name: str) -> bool:
    if not name or "\x00" in name or "\\" in name:
        return False
    path = PurePosixPath(name)
    return (
        not path.is_absolute()
        and bool(path.parts)
        and all(part not in {"", ".", ".."} for part in path.parts)
        and not re.fullmatch(r"[A-Za-z]:", path.parts[0])
    )


def _member_parts(name: str, label: str) -> tuple[str, ...]:
    if not safe_archive_name(name):
        raise RuntimeError(f"{label} contains an unsafe member")
    return PurePosixPath(name).parts


def _portable_key(parts: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(unicodedata.normalize("NFC", part).casefold() for part in parts)


def _validate_member_inventory(
    members: list[tuple[str, str, int]], label: str
) -> list[tuple[tuple[str, ...], str, int]]:
    if len(members) > MAX_ARCHIVE_MEMBERS:
        raise RuntimeError(f"{label} exceeds the member-count limit")

    records: list[tuple[tuple[str, ...], str, int]] = []
    names: dict[tuple[str, ...], str] = {}
    spellings: dict[tuple[str, ...], tuple[str, ...]] = {}
    kinds: dict[tuple[str, ...], str] = {}
    expanded = 0
    for name, kind, size in members:
        parts = _member_parts(name, label)
        key = _portable_key(parts)
        if key in names:
            raise RuntimeError(
                f"{label} contains a portable-name collision: {names[key]!r} and {name!r}"
            )
        names[key] = name
        kinds[key] = kind
        for length in range(1, len(parts) + 1):
            prefix_key = key[:length]
            prefix_spelling = parts[:length]
            previous = spellings.setdefault(prefix_key, prefix_spelling)
            if previous != prefix_spelling:
                raise RuntimeError(f"{label} contains a portable-name collision")
        if size < 0 or (kind == "file" and size > MAX_ARCHIVE_MEMBER_BYTES):
            raise RuntimeError(f"{label} contains a member exceeding the per-member limit")
        if kind == "file":
            expanded += size
            if expanded > MAX_ARCHIVE_EXPANDED_BYTES:
                raise RuntimeError(f"{label} exceeds the aggregate expanded-size limit")
        records.append((parts, kind, size))

    for parts, _kind, _size in records:
        key = _portable_key(parts)
        if any(
            key[:length] in kinds and kinds[key[:length]] != "directory"
            for length in range(1, len(key))
        ):
            raise RuntimeError(f"{label} contains an unsafe member hierarchy")
    return records


def _prepare_empty_destination(destination: Path, label: str) -> Path:
    if destination.is_symlink():
        raise RuntimeError(f"{label} extraction destination is unsafe")
    destination.mkdir(parents=True, exist_ok=True)
    if not destination.is_dir() or any(destination.iterdir()):
        raise RuntimeError(f"{label} extraction destination must be an empty directory")
    return destination.resolve(strict=True)


def _contained_target(root: Path, parts: tuple[str, ...], label: str) -> Path:
    target = root.joinpath(*parts)
    try:
        target.resolve(strict=False).relative_to(root)
    except (OSError, RuntimeError, ValueError):
        raise RuntimeError(f"{label} contains a member outside the destination") from None
    return target


def _validate_destination_targets(
    root: Path, records: list[tuple[tuple[str, ...], str, int]], label: str
) -> None:
    for parts, _kind, _size in records:
        _contained_target(root, parts, label)


def _link_target_parts(
    member_parts: tuple[str, ...], linkname: str, *, relative_to_parent: bool, label: str
) -> tuple[str, ...]:
    if not linkname or "\x00" in linkname or "\\" in linkname:
        raise RuntimeError(f"{label} contains an unsafe link target")
    link = PurePosixPath(linkname)
    if link.is_absolute() or (link.parts and re.fullmatch(r"[A-Za-z]:", link.parts[0])):
        raise RuntimeError(f"{label} contains an unsafe link target")
    resolved = list(member_parts[:-1] if relative_to_parent else ())
    for part in link.parts:
        if part in {"", "."}:
            continue
        if part == "..":
            if not resolved:
                raise RuntimeError(f"{label} contains a link outside the destination")
            resolved.pop()
        else:
            resolved.append(part)
    if not resolved:
        raise RuntimeError(f"{label} contains an unsafe link target")
    return tuple(resolved)


def _inspect_tree(root: Path, label: str) -> dict[str, tuple[str, int, str]]:
    if root.is_symlink() or not root.is_dir():
        raise RuntimeError(f"{label} tree root is unsafe")
    resolved_root = root.resolve(strict=True)
    members: list[tuple[str, str, int]] = []
    details: dict[str, tuple[str, int, str]] = {}
    stack = [root]
    expanded = 0
    while stack:
        directory = stack.pop()
        try:
            entries = sorted(os.scandir(directory), key=lambda item: item.name)
        except OSError as error:
            raise RuntimeError(f"{label} tree could not be inspected") from error
        for entry in entries:
            path = Path(entry.path)
            relative = path.relative_to(root).as_posix()
            try:
                metadata = entry.stat(follow_symlinks=False)
            except OSError as error:
                raise RuntimeError(f"{label} tree could not be inspected") from error
            mode = metadata.st_mode
            if stat.S_ISDIR(mode):
                kind = "directory"
                size = 0
                link_target = ""
                stack.append(path)
            elif stat.S_ISREG(mode):
                kind = "file"
                size = metadata.st_size
                link_target = ""
            elif stat.S_ISLNK(mode):
                kind = "symlink"
                size = 0
                try:
                    link_target = os.readlink(path)
                    if Path(link_target).is_absolute():
                        raise RuntimeError(f"{label} tree contains an unsafe link")
                    path.resolve(strict=False).relative_to(resolved_root)
                except (OSError, RuntimeError, ValueError):
                    raise RuntimeError(f"{label} tree contains a link outside its root") from None
            else:
                raise RuntimeError(f"{label} tree contains an unsafe special file")
            members.append((relative, kind, size))
            if len(members) > MAX_ARCHIVE_MEMBERS:
                raise RuntimeError(f"{label} exceeds the member-count limit")
            if kind == "file":
                if size > MAX_ARCHIVE_MEMBER_BYTES:
                    raise RuntimeError(f"{label} contains a member exceeding the per-member limit")
                expanded += size
                if expanded > MAX_ARCHIVE_EXPANDED_BYTES:
                    raise RuntimeError(f"{label} exceeds the aggregate expanded-size limit")
            details[relative] = (kind, size, link_target)
    _validate_member_inventory(members, label)
    return details


def extract_zip(archive: Path, destination: Path) -> None:
    label = "official Blender ZIP"
    root = _prepare_empty_destination(destination, label)
    with zipfile.ZipFile(archive) as source:
        members: list[tuple[str, str, int]] = []
        for member in source.infolist():
            mode = member.external_attr >> 16
            file_type = stat.S_IFMT(mode)
            directory = member.is_dir()
            if (
                member.flag_bits & 1
                or (directory and file_type not in {0, stat.S_IFDIR})
                or (not directory and file_type not in {0, stat.S_IFREG})
            ):
                raise RuntimeError(f"{label} contains an unsafe member")
            members.append(
                (member.filename, "directory" if directory else "file", member.file_size)
            )
        records = _validate_member_inventory(members, label)
        _validate_destination_targets(root, records, label)
        source.extractall(root)
    _inspect_tree(root, label)


def extract_tar(archive: Path, destination: Path) -> None:
    label = "official Blender tar archive"
    root = _prepare_empty_destination(destination, label)
    with tarfile.open(archive, mode="r:xz") as source:
        source_members = source.getmembers()
        members: list[tuple[str, str, int]] = []
        for member in source_members:
            if member.isdir():
                kind = "directory"
            elif member.isfile():
                kind = "file"
            elif member.issym():
                kind = "symlink"
            elif member.islnk():
                kind = "hardlink"
            else:
                raise RuntimeError(f"{label} contains an unsafe special member")
            members.append((member.name, kind, member.size))
        records = _validate_member_inventory(members, label)
        _validate_destination_targets(root, records, label)
        records_by_name = {parts: kind for parts, kind, _size in records}
        for member, (parts, kind, _size) in zip(source_members, records, strict=True):
            if kind == "symlink":
                target_parts = _link_target_parts(
                    parts, member.linkname, relative_to_parent=True, label=label
                )
                _contained_target(root, target_parts, label)
            elif kind == "hardlink":
                target_parts = _link_target_parts(
                    parts, member.linkname, relative_to_parent=False, label=label
                )
                if records_by_name.get(target_parts) != "file":
                    raise RuntimeError(f"{label} contains an unsafe hard-link target")
                _contained_target(root, target_parts, label)
        source.extractall(root, members=source_members, filter="data")
    _inspect_tree(root, label)


def extract_dmg(archive: Path, destination: Path) -> None:
    label = "official Blender mounted app"
    destination_root = _prepare_empty_destination(destination, label)
    mount = Path(tempfile.mkdtemp(prefix="vao-blender-dmg-"))
    attached = False
    try:
        subprocess.run(
            (
                "hdiutil",
                "attach",
                "-readonly",
                "-nobrowse",
                "-mountpoint",
                str(mount),
                str(archive),
            ),
            check=True,
        )
        attached = True
        applications = list(mount.glob("*.app"))
        if len(applications) != 1 or applications[0].name != "Blender.app":
            raise RuntimeError("official Blender DMG does not contain exactly Blender.app")
        application = applications[0]
        if application.is_symlink() or not application.is_dir():
            raise RuntimeError("official Blender DMG contains an unsafe Blender.app")
        source_inventory = _inspect_tree(application, label)
        copy_destination = _contained_target(destination_root, ("Blender.app",), label)
        shutil.copytree(application, copy_destination, symlinks=True)
        if _inspect_tree(copy_destination, label) != source_inventory:
            raise RuntimeError("copied Blender.app differs from the mounted source")
    finally:
        if attached:
            subprocess.run(("hdiutil", "detach", str(mount)), check=True)
        if mount.exists():
            mount.rmdir()


def find_executable(destination: Path, platform_name: str) -> Path:
    if platform_name == "windows-x64":
        matches = list(destination.rglob("blender.exe"))
    elif platform_name == "macos-arm64":
        matches = list(destination.glob("Blender.app/Contents/MacOS/Blender"))
    else:
        matches = [
            item
            for item in destination.rglob("blender")
            if item.is_file() and item.parent.name.startswith("blender-")
        ]
    if len(matches) != 1 or matches[0].is_symlink() or not matches[0].is_file():
        raise RuntimeError("extracted official archive has no unique Blender executable")
    matches[0].chmod(matches[0].stat().st_mode | stat.S_IXUSR)
    return matches[0].resolve()


def probe(executable: Path, policy: dict[str, Any]) -> dict[str, Any]:
    marker = "VAO_NATIVE_HOST_PROBE="
    expression = (
        "import bpy,hashlib,json,platform;"
        f"print({marker!r}+json.dumps({{"
        "'blenderVersion':'.'.join(str(item) for item in bpy.app.version),"
        "'blenderBuildHash':bpy.app.build_hash.decode('ascii','replace'),"
        "'pythonVersion':platform.python_version(),"
        "'system':platform.system(),"
        "'machine':platform.machine()"
        "},sort_keys=True))"
    )
    executable_sha256 = sha256(executable)
    try:
        result = subprocess.run(
            (
                str(executable),
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
            f"Blender native-host probe exited with status {exc.returncode}"
            + (f":\n{detail}" if detail else "")
        ) from exc
    if sha256(executable) != executable_sha256:
        raise RuntimeError("Blender executable changed during the native-host probe")
    line = next((item for item in result.stdout.splitlines() if item.startswith(marker)), None)
    if line is None:
        raise RuntimeError("Blender did not emit native-host provenance")
    actual = json.loads(line.removeprefix(marker))
    expected = {
        "blenderVersion": policy["blender_version"],
        "blenderBuildHash": policy["build_hash"],
        "pythonVersion": policy["python_version"],
        "system": policy["system"],
        "machine": policy["machine"],
    }
    if actual != expected:
        raise RuntimeError(
            "official Blender host does not match native policy: "
            + json.dumps({"expected": expected, "actual": actual}, sort_keys=True)
        )
    return {**actual, "blenderExecutableSha256": executable_sha256}


def write_github_output(path: Path, values: dict[str, object]) -> None:
    with path.open("a", encoding="utf-8", newline="\n") as output:
        for name, value in values.items():
            text = str(value)
            if not re.fullmatch(r"[^\r\n]+", text):
                raise RuntimeError("GitHub output contains an unsafe newline")
            output.write(f"{name}={text}\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--blender-version", required=True)
    parser.add_argument("--platform", required=True)
    parser.add_argument("--runner-image", required=True)
    parser.add_argument("--runner-image-version", default=os.environ.get("ImageVersion", ""))
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument(
        "--github-output",
        type=Path,
        default=Path(os.environ["GITHUB_OUTPUT"]) if os.environ.get("GITHUB_OUTPUT") else None,
    )
    args = parser.parse_args()
    release, policy = host_policy(args.blender_version, args.platform)
    if args.runner_image != policy["runner_image"] or not re.fullmatch(
        r"[A-Za-z0-9._+-]{1,128}", args.runner_image_version
    ):
        raise RuntimeError("runner image label/version does not match native policy")
    if platform.system() != policy["system"] or platform.machine() != policy["machine"]:
        raise RuntimeError("workflow runner architecture does not match native policy")
    destination = args.destination.expanduser().absolute()
    if destination.exists() or destination.is_symlink():
        raise RuntimeError("native Blender destination must not already exist")
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{destination.name}.", dir=destination.parent))
    promoted = False
    try:
        archive = download(policy, destination)
        if archive.suffix == ".zip":
            extract_zip(archive, staging)
        elif archive.suffix == ".dmg":
            extract_dmg(archive, staging)
        elif archive.name.endswith(".tar.xz"):
            extract_tar(archive, staging)
        else:
            raise RuntimeError("unsupported official Blender archive type")
        executable = find_executable(staging, args.platform)
        observed = probe(executable, policy)
        builder = release["builder"]
        if (
            args.blender_version == builder["blender_version"]
            and args.platform == "linux-x64"
            and observed["blenderExecutableSha256"] != builder["blender_executable_sha256"]
        ):
            raise RuntimeError("canonical builder executable failed its independent pin")
        relative_executable = executable.relative_to(staging)
        os.replace(staging, destination)
        promoted = True
        executable = (destination / relative_executable).resolve()
        values = {
            "blender_path": executable,
            "archive_url": policy["archive_url"],
            "archive_sha256": policy["archive_sha256"],
            "blender_executable_sha256": observed["blenderExecutableSha256"],
        }
        if args.github_output:
            write_github_output(args.github_output, values)
        print(json.dumps({**policy, **observed, "blenderPath": str(executable)}, sort_keys=True))
    finally:
        if not promoted and staging.exists():
            shutil.rmtree(staging)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
