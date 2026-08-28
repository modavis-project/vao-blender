"""Safe, streaming, read-only VAO package validation."""

from __future__ import annotations

import hashlib
import os
import stat
import unicodedata
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import Callable, Iterable

from .cancellation import CancellationToken, CancelledError
from .capability import negotiate
from .contract import (
    RELEASE_BUNDLE_03_SHA256,
    RELEASE_BUNDLE_04_SHA256,
    RELEASE_BUNDLE_05_SHA256,
    ContractIntegrityError,
    reference_validator_03,
    reference_validator_04,
    reference_validator_05,
)
from .diagnostics import Diagnostic, Severity, Stage, ordered
from .graph import build_graph
from .interaction_compile import compile_interactions
from .model import (
    CapabilityResult,
    CarrierRecord,
    OutcomeState,
    ValidationOutcome,
    VerificationRecord,
    freeze,
)
from .schema_validation import validate_schema
from .semantic_validation import rights_require_acknowledgement, validate_semantics
from .strict_json import StrictJSONError, loads
from .vao03 import build_graph_03, build_records_03

MIMETYPE = b"application/vnd.modavis.vao+zip"
CONTRACT_SHA256 = "76b55f33b09c94ad90aac79e8a599d007841e2c11288664f9c67987b4e68f328"
CHUNK_SIZE = 4 * 1024 * 1024
VAO03_CARRIER_PATH = "META-INF/vao-carrier.json"
VAO03_MAX_CARRIER_BYTES = 16 * 1024 * 1024
MODERN_VERSIONS = {"0.3.2", "0.4.0", "0.5.0"}


@dataclass(frozen=True, slots=True)
class ValidationLimits:
    max_entries: int = 20_000
    max_manifest_bytes: int = 32 * 1024 * 1024
    max_entry_bytes: int = 8 * 1024 * 1024 * 1024
    max_total_expanded_bytes: int = 64 * 1024 * 1024 * 1024
    max_compression_ratio: float = 2_000.0


@dataclass(frozen=True, slots=True)
class ProgressRecord:
    stage: str
    current_path: str = ""
    completed_entries: int = 0
    total_entries: int = 0
    verified_bytes: int = 0
    total_bytes: int = 0


ProgressCallback = Callable[[ProgressRecord], None]


class PackageInvalid(RuntimeError):
    def __init__(self, code: str, message: str, *, path: str = "") -> None:
        super().__init__(message)
        self.code = code
        self.path = path


class ResourceLimited(RuntimeError):
    pass


def _emit(callback: ProgressCallback | None, record: ProgressRecord) -> None:
    if callback is not None:
        callback(record)


def validate_archive_path(name: str) -> str:
    """Return the NFC normalized safe archive path or raise PackageInvalid."""
    if (
        not name
        or "\\" in name
        or any(ord(character) < 0x20 or ord(character) == 0x7F for character in name)
    ):
        raise PackageInvalid(
            "VAO-CNT-002", "empty, control-character, or backslash archive path", path=name
        )
    normalized = unicodedata.normalize("NFC", name)
    if normalized != name:
        raise PackageInvalid("VAO-CNT-003", "archive path is not Unicode NFC", path=name)
    if name.startswith(("/", "//")) or (len(name) >= 2 and name[1] == ":"):
        raise PackageInvalid("VAO-CNT-004", "absolute, UNC, or drive archive path", path=name)
    components = name.rstrip("/").split("/")
    if any(component in {"", ".", ".."} for component in components):
        raise PackageInvalid("VAO-CNT-005", "unsafe archive path component", path=name)
    if len(components) > 128:
        raise PackageInvalid("VAO-CNT-024", "archive path exceeds 128 segments", path=name)
    path = PurePosixPath(name)
    if path.parts[0] not in {"mimetype", "vao-manifest.json", "payload", "META-INF"}:
        raise PackageInvalid("VAO-CNT-006", "unknown VAO root entry", path=name)
    if path.parts[0] in {"mimetype", "vao-manifest.json"} and len(path.parts) != 1:
        raise PackageInvalid("VAO-CNT-007", "structural record must be at archive root", path=name)
    return normalized


def _check_entry_type(info: zipfile.ZipInfo) -> None:
    if info.flag_bits & 0x1:
        raise PackageInvalid(
            "VAO-CNT-008", "encrypted ZIP entries are forbidden", path=info.filename
        )
    if info.compress_type not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}:
        raise PackageInvalid(
            "VAO-CNT-009", "unsupported ZIP compression method", path=info.filename
        )
    if any(ord(character) > 127 for character in info.filename) and not (info.flag_bits & 0x800):
        raise PackageInvalid(
            "VAO-CNT-023",
            "non-ASCII archive names require the ZIP UTF-8 language flag",
            path=info.filename,
        )
    mode = info.external_attr >> 16
    if mode:
        kind = stat.S_IFMT(mode)
        if kind not in {0, stat.S_IFREG, stat.S_IFDIR}:
            raise PackageInvalid(
                "VAO-CNT-010", "links and special archive entries are forbidden", path=info.filename
            )


