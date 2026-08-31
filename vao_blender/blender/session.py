"""Main-thread session ownership and persistent .blend trace metadata."""

from __future__ import annotations

import hashlib
import json
import zipfile
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable
from uuid import uuid4

import bpy

from ..core.cache import AssetCache
from ..core.diagnostics import Diagnostic, Severity, Stage
from ..core.model import OutcomeState, ValidationOutcome
from .preferences import addon_preferences, cache_root

TRACE_MATERIALIZATION_ID = "vao_materialization_id"
TRACE_SESSION_ID = "vao_session_id"
TRACE_ROOT = "vao_materialization_root"
MAX_SAVED_DIAGNOSTICS = 20_000
MAX_SAVED_RELATED_IDS = 1_024


@dataclass(frozen=True, slots=True)
class DetachedMaterialization:
    """Persistent identity recovered from one managed collection in one scene."""

    materialization_id: str
    root_name: str
    title: str
    package_id: str
    revision: str
    release_id: str
    format_version: str
    manifest_sha256: str
    archive_sha256: str
    source_path: str


@dataclass(slots=True)
class Session:
    """Ephemeral runtime state owned by exactly one Blender scene."""

    id: str
    outcome: ValidationOutcome
    scene: bpy.types.Scene
    materialization_id: str
    scene_name: str = ""
    active_configurations: set[str] = field(default_factory=set)
    pressed_gates: set[str] = field(default_factory=set)
    audio_engine: object | None = None
    root_collection_name: str = ""
    source_matches_materialization: bool = True
    expected_archive_sha256: str = ""
    expected_manifest_sha256: str = ""
    protected_cache_paths: dict[str, str] = field(default_factory=dict)
    transient_text_names: set[str] = field(default_factory=set)

    @property
    def source_path(self) -> str:
        return self.outcome.source_path

    @property
    def cache(self) -> AssetCache:
        preferences = addon_preferences()
        quota = (preferences.cache_quota_gib if preferences else 20) * 1024**3
        return AssetCache(cache_root(), quota_bytes=quota)

    @property
    def validation_complete(self) -> bool:
        """Whether the result authorizes payload-dependent host operations."""
        if not self.outcome.is_valid:
            return False
        # Newer outcomes expose an explicit completeness bit/state.  The
        # fallbacks keep hand-built outcomes usable without treating an
        # explicitly incomplete validation as complete.
        for name in (
            "verification_complete",
            "payload_verification_complete",
            "validation_complete",
        ):
            value = getattr(self.outcome, name, None)
            if value is not None and not bool(value):
                return False
        return self.outcome.state.value not in {"incomplete", "unchecked"}

    def rights_ready(self, scene: bpy.types.Scene | None = None) -> bool:
        scene = scene or self.scene
        return bool(
            scene
            and hasattr(scene, "vao_runtime")
            and (
                not self.outcome.rights_acknowledgement_required
                or scene.vao_runtime.rights_acknowledged
            )
        )

    def media_ready(self, scene: bpy.types.Scene | None = None) -> bool:
        """Gate extraction/decoding on validity, completeness, relink, and rights."""
        scene = scene or self.scene
        runtime_ready = bool(
            scene
            and hasattr(scene, "vao_runtime")
            and scene.vao_runtime.session_id == self.id
            and scene.vao_runtime.state != "VALIDATING"
        )
        return bool(
            runtime_ready
            and self.validation_complete
            and self.source_matches_materialization
            and self.rights_ready(scene)
        )

    def ensure_audio(self):
        if not self.media_ready(self.scene):
            raise RuntimeError(
                "media is unavailable until validation is complete, the exact source is "
                "attached, and any rights limitation is acknowledged"
            )
        if self.outcome.contract_line in {"0.3.2", "0.4.0", "0.5.0"}:
            raise RuntimeError(
                f"VAO {self.outcome.contract_line} program-audio and acoustic execution are not "
                "implemented; validated records remain inspectable and supported visual geometry "
                "can still be materialized"
            )
        bundle = self.outcome.interaction_plans
        if bundle is None or not bundle.supported:
            raise RuntimeError("package has no fully supported compiled interaction plan")
        if not bundle.gates or not bundle.voices:
            raise RuntimeError("compiled interaction plan has no executable gate/voice mappings")
        if self.audio_engine is None:
            from .audio_engine import AudioEngine

            preferences = addon_preferences()
            polyphony = preferences.max_polyphony if preferences else 64
            self.audio_engine = AudioEngine(self, max_polyphony=polyphony)
        return self.audio_engine

    def stop_audio(self) -> None:
        if self.audio_engine is not None:
            self.audio_engine.close()
            self.audio_engine = None
        self.pressed_gates.clear()
        try:
            from .scene_adapter import update_control_surface

            update_control_surface(self)
        except (ReferenceError, RuntimeError):
            pass

    def protect_cache_path(self, path: str | Path) -> Path:
        """Retain one extracted asset for this session until close/replacement."""
        candidate = str(Path(path).expanduser().resolve())
        if candidate not in self.protected_cache_paths:
            cache = self.cache
            registered = cache.register_protected(candidate)
            self.protected_cache_paths[str(registered)] = str(cache.root)
            return registered
        return Path(candidate)

    def adopt_protected_cache_path(self, path: str | Path, root: str | Path) -> Path:
        """Take ownership of an atomic ``extract(..., protect=True)`` registration."""
        candidate = str(Path(path).expanduser().resolve())
        cache_root_path = str(Path(root).expanduser().resolve())
        if candidate in self.protected_cache_paths:
            # The extracting call registered another reference; retain exactly
            # one session-owned reference for this path.
            AssetCache(cache_root_path).unregister_protected(candidate)
        else:
            self.protected_cache_paths[candidate] = cache_root_path
        return Path(candidate)

    def release_cache_paths(self) -> None:
        for path, root in tuple(self.protected_cache_paths.items()):
            try:
                AssetCache(root).unregister_protected(path)
            except Exception:
                # Teardown stays best effort if the recorded cache root has
                # become unavailable; normal close releases the shared lease.
                pass
            self.protected_cache_paths.pop(path, None)

    def release_cache_path(self, path: str | Path) -> None:
        candidate = str(Path(path).expanduser().resolve())
        root = self.protected_cache_paths.pop(candidate, None)
        if root is None:
            return
        try:
            AssetCache(root).unregister_protected(candidate)
        except Exception:
            pass


