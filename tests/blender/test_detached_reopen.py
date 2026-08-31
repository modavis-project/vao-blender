"""Save/reopen discovery and exact detached relink smoke test."""

from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

import bpy

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from vao_blender.blender.scene_adapter import ensure_root, remove_materialization
from vao_blender.blender.session import (
    active_session,
    close_session,
    install_outcome,
    selected_detached,
)
from vao_blender.core.diagnostics import Diagnostic, Severity, Stage
from vao_blender.core.model import OutcomeState, ValidationOutcome, freeze
from vao_blender.registration import register, unregister

manifest = {
    "formatVersion": "0.4.0",
    "id": "urn:vao:test:reopen",
    "title": {"en": "Reopen lifecycle"},
    "release": {"id": "urn:vao:test:reopen:release", "revision": 7},
}
raw = json.dumps(manifest, separators=(",", ":")).encode("utf-8")
outcome = ValidationOutcome(
    OutcomeState.VALID,
    "/tmp/reopen.vao",
    archive_sha256="c" * 64,
    manifest_sha256=hashlib.sha256(raw).hexdigest(),
    manifest_bytes=raw,
    manifest=freeze(manifest),
    payload_verification_complete=True,
    archive_hash_complete=True,
)

register()
scene = bpy.context.scene
session = install_outcome(scene, outcome)
root = ensure_root(session, scene)
root_name = root.name
materialization_id = session.materialization_id
output = Path(
    os.environ.get(
        "VAO_TEST_DETACHED_BLEND",
        str(Path(tempfile.gettempdir()) / "vao-blender-detached.blend"),
    )
)
bpy.ops.wm.save_as_mainfile(filepath=str(output), check_existing=False)
bpy.ops.wm.open_mainfile(filepath=str(output), load_ui=False)

scene = bpy.context.scene
runtime = scene.vao_runtime
assert active_session(scene) is None
assert runtime.state == "DETACHED"
assert runtime.materialization_state == "DETACHED"
assert runtime.detached_count == 1
assert runtime.source_path == "reopen.vao"
detached = selected_detached(scene)
assert detached is not None
assert detached.materialization_id == materialization_id
assert detached.root_name == root_name
assert detached.archive_sha256 == outcome.archive_sha256
assert detached.manifest_sha256 == outcome.manifest_sha256
assert detached.source_path == "reopen.vao"
assert "vao_source_path" not in bpy.data.collections[root_name]

relinked = install_outcome(scene, outcome, detached=detached)
assert relinked.materialization_id == materialization_id
assert relinked.root_collection_name == root_name
assert relinked.source_matches_materialization
assert runtime.materialization_state == "ATTACHED"
assert relinked.media_ready(scene)

# Diagnostic-only results survive save/reopen for inspection, but never regain
# validity or payload authority from serialized host state.  They also remain
# selected when an unrelated detached materialization exists in the same scene.
invalid = ValidationOutcome(
    OutcomeState.INVALID,
    "/tmp/reopen-invalid.vao",
    diagnostics=(
        Diagnostic("VAO-CNT-998", Severity.ERROR, Stage.CONTAINER, "saved invalid result"),
    ),
)
invalid_session = install_outcome(scene, invalid)
invalid_materialization_id = invalid_session.materialization_id
bpy.ops.wm.save_as_mainfile(filepath=str(output), check_existing=False)
bpy.ops.wm.open_mainfile(filepath=str(output), load_ui=False)
scene = bpy.context.scene
restored = active_session(scene)
assert restored is not None
assert restored.materialization_id == invalid_materialization_id
assert restored.outcome.state == OutcomeState.INVALID
assert not restored.media_ready(scene)
assert scene.vao_runtime.validity_state == "INVALID"
assert scene.vao_runtime.detached_count == 1
assert any(item.code == "VAO-CNT-998" for item in restored.outcome.diagnostics)

remove_materialization(root_name=root_name, materialization_id=materialization_id)
close_session(scene)

# Crafted .blend Text blocks are untrusted too.  Wrong top-level/diagnostic
# shapes fail closed during load discovery instead of breaking load_post.
malformed_id = "malformed-saved-diagnostic"
malformed = bpy.data.texts.new("VAO::malformed::diagnostics.json")
malformed.write(
    json.dumps(
        {
            "state": "invalid",
            "contract": [],
            "diagnostics": "this must be a bounded array of diagnostic objects",
        }
    )
)
malformed["vao_diagnostic_result"] = True
malformed["vao_materialization_id"] = malformed_id
scene.vao_runtime.materialization_id = malformed_id
scene.vao_runtime.state = "INVALID"
bpy.ops.wm.save_as_mainfile(filepath=str(output), check_existing=False)
bpy.ops.wm.open_mainfile(filepath=str(output), load_ui=False)
scene = bpy.context.scene
assert active_session(scene) is None
assert scene.vao_runtime.state == "EMPTY"
assert scene.vao_runtime.materialization_id == ""
assert scene.vao_runtime.detached_count == 0

unregister()
print(f"VAO_BLENDER_DETACHED_REOPEN_OK blend={output}")