def _preflight(zf: zipfile.ZipFile, limits: ValidationLimits) -> dict[str, zipfile.ZipInfo]:
    infos = zf.infolist()
    if len(infos) > limits.max_entries:
        raise ResourceLimited(
            f"archive contains {len(infos)} entries; limit is {limits.max_entries}"
        )
    if len(infos) < 2:
        raise PackageInvalid("VAO-CNT-011", "archive is missing structural records")
    if infos[0].filename != "mimetype":
        raise PackageInvalid("VAO-CNT-012", "mimetype must be the first archive entry")
    if infos[0].compress_type != zipfile.ZIP_STORED:
        raise PackageInvalid("VAO-CNT-013", "mimetype must be uncompressed", path="mimetype")

    by_name: dict[str, zipfile.ZipInfo] = {}
    casefolded: dict[str, str] = {}
    total = 0
    for info in infos:
        normalized = validate_archive_path(info.filename)
        _check_entry_type(info)
        if normalized in by_name:
            raise PackageInvalid("VAO-CNT-014", "duplicate archive path", path=normalized)
        folded = normalized.casefold()
        if folded in casefolded:
            raise PackageInvalid(
                "VAO-CNT-015",
                f"case-folding collision with {casefolded[folded]!r}",
                path=normalized,
            )
        by_name[normalized] = info
        casefolded[folded] = normalized
        if not info.is_dir():
            total += info.file_size
            if info.file_size > limits.max_entry_bytes:
                raise ResourceLimited(f"entry {normalized!r} exceeds the per-entry limit")
            compressed = max(info.compress_size, 1)
            if info.file_size / compressed > limits.max_compression_ratio:
                raise ResourceLimited(f"entry {normalized!r} exceeds the compression-ratio limit")
    if total > limits.max_total_expanded_bytes:
        raise ResourceLimited("archive exceeds the total expanded-byte limit")
    files = {name.rstrip("/") for name, info in by_name.items() if not info.is_dir()}
    for name in by_name:
        parts = name.rstrip("/").split("/")
        for index in range(1, len(parts)):
            parent = "/".join(parts[:index])
            if parent in files:
                raise PackageInvalid(
                    "VAO-CNT-022",
                    f"archive file overlaps descendant entry {name!r}",
                    path=parent,
                )
    manifest = by_name.get("vao-manifest.json")
    if manifest is None or manifest.file_size > limits.max_manifest_bytes:
        raise ResourceLimited("manifest is absent or exceeds the configured manifest limit")
    return by_name


def _has_errors(diagnostics: Iterable[Diagnostic]) -> bool:
    return any(item.severity == Severity.ERROR for item in diagnostics)


def _check_version_entries(
    entries: dict[str, zipfile.ZipInfo],
    version: str,
    limits: ValidationLimits,
) -> None:
    ordered_names = [info.filename for info in entries.values()]
    if version == "0.2.2":
        if len(ordered_names) < 2 or ordered_names[1] != "vao-manifest.json":
            raise PackageInvalid(
                "VAO-CNT-012",
                "VAO 0.2.2 requires vao-manifest.json as the second archive entry",
            )
        return
    if version not in MODERN_VERSIONS:
        return
    prefix = {"0.3.2": "VAO03", "0.4.0": "VAO04", "0.5.0": "VAO05"}[version]
    descriptor = entries.get(VAO03_CARRIER_PATH)
    if descriptor is None:
        raise PackageInvalid(
            f"{prefix}-CNT-001",
            f"VAO {version} carrier is missing META-INF/vao-carrier.json",
            path=VAO03_CARRIER_PATH,
        )
    if descriptor.is_dir():
        raise PackageInvalid(
            f"{prefix}-CNT-002",
            f"VAO {version} carrier descriptor is not a regular file",
            path=VAO03_CARRIER_PATH,
        )
    if descriptor.file_size > min(VAO03_MAX_CARRIER_BYTES, limits.max_manifest_bytes):
        raise ResourceLimited(f"VAO {version} carrier descriptor exceeds its configured limit")
    for name, info in entries.items():
        if info.is_dir():
            if not (name == "META-INF/" or name.startswith("payload/")):
                raise PackageInvalid(
                    f"{prefix}-CNT-003", f"unknown VAO {version} directory entry", path=name
                )
        elif name not in {
            "mimetype",
            "vao-manifest.json",
            VAO03_CARRIER_PATH,
        } and not name.startswith("payload/"):
            raise PackageInvalid(
                f"{prefix}-CNT-004", f"unknown VAO {version} carrier entry", path=name
            )


