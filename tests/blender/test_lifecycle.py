"""Blender lifecycle/state regression coverage for independent scene ownership."""

from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import bpy

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from vao_blender.blender.operators import VAO_OT_import_package, VAO_OT_remove_materialization
from vao_blender.blender.scene_adapter import (
    TRACE_KEYS,
    create_control_surface,
    ensure_root,
    remove_materialization,
    remove_representation,
    update_control_surface,
)
from vao_blender.blender.session import (
    active_session,
    close_all,
    close_session,
    detached_materializations,
    discover_detached,
    install_outcome,
    resync_after_undo,
)
from vao_blender.core.diagnostics import Diagnostic, Severity, Stage
from vao_blender.core.model import (
    GatePlan,
    InteractionBundle,
    OutcomeState,
    SelectionPlan,
    ValidationOutcome,
    freeze,
)
from vao_blender.registration import register, unregister

TEST_TEMP = Path(os.environ.get("VAO_TEST_TEMP", tempfile.gettempdir())).resolve()


def outcome(state=OutcomeState.VALID, *, rights=False):
    manifest = {
        "formatVersion": "0.4.0",
        "id": "urn:vao:test:shared-package",
        "title": {"en": "Shared lifecycle package"},
        "release": {"id": "urn:vao:test:release:1", "revision": 1},
    }
    raw = json.dumps(manifest, separators=(",", ":")).encode("utf-8")
    return ValidationOutcome(
        state=state,
        source_path="/tmp/shared-lifecycle.vao",
        archive_sha256="a" * 64,
        manifest_sha256=hashlib.sha256(raw).hexdigest(),
        manifest_bytes=raw,
        manifest=freeze(manifest),
        payload_verification_complete=True,
        archive_hash_complete=True,
        rights_acknowledgement_required=rights,
    )


register()
scene_a = bpy.context.scene
scene_a.name = "Lifecycle A"
scene_b = bpy.data.scenes.new("Lifecycle B")
validated = outcome()

# One package may be active independently in two scenes.
session_a = install_outcome(scene_a, validated)
session_b = install_outcome(scene_b, validated)
assert session_a.id != session_b.id
assert session_a.materialization_id != session_b.materialization_id
assert active_session(scene_a) is session_a
assert active_session(scene_b) is session_b
assert scene_a.vao_runtime.rights_state == "READY"
manifest_text = next(
    text
    for text in bpy.data.texts
    if text.get("vao_materialization_id") == session_a.materialization_id
    and text.get("vao_manifest_sha256")
)
assert manifest_text["vao_exact_validated_bytes"] is True
assert manifest_text.as_string().encode("utf-8") == validated.manifest_bytes

# A duplicated scene may inherit a stale RNA session ID, but it cannot steal
# the originating scene's live registry entry.
scene_copy = scene_a.copy()
scene_copy.name = "Lifecycle copied scene"
assert active_session(scene_copy) is None
copy_session = install_outcome(scene_copy, validated)
assert active_session(scene_a) is session_a
assert active_session(scene_copy) is copy_session
close_session(scene_copy)
assert active_session(scene_a) is session_a
bpy.data.scenes.remove(scene_copy)

# Undo/redo can replace RNA pointers.  A stale owner pointer may rebind only to
# the unique same-named scene that still claims this session ID.
stale_owner = bpy.data.scenes.new("Lifecycle stale owner")
session_a.scene = stale_owner
session_a.scene_name = scene_a.name
bpy.data.scenes.remove(stale_owner)
assert active_session(scene_a) is session_a
assert session_a.scene == scene_a

# Generated controls remain scoped, labeled, and visibly reflect runtime state.
controls_scene = bpy.data.scenes.new("Lifecycle controls")
controls_outcome = replace(
    validated,
    interaction_plans=InteractionBundle(
        selections=(SelectionPlan("urn:selection", "urn:configuration", "Test stop", False, ()),),
        gates=(GatePlan("urn:gate", 60, "Middle C", "urn:component", ()),),
        voices=(),
    ),
)
controls_session = install_outcome(controls_scene, controls_outcome)
assert create_control_surface(controls_session, controls_scene) == 2
controls_root = bpy.data.collections[controls_session.root_collection_name]
controls = next(
    child for child in controls_root.children if child["vao_collection_role"] == "Controls"
)
gate_control = next(obj for obj in controls.objects if obj.get("vao_gate_id"))
stop_control = next(obj for obj in controls.objects if obj.get("vao_configuration_id"))
assert gate_control["vao_session_id"] == controls_session.id
assert gate_control["vao_materialization_id"] == controls_session.materialization_id
assert gate_control["vao_control_label"] == "Middle C"
assert gate_control.show_name and stop_control.show_name
controls_session.active_configurations.add("urn:configuration")
controls_session.pressed_gates.add("urn:gate")
update_control_surface(controls_session)
assert stop_control["vao_control_active"] is True
assert gate_control["vao_control_active"] is True
try:
    controls_session.ensure_audio()
    raise AssertionError("gate plan without voices was treated as executable audio")
