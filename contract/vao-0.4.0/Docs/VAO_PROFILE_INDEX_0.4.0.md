# VAO 0.4.0 profile index

Profiles are versioned conformance contracts. Core and Dynamic Delivery are mandatory for every VAO 0.4.0 manifest. Other profiles become mandatory when their registries are non-empty or when explicitly claimed.

| Profile | IRI | Trigger |
| --- | --- | --- |
| [Core](VAO_CORE_PROFILE_0.4.0.md) | `https://w3id.org/modavis/vao/profile/core/0.4.0` | always |
| [Dynamic Delivery](VAO_DYNAMIC_DELIVERY_PROFILE_0.4.0.md) | `https://w3id.org/modavis/vao/profile/dynamic-delivery/0.4.0` | always |
| [Scientific](VAO_SCIENTIFIC_PROFILE_0.4.0.md) | `https://w3id.org/modavis/vao/profile/scientific/0.4.0` | any scientific record |
| [Multimodal Timeline](VAO_MULTIMODAL_PROFILE_0.4.0.md) | `https://w3id.org/modavis/vao/profile/multimodal/0.4.0` | any timebase/track/mapping/annotation |
| [Physical Instrument](VAO_PHYSICAL_INSTRUMENT_PROFILE_0.4.0.md) | `https://w3id.org/modavis/vao/profile/physical-instrument/0.4.0` | any physical-system record |
| [Playable](VAO_PLAYABLE_PROFILE_0.4.0.md) | `https://w3id.org/modavis/vao/profile/playable/0.4.0` | playable/interaction/capture data |
| [Deterministic Runtime](VAO_DETERMINISTIC_RUNTIME_PROFILE_0.4.0.md) | `https://w3id.org/modavis/vao/profile/deterministic-runtime/0.4.0` | conformance traces, random/runtime records, or stochastic process |
| [Spatial](VAO_SPATIAL_PROFILE_0.4.0.md) | `https://w3id.org/modavis/vao/profile/spatial/0.4.0` | spatial coordinate/pose/geometry assertion or spatial Track |
| [Acoustics](VAO_ACOUSTICS_PROFILE_0.4.0.md) | `https://w3id.org/modavis/vao/profile/acoustics/0.4.0` | acoustic material/response/metric/scene/render assertion |
| [Zenodo Repository](VAO_ZENODO_PROFILE_0.4.0.md) | `https://w3id.org/modavis/vao/profile/repository/zenodo/0.4.0` | Zenodo projection claim |

A profile record occurs in `profiles` with its exact IRI, version `0.4.0`, and required capability IRIs. The same profile IRI occurs in `conformsTo`. Materializable profiles occur in `materializableProfiles` and identify the groups that must be acquired before conformance can be realized.

Processors list supported profile and capability IRIs in their conformance statement. Partial understanding is useful but is not profile conformance.