def _reference_diagnostics(report: dict, prefix: str = "VAO03") -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    for severity, key in ((Severity.ERROR, "errors"), (Severity.WARNING, "warnings")):
        for message in report.get(key, []):
            lowered = str(message).casefold()
            if str(message).startswith("$"):
                stage, code = Stage.SCHEMA, f"{prefix}-SCH-001"
            elif any(
                token in lowered
                for token in (
                    "carrier",
                    "payload",
                    "embedded realization",
                    "manifestsha256",
                    "manifestbytesize",
                )
            ):
                stage, code = Stage.CONTAINER, f"{prefix}-CNT-005"
            else:
                stage, code = Stage.SEMANTIC, f"{prefix}-SEM-001"
            diagnostics.append(Diagnostic(code, severity, stage, str(message)))
    return diagnostics


def _hash_file(path: Path, token: CancellationToken, callback: ProgressCallback | None) -> str:
    digest = hashlib.sha256()
    size = path.stat().st_size
    done = 0
    with path.open("rb") as stream:
        while chunk := stream.read(CHUNK_SIZE):
            token.check()
            digest.update(chunk)
            done += len(chunk)
            _emit(callback, ProgressRecord("archive-hash", verified_bytes=done, total_bytes=size))
    return digest.hexdigest()


def _outcome(
    state: OutcomeState,
    source: Path,
    diagnostics: list[Diagnostic],
    **kwargs,
) -> ValidationOutcome:
    return ValidationOutcome(
        state=state,
        source_path=str(source),
        diagnostics=ordered(diagnostics),
        **kwargs,
    )


def _rights_require_acknowledgement_03(manifest: dict) -> bool:
    rights = manifest.get("rights", [])
    if not rights:
        return True
    for record in rights:
        license_value = str(record.get("license", "")).strip()
        access = str(record.get("access", "")).strip().lower()
        if not license_value or access in {"", "restricted", "unknown", "pending", "closed"}:
            return True
    return False


def _capabilities_03(
    manifest: dict,
    visual_support: tuple[bool, str],
) -> tuple[CapabilityResult, ...]:
    """Report consumer support without advertising an acoustic renderer."""
    metadata_capabilities = {
        "https://w3id.org/modavis/vao/vocab/capability/core-graph",
        "https://w3id.org/modavis/vao/vocab/capability/fixity",
        "https://w3id.org/modavis/vao/vocab/capability/immutable-release",
        "https://w3id.org/modavis/vao/vocab/capability/carrier-mapping",
        "https://w3id.org/modavis/vao/vocab/capability/spatial",
        "https://w3id.org/modavis/vao/vocab/capability/simulated-impulse-response",
        "https://w3id.org/modavis/vao/vocab/capability/measured-impulse-response",
        "https://w3id.org/modavis/vao/vocab/capability/position-registered-acoustic-scene",
    }
    visual = "https://w3id.org/modavis/vao/vocab/capability/visual-acoustic-scene"
    renderer_capabilities = {
        "https://w3id.org/modavis/vao/vocab/capability/spatial-audio-scene",
        "https://w3id.org/modavis/vao/vocab/capability/spatial-response-field",
        "https://w3id.org/modavis/vao/vocab/capability/tracked-listener-convolution",
        "https://w3id.org/modavis/vao/vocab/capability/geometry-acoustic-rendering",
        "https://w3id.org/modavis/vao/vocab/capability/hybrid-acoustic-rendering",
    }
    required = sorted(
        {
            capability
            for profile in manifest.get("profiles", [])
            for capability in profile.get("requiredCapabilities", [])
        }
    )
    results: list[CapabilityResult] = []
    for capability in required:
        if capability in metadata_capabilities:
            results.append(
                CapabilityResult(
                    capability,
                    True,
                    "validated offline metadata/fixity support; not an execution claim",
                )
            )
        elif capability == visual:
            supported, reason = visual_support
            results.append(
                CapabilityResult(
                    capability,
                    supported,
                    reason,
                )
            )
        elif capability in renderer_capabilities:
            results.append(
                CapabilityResult(
                    capability,
                    False,
                    "metadata only; VAO-Blender does not implement convolution, simulation, "
                    "response interpolation, or acoustic rendering",
                )
            )
        else:
            results.append(
                CapabilityResult(capability, False, "capability is not implemented by VAO-Blender")
            )
    return tuple(results)


def _visual_support_03(acoustic_scene) -> tuple[bool, str]:
    if acoustic_scene is None or not acoustic_scene.runtime_visual_realization_id:
        return False, "no embedded runtime-visual GLB realization"
    root_id = acoustic_scene.common_frame_root_id
    root = acoustic_scene.coordinate_frames.get(root_id)
    if root is None:
        return False, "runtime visual geometry and declared poses lack a common frame root"
    if (
        root.dimension != 3
        or root.handedness != "right"
        or root.up_axis != "+Z"
        or not root.unit.endswith("/M")
    ):
        return (
            False,
            "runtime placement requires a three-dimensional, right-handed, metre, +Z common root",
        )
    return True, ""


