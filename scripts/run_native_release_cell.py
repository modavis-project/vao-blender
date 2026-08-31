#!/usr/bin/env python3
"""Exercise one exact installed extension ZIP and emit its native evidence cell."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import unicodedata
import zipfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.native_evidence import release_context, template  # noqa: E402
from scripts.prepare_native_blender import probe  # noqa: E402

TEST_SCRIPTS = {
    "lifecycle": "tests/blender/test_lifecycle.py",
    "detached-reopen": "tests/blender/test_detached_reopen.py",
    "vao-0.3.2": "tests/blender/test_vao03_integration.py",
    "vao-0.4.0": "tests/blender/test_vao04_integration.py",
    "vao-0.5.0": "tests/blender/test_vao05_integration.py",
    "audio-policy": "tests/blender/test_audio_engine_policy.py",
}
MAX_WHEEL_MEMBER_BYTES = 64 * 1024 * 1024
MAX_WHEEL_MEMBERS = 16_384
MAX_EXTRACTED_DEPENDENCY_BYTES = 256 * 1024 * 1024
MAX_INSTALLED_FILE_BYTES = 512 * 1024 * 1024
MAX_INSTALLED_TOTAL_BYTES = 1024 * 1024 * 1024
MAX_INSTALLED_MEMBERS = 4096


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def run(args: tuple[str, ...], *, environment: dict[str, str], cwd: Path) -> None:
    subprocess.run(args, check=True, env=environment, cwd=cwd)


def run_blender(
    blender: Path,
    arguments: tuple[str, ...],
    *,
    expected_digest: str,
    environment: dict[str, str],
    cwd: Path,
) -> None:
    if sha256(blender) != expected_digest:
        raise RuntimeError("native Blender executable changed before launch")
    run((str(blender), *arguments), environment=environment, cwd=cwd)
    if sha256(blender) != expected_digest:
        raise RuntimeError("native Blender executable changed during launch")


def _portable_name(path: PurePosixPath) -> str:
    return unicodedata.normalize("NFC", "/".join(path.parts)).casefold()


def _zip_member_path(member: zipfile.ZipInfo, *, label: str) -> PurePosixPath:
    path = PurePosixPath(member.filename)
    mode = member.external_attr >> 16
    kind = stat.S_IFMT(mode)
    if (
        "\\" in member.filename
        or path.is_absolute()
        or not path.parts
        or any(part in {"", ".", ".."} for part in path.parts)
        or member.flag_bits & 0x1
        or stat.S_ISLNK(mode)
        or kind not in {0, stat.S_IFREG, stat.S_IFDIR}
        or (kind == stat.S_IFDIR and not member.is_dir())
        or (kind == stat.S_IFREG and member.is_dir())
    ):
        raise RuntimeError(f"{label} has an unsafe member: {member.filename}")
    return path


def _zip_member_sha256(archive: zipfile.ZipFile, member: zipfile.ZipInfo) -> str:
    digest = hashlib.sha256()
    with archive.open(member) as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _is_generated_bytecode(name: str, expected_files: set[str]) -> bool:
    path = PurePosixPath(name)
    if len(path.parts) < 2 or path.parts[-2] != "__pycache__":
        return False
    match = re.fullmatch(r"(.+)\.cpython-313(?:\.opt-[12])?\.pyc", path.name)
    if not match:
        return False
    source = PurePosixPath(*path.parts[:-2], f"{match.group(1)}.py").as_posix()
    return source in expected_files


def _is_generated_bytecode_directory(name: str, expected_files: set[str]) -> bool:
    path = PurePosixPath(name)
    if not path.parts or path.name != "__pycache__":
        return False
    parent = path.parent
    return any(
        PurePosixPath(expected).parent == parent and expected.endswith(".py")
        for expected in expected_files
    )


def verify_installed_tree(artifact: Path, installed_root: Path) -> dict[str, str]:
    """Bind every installed source byte to the tested ZIP, allowing derived pyc only."""
    if installed_root.is_symlink() or not installed_root.is_dir():
        raise RuntimeError("installed extension root must be a regular directory")
    expected: dict[str, str] = {}
    expected_directories: set[str] = set()
    portable_names: set[str] = set()
    total_bytes = 0
    with zipfile.ZipFile(artifact) as archive:
        members = archive.infolist()
        if len(members) > MAX_INSTALLED_MEMBERS:
            raise RuntimeError("extension artifact exceeds the installed member-count limit")
        for member in members:
            path = _zip_member_path(member, label="extension artifact")
            portable = _portable_name(path)
            if portable in portable_names:
                raise RuntimeError("extension artifact has a portable-name collision")
            portable_names.add(portable)
            if member.file_size > MAX_INSTALLED_FILE_BYTES:
                raise RuntimeError("extension artifact member exceeds the installed-byte limit")
            total_bytes += member.file_size
            if total_bytes > MAX_INSTALLED_TOTAL_BYTES:
                raise RuntimeError("extension artifact exceeds the installed-byte limit")
            if not member.is_dir():
                expected[path.as_posix()] = _zip_member_sha256(archive, member)
                expected_directories.update(
                    parent.as_posix() for parent in path.parents if parent != PurePosixPath(".")
                )
            else:
                expected_directories.add(path.as_posix().rstrip("/"))

    actual: dict[str, Path] = {}
    actual_directories: set[str] = set()
    actual_portable: set[str] = set()
    actual_total_bytes = 0
    for directory, child_directories, filenames in os.walk(installed_root, followlinks=False):
        base = Path(directory)
        for child in child_directories:
            candidate = base / child
            if candidate.is_symlink():
                raise RuntimeError("installed extension contains a symbolic-link directory")
            relative = candidate.relative_to(installed_root).as_posix()
            portable = _portable_name(PurePosixPath(relative))
            if portable in actual_portable:
                raise RuntimeError("installed extension has a portable-name collision")
            actual_portable.add(portable)
            actual_directories.add(relative)
        for filename in filenames:
            candidate = base / filename
            if candidate.is_symlink() or not candidate.is_file():
                raise RuntimeError("installed extension contains a non-regular file")
            size = candidate.stat().st_size
            if size > MAX_INSTALLED_FILE_BYTES:
                raise RuntimeError("installed extension file exceeds the byte limit")
            actual_total_bytes += size
            if actual_total_bytes > MAX_INSTALLED_TOTAL_BYTES * 2:
                raise RuntimeError("installed extension tree exceeds the byte limit")
            relative = candidate.relative_to(installed_root).as_posix()
            portable = _portable_name(PurePosixPath(relative))
            if portable in actual_portable:
                raise RuntimeError("installed extension has a portable-name collision")
            actual_portable.add(portable)
            actual[relative] = candidate
        if len(actual) + len(actual_directories) > MAX_INSTALLED_MEMBERS * 2:
            raise RuntimeError("installed extension exceeds the member-count limit")

    missing = set(expected) - set(actual)
    unexpected = {
        name
        for name in set(actual) - set(expected)
        if not _is_generated_bytecode(name, set(expected))
    }
    unexpected_directories = {
        name
        for name in actual_directories - expected_directories
        if not _is_generated_bytecode_directory(name, set(expected))
    }
    if missing or unexpected or unexpected_directories:
        raise RuntimeError(
            "installed extension inventory differs from the artifact; "
            f"missing={sorted(missing)}, unexpected={sorted(unexpected)}, "
            f"unexpected_directories={sorted(unexpected_directories)}"
        )
    for name, expected_digest in expected.items():
        if sha256(actual[name]) != expected_digest:
            raise RuntimeError(f"installed extension file differs from the artifact: {name}")
    return expected


def extract_installed_wheels(installed_root: Path, destination: Path) -> None:
    wheels = sorted((installed_root / "wheels").glob("*.whl"))
    if not wheels:
        raise RuntimeError("installed extension contains no dependency wheels")
    if destination.is_symlink() or not destination.is_dir() or any(destination.iterdir()):
        raise RuntimeError("dependency extraction destination must be an empty regular directory")
    portable_names: set[str] = set()
    total_bytes = 0
    member_count = 0
    for wheel in wheels:
        if wheel.is_symlink() or not wheel.is_file():
            raise RuntimeError("installed dependency wheel must be a regular file")
        with zipfile.ZipFile(wheel) as archive:
            members = archive.infolist()
            member_count += len(members)
            if member_count > MAX_WHEEL_MEMBERS:
                raise RuntimeError("installed dependency wheels exceed the member-count limit")
            for member in members:
                path = _zip_member_path(member, label="installed dependency wheel")
                if member.file_size > MAX_WHEEL_MEMBER_BYTES:
                    raise RuntimeError(
                        f"installed dependency wheel has an unsafe member: {member.filename}"
                    )
                portable = _portable_name(path)
                if portable in portable_names:
                    raise RuntimeError(
                        f"installed dependency wheels have a portable-name collision: {member.filename}"
                    )
                portable_names.add(portable)
                total_bytes += member.file_size
                if total_bytes > MAX_EXTRACTED_DEPENDENCY_BYTES:
                    raise RuntimeError("installed dependency wheels exceed the extraction limit")
            for member in members:
                path = PurePosixPath(member.filename)
                target = destination.joinpath(*path.parts)
                if member.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(member) as source, target.open("xb") as output:
                    shutil.copyfileobj(source, output, length=1024 * 1024)


def write_wrapper(path: Path) -> None:
    path.write_text(
        """from __future__ import annotations