SESSIONS: dict[str, Session] = {}


def active_session(scene: bpy.types.Scene | None = None) -> Session | None:
    scene = scene or bpy.context.scene
    if scene is None or not hasattr(scene, "vao_runtime"):
        return None
    session = SESSIONS.get(scene.vao_runtime.session_id)
    if session is None:
        return None
    try:
        if session.scene == scene:
            session.scene_name = scene.name
            return session
        owner_is_live = bpy.data.scenes.get(session.scene.name) == session.scene
    except ReferenceError:
        owner_is_live = False
    if owner_is_live:
        # A copied/stale RNA session identifier must never cross scene ownership.
        return None
    claims = [
        candidate
        for candidate in bpy.data.scenes
        if hasattr(candidate, "vao_runtime") and candidate.vao_runtime.session_id == session.id
    ]
    if len(claims) != 1 or claims[0] != scene or scene.name != session.scene_name:
        return None
    # Blender undo/redo may replace RNA pointers.  Rebind only to the unique
    # same-named claimant; copied scenes retain no authority to steal a session.
    session.scene = scene
    return session


def install_outcome(
    scene: bpy.types.Scene,
    outcome: ValidationOutcome,
    *,
    detached: DetachedMaterialization | None = None,
    source_matches_materialization: bool = True,
    materialization_id: str = "",
) -> Session:
    """Install every validation result, including diagnostic-only outcomes."""
    if detached and source_matches_materialization:
        reasons = relink_mismatch_reasons(detached, outcome)
        if reasons:
            raise RuntimeError("exact relink rejected: " + "; ".join(reasons))
        if not detached.root_name or bpy.data.collections.get(detached.root_name) is None:
            raise RuntimeError("exact relink rejected: managed collection is unavailable")
        if materialization_is_shared(detached.root_name):
            raise RuntimeError(
                "exact relink rejected: managed collection is linked into multiple scenes"
            )
    current_id = scene.vao_runtime.session_id
    if current_id:
        current = SESSIONS.get(current_id)
        if current and current.scene == scene:
            SESSIONS.pop(current_id, None)
            current.stop_audio()
            current.release_cache_paths()
            _remove_transient_texts(current)
            if not current.root_collection_name:
                _remove_session_texts(current.materialization_id)

    session_id = uuid4().hex
    materialization_id = materialization_id or (
        detached.materialization_id if detached and detached.materialization_id else uuid4().hex
    )
    session = Session(
        session_id,
        outcome,
        scene,
        materialization_id,
        scene_name=scene.name,
        root_collection_name=detached.root_name if detached else "",
        source_matches_materialization=source_matches_materialization,
        expected_archive_sha256=(detached.archive_sha256 if detached else outcome.archive_sha256),
        expected_manifest_sha256=(
            detached.manifest_sha256 if detached else outcome.manifest_sha256
        ),
    )
    if detached and detached.root_name:
        root = bpy.data.collections.get(detached.root_name)
        if root is not None:
            existing_id = str(root.get(TRACE_MATERIALIZATION_ID, ""))
            if existing_id and existing_id != materialization_id:
                raise RuntimeError("detached materialization identity changed during relink")
            root[TRACE_MATERIALIZATION_ID] = materialization_id
            root[TRACE_ROOT] = True
            if source_matches_materialization:
                root[TRACE_SESSION_ID] = session_id
    SESSIONS[session_id] = session
    _populate_runtime(scene, session, detached=detached)
    _store_manifest_text(session)
    _store_diagnostics_text(session)
    discover_detached(scene)
    return session