def _validate_03_reference(
    source: Path,
    zf: zipfile.ZipFile,
    entries: dict[str, zipfile.ZipInfo],
    raw_manifest: bytes,
    manifest: dict,
    manifest_sha: str,
    archive_sha: str,
    token: CancellationToken,
    progress: ProgressCallback | None,
    verify_payload: bool,
) -> ValidationOutcome:
    """Validate exact 0.3.2 semantics and carrier closure with OrgRec's pinned code."""
    diagnostics: list[Diagnostic] = []
    verified: dict[str, VerificationRecord] = {}
    verified_bytes = 0
    raw_carrier = zf.read(entries[VAO03_CARRIER_PATH])
    try:
        carrier_document = loads(raw_carrier)
    except StrictJSONError as exc:
        raise PackageInvalid(
            "VAO03-CNT-006",
            f"carrier descriptor JSON is not strict: {exc}",
            path=VAO03_CARRIER_PATH,
        ) from exc
    if not isinstance(carrier_document, dict):
        raise PackageInvalid(
            "VAO03-CNT-007",
            "carrier descriptor root must be an object",
            path=VAO03_CARRIER_PATH,
        )

    payload_paths = sorted(
        name for name, info in entries.items() if name.startswith("payload/") and not info.is_dir()
    )
    realization_by_id = {
        item.get("id"): item for item in manifest.get("realizations", []) if isinstance(item, dict)
    }
    mapping_by_path = {
        item.get("path"): item.get("realizationId")
        for item in carrier_document.get("embeddedRealizations", [])
        if isinstance(item, dict)
        and isinstance(item.get("path"), str)
        and isinstance(item.get("realizationId"), str)
    }
    total = sum(
        int(realization_by_id.get(identifier, {}).get("byteSize", 0))
        for identifier in mapping_by_path.values()
    )
    completed = 0
    streamed_bytes = 0

    def reader(path: str) -> tuple[str, int]:
        nonlocal completed, streamed_bytes, verified_bytes
        realization_id = mapping_by_path.get(path, "")
        realization = realization_by_id.get(realization_id, {})
        if not verify_payload:
            return str(realization.get("sha256", "")), int(realization.get("byteSize", 0))
        token.check()
        digest = hashlib.sha256()
        count = 0
        with zf.open(entries[path], "r") as stream:
            while chunk := stream.read(CHUNK_SIZE):
                token.check()
                digest.update(chunk)
                count += len(chunk)
                streamed_bytes += len(chunk)
                _emit(
                    progress,
                    ProgressRecord(
                        "fixity",
                        path,
                        completed,
                        len(mapping_by_path),
                        streamed_bytes,
                        total,
                    ),
                )
        actual = digest.hexdigest()
        completed += 1
        if count == realization.get("byteSize") and actual == realization.get("sha256"):
            verified[realization_id] = VerificationRecord(realization_id, count, actual)
            verified_bytes += count
        _emit(
            progress,
            ProgressRecord(
                "fixity",
                path,
                completed,
                len(mapping_by_path),
                streamed_bytes,
                total,
            ),
        )
        return actual, count

    _emit(progress, ProgressRecord("schema"))
    report = reference_validator_03().validate_carrier_parts(
        raw_manifest,
        raw_carrier,
        payload_paths,
        reader,
    )
    diagnostics.extend(_reference_diagnostics(report))
    if _has_errors(diagnostics):
        return _outcome(
            OutcomeState.INVALID,
            source,
            diagnostics,
            archive_sha256=archive_sha,
            manifest_sha256=manifest_sha,
            manifest=freeze(manifest),
            verified_assets=MappingProxyType(verified),
            verified_payload_bytes=verified_bytes,
            contract_line="0.3.2",
            contract_sha256=RELEASE_BUNDLE_03_SHA256,
        )

    embedded_paths = MappingProxyType(
        {
            str(item["realizationId"]): str(item["path"])
            for item in carrier_document["embeddedRealizations"]
        }
    )
    logical_assets, realizations, acoustic_scene = build_records_03(manifest, embedded_paths)
    graph = build_graph_03(manifest)
    capabilities = _capabilities_03(manifest, _visual_support_03(acoustic_scene))
    for capability in capabilities:
        if not capability.supported:
            diagnostics.append(
                Diagnostic(
                    "VAO-CAP-001",
                    Severity.WARNING,
                    Stage.CAPABILITY,
                    f"unsupported runtime capability {capability.capability}: {capability.reason}",
                    related_ids=(capability.capability,),
                )
            )
    rights_required = _rights_require_acknowledgement_03(manifest)
    if any(not capability.supported for capability in capabilities):
        state = OutcomeState.UNSUPPORTED
    elif rights_required:
        state = OutcomeState.BLOCKED_RIGHTS
    else:
        state = OutcomeState.VALID
    carrier = CarrierRecord(
        str(carrier_document["releaseId"]),
        str(carrier_document["manifestSHA256"]),
        int(carrier_document["manifestByteSize"]),
        str(carrier_document["carrierMode"]),
        embedded_paths,
        tuple(carrier_document.get("completeGroupIds", [])),
    )
    return _outcome(
        state,
        source,
        diagnostics,
        archive_sha256=archive_sha,
        manifest_sha256=manifest_sha,
        manifest=freeze(manifest),
        graph=graph,
        verified_assets=MappingProxyType(verified),
        capabilities=capabilities,
        verified_payload_bytes=verified_bytes,
        contract_line="0.3.2",
        contract_sha256=RELEASE_BUNDLE_03_SHA256,
        carrier=carrier,
        logical_assets=logical_assets,
        realizations=realizations,
        acoustic_scene=acoustic_scene,
        rights_acknowledgement_required=rights_required,
    )


