"""Main-thread session ownership and .blend trace metadata."""

from __future__ import annotations

import hashlib
import json
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

import bpy

from ..core.cache import AssetCache
from ..core.model import OutcomeState, ValidationOutcome
from .preferences import addon_preferences, cache_root


@dataclass(slots=True)
class Session:
    id: str
    outcome: ValidationOutcome
    active_configurations: set[str] = field(default_factory=set)
    pressed_gates: set[str] = field(default_factory=set)
    audio_engine: object | None = None
    root_collection_name: str = ""

    @property
    def source_path(self) -> str:
        return self.outcome.source_path

    @property
    def cache(self) -> AssetCache:
        preferences = addon_preferences()
        quota = (preferences.cache_quota_gib if preferences else 20) * 1024**3
        return AssetCache(cache_root(), quota_bytes=quota)

    def rights_ready(self, scene: bpy.types.Scene) -> bool:
        return (
            not self.outcome.rights_acknowledgement_required
            or scene.vao_runtime.rights_acknowledged
        )

    def ensure_audio(self):
        if self.outcome.contract_line in {"0.3.2", "0.4.0", "0.5.0"}:
            raise RuntimeError(
                f"VAO {self.outcome.contract_line} impulse responses are metadata/filter-kernel "
                f"records; VAO {self.outcome.contract_line} Playable execution, ordinary playback, "
                "and convolution are not implemented"
            )
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


SESSIONS: dict[str, Session] = {}


def active_session(scene: bpy.types.Scene | None = None) -> Session | None:
    scene = scene or bpy.context.scene
    if scene is None or not hasattr(scene, "vao_runtime"):
        return None
    return SESSIONS.get(scene.vao_runtime.session_id)


def install_outcome(scene: bpy.types.Scene, outcome: ValidationOutcome) -> Session:
    manifest = outcome.manifest or {}
    source_identity = hashlib.sha256(
        str(Path(outcome.source_path).expanduser().resolve()).encode("utf-8")
    ).hexdigest()
    session_id = outcome.manifest_sha256 or outcome.archive_sha256 or source_identity
    current_id = scene.vao_runtime.session_id
    if current_id and current_id != session_id:
        current = SESSIONS.pop(current_id, None)
        if current:
            current.stop_audio()
    previous = SESSIONS.pop(session_id, None)
    if previous:
        previous.stop_audio()
    session = Session(session_id, outcome)
    SESSIONS[session_id] = session
    runtime = scene.vao_runtime
    runtime.session_id = session_id
    runtime.state = outcome.state.value.upper()
    runtime.status_message = {
        OutcomeState.VALID: "Valid and supported",
        OutcomeState.BLOCKED_RIGHTS: "Valid; media use needs rights acknowledgement",
        OutcomeState.UNSUPPORTED: "Valid package with unsupported runtime capabilities",
    }.get(outcome.state, outcome.state.value)
    runtime.source_name = Path(outcome.source_path).name
    title = manifest.get("title", {})
    runtime.title = (
        title.get("en") or next(iter(title.values()), runtime.source_name)
        if hasattr(title, "values")
        else str(title)
    )
    runtime.package_id = str(manifest.get("id", ""))
    release = manifest.get("release", {})
    runtime.revision = str(
        release.get("revision", "") if hasattr(release, "get") else manifest.get("revision", "")
    )
    runtime.release_id = str(release.get("id", "") if hasattr(release, "get") else "")
    runtime.format_version = str(manifest.get("formatVersion", ""))
    runtime.carrier_mode = outcome.carrier.mode if outcome.carrier else ""
    runtime.verified_assets = len(outcome.verified_assets)
    runtime.entity_count = 0
    runtime.relation_count = 0
    runtime.asset_count = 0
    runtime.logical_asset_count = len(outcome.logical_assets)
    runtime.realization_count = len(outcome.realizations)
    scientific = manifest.get("scientific", {})
    interaction = manifest.get("interactionModel", {})
    physical = manifest.get("physicalSystem", {})
    runtime.scientific_observation_count = len(scientific.get("observations", ()))
    runtime.protocol_binding_count = len(interaction.get("protocolBindings", ()))
    runtime.physical_component_count = len(physical.get("components", ()))
    runtime.distribution_count = len(manifest.get("distributions", ()))
    runtime.frame_count = 0
    runtime.pose_count = 0
    runtime.measurement_count = 0
    runtime.response_set_count = 0
    runtime.rir_count = 0
    runtime.selected_asset_id = ""
    runtime.selected_entity_id = ""
    runtime.selected_logical_asset_id = ""
    runtime.selected_realization_id = ""
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
    runtime.progress = 1.0
    runtime.progress_stage = "complete"
    _store_manifest_text(session)
    return session


def _store_manifest_text(session: Session) -> None:
    name = f"VAO::{session.id[:12]}::manifest.json"
    text = bpy.data.texts.get(name) or bpy.data.texts.new(name)
    try:
        with zipfile.ZipFile(session.source_path, "r") as zf:
            source = zf.read("vao-manifest.json").decode("utf-8")
    except (OSError, zipfile.BadZipFile, KeyError, UnicodeError):
        source = json.dumps(_thaw(session.outcome.manifest or {}), ensure_ascii=False, indent=2)
    text.clear()
    text.write(source)
    text["vao_manifest_sha256"] = session.outcome.manifest_sha256
    text["vao_read_only_source"] = True


def _thaw(value):
    if hasattr(value, "items"):
        return {str(key): _thaw(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_thaw(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return sorted(_thaw(item) for item in value)
    return value


def close_all() -> None:
    for session in tuple(SESSIONS.values()):
        session.stop_audio()
    SESSIONS.clear()


def discover_detached(scene: bpy.types.Scene) -> None:
    runtime = scene.vao_runtime
    for collection in bpy.data.collections:
        if collection.get("vao_package_id") and collection.get("vao_manifest_sha256"):
            runtime.session_id = ""
            runtime.state = "DETACHED"
            runtime.title = collection.name.removeprefix("VAO::")
            runtime.package_id = collection.get("vao_package_id", "")
            runtime.revision = str(collection.get("vao_revision", ""))
            runtime.format_version = collection.get("vao_format_version", "")
            runtime.status_message = "Detached scene data: relink and revalidate the original VAO"
            return
