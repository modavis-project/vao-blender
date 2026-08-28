"""Validate and install the DOI-bound Kinoorgel bootstrap in Blender."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import bpy

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from vao_blender.blender.session import close_all, install_outcome
from vao_blender.core.archive import validate_package
from vao_blender.core.model import OutcomeState
from vao_blender.registration import register, unregister

package = Path(os.environ["KINOORGEL_VAO_BOOTSTRAP"])
register()
outcome = validate_package(package)
assert outcome.state == OutcomeState.UNSUPPORTED
assert outcome.is_valid
assert outcome.contract_line == "0.5.0"
assert outcome.carrier.mode == "bootstrap"
assert len(outcome.verified_assets) == 36
assert len(outcome.logical_assets) == 1462
assert len(outcome.realizations) == 4584
assert not outcome.rights_acknowledgement_required
assert outcome.acoustic_scene is None

session = install_outcome(bpy.context.scene, outcome)
runtime = bpy.context.scene.vao_runtime
assert runtime.format_version == "0.5.0"
assert runtime.carrier_mode == "bootstrap"
assert runtime.scientific_observation_count == 5766
assert runtime.protocol_binding_count == 543
assert runtime.physical_component_count == 110
assert runtime.distribution_count == 4548
assert session.rights_ready(bpy.context.scene)

close_all()
unregister()
print("VAO_BLENDER_KINOORGEL_05_OK")