def _capabilities_modern(
    manifest: dict,
    visual_support: tuple[bool, str],
) -> tuple[CapabilityResult, ...]:
    """Describe the exact modern-reader boundary without runtime overclaims."""
    base = "https://w3id.org/modavis/vao/vocab/capability/"
    validated_metadata = {
        base + name
        for name in (
            "core-graph",
            "fixity",
            "immutable-release",
            "carrier-mapping",
            "typed-scientific-provenance",
            "multimodal-synchronization",
            "physical-system-topology",
            "spatial",
            "semantic-building-model",
            "measured-impulse-response",
            "simulated-impulse-response",
            "position-registered-acoustic-scene",
            "source-directivity",
            "room-acoustic-metrics",
            "building-acoustic-performance",
        )
    }
    visual = base + "visual-acoustic-scene"
    execution_only = {
        base + name
        for name in (
            "interaction",
            "deterministic-render-trace",
            "spatial-response-field",
            "spatial-audio-scene",
            "tracked-listener-convolution",
            "tracked-sources",
            "geometry-acoustic-rendering",
            "hybrid-acoustic-rendering",
            "learned-acoustic-field",
        )
    }
    required = sorted(
        {
            capability
            for profile in manifest.get("profiles", [])
            for capability in profile.get("requiredCapabilities", [])
        }
    )
    results: list[CapabilityResult] = []
    for capability in required:
        if capability in validated_metadata:
            results.append(
                CapabilityResult(
                    capability,
                    True,
                    "validated offline metadata/fixity support; not an execution claim",
                )
            )
        elif capability == visual:
            supported, reason = visual_support
            results.append(CapabilityResult(capability, supported, reason))
        elif capability in execution_only:
            results.append(
                CapabilityResult(
                    capability,
                    False,
                    "validated as package metadata, but this Blender runtime does not implement it",
                )
            )
        else:
            results.append(
                CapabilityResult(capability, False, "capability is not implemented by VAO-Blender")
            )
    return tuple(results)