import importlib
import os
import pkgutil
import runpy
import sys
from pathlib import Path

import bpy

source_root = Path(os.environ["VAO_NATIVE_SOURCE_ROOT"]).resolve()
installed_root = Path(os.environ["VAO_NATIVE_INSTALLED_ROOT"]).resolve()
working_root = Path(os.environ["VAO_NATIVE_WORKING_ROOT"]).resolve()
module_root = os.environ["VAO_NATIVE_MODULE_ROOT"]
os.chdir(working_root)
clean_path = []
for entry in sys.path:
    if not entry:
        continue
    resolved = Path(entry).resolve()
    if resolved == source_root or source_root in resolved.parents:
        continue
    clean_path.append(entry)
sys.path[:] = clean_path
if module_root not in bpy.context.preferences.addons:
    raise RuntimeError("installed extension is not enabled in the isolated profile")
importlib.import_module(module_root)
implementation_prefix = module_root + ".vao_blender"
implementation = importlib.import_module(implementation_prefix)
for discovered in pkgutil.walk_packages(
    implementation.__path__, implementation_prefix + "."
):
    importlib.import_module(discovered.name)
namespaced_modules = {
    name: module
    for name, module in tuple(sys.modules.items())
    if name == implementation_prefix or name.startswith(implementation_prefix + ".")
}
for name, module in namespaced_modules.items():
    module_file = getattr(module, "__file__", None)
    if module_file is None:
        continue
    module_path = Path(module_file).resolve()
    if module_path != installed_root and installed_root not in module_path.parents:
        raise RuntimeError(f"namespaced module escaped installed bytes: {name}={module_path}")
