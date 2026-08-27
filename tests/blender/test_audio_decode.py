"""Blender aud smoke test for the Cuntz 192 kHz float WAVE master format."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import aud

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from vao_blender.core.archive import validate_package
from vao_blender.core.cache import AssetCache

package = ROOT / "dist/Cuntz-Positiv-4010243-VAO-0.2.2.vao"
outcome = validate_package(package, verify_payload=False, hash_archive=False)
asset = next(item for item in outcome.graph.assets.values() if item.media_type == "audio/wav")
with tempfile.TemporaryDirectory(prefix="vao-audio-smoke-") as directory:
    path = AssetCache(Path(directory) / "cache").extract(package, asset)
    sound = aud.Sound.file(str(path))
    specs = sound.specs
    length = sound.length
    # Force the backend to decode rather than merely accept the filename.
    data = sound.data()
    assert data is not None
    assert length > 1.0
    print(f"AUD_SPECS_RAW {specs!r}")
    rate, channels = specs
    assert rate == 192000
    assert channels == aud.CHANNELS_STEREO
    print(f"VAO_AUDIO_DECODE_OK rate={rate} channels={channels} length={length:.3f}")