def _validate_modern_reference(
    source: Path,
    zf: zipfile.ZipFile,
    entries: dict[str, zipfile.ZipInfo],
    raw_manifest: bytes,
    manifest: dict,
    manifest_sha: str,
    archive_sha: str,
    token: CancellationToken,
    progress: ProgressCallback | None,
    verify_payload: bool,
    version: str,
) -> ValidationOutcome:
    """Validate a pinned modern schema, carrier closure, chunks, and fixity."""
    if version == "0.5.0":
        prefix = "VAO05"
        contract_sha = RELEASE_BUNDLE_05_SHA256
        reference = reference_validator_05()
    else:
        prefix = "VAO04"
        contract_sha = RELEASE_BUNDLE_04_SHA256
        reference = reference_validator_04()
    diagnostics: list[Diagnostic] = []
    verified: dict[str, VerificationRecord] = {}
    verified_bytes = 0
    raw_carrier = zf.read(entries[VAO03_CARRIER_PATH])
    try:
        carrier_document = loads(raw_carrier)
    except StrictJSONError as exc:
        raise PackageInvalid(
            f"{prefix}-CNT-006",
            f"carrier descriptor JSON is not strict: {exc}",
            path=VAO03_CARRIER_PATH,
        ) from exc
    if not isinstance(carrier_document, dict):
        raise PackageInvalid(
            f"{prefix}-CNT-007",
            "carrier descriptor root must be an object",
            path=VAO03_CARRIER_PATH,
        )

    payload_paths = sorted(
        name for name, info in entries.items() if name.startswith("payload/") and not info.is_dir()
    )
    realization_by_id = {
        item.get("id"): item for item in manifest.get("realizations", []) if isinstance(item, dict)
    }
    mapping_by_path = {
        item.get("path"): item.get("realizationId")
        for item in carrier_document.get("embeddedRealizations", [])
        if isinstance(item, dict)
        and isinstance(item.get("path"), str)
        and isinstance(item.get("realizationId"), str)
    }
    total = sum(
        int(realization_by_id.get(identifier, {}).get("byteSize", 0))
        for identifier in mapping_by_path.values()
    )
    completed = 0
    streamed_bytes = 0
    chunk_errors: list[str] = []

    def reader(path: str, expected_size: int) -> tuple[str, int]:
        nonlocal completed, streamed_bytes, verified_bytes
        realization_id = mapping_by_path.get(path, "")
        realization = realization_by_id.get(realization_id, {})
        if not verify_payload:
            return str(realization.get("sha256", "")), int(realization.get("byteSize", 0))
        token.check()
        digest = hashlib.sha256()
        count = 0

        class HashingStream:
            def __init__(self, stream) -> None:
                self.stream = stream

            def read(self, size: int = -1) -> bytes:
                nonlocal count, streamed_bytes
                token.check()
                data = self.stream.read(size)
                if data:
                    digest.update(data)
                    count += len(data)
                    streamed_bytes += len(data)
                    _emit(
                        progress,
                        ProgressRecord(
                            "fixity",
                            path,
                            completed,
                            len(mapping_by_path),
                            streamed_bytes,
                            total,
                        ),
                    )
                return data

        with zf.open(entries[path], "r") as stream:
            hashing_stream = HashingStream(stream)
            try:
                chunk_errors.extend(reference.validate_chunk_stream(realization, hashing_stream))
            except (KeyError, TypeError, ValueError) as exc:
                chunk_errors.append(f"Cannot verify embedded chunks for {path!r}: {exc}")
            while hashing_stream.read(CHUNK_SIZE):
                pass
        actual = digest.hexdigest()
        completed += 1
        if count == expected_size and actual == realization.get("sha256"):
            verified[realization_id] = VerificationRecord(realization_id, count, actual)
            verified_bytes += count
        _emit(
            progress,
            ProgressRecord(
                "fixity",
                path,
                completed,
                len(mapping_by_path),
                streamed_bytes,
                total,
            ),
        )
        return actual, count

    _emit(progress, ProgressRecord("schema"))
    report = reference.validate_carrier_parts(
        raw_manifest,
        raw_carrier,
        payload_paths,
        reader,
    )
    report.setdefault("errors", []).extend(chunk_errors)
    report["errors"] = sorted(set(report["errors"]))
    report["valid"] = not report["errors"]
    diagnostics.extend(_reference_diagnostics(report, prefix))
    if _has_errors(diagnostics):
        return _outcome(
            OutcomeState.INVALID,
            source,
            diagnostics,
            archive_sha256=archive_sha,
            manifest_sha256=manifest_sha,
            manifest=freeze(manifest),
            verified_assets=MappingProxyType(verified),
            verified_payload_bytes=verified_bytes,
            contract_line=version,
            contract_sha256=contract_sha,
        )

    embedded_paths = MappingProxyType(
        {
            str(item["realizationId"]): str(item["path"])
            for item in carrier_document["embeddedRealizations"]
        }
    )
    logical_assets, realizations, acoustic_scene = build_records_03(manifest, embedded_paths)
    graph = build_graph_03(manifest)
    capabilities = _capabilities_modern(manifest, _visual_support_03(acoustic_scene))
    for capability in capabilities:
        if not capability.supported:
            diagnostics.append(
                Diagnostic(
                    "VAO-CAP-001",
                    Severity.WARNING,
                    Stage.CAPABILITY,
                    f"unsupported runtime capability {capability.capability}: {capability.reason}",
                    related_ids=(capability.capability,),
                )
            )
    rights_required = _rights_require_acknowledgement_03(manifest)
    if any(not capability.supported for capability in capabilities):
        state = OutcomeState.UNSUPPORTED
    elif rights_required:
        state = OutcomeState.BLOCKED_RIGHTS
    else:
        state = OutcomeState.VALID
    carrier = CarrierRecord(
        str(carrier_document["releaseId"]),
        str(carrier_document["manifestSHA256"]),
        int(carrier_document["manifestByteSize"]),
        str(carrier_document["carrierMode"]),
        embedded_paths,
        tuple(carrier_document.get("completeGroupIds", [])),
    )
    return _outcome(
        state,
        source,
        diagnostics,
        archive_sha256=archive_sha,
        manifest_sha256=manifest_sha,
        manifest=freeze(manifest),
        graph=graph,
        verified_assets=MappingProxyType(verified),
        capabilities=capabilities,
        verified_payload_bytes=verified_bytes,
        contract_line=version,
        contract_sha256=contract_sha,
        carrier=carrier,
        logical_assets=logical_assets,
        realizations=realizations,
        acoustic_scene=acoustic_scene,
        rights_acknowledgement_required=rights_required,
    )