def relink_mismatch_reasons(
    detached: DetachedMaterialization, outcome: ValidationOutcome
) -> tuple[str, ...]:
    """Return deterministic reasons why a validated source is not this saved materialization."""
    reasons: list[str] = []
    if not outcome.is_valid:
        reasons.append("validation did not produce a complete valid result")
    if not detached.manifest_sha256:
        reasons.append("saved materialization has no manifest hash")
    elif outcome.manifest_sha256 != detached.manifest_sha256:
        reasons.append("manifest SHA-256 differs")
    if not detached.archive_sha256:
        reasons.append("saved materialization has no archive hash")
    elif outcome.archive_sha256 != detached.archive_sha256:
        reasons.append("archive SHA-256 differs")
    manifest = _mapping(outcome.manifest)
    release = _mapping(manifest.get("release"))
    actual_revision = str(release.get("revision", manifest.get("revision", "")))
    actual_release = str(release.get("id", ""))
    for label, expected, actual in (
        ("package identity", detached.package_id, str(manifest.get("id", ""))),
        ("revision", detached.revision, actual_revision),
        ("release identity", detached.release_id, actual_release),
        ("format version", detached.format_version, str(manifest.get("formatVersion", ""))),
    ):
        if expected and actual != expected:
            reasons.append(f"{label} differs")
    return tuple(reasons)


def _mapping(value) -> Mapping:
    return value if isinstance(value, Mapping) else {}


def _sequence_length(value) -> int:
    return len(value) if isinstance(value, (tuple, list)) else 0


def _display_text(value, fallback: str = "") -> str:
    if isinstance(value, Mapping):
        candidate = value.get("en") or next(iter(value.values()), fallback)
    else:
        candidate = value
    return _scalar_text(candidate, fallback)


def _scalar_text(value, fallback: str = "") -> str:
    return str(value) if isinstance(value, (str, int, float, bool)) else fallback