except RuntimeError as exc:
    assert "gate/voice" in str(exc)
remove_materialization(controls_session)
close_session(controls_scene)
bpy.data.scenes.remove(controls_scene)

selection_scene = bpy.data.scenes.new("Lifecycle selection-only controls")
selection_outcome = replace(
    validated,
    interaction_plans=InteractionBundle(
        selections=(
            SelectionPlan("urn:selection-only", "urn:configuration-only", "Solo", True, ()),
        ),
        gates=(),
        voices=(),
    ),
)
selection_session = install_outcome(selection_scene, selection_outcome)
assert create_control_surface(selection_session, selection_scene) == 1
remove_materialization(selection_session)
close_session(selection_scene)
bpy.data.scenes.remove(selection_scene)

root_a = ensure_root(session_a, scene_a)
root_b = ensure_root(session_b, scene_b)
assert root_a != root_b
assert root_a["vao_materialization_id"] == session_a.materialization_id
assert root_b["vao_materialization_id"] == session_b.materialization_id
assert root_a["vao_archive_sha256"] == validated.archive_sha256
assert root_a["vao_source_name"] == Path(validated.source_path).name
assert "vao_source_path" not in root_a

# A user rename never changes durable ownership.  Every live operation resolves
# the unique in-scene materialization ID and refreshes the optional name hint.
root_b.name = "User-renamed VAO materialization"
assert ensure_root(session_b, scene_b) == root_b
assert session_b.root_collection_name == root_b.name
assert scene_b.vao_runtime.root_collection_name == root_b.name

# A live root linked into a second scene is no longer an exclusive mutation
# target, even though its materialization ID remains unique.
scene_a.collection.children.link(root_b)
try:
    ensure_root(session_b, scene_b)
    raise AssertionError("a root shared across two scenes retained mutation authority")
except RuntimeError as exc:
    assert "exclusively" in str(exc)
try:
    remove_materialization(session_b)
    raise AssertionError("a root shared across two scenes was removed globally")
except RuntimeError as exc:
    assert "exclusively" in str(exc)
assert root_b.name in bpy.data.collections
scene_a.collection.children.unlink(root_b)

# Duplicate durable IDs in one scene are ambiguous and fail closed.  The stale
# Blender name is never allowed to choose one duplicate over the other.
duplicate_root = bpy.data.collections.new("Duplicate VAO materialization ID")
duplicate_root["vao_materialization_root"] = True
duplicate_root[TRACE_KEYS["materialization"]] = session_b.materialization_id
scene_b.collection.children.link(duplicate_root)
try:
    ensure_root(session_b, scene_b)
    raise AssertionError("duplicate materialization IDs were resolved by collection name")
except RuntimeError as exc:
    assert "multiple managed VAO roots" in str(exc)
try:
    remove_materialization(session_b)
    raise AssertionError("ambiguous duplicate materialization IDs were removed")
except RuntimeError as exc:
    assert "multiple managed VAO roots" in str(exc)
assert root_b.name in bpy.data.collections and duplicate_root.name in bpy.data.collections
scene_b.collection.children.unlink(duplicate_root)
bpy.data.collections.remove(duplicate_root)

# A live session never materializes into a globally surviving collection that
# has been unlinked from its owning scene.
scene_b.collection.children.unlink(root_b)
try:
    ensure_root(session_b, scene_b)
    raise AssertionError("unlinked global collection was reused outside its owning scene")
except RuntimeError as exc:
    assert "owning scene" in str(exc)
scene_b.collection.children.link(root_b)

