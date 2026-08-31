"""Validate and install the checked-in minimal VAO 0.5 carrier in Blender."""

from __future__ import annotations

import sys
from pathlib import Path

import bpy

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from vao_blender.blender.panels import _registry_records
from vao_blender.blender.session import active_session, close_all, install_outcome
from vao_blender.core.archive import validate_package
from vao_blender.core.model import OutcomeState
from vao_blender.registration import register, unregister

FIXTURE = ROOT / "tests" / "fixtures" / "vao-0.5.0" / "carriers" / "minimal.vao"
EXPECTED_ARCHIVE_SHA256 = "9bc7ff7eb06cd50a66ab5bfeabdecaef68c8b24a15f5b47bc0013811a241403e"
EXPECTED_MANIFEST_SHA256 = "9261db2780dc4cb7530c0283d3c0c3a2b94f82b77432611313c6737a256197da"

register()
outcome = validate_package(FIXTURE)
assert outcome.state == OutcomeState.VALID
assert outcome.is_valid
assert outcome.payload_verification_complete
assert outcome.archive_hash_complete
assert outcome.contract_line == "0.5.0"
assert outcome.archive_sha256 == EXPECTED_ARCHIVE_SHA256
assert outcome.manifest_sha256 == EXPECTED_MANIFEST_SHA256
assert outcome.manifest_bytes
assert len(outcome.verified_assets) == 1
assert len(outcome.logical_assets) == 1
assert len(outcome.realizations) == 1
assert outcome.carrier.mode == "bootstrap"
assert outcome.acoustic_scene is None

session = install_outcome(bpy.context.scene, outcome)
runtime = bpy.context.scene.vao_runtime
assert active_session(bpy.context.scene) is session
assert runtime.state == "VALID"
assert runtime.validity_state == "VALID"
assert runtime.support_state == "SUPPORTED"
assert runtime.rights_state == "READY"
assert runtime.format_version == "0.5.0"
assert runtime.carrier_mode == "bootstrap"
assert runtime.verified_assets == 1
assert runtime.logical_asset_count == 1
assert runtime.realization_count == 1
assert runtime.scientific_observation_count == 0
assert runtime.protocol_binding_count == 0
assert runtime.physical_component_count == 0
assert runtime.distribution_count == 0
assert runtime.selected_realization_id == ""
assert not bpy.ops.vao.load_visual.poll()
scientific_records = _registry_records(outcome.manifest, "SCIENTIFIC")
assert {record[1] for record in scientific_records} == {
    "activities",
    "agents",
    "protocols",
    "softwareEnvironments",
}
assert all(record[2] for record in scientific_records)
assert _registry_records(outcome.manifest, "PHYSICAL") == []

close_all()
assert active_session(bpy.context.scene) is None
unregister()
print("VAO_BLENDER_05_INTEGRATION_OK")