def _populate_runtime(
    scene: bpy.types.Scene,
    session: Session,
    *,
    detached: DetachedMaterialization | None,
) -> None:
    outcome = session.outcome
    manifest = _mapping(outcome.manifest)
    runtime = scene.vao_runtime
    runtime.session_id = session.id
    runtime.materialization_id = session.materialization_id
    runtime.root_collection_name = session.root_collection_name
    runtime.result_state = outcome.state.value.upper()
    runtime.state = runtime.result_state
    runtime.validity_state = _validity_state(outcome)
    runtime.support_state = _support_state(outcome)
    if outcome.is_valid:
        runtime.rights_state = (
            "ACKNOWLEDGEMENT_REQUIRED" if outcome.rights_acknowledgement_required else "READY"
        )
    else:
        runtime.rights_state = "NOT_EVALUATED"
    runtime.materialization_state = "ATTACHED" if detached else "NONE"
    if not session.source_matches_materialization:
        runtime.materialization_state = "DETACHED"
    runtime.status_message = _status_message(session)
    source_path = str(outcome.source_path or "")
    runtime.source_name = Path(source_path).name
    runtime.source_path = runtime.source_name
    runtime.expected_archive_sha256 = session.expected_archive_sha256
    runtime.expected_manifest_sha256 = session.expected_manifest_sha256
    runtime.archive_sha256 = outcome.archive_sha256
    runtime.manifest_sha256 = outcome.manifest_sha256
    runtime.title = _display_text(manifest.get("title"), runtime.source_name)
    if detached and not session.source_matches_materialization:
        runtime.title = detached.title
    elif not runtime.title and detached:
        runtime.title = detached.title
    runtime.package_id = _scalar_text(
        detached.package_id
        if detached and not session.source_matches_materialization
        else manifest.get("id", detached.package_id if detached else "")
    )
    release = _mapping(manifest.get("release"))
    if detached and not session.source_matches_materialization:
        runtime.revision = detached.revision
        runtime.release_id = detached.release_id
        runtime.format_version = detached.format_version
    else:
        runtime.revision = _scalar_text(
            release.get("revision", manifest.get("revision", detached.revision if detached else ""))
        )
        runtime.release_id = _scalar_text(
            release.get("id", detached.release_id if detached else "")
        )
        runtime.format_version = _scalar_text(
            manifest.get("formatVersion", detached.format_version if detached else "")
        )
    runtime.carrier_mode = str(outcome.carrier.mode) if outcome.carrier else ""
    runtime.verified_assets = len(outcome.verified_assets)
    runtime.entity_count = 0
    runtime.relation_count = 0
    runtime.asset_count = 0
    runtime.logical_asset_count = len(outcome.logical_assets)
    runtime.realization_count = len(outcome.realizations)
    scientific = _mapping(manifest.get("scientific"))
    interaction = _mapping(manifest.get("interactionModel"))
    physical = _mapping(manifest.get("physicalSystem"))
    runtime.scientific_observation_count = _sequence_length(scientific.get("observations"))
    runtime.protocol_binding_count = _sequence_length(interaction.get("protocolBindings"))
    runtime.physical_component_count = _sequence_length(physical.get("components"))
    runtime.distribution_count = _sequence_length(manifest.get("distributions"))
    runtime.frame_count = 0
    runtime.pose_count = 0
    runtime.measurement_count = 0
    runtime.response_set_count = 0
    runtime.rir_count = 0
    runtime.selected_asset_id = ""
    runtime.selected_entity_id = ""
    runtime.selected_logical_asset_id = ""
    runtime.selected_realization_id = ""
    runtime.selected_relation_id = ""
    runtime.selected_record_key = ""
    runtime.model_section = "SCIENTIFIC"
    if outcome.graph:
        runtime.entity_count = len(outcome.graph.entities)
        runtime.relation_count = len(outcome.graph.relations)
        runtime.asset_count = len(outcome.graph.assets)
        models = [
            item.id
            for item in outcome.graph.assets.values()
            if item.media_type in {"model/gltf-binary", "model/gltf+json"}
        ]
        runtime.selected_asset_id = models[0] if models else next(iter(outcome.graph.assets), "")
        runtime.selected_entity_id = str(manifest.get("primaryEntityId", ""))
    if outcome.acoustic_scene:
        acoustic = outcome.acoustic_scene
        runtime.frame_count = len(acoustic.coordinate_frames)
        runtime.pose_count = len(acoustic.poses)
        runtime.measurement_count = len(acoustic.measurements)
        runtime.response_set_count = len(acoustic.response_sets)
        runtime.rir_count = len(acoustic.impulse_responses)
        runtime.selected_realization_id = acoustic.runtime_visual_realization_id
        runtime.selected_asset_id = acoustic.runtime_visual_realization_id
        selected = outcome.realizations.get(acoustic.runtime_visual_realization_id)
        runtime.selected_logical_asset_id = selected.logical_asset_id if selected else ""
    runtime.rights_acknowledged = False
    runtime.media_enabled = session.media_ready(scene)
    runtime.progress = 1.0
    runtime.progress_stage = "complete"
    runtime.progress_detail = "Validation result retained for inspection"
    runtime.performance_active = False
    runtime.explore_page = 0
    runtime.explore_details_page = 0
    runtime.entity_properties_page = 0
    runtime.relation_properties_page = 0
    runtime.linked_assets_page = 0
    runtime.asset_properties_page = 0
    runtime.record_properties_page = 0
    runtime.diagnostics_page = 0
    runtime.acoustic_measurement_page = 0
    runtime.acoustic_response_page = 0
    runtime.acoustic_rir_page = 0
    runtime.rights_page = 0
    runtime.detached_page = 0
    runtime.play_selection_page = 0
    runtime.play_gate_page = 0