# Selection is restricted to the active session's managed root even when IDs collide.
object_a = bpy.data.objects.new("Lifecycle entity A", None)
object_a["vao_entity_ids"] = "urn:vao:test:entity"
object_a[TRACE_KEYS["materialization"]] = session_a.materialization_id
object_a[TRACE_KEYS["session"]] = session_a.id
representations_a = next(
    child for child in root_a.children if child["vao_collection_role"] == "Representations"
)
representations_a.objects.link(object_a)
object_b = bpy.data.objects.new("Lifecycle entity B", None)
object_b["vao_entity_id"] = "urn:vao:test:entity"
object_b[TRACE_KEYS["materialization"]] = session_b.materialization_id
object_b[TRACE_KEYS["session"]] = session_b.id
representations_b = next(
    child for child in root_b.children if child["vao_collection_role"] == "Representations"
)
representations_b.objects.link(object_b)

# Global collection deletion refuses separately linked managed subtrees, and a
# successful exact-representation removal also cleans its now-unused mesh.
representation = bpy.data.collections.new("Lifecycle removable representation")
representation[TRACE_KEYS["asset"]] = "urn:vao:test:removable-representation"
representation[TRACE_KEYS["materialization"]] = session_b.materialization_id
representations_b.children.link(representation)
representation_mesh = bpy.data.meshes.new("Lifecycle removable mesh")
representation_object = bpy.data.objects.new("Lifecycle removable object", representation_mesh)
representation_object[TRACE_KEYS["materialization"]] = session_b.materialization_id
representation_object[TRACE_KEYS["session"]] = session_b.id
representation.objects.link(representation_object)

# User objects and collections inside a managed representation are not inferred
# to be owned.  Removal preflights the complete subtree before unlinking anything.
representation_user_object = bpy.data.objects.new("Representation user object", None)
representation.objects.link(representation_user_object)
try:
    remove_representation(session_b, "urn:vao:test:removable-representation")
    raise AssertionError("an untagged user object was deleted with its representation")
except RuntimeError as exc:
    assert "object" in str(exc) and "untagged" in str(exc)
assert representation_user_object.name in bpy.data.objects
representation.objects.unlink(representation_user_object)
bpy.data.objects.remove(representation_user_object)
representation_user_collection = bpy.data.collections.new("Representation user collection")
representation.children.link(representation_user_collection)
try:
    remove_representation(session_b, "urn:vao:test:removable-representation")
    raise AssertionError("an untagged user collection was deleted with its representation")
except RuntimeError as exc:
    assert "collection" in str(exc) and "untagged" in str(exc)
assert representation_user_collection.name in bpy.data.collections
representation.children.unlink(representation_user_collection)
bpy.data.collections.remove(representation_user_collection)
external_holder = bpy.data.collections.new("Lifecycle external holder")
scene_b.collection.children.link(external_holder)
external_holder.children.link(representation)
try:
    remove_representation(session_b, "urn:vao:test:removable-representation")
    raise AssertionError("separately linked representation was deleted globally")
except RuntimeError as exc:
    assert "also linked" in str(exc)
assert representation.name in bpy.data.collections
external_holder.children.unlink(representation)
representation_mesh_name = representation_mesh.name
remove_representation(session_b, "urn:vao:test:removable-representation")
assert bpy.data.meshes.get(representation_mesh_name) is None

# The same owned-data-only rule applies to the full materialization root.
root_user_object = bpy.data.objects.new("Root user object", None)
root_b.objects.link(root_user_object)
try:
    remove_materialization(session_b)
    raise AssertionError("an untagged user object was deleted with the materialization")
except RuntimeError as exc:
    assert "object" in str(exc) and "untagged" in str(exc)
assert root_user_object.name in bpy.data.objects
root_b.objects.unlink(root_user_object)
bpy.data.objects.remove(root_user_object)
root_user_collection = bpy.data.collections.new("Root user collection")
root_b.children.link(root_user_collection)
try:
    remove_materialization(session_b)
    raise AssertionError("an untagged user collection was deleted with the materialization")
except RuntimeError as exc:
    assert "collection" in str(exc) and "untagged" in str(exc)
assert root_user_collection.name in bpy.data.collections
root_b.children.unlink(root_user_collection)
bpy.data.collections.remove(root_user_collection)