for name, module in sorted(namespaced_modules.items(), key=lambda item: len(item[0])):
    alias = "vao_blender" + name.removeprefix(implementation_prefix)
    existing = sys.modules.get(alias)
    if existing is not None and existing is not module:
        raise RuntimeError(f"source module contaminated installed test namespace: {alias}")
    sys.modules[alias] = module
runpy.run_path(os.environ["VAO_NATIVE_TEST_SCRIPT"], run_name="__main__")
for name, module in namespaced_modules.items():
    alias = "vao_blender" + name.removeprefix(implementation_prefix)
    if sys.modules.get(alias) is not module:
        raise RuntimeError(f"installed module alias changed during native test: {alias}")
""",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--blender", type=Path, required=True)
    parser.add_argument("--blender-executable-sha256", required=True)
    parser.add_argument("--release-dir", type=Path, required=True)
    parser.add_argument("--blender-version", required=True)
    parser.add_argument("--platform", required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--run-url", required=True)
    parser.add_argument("--runner-image", required=True)
    parser.add_argument("--runner-image-version", default=os.environ.get("ImageVersion", ""))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"[0-9a-f]{40}", args.source_commit):
        raise RuntimeError("source commit must be a full Git SHA-1")
    if not re.fullmatch(r"[0-9a-f]{64}", args.blender_executable_sha256):
        raise RuntimeError("Blender executable SHA-256 must be a lowercase digest")
    context = release_context()
    expected_run_url = re.compile(
        re.escape(context["release"]["repository"]) + r"/actions/runs/[1-9]\d*/attempts/[1-9]\d*"
    )
    if not expected_run_url.fullmatch(args.run_url):
        raise RuntimeError("run URL must identify one exact workflow attempt in this repository")
    if not re.fullmatch(r"[A-Za-z0-9._+-]{1,128}", args.runner_image_version):
        raise RuntimeError("runner image version is missing or malformed")
    output_path = args.output.expanduser().absolute()
    if output_path.exists() or output_path.is_symlink():
        raise RuntimeError("native cell output path must not already exist")
    release_dir = args.release_dir.expanduser().absolute()
    evidence_template = template(release_dir)
    matching = [
        cell
        for cell in evidence_template["cells"]
        if cell["blenderVersion"] == args.blender_version and cell["platform"] == args.platform
    ]
    if len(matching) != 1 or evidence_template["releaseCommit"] != args.source_commit:
        raise RuntimeError("requested native cell does not match the immutable release set")
    cell = matching[0]
    if cell["runnerImage"] != args.runner_image:
        raise RuntimeError("runner image does not match the native host policy")
    host_policies = [
        item
        for item in context["config"]["hosts"]
        if item["blender_version"] == args.blender_version and item["platform"] == args.platform
    ]
    if len(host_policies) != 1:
        raise RuntimeError("native host policy is not unique")
    host_policy = host_policies[0]
    artifact = release_dir / cell["artifactFile"]
    original_artifact_digest = sha256(artifact)
    if original_artifact_digest != cell["artifactSha256"]:
        raise RuntimeError("native artifact does not match the base checksum inventory")

    blender = args.blender.expanduser().absolute()
    if blender.is_symlink() or not blender.is_file():
        raise RuntimeError("native Blender executable must be a regular non-symbolic-link file")
    if sha256(blender) != args.blender_executable_sha256:
        raise RuntimeError("native Blender executable differs from the pinned archive extraction")
    observed_host = probe(blender, host_policy)
    executable_digest = observed_host["blenderExecutableSha256"]
    if executable_digest != args.blender_executable_sha256:
        raise RuntimeError("native Blender executable changed while re-probing the host")
    if any(
        cell[field] != observed_host[observed]
        for field, observed in (
            ("blenderVersion", "blenderVersion"),
            ("blenderBuildHash", "blenderBuildHash"),
            ("blenderPythonVersion", "pythonVersion"),
            ("hostSystem", "system"),
            ("hostMachine", "machine"),
        )
    ):
        raise RuntimeError("native Blender probe differs from the evidence cell policy")
    with tempfile.TemporaryDirectory(prefix="vao-native-cell-") as directory:
        working = Path(directory)
        profile = working / "profile"
        repository = profile / "extensions" / "vao_rc_test"
        repository.mkdir(parents=True)
        fixture = working / "visual-bootstrap.vao"
        subprocess.run(
            (
                sys.executable,
                "-c",
                (
                    "from pathlib import Path; "
                    "from tests.unit.test_vao04 import build_visual_bootstrap; "
                    f"build_visual_bootstrap(Path({str(fixture)!r}))"
                ),
            ),
            cwd=ROOT,
            check=True,
        )
        profile_environment = {
            key: value
            for key, value in os.environ.items()
            if key not in {"BLENDER_USER_RESOURCES", "PYTHONHOME", "PYTHONPATH"}
        }
        profile_environment["BLENDER_USER_RESOURCES"] = str(profile)
        run_blender(
            blender,
            (
                "--command",
                "extension",
                "repo-add",
                "vao_rc_test",
                "--name",
                "VAO RC Native Test",
                "--directory",
                str(repository),
                "--clear-all",
            ),
            expected_digest=executable_digest,
            environment=profile_environment,
            cwd=working,
        )
        run_blender(
            blender,
            (
                "--command",
                "extension",
                "install-file",
                "-r",
                "vao_rc_test",
                "-e",
                str(artifact),
            ),
            expected_digest=executable_digest,
            environment=profile_environment,
            cwd=working,
        )
        installed_root = repository / "vao_blender"
        if installed_root.is_symlink() or not (installed_root / "blender_manifest.toml").is_file():
            raise RuntimeError("Blender did not install the expected extension directory")
        installed_inventory = verify_installed_tree(artifact, installed_root)

        smoke_environment = {
            **profile_environment,
            "VAO_BLENDER_SMOKE_PACKAGE": str(fixture),
            "VAO_BLENDER_SMOKE_MODULE": "bl_ext.vao_rc_test.vao_blender",
        }
        run_blender(
            blender,
            (
                "--background",
                "--offline-mode",
                "--python-exit-code",
                "1",
                "--python",
                str(ROOT / "tests/blender/test_installed_extension.py"),
            ),
            expected_digest=executable_digest,
            environment=smoke_environment,
            cwd=working,
        )

        dependencies = working / "dependencies"
        dependencies.mkdir()
        extract_installed_wheels(installed_root, dependencies)
        wrapper = working / "run_exact_installed_test.py"
        write_wrapper(wrapper)
        test_environment = {
            key: value
            for key, value in profile_environment.items()
            if key not in {"PYTHONHOME", "PYTHONPATH"}
        }
        test_environment.update(
            {
                "VAO_NATIVE_SOURCE_ROOT": str(ROOT),
                "VAO_NATIVE_INSTALLED_ROOT": str(installed_root),
                "VAO_NATIVE_WORKING_ROOT": str(working),
                "VAO_NATIVE_MODULE_ROOT": "bl_ext.vao_rc_test.vao_blender",
                "VAO_TEST_TEMP": str(working),
                "VAO_TEST_BLEND": str(working / "integration.blend"),
                "VAO_TEST_DETACHED_BLEND": str(working / "detached.blend"),
                "VAO_TEST_VAO03_BLEND": str(working / "vao-0.3.2.blend"),
            }
        )
        for test_name in cell["tests"]:
            if test_name == "installed-extension-smoke":
                continue
            test_script = TEST_SCRIPTS.get(test_name)
            if test_script is None:
                raise RuntimeError(f"native evidence names an unknown test: {test_name}")
            test_environment["VAO_NATIVE_TEST_SCRIPT"] = str(ROOT / test_script)
            run_blender(
                blender,
                (
                    "--background",
                    "--offline-mode",
                    "--python-exit-code",
                    "1",
                    "--python",
                    str(wrapper),
                ),
                expected_digest=executable_digest,
                environment=test_environment,
                cwd=working,
            )

        if verify_installed_tree(artifact, installed_root) != installed_inventory:
            raise RuntimeError("installed extension inventory changed during native tests")
        run_blender(
            blender,
            ("--command", "extension", "remove", "vao_blender"),
            expected_digest=executable_digest,
            environment=profile_environment,
            cwd=working,
        )
        if installed_root.exists():
            raise RuntimeError("native cell could not uninstall the tested extension")

    if sha256(artifact) != original_artifact_digest:
        raise RuntimeError("native test mutated the immutable extension artifact")
    cell.update(
        {
            "status": "pass",
            "runUrl": args.run_url,
            "observedAt": dt.datetime.now(dt.UTC)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z"),
            "blenderExecutableSha256": executable_digest,
            "runnerImageVersion": args.runner_image_version,
        }
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{output_path.name}.", dir=output_path.parent
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as output:
            json.dump(cell, output, indent=2, sort_keys=True)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary_path, output_path)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()
    print(f"Native release cell passed: {args.blender_version}/{args.platform}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