def _validity_state(outcome: ValidationOutcome) -> str:
    if outcome.is_valid:
        return "VALID"
    value = outcome.state.value
    if value == "invalid":
        return "INVALID"
    if value == "resource-limited":
        return "UNDETERMINED_LIMIT"
    if value == "cancelled":
        return "NOT_EVALUATED"
    if value in {"incomplete", "unchecked"}:
        return "INCOMPLETE"
    return "UNDETERMINED"


def _support_state(outcome: ValidationOutcome) -> str:
    if not outcome.is_valid:
        return "NOT_EVALUATED"
    return "UNSUPPORTED" if outcome.state == OutcomeState.UNSUPPORTED else "SUPPORTED"


def _status_message(session: Session) -> str:
    outcome = session.outcome
    if not session.source_matches_materialization:
        return (
            "Validated source does not match this materialization; reimport it as another revision"
        )
    messages = {
        OutcomeState.VALID: "Valid and supported",
        OutcomeState.BLOCKED_RIGHTS: "Valid and supported; media requires acknowledgement",
        OutcomeState.UNSUPPORTED: "Valid package; one or more runtime capabilities are unsupported",
        OutcomeState.INVALID: "Invalid package; diagnostics are available and media is disabled",
        OutcomeState.INCOMPLETE: (
            "Inspection is incomplete because one or more trust checks were skipped; media is disabled"
        ),
        OutcomeState.RESOURCE_LIMITED: (
            "Validation stopped at a configured local limit; package validity is undetermined"
        ),
        OutcomeState.CANCELLED: "Validation cancelled; diagnostics are available and media is disabled",
    }
    return messages.get(outcome.state, outcome.state.value)


def _store_manifest_text(session: Session) -> None:
    if not session.source_matches_materialization:
        # A rejected relink candidate must never overwrite the exact manifest
        # preserved for the existing materialization.
        return
    if session.outcome.manifest is None and not getattr(session.outcome, "manifest_bytes", b""):
        return
    name = f"VAO::{session.materialization_id[:12]}::manifest.json"
    text = bpy.data.texts.get(name) or bpy.data.texts.new(name)
    raw = getattr(session.outcome, "manifest_bytes", b"") or b""
    exact = _manifest_bytes_match(raw, session.outcome.manifest_sha256)
    if not exact:
        raw = _read_matching_manifest(session)
        exact = bool(raw)
    if exact:
        try:
            source = raw.decode("utf-8")
        except UnicodeError:
            source = ""
            exact = False
    else:
        source = ""
    if not source:
        source = json.dumps(
            thaw_json_value(session.outcome.manifest or {}),
            ensure_ascii=False,
            indent=2,
        )
    text.clear()
    text.write(source)
    text["vao_manifest_sha256"] = session.outcome.manifest_sha256
    text[TRACE_MATERIALIZATION_ID] = session.materialization_id
    text["vao_exact_validated_bytes"] = exact
    text["vao_read_only_source"] = True


def _manifest_bytes_match(raw: bytes, expected_sha256: str) -> bool:
    return bool(raw and expected_sha256 and hashlib.sha256(raw).hexdigest() == expected_sha256)


def _read_matching_manifest(session: Session) -> bytes:
    """Compatibility fallback that accepts only the already validated manifest hash."""
    try:
        with zipfile.ZipFile(session.source_path, "r") as zf:
            info = zf.getinfo("vao-manifest.json")
            if info.file_size > 32 * 1024 * 1024:
                return b""
            raw = zf.read(info)
    except (OSError, zipfile.BadZipFile, KeyError):
        return b""
    return raw if _manifest_bytes_match(raw, session.outcome.manifest_sha256) else b""


def _store_diagnostics_text(session: Session) -> None:
    if session.source_matches_materialization:
        name = f"VAO::{session.materialization_id[:12]}::diagnostics.json"
    else:
        name = f"VAO::relink-attempt::{session.id[:12]}::diagnostics.json"
        session.transient_text_names.add(name)
    text = bpy.data.texts.get(name) or bpy.data.texts.new(name)
    source = json.dumps(
        thaw_json_value(session.outcome.report(redact_paths=True)),
        ensure_ascii=False,
        indent=2,
    )
    text.clear()
    text.write(source + "\n")
    if session.source_matches_materialization:
        text[TRACE_MATERIALIZATION_ID] = session.materialization_id
    else:
        text["vao_relink_attempt_for"] = session.materialization_id
    text["vao_diagnostic_result"] = True
    text["vao_read_only_source"] = True