spatial_b = next(child for child in root_b.children if child["vao_collection_role"] == "Spatial")
external_holder.children.link(spatial_b)
try:
    remove_materialization(session_b)
    raise AssertionError("materialization removed a separately linked managed descendant")
except RuntimeError as exc:
    assert "also linked" in str(exc)
assert root_b.name in bpy.data.collections
external_holder.children.unlink(spatial_b)
scene_b.collection.children.unlink(external_holder)
bpy.data.collections.remove(external_holder)

assert bpy.ops.vao.select_entity(entity_id="urn:vao:test:entity") == {"FINISHED"}
assert object_a.select_get()
assert not object_b.select_get()
assert bpy.context.view_layer.objects.active == object_a

# Explicit materialization removal participates in Blender undo; its post-undo
# reconciliation restores ephemeral ownership from the reinstated trace root.
root_a_name = root_a.name
assert "UNDO" in VAO_OT_remove_materialization.bl_options
session_a.root_collection_name = ""
scene_a.vao_runtime.root_collection_name = ""
scene_a.vao_runtime.materialization_state = "NONE"
resync_after_undo(scene_a)
assert session_a.root_collection_name == root_a_name
assert scene_a.vao_runtime.root_collection_name == root_a_name
assert scene_a.vao_runtime.materialization_state == "READY"

# Closing one scene must not affect the other scene's session.
assert close_session(scene_b) is session_b
assert active_session(scene_b) is None
assert active_session(scene_a) is session_a
records_b = discover_detached(scene_b)
assert len(records_b) == 1
assert records_b[0].root_name == root_b.name
assert all(record.root_name != root_a.name for record in records_b)

# Detached discovery is complete and strictly scene-scoped.
root_a["vao_source_path"] = "/Users/example/Private/shared-lifecycle.vao"
records_a = detached_materializations(scene_a)
assert len(records_a) == 1
detached_a = records_a[0]
assert detached_a.root_name == root_a.name
assert detached_a.archive_sha256 == validated.archive_sha256
assert detached_a.source_path == "shared-lifecycle.vao"
assert "vao_source_path" not in root_a

# Exact relink accepts both hashes; a changed archive remains inspectable but detached.
close_session(scene_a)
fake = SimpleNamespace(
    _target_scene=scene_a,
    operation="RELINK",
    _detached_record=lambda: detached_a,
)
VAO_OT_import_package._install_result(fake, validated)
exact_session = active_session(scene_a)
assert exact_session is not None
assert exact_session.source_matches_materialization
assert exact_session.materialization_id == detached_a.materialization_id
assert scene_a.vao_runtime.materialization_state == "ATTACHED"

changed = replace(validated, archive_sha256="b" * 64)
VAO_OT_import_package._install_result(fake, changed)
mismatch_session = active_session(scene_a)
assert mismatch_session is not None
assert not mismatch_session.source_matches_materialization
assert not mismatch_session.media_ready(scene_a)
assert scene_a.vao_runtime.materialization_state == "DETACHED"
assert any(item.code == "VAO-LIF-001" for item in mismatch_session.outcome.diagnostics)
preserved_manifest = next(
    text
    for text in bpy.data.texts
    if text.get("vao_materialization_id") == detached_a.materialization_id
    and text.get("vao_manifest_sha256")
)
assert preserved_manifest.as_string().encode("utf-8") == validated.manifest_bytes
assert any(
    text.get("vao_relink_attempt_for") == detached_a.materialization_id for text in bpy.data.texts
)

# Acknowledgement changes only the rights dimension, never unsupported support state.
unsupported = outcome(OutcomeState.UNSUPPORTED, rights=True)
unsupported_session = install_outcome(scene_a, unsupported)
assert scene_a.vao_runtime.state == "UNSUPPORTED"
assert scene_a.vao_runtime.support_state == "UNSUPPORTED"
assert scene_a.vao_runtime.rights_state == "ACKNOWLEDGEMENT_REQUIRED"
assert bpy.ops.vao.acknowledge_rights() == {"FINISHED"}
assert scene_a.vao_runtime.state == "UNSUPPORTED"
assert scene_a.vao_runtime.support_state == "UNSUPPORTED"
assert scene_a.vao_runtime.rights_state == "ACKNOWLEDGED"
assert unsupported_session.rights_ready(scene_a)

