"""Concrete-package capability negotiation."""

from __future__ import annotations

from .model import CapabilityResult, GraphIndex, InteractionBundle

SUPPORTED_ALWAYS = {
    "https://w3id.org/modavis/vao/vocab/capability/core-graph",
    "https://w3id.org/modavis/vao/vocab/capability/fixity",
    "https://w3id.org/modavis/vao/vocab/capability/paradata",
}
GENERIC_MODEL = "https://w3id.org/modavis/vao/vocab/capability/generic-model-viewing"
SPATIAL = "https://w3id.org/modavis/vao/vocab/capability/spatial"
INTERACTION = "https://w3id.org/modavis/vao/vocab/capability/interaction"
SAMPLED = "https://w3id.org/modavis/vao/vocab/capability/sampled-instrument-playback"


def negotiate(
    manifest: dict,
    graph: GraphIndex,
    bundle: InteractionBundle | None,
) -> tuple[CapabilityResult, ...]:
    required = sorted(
        {
            capability
            for profile in manifest.get("profiles", [])
            for capability in profile.get("requiredCapabilities", [])
        }
    )
    results: list[CapabilityResult] = []
    for capability in required:
        supported = False
        reason = ""
        if capability in SUPPORTED_ALWAYS:
            supported = True
        elif capability == GENERIC_MODEL:
            supported = any(
                asset.media_type in {"model/gltf-binary", "model/gltf+json"}
                for asset in graph.assets.values()
            )
            reason = "no verified local glTF representation" if not supported else ""
        elif capability == SPATIAL:
            supported = any(
                "https://w3id.org/modavis/vao/ontology#coordinateUnit" in asset.properties
                for asset in graph.assets.values()
            )
            reason = "no supported declared model coordinate metadata" if not supported else ""
        elif capability in {INTERACTION, SAMPLED}:
            supported = bool(bundle and bundle.supported)
            reason = "the complete interaction plan did not compile" if not supported else ""
        else:
            reason = "capability is not implemented by VAO-Blender 0.1"
        results.append(CapabilityResult(capability, supported, reason))
    return tuple(results)