def thaw_json_value(value):
    if hasattr(value, "items"):
        return {str(key): thaw_json_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [thaw_json_value(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return sorted(thaw_json_value(item) for item in value)
    return value


def close_session(scene: bpy.types.Scene) -> Session | None:
    if not hasattr(scene, "vao_runtime"):
        return None
    runtime = scene.vao_runtime
    session = SESSIONS.get(runtime.session_id)
    if session is not None and session.scene == scene:
        SESSIONS.pop(runtime.session_id, None)
    else:
        session = None
    if session:
        session.stop_audio()
        session.release_cache_paths()
        _remove_transient_texts(session)
        if not session.root_collection_name:
            _remove_session_texts(session.materialization_id)
            runtime.materialization_id = ""
    runtime.session_id = ""
    runtime.media_enabled = False
    runtime.performance_active = False
    runtime.rights_acknowledged = False
    runtime.rights_state = "NOT_EVALUATED"
    return session


def _remove_session_texts(materialization_id: str) -> None:
    if not materialization_id:
        return
    for text in tuple(bpy.data.texts):
        if text.get(TRACE_MATERIALIZATION_ID) == materialization_id:
            bpy.data.texts.remove(text)


def _remove_transient_texts(session: Session) -> None:
    for name in tuple(session.transient_text_names):
        text = bpy.data.texts.get(name)
        if text is not None:
            bpy.data.texts.remove(text)
        session.transient_text_names.discard(name)


def close_all() -> None:
    for session in tuple(SESSIONS.values()):
        session.stop_audio()
        session.release_cache_paths()
        _remove_transient_texts(session)
        try:
            if hasattr(session.scene, "vao_runtime"):
                runtime = session.scene.vao_runtime
                if runtime.session_id == session.id:
                    runtime.session_id = ""
                    runtime.media_enabled = False
                    runtime.performance_active = False
        except ReferenceError:
            pass
    SESSIONS.clear()


def _scene_collections(scene: bpy.types.Scene) -> Iterable[bpy.types.Collection]:
    seen: set[int] = set()

    def walk(collection: bpy.types.Collection):
        pointer = collection.as_pointer()
        if pointer in seen:
            return
        seen.add(pointer)
        yield collection
        for child in collection.children:
            yield from walk(child)

    for child in scene.collection.children:
        yield from walk(child)


def detached_materializations(scene: bpy.types.Scene) -> tuple[DetachedMaterialization, ...]:
    """Discover every managed root reachable from ``scene`` only."""
    collections = tuple(_scene_collections(scene))
    roots: list[bpy.types.Collection] = []
    for collection in collections:
        is_root = bool(collection.get(TRACE_ROOT))
        if not is_root and collection.name.startswith("VAO::"):
            # Compatibility with files saved before explicit root tagging.
            has_representations = any(
                child.name == "Representations"
                or child.get("vao_collection_role") == "Representations"
                for child in collection.children
            )
            is_root = bool(
                collection.get("vao_package_id")
                and collection.get("vao_manifest_sha256")
                and has_representations
            )
        if is_root:
            roots.append(collection)
    records = []
    for root in roots:
        legacy_source = str(root.get("vao_source_path", ""))
        source_name = Path(str(root.get("vao_source_name", "")) or legacy_source).name
        if legacy_source:
            try:
                del root["vao_source_path"]
            except (AttributeError, RuntimeError, TypeError):
                pass
        materialization_id = (
            str(root.get(TRACE_MATERIALIZATION_ID, ""))
            or hashlib.sha256(
                f"{scene.name}\0{root.name}\0{root.get('vao_manifest_sha256', '')}".encode("utf-8")
            ).hexdigest()
        )
        records.append(
            DetachedMaterialization(
                materialization_id=materialization_id,
                root_name=root.name,
                title=str(root.get("vao_title", root.name.removeprefix("VAO::"))),
                package_id=str(root.get("vao_package_id", "")),
                revision=str(root.get("vao_revision", "")),
                release_id=str(root.get("vao_release_id", "")),
                format_version=str(root.get("vao_format_version", "")),
                manifest_sha256=str(root.get("vao_manifest_sha256", "")),
                archive_sha256=str(root.get("vao_archive_sha256", "")),
                source_path=source_name,
            )
        )
    return tuple(sorted(records, key=lambda item: (item.title.casefold(), item.materialization_id)))


def materialization_is_shared(root_name: str) -> bool:
    root = bpy.data.collections.get(root_name)
    if root is None:
        return False
    return sum(root in tuple(_scene_collections(scene)) for scene in bpy.data.scenes) > 1


def resync_after_undo(scene: bpy.types.Scene) -> None:
    """Reconcile ephemeral session root ownership with Blender's undoable data state."""
    session = active_session(scene)
    if session is None:
        discover_detached(scene)
        return
    match = next(
        (
            item
            for item in detached_materializations(scene)
            if item.materialization_id == session.materialization_id
        ),
        None,
    )
    runtime = scene.vao_runtime
    if match:
        session.root_collection_name = match.root_name
        runtime.root_collection_name = match.root_name
        runtime.materialization_state = "READY"
        root = bpy.data.collections.get(match.root_name)
        if root is not None:
            root[TRACE_SESSION_ID] = session.id
    else:
        session.root_collection_name = ""
        runtime.root_collection_name = ""
        runtime.materialization_state = "NONE"
    discover_detached(scene)


def discover_detached(scene: bpy.types.Scene) -> tuple[DetachedMaterialization, ...]:
    runtime = scene.vao_runtime
    records = detached_materializations(scene)
    runtime.detached_materializations.clear()
    for record in records:
        item = runtime.detached_materializations.add()
        item.materialization_id = record.materialization_id
        item.root_name = record.root_name
        item.title = record.title
        item.package_id = record.package_id
        item.revision = record.revision
        item.release_id = record.release_id
        item.format_version = record.format_version
        item.manifest_sha256 = record.manifest_sha256
        item.archive_sha256 = record.archive_sha256
        item.source_path = record.source_path
    runtime.detached_count = len(records)
    if active_session(scene):
        return records
    runtime.session_id = ""
    runtime.media_enabled = False
    runtime.rights_acknowledged = False
    runtime.performance_active = False
    # A saved diagnostic-only result remains the selected inspection target
    # even when unrelated managed roots also exist in this scene.
    if _restore_saved_diagnostic(scene):
        return records
    if records:
        select_detached(scene, records[0].materialization_id)
    else:
        _reset_empty_runtime(runtime)
    return records


def _reset_empty_runtime(runtime) -> None:
    runtime.session_id = ""
    runtime.materialization_id = ""
    runtime.root_collection_name = ""
    runtime.state = "EMPTY"
    runtime.result_state = ""
    runtime.validity_state = "NOT_EVALUATED"
    runtime.support_state = "NOT_EVALUATED"
    runtime.rights_state = "NOT_EVALUATED"
    runtime.materialization_state = "NONE"
    runtime.status_message = "Choose a .vao package to begin"
    runtime.source_path = ""
    runtime.source_name = ""
    runtime.title = ""
    runtime.package_id = ""
    runtime.revision = ""
    runtime.release_id = ""
    runtime.format_version = ""
    runtime.carrier_mode = ""
    runtime.archive_sha256 = ""
    runtime.manifest_sha256 = ""
    runtime.expected_archive_sha256 = ""
    runtime.expected_manifest_sha256 = ""
    for name in (
        "verified_assets",
        "entity_count",
        "relation_count",
        "asset_count",
        "logical_asset_count",
        "realization_count",
        "scientific_observation_count",
        "protocol_binding_count",
        "physical_component_count",
        "distribution_count",
        "frame_count",
        "pose_count",
        "measurement_count",
        "response_set_count",
        "rir_count",
    ):
        setattr(runtime, name, 0)
    for name in (
        "selected_asset_id",
        "selected_entity_id",
        "selected_relation_id",
        "selected_logical_asset_id",
        "selected_realization_id",
        "selected_record_key",
    ):
        setattr(runtime, name, "")


def _restore_saved_diagnostic(scene: bpy.types.Scene) -> bool:
    """Restore inspectability only; saved reports never restore payload authority."""
    runtime = scene.vao_runtime
    materialization_id = runtime.materialization_id
    if not materialization_id:
        return False
    text = next(
        (
            item
            for item in bpy.data.texts
            if item.get("vao_diagnostic_result")
            and item.get(TRACE_MATERIALIZATION_ID) == materialization_id
        ),
        None,
    )
    if text is None:
        return False
    try:
        source = text.as_string()
        if len(source.encode("utf-8")) > 16 * 1024 * 1024:
            return False
        report = json.loads(source)
        if not isinstance(report, Mapping):
            return False
        state_value = report.get("state", "")
        if not isinstance(state_value, str):
            return False
        state = OutcomeState(state_value)
        if state in {OutcomeState.VALID, OutcomeState.UNSUPPORTED, OutcomeState.BLOCKED_RIGHTS}:
            return False
        raw_diagnostics = report.get("diagnostics", ())
        if (
            not isinstance(raw_diagnostics, (tuple, list))
            or len(raw_diagnostics) > MAX_SAVED_DIAGNOSTICS
        ):
            return False
        restored_diagnostics: list[Diagnostic] = []
        for item in raw_diagnostics:
            if not isinstance(item, Mapping):
                return False
            fields = {
                "code": item.get("code", "VAO-LIF-003"),
                "severity": item.get("severity", "error"),
                "stage": item.get("stage", "lifecycle"),
                "message": item.get("message", "Saved diagnostic result"),
                "pointer": item.get("pointer", ""),
                "archive_path": item.get("archive_path", ""),
            }
            if any(not isinstance(value, str) for value in fields.values()):
                return False
            related_ids = item.get("related_ids", ())
            if (
                not isinstance(related_ids, (tuple, list))
                or len(related_ids) > MAX_SAVED_RELATED_IDS
                or any(not isinstance(value, str) for value in related_ids)
            ):
                return False
            restored_diagnostics.append(
                Diagnostic(
                    fields["code"],
                    Severity(fields["severity"]),
                    Stage(fields["stage"]),
                    fields["message"],
                    pointer=fields["pointer"],
                    archive_path=fields["archive_path"],
                    related_ids=tuple(related_ids),
                )
            )
        diagnostics = tuple(restored_diagnostics)
        contract = report.get("contract", {})
        if not isinstance(contract, Mapping):
            return False
        archive_sha256 = report.get("archiveSHA256", "")
        manifest_sha256 = report.get("manifestSHA256", "")
        contract_line = contract.get("line", "0.2.2")
        contract_sha256 = contract.get("releaseBundleSHA256", "")
        if any(
            not isinstance(value, str)
            for value in (
                archive_sha256,
                manifest_sha256,
                contract_line,
                contract_sha256,
            )
        ):
            return False
    except (AttributeError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return False
    outcome = ValidationOutcome(
        state=state,
        source_path=runtime.source_path,
        archive_sha256=archive_sha256,
        manifest_sha256=manifest_sha256,
        diagnostics=diagnostics,
        contract_line=contract_line,
        contract_sha256=contract_sha256,
    )
    try:
        install_outcome(scene, outcome, materialization_id=materialization_id)
    except (AttributeError, ReferenceError, RuntimeError, TypeError, ValueError):
        session = active_session(scene)
        if session is not None and session.materialization_id == materialization_id:
            close_session(scene)
        return False
    runtime.materialization_state = "NONE"
    runtime.status_message = (
        "Saved diagnostic-only result restored; reopen the source VAO to perform a new validation"
    )
    return True


def selected_detached(scene: bpy.types.Scene) -> DetachedMaterialization | None:
    runtime = scene.vao_runtime
    materialization_id = runtime.materialization_id
    for item in runtime.detached_materializations:
        if item.materialization_id == materialization_id:
            return DetachedMaterialization(
                item.materialization_id,
                item.root_name,
                item.title,
                item.package_id,
                item.revision,
                item.release_id,
                item.format_version,
                item.manifest_sha256,
                item.archive_sha256,
                item.source_path,
            )
    return None


def select_detached(scene: bpy.types.Scene, materialization_id: str) -> bool:
    runtime = scene.vao_runtime
    for item in runtime.detached_materializations:
        if item.materialization_id != materialization_id:
            continue
        runtime.session_id = ""
        runtime.materialization_id = item.materialization_id
        runtime.root_collection_name = item.root_name
        runtime.state = "DETACHED"
        runtime.result_state = ""
        runtime.validity_state = "PREVIOUSLY_VALIDATED"
        runtime.support_state = "NOT_EVALUATED"
        runtime.rights_state = "NOT_EVALUATED"
        runtime.materialization_state = "DETACHED"
        runtime.title = item.title
        runtime.package_id = item.package_id
        runtime.revision = item.revision
        runtime.release_id = item.release_id
        runtime.format_version = item.format_version
        runtime.expected_manifest_sha256 = item.manifest_sha256
        runtime.expected_archive_sha256 = item.archive_sha256
        runtime.manifest_sha256 = item.manifest_sha256
        runtime.archive_sha256 = item.archive_sha256
        runtime.source_path = item.source_path
        runtime.source_name = Path(item.source_path).name if item.source_path else ""
        runtime.status_message = (
            "Detached scene data: relink and fully revalidate the exact original VAO"
        )
        runtime.media_enabled = False
        return True
    return False