# Wrong-shaped values from an invalid manifest remain diagnostic data and must
# never crash Blender RNA population or be mistaken for supported model counts.
hostile_manifest = ValidationOutcome(
    OutcomeState.INVALID,
    "/tmp/hostile-shapes.vao",
    manifest=freeze(
        {
            "id": ["not", "a", "string"],
            "title": {"en": 7},
            "release": [],
            "formatVersion": {"unexpected": "mapping"},
            "scientific": [],
            "interactionModel": "not-a-registry",
            "physicalSystem": 42,
            "distributions": {},
        }
    ),
    rights_acknowledgement_required=True,
)
hostile_session = install_outcome(scene_a, hostile_manifest)
assert active_session(scene_a) is hostile_session
assert scene_a.vao_runtime.title == "7"
assert scene_a.vao_runtime.package_id == ""
assert scene_a.vao_runtime.format_version == ""
assert scene_a.vao_runtime.scientific_observation_count == 0
assert scene_a.vao_runtime.protocol_binding_count == 0
assert scene_a.vao_runtime.physical_component_count == 0
assert scene_a.vao_runtime.distribution_count == 0
assert scene_a.vao_runtime.rights_state == "NOT_EVALUATED"
assert not bpy.ops.vao.acknowledge_rights.poll()
assert not hostile_session.media_ready(scene_a)
hostile_report_path = TEST_TEMP / "vao-blender-hostile-shapes-diagnostics.json"
assert bpy.ops.vao.export_diagnostics(filepath=str(hostile_report_path)) == {"FINISHED"}
assert json.loads(hostile_report_path.read_text(encoding="utf-8"))["state"] == "invalid"

# Local-limit, cancelled, and intentionally incomplete results are equally
# inspectable while remaining unable to authorize payload operations.
for result_state, expected_validity in (
    (OutcomeState.RESOURCE_LIMITED, "UNDETERMINED_LIMIT"),
    (OutcomeState.CANCELLED, "NOT_EVALUATED"),
    (OutcomeState.INCOMPLETE, "INCOMPLETE"),
):
    diagnostic_only = ValidationOutcome(
        result_state,
        f"/tmp/{result_state.value}.vao",
        diagnostics=(
            Diagnostic(
                "VAO-LIF-997",
                Severity.INFO,
                Stage.LIFECYCLE,
                f"synthetic {result_state.value} result",
            ),
        ),
    )
    diagnostic_session = install_outcome(scene_a, diagnostic_only)
    assert active_session(scene_a) is diagnostic_session
    assert scene_a.vao_runtime.validity_state == expected_validity
    assert scene_a.vao_runtime.rights_state == "NOT_EVALUATED"
    assert not diagnostic_session.media_ready(scene_a)

# Invalid results remain active/exportable diagnostic sessions and cannot use media.
invalid = ValidationOutcome(
    state=OutcomeState.INVALID,
    source_path="/tmp/invalid.vao",
    diagnostics=(
        Diagnostic("VAO-CNT-999", Severity.ERROR, Stage.CONTAINER, "synthetic invalid result"),
    ),
)
invalid_session = install_outcome(scene_a, invalid)
assert active_session(scene_a) is invalid_session
assert scene_a.vao_runtime.validity_state == "INVALID"
assert scene_a.vao_runtime.state == "INVALID"
assert scene_a.vao_runtime.rights_state == "NOT_EVALUATED"
assert not invalid_session.media_ready(scene_a)
assert any(
    text.get("vao_diagnostic_result")
    and text.get("vao_materialization_id") == invalid_session.materialization_id
    for text in bpy.data.texts
)
diagnostic_path = TEST_TEMP / "vao-blender-invalid-diagnostics.json"
assert bpy.ops.vao.export_diagnostics(filepath=str(diagnostic_path)) == {"FINISHED"}
report = json.loads(diagnostic_path.read_text(encoding="utf-8"))
assert report["state"] == "invalid"
assert report["source"] == "invalid.vao"
assert report["hostState"]["validity"] == "INVALID"
assert report["hostState"]["sourceMatchesMaterialization"] is True
assert close_session(scene_a) is invalid_session
assert active_session(scene_a) is None
assert not any(
    text.get("vao_materialization_id") == invalid_session.materialization_id
    for text in bpy.data.texts
)

close_all()
remove_materialization(session_a)
remove_materialization(session_b)
unregister()
print("VAO_BLENDER_LIFECYCLE_OK")