def validate_package(
    source_path: str | os.PathLike[str],
    *,
    limits: ValidationLimits | None = None,
    cancellation: CancellationToken | None = None,
    progress: ProgressCallback | None = None,
    verify_payload: bool = True,
    hash_archive: bool = True,
) -> ValidationOutcome:
    """Fully validate one VAO without extracting or decoding any payload media."""
    source = Path(source_path).expanduser().resolve()
    limits = limits or ValidationLimits()
    token = cancellation or CancellationToken()
    diagnostics: list[Diagnostic] = []
    archive_sha = ""
    manifest_sha = ""
    manifest: dict | None = None
    graph = None
    bundle = None
    verified: dict[str, VerificationRecord] = {}
    verified_bytes = 0

    try:
        token.check()
        if not source.is_file():
            raise PackageInvalid("VAO-CNT-001", "VAO source is not a regular file")
        if source.suffix.lower() != ".vao":
            raise PackageInvalid("VAO-CNT-016", "source filename does not end in .vao")
        if hash_archive:
            archive_sha = _hash_file(source, token, progress)

        with zipfile.ZipFile(source, mode="r", allowZip64=True) as zf:
            entries = _preflight(zf, limits)
            token.check()
            mimetype_bytes = zf.read(entries["mimetype"])
            if mimetype_bytes != MIMETYPE:
                raise PackageInvalid("VAO-CNT-017", "mimetype bytes are not exact", path="mimetype")
            raw_manifest = zf.read(entries["vao-manifest.json"])
            manifest_sha = hashlib.sha256(raw_manifest).hexdigest()
            try:
                decoded = loads(raw_manifest)
            except StrictJSONError as exc:
                raise PackageInvalid("VAO-CNT-018", f"manifest JSON is not strict: {exc}") from exc
            if not isinstance(decoded, dict):
                raise PackageInvalid("VAO-CNT-019", "manifest root must be an object")
            manifest = decoded
            version = str(manifest.get("formatVersion", ""))
            _check_version_entries(entries, version, limits)
            if version == "0.3.2":
                return _validate_03_reference(
                    source,
                    zf,
                    entries,
                    raw_manifest,
                    manifest,
                    manifest_sha,
                    archive_sha,
                    token,
                    progress,
                    verify_payload,
                )
            if version == "0.4.0":
                return _validate_modern_reference(
                    source,
                    zf,
                    entries,
                    raw_manifest,
                    manifest,
                    manifest_sha,
                    archive_sha,
                    token,
                    progress,
                    verify_payload,
                    "0.4.0",
                )
            if version == "0.5.0":
                return _validate_modern_reference(
                    source,
                    zf,
                    entries,
                    raw_manifest,
                    manifest,
                    manifest_sha,
                    archive_sha,
                    token,
                    progress,
                    verify_payload,
                    "0.5.0",
                )
            if version != "0.2.2":
                diagnostics.append(
                    Diagnostic(
                        code="VAO-SCH-002",
                        severity=Severity.ERROR,
                        stage=Stage.SCHEMA,
                        message=(
                            f"unsupported VAO formatVersion {version!r}; VAO-Blender supports "
                            "only the exact pinned 0.2.2, 0.3.2, 0.4.0, and 0.5.0 contracts"
                        ),
                        pointer="/formatVersion",
                    )
                )
                return _outcome(
                    OutcomeState.INVALID,
                    source,
                    diagnostics,
                    archive_sha256=archive_sha,
                    manifest_sha256=manifest_sha,
                    manifest=freeze(manifest),
                    contract_line=version or "unknown",
                )
            _emit(progress, ProgressRecord("schema"))
            diagnostics.extend(validate_schema(manifest))
            if any(item.severity == Severity.ERROR for item in diagnostics):
                return _outcome(
                    OutcomeState.INVALID,
                    source,
                    diagnostics,
                    archive_sha256=archive_sha,
                    manifest_sha256=manifest_sha,
                    manifest=freeze(manifest),
                )

            _emit(progress, ProgressRecord("semantic"))
            diagnostics.extend(validate_semantics(manifest))
            if any(item.severity == Severity.ERROR for item in diagnostics):
                return _outcome(
                    OutcomeState.INVALID,
                    source,
                    diagnostics,
                    archive_sha256=archive_sha,
                    manifest_sha256=manifest_sha,
                    manifest=freeze(manifest),
                )

            asset_by_path = {item["path"]: item for item in manifest.get("assets", [])}
            payload_paths = {
                name
                for name, info in entries.items()
                if name.startswith("payload/") and not info.is_dir()
            }
            indexed_paths = set(asset_by_path)
            if payload_paths != indexed_paths:
                missing = sorted(indexed_paths - payload_paths)
                unindexed = sorted(payload_paths - indexed_paths)
                message = (
                    f"payload index mismatch; missing={missing[:3]!r}, unindexed={unindexed[:3]!r}"
                )
                diagnostics.append(
                    Diagnostic("VAO-SEM-016", Severity.ERROR, Stage.SEMANTIC, message)
                )
                return _outcome(
                    OutcomeState.INVALID,
                    source,
                    diagnostics,
                    archive_sha256=archive_sha,
                    manifest_sha256=manifest_sha,
                    manifest=freeze(manifest),
                )

            if verify_payload:
                total = sum(item["byteSize"] for item in asset_by_path.values())
                for entry_number, path in enumerate(sorted(payload_paths), start=1):
                    token.check()
                    asset = asset_by_path[path]
                    digest = hashlib.sha256()
                    count = 0
                    with zf.open(entries[path], "r") as stream:
                        while chunk := stream.read(CHUNK_SIZE):
                            token.check()
                            digest.update(chunk)
                            count += len(chunk)
                            verified_bytes += len(chunk)
                            _emit(
                                progress,
                                ProgressRecord(
                                    "fixity",
                                    path,
                                    entry_number - 1,
                                    len(payload_paths),
                                    verified_bytes,
                                    total,
                                ),
                            )
                    actual_hash = digest.hexdigest()
                    if count != asset["byteSize"] or actual_hash != asset["sha256"]:
                        diagnostics.append(
                            Diagnostic(
                                "VAO-SEM-017",
                                Severity.ERROR,
                                Stage.SEMANTIC,
                                "asset byte size or SHA-256 does not match the manifest",
                                archive_path=path,
                                related_ids=(asset["id"],),
                            )
                        )
                        return _outcome(
                            OutcomeState.INVALID,
                            source,
                            diagnostics,
                            archive_sha256=archive_sha,
                            manifest_sha256=manifest_sha,
                            manifest=freeze(manifest),
                        )
                    verified[asset["id"]] = VerificationRecord(asset["id"], count, actual_hash)
                    _emit(
                        progress,
                        ProgressRecord(
                            "fixity",
                            path,
                            entry_number,
                            len(payload_paths),
                            verified_bytes,
                            total,
                        ),
                    )

            graph = build_graph(manifest)
            bundle = (
                compile_interactions(graph)
                if any(item.kind == "interaction" for item in graph.entities.values())
                else None
            )
            if bundle:
                diagnostics.extend(bundle.diagnostics)
            capabilities = negotiate(manifest, graph, bundle)
            for result in capabilities:
                if not result.supported:
                    diagnostics.append(
                        Diagnostic(
                            "VAO-CAP-001",
                            Severity.WARNING,
                            Stage.CAPABILITY,
                            f"unsupported required capability {result.capability}: {result.reason}",
                            related_ids=(result.capability,),
                        )
                    )
            rights_required = rights_require_acknowledgement(manifest)
            if bundle and not bundle.supported:
                state = OutcomeState.UNSUPPORTED
            elif any(not item.supported for item in capabilities):
                state = OutcomeState.UNSUPPORTED
            elif rights_required:
                state = OutcomeState.BLOCKED_RIGHTS
            else:
                state = OutcomeState.VALID
            return _outcome(
                state,
                source,
                diagnostics,
                archive_sha256=archive_sha,
                manifest_sha256=manifest_sha,
                manifest=freeze(manifest),
                graph=graph,
                verified_assets=MappingProxyType(verified),
                capabilities=capabilities,
                interaction_plans=bundle,
                verified_payload_bytes=verified_bytes,
                rights_acknowledgement_required=rights_required,
            )
    except CancelledError:
        diagnostics.append(
            Diagnostic("VAO-LIF-001", Severity.INFO, Stage.LIFECYCLE, "validation cancelled")
        )
        return _outcome(OutcomeState.CANCELLED, source, diagnostics)
    except ResourceLimited as exc:
        diagnostics.append(Diagnostic("VAO-CNT-020", Severity.WARNING, Stage.CONTAINER, str(exc)))
        return _outcome(OutcomeState.RESOURCE_LIMITED, source, diagnostics)
    except PackageInvalid as exc:
        diagnostics.append(
            Diagnostic(
                exc.code,
                Severity.ERROR,
                Stage.CONTAINER,
                str(exc),
                archive_path=exc.path,
            )
        )
    except ContractIntegrityError as exc:
        diagnostics.append(
            Diagnostic(
                "VAO-CON-001",
                Severity.ERROR,
                Stage.SCHEMA,
                f"local VAO contract integrity failure: {exc}",
            )
        )
    except (zipfile.BadZipFile, OSError, EOFError) as exc:
        diagnostics.append(
            Diagnostic(
                "VAO-CNT-021", Severity.ERROR, Stage.CONTAINER, f"archive I/O failure: {exc}"
            )
        )
    return _outcome(
        OutcomeState.INVALID,
        source,
        diagnostics,
        archive_sha256=archive_sha,
        manifest_sha256=manifest_sha,
        manifest=freeze(manifest) if manifest else None,
        graph=graph,
        verified_assets=MappingProxyType(verified),
        interaction_plans=bundle,
        verified_payload_bytes=verified_bytes,
    )
