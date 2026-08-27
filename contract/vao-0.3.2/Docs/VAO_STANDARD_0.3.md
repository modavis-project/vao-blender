# Virtual Acoustic Object (VAO) 0.3.2

Status: private editor's draft and implementation target  
Release line: 0.3  
Normative manifest schema: `https://w3id.org/modavis/vao/0.3/schema/manifest.json`  
Normative context: `https://w3id.org/modavis/vao/0.3/context.jsonld`

## 1. Scope and conformance language

VAO 0.3 defines an immutable, carrier-independent semantic release that names exact byte realizations. A release can be distributed in a small bootstrap carrier, dynamically materialized from version-pinned repositories, or exported as a preservation closure without changing the release identity.

Use of a repository, network access, a DOI, and Zenodo are all OPTIONAL. A fully embedded VAO is conforming and is the normal form for development, local testing, private sharing, air-gapped use, and any workflow that does not need external acquisition. `distributions` and `repositoryBindings` are required registries so their absence is explicit, but both MAY be empty. Zenodo is only one optional adapter profile; the Core and Dynamic Delivery profiles never require it.

The key words MUST, MUST NOT, REQUIRED, SHALL, SHALL NOT, SHOULD, SHOULD NOT, RECOMMENDED, NOT RECOMMENDED, MAY, and OPTIONAL are to be interpreted as described by BCP 14 when they appear in uppercase.

This document and the schemas in `Schemas/*-0.3*` are the candidate normative source set. VAO 0.2.2 remains a separate compatibility line. A 0.3 manifest MUST NOT claim a 0.2 profile IRI, and a processor MUST NOT interpret remote content as satisfying a 0.2.2 profile.

## 2. Design invariants

1. A VAO release is immutable. Hydration, eviction, mirroring, and carrier construction do not revise its semantic manifest.
2. Scientific identity, exact byte identity, repository identity, carrier identity, and local runtime state are distinct.
3. Every realization is pinned by lowercase SHA-256, byte size, media type, representation status, rights, provenance, and objective technical metadata.
4. A repository concept DOI is an update channel only. Automatic acquisition MUST use a version-specific persistent identifier, record identifier, and file identifier, then verify the VAO SHA-256.
5. The manifest cannot grant network trust. Host allowlists, credentials, redirects, transport limits, and user consent are local policy.
6. A bootstrap carrier MUST remain independently meaningful and MUST embed at least one exact realization.
7. A preservation-closure carrier MUST embed every realization needed by every declared profile and group that it marks complete.
8. Materialization receipts are mutable operational evidence and MUST NOT be embedded into the immutable semantic manifest.
9. Publication uses one modular repository record by default. A record family is OPTIONAL and MUST state exact, semantically correct PID relations for every member.

## 3. Identity layers

VAO 0.3 defines the following non-interchangeable identifiers:

| Layer | Required identifier | Meaning |
| --- | --- | --- |
| Conceptual VAO | root `id` | Continuing scientific object across releases |
| Semantic release | `release.id`, `revision`, `contentVersion` | Exact graph, realization set, dependency lock, and policy |
| Manifest bytes | SHA-256 in carrier/release descriptors | Exact serialization of `vao-manifest.json` |
| Carrier | SHA-256 of a `.vao` file in `vao-release.json` | One bootstrap, closure, or custom envelope |
| Repository version | version PID plus record ID | Exact published repository record |
| Repository concept | optional concept PID | Discovery/update channel only |
| Publication topology | publication record IDs plus exact version PIDs | One modular record or an explicit root/member family |
| Realization | SHA-256 and byte size | Exact content bytes |
| Runtime instance | receipt `instanceId` | Local cache/materialization event |

A changed manifest creates a new release ID or revision. A changed realization creates a new SHA-256 and therefore a new release. A differently populated carrier MAY contain the same manifest bytes and release ID. A cache change creates neither a release nor a carrier revision.

## 4. Container format

A `.vao` carrier is ZIP/ZIP64 with UTF-8 entry names. `mimetype` MUST be the first entry, uncompressed, and contain exactly `application/vnd.modavis.vao+zip` without a byte-order mark. `vao-manifest.json` and `META-INF/vao-carrier.json` are REQUIRED. Embedded bytes occur only below `payload/`.

Processors MUST reject absolute paths, backslashes, NUL bytes, dot segments, duplicate normalized paths, symlinks, encrypted entries, unsupported compression, resource-limit violations, and entries outside:

- `mimetype`;
- `vao-manifest.json`;
- `META-INF/vao-carrier.json`;
- `payload/`.

The manifest is carrier-independent and MUST NOT contain embedded paths. The carrier descriptor maps realization IDs to the `payload/` paths present in that carrier. Every payload file MUST occur exactly once in the descriptor, and each mapped file MUST match the realization's size and SHA-256. The descriptor pins the exact manifest bytes; it does not hash itself.

## 5. Manifest model

### 5.1 Release and graph

The root `id` identifies the conceptual VAO. `release.id` identifies the semantic release. `release.revision` is a positive integer local to the conceptual VAO; `release.contentVersion` is the human-facing content version and is not the VAO format version.

`entities` and `relations` preserve the evidence-capable VAO graph. `primaryEntityId` and all `focusEntityIds` MUST resolve locally. A relation has exactly one object resource or literal. Local evidence and provenance references MUST resolve.

### 5.2 Logical assets

A logical asset identifies documented scientific or semantic content independent of its encoding and storage. It has roles, subjects, and one or more realization IDs. A different historical state, capture campaign, reconstruction hypothesis, or materially different spatial meaning SHOULD use a distinct logical asset rather than a quality label.

### 5.3 Realizations

A realization identifies one exact byte sequence. The following fields are mandatory:

- parent `assetId` and `variantSetId`;
- quality tier;
- media type, byte size, and lowercase SHA-256;
- representation status;
- rights and provenance references;
- typed technical metadata;
- zero or more distributions.

Representation status, provenance, and rights are realization-level because a scan, reconstruction, simulation, and creative derivative may share a subject without sharing epistemic status or reuse terms.

An embedded-only realization may have no distribution. A remotely materializable realization MUST have at least one distribution. Multiple distributions of one realization are mirrors only when the expected SHA-256 and byte size are identical.

For audio, technical metadata MUST include sample rate and channel count. Ambisonic material additionally declares order, dimensionality, ACN ordering, and SN3D or N3D normalization. Exchange communities SHOULD also record container, sample format/bit depth, channel labels, calibration, reference level, receiver poses, timing, and ADM/BW64 status where applicable.

For geometry, technical metadata MUST include coordinate-frame reference, unit IRI, handedness, up axis, and LOD. Triangle/vertex counts, texture bounds, geometric error, materials, and purpose limitations SHOULD be recorded when meaningful.

### 5.4 Spatial and acoustic scenes

The Spatial profile requires the closed `acoustics` object and at least one pose or geometry binding. The Acoustics profile requires Spatial and at least one standard acoustic capability. The object contains nine explicit registries: `coordinateFrames`, `poses`, `geometryBindings`, `materialModels`, `measurements`, `responseSets`, `metricSets`, `audioScenes`, and `renderConfigurations`. Registry identifiers share the package-wide identifier space.

A coordinate frame declares 2D/3D dimension, Cartesian or geodetic coordinates, an absolute unit IRI, handedness, up and forward axes, and optional CRS. A child frame MUST identify its parent and an invertible row-major 4×4 homogeneous `transformToParent`; parent links MUST be acyclic. A pose binds an entity to a frame and position. Orientation, when known, is a normalized XYZW quaternion. Producers MUST state `not-applicable` when an axis has no defined meaning and MUST NOT infer axes, units, scale, orientation, or origin from a filename or format.

A geometry binding connects an entity to a logical spatial-model asset and states its purpose: `authoritative-semantic`, `acoustic-simulation`, `runtime-visual`, `collision`, `occlusion`, or `navigation`. Format-specific selectors MAY identify glTF node indices or feature IDs, IFC `GlobalId` values, CityGML identifiers, or absolute USD prim paths. A visualization derivative MUST remain a distinct realization with its own coordinate frame and provenance. A convenient mesh MUST NOT silently become authoritative geometry or proof of an acoustic simulation boundary/material model.

Each `measurement` has a stable identifier and binds an emitter, receiver, source pose, receiver pose, and optional space/configuration state. Both poses MUST describe their named subjects and MUST be transformable to a common coordinate-frame root. `responseSets` describe logical acoustic responses and reference measurements by these stable identifiers; they do not encode storage-array indices.

Byte-specific impulse-response layout belongs in each audio realization's `technicalMetadata.impulseResponse`. It records `responseSetId`, encoding, exact `sampleCount`, time-zero policy, normalization, and one mapping per logical measurement. Each mapping fixes its `dataIRIndex`, channel indices, and optional sample delay. Mappings MUST cover every response-set measurement exactly once, without repeated data indices or channels outside `channelCount`. A WAVE or FLAC realization represents exactly one fixed source–receiver measurement. AES69-SOFA realizations MUST record their SOFA convention and map the SOFA `M` dimension through `dataIRIndex`. HDF5, netCDF, Zarr, and custom encodings MAY be used only with an explicit convention or layout description sufficient to interpret the mapping.

Measured, simulated, hybrid, inferred, and learned responses remain distinct. Their response-set status MUST agree with every realization and the generating activity MUST resolve. A measured response requires measurement/deconvolution evidence; a simulated or hybrid response identifies its simulation activity and SHOULD retain configuration, geometry/material inputs, software/version, solver settings, and random seed. `unspecified` is an explicit time-zero or normalization value and MUST NOT be replaced by a guess.

The capability `position-registered-acoustic-scene` requires resolvable source/receiver measurements. `visual-acoustic-scene` additionally requires geometry and response sets whose realizations and measurement poses share a transformable coordinate-frame root. `simulated-impulse-response` requires simulated or hybrid response data; `measured-impulse-response` requires measured data. A capability claim is machine-checked conformance, not descriptive advertising.

An `audioScene` and `renderConfiguration` MAY document a fixed convolution, response-field interpolation, geometry renderer, learned field, or hybrid renderer. The configuration names the coordinate frame, listener, inputs, valid domain, unsupported-domain policy, and fallbacks. It is declarative and MUST NOT contain executable code. A Blender or game-engine importer can therefore load a glTF realization, apply its declared transform to the acoustic frame, and display source/receiver poses without treating that application as part of the VAO standard.

### 5.5 Distributions and repository bindings

A repository distribution, when present, provides a repository binding, exact version PID, record identifier, file identifier, and access state. It MUST NOT contain bearer tokens, credentials, API base overrides, host allowlists, arbitrary download URLs, or redirect policy. A realization that is embedded in every intended carrier need not have a distribution.

The repository binding identifies the repository type, public instance identity, adapter profile, and resolution rule. Clients supply a trusted adapter configuration. The Zenodo 0.3 profile uses `version-pid-record-file`: resolve the record by ID through the locally configured Zenodo Records API, confirm the version DOI and file key, follow only policy-approved API links, download to a temporary file, then verify size and SHA-256 before commit.

A pack-member distribution identifies an outer pack realization, safe member path, and exact pack-manifest SHA-256. The outer pack is itself a realization with its own repository distribution. The pack manifest lists every member and never includes a hash of itself. Its exact bytes are pinned by the root distribution and release descriptor.

### 5.6 Asset groups

Asset groups specify acquisition and runtime selection without changing asset identity. Each group has:

- a `selectionSetId` for alternatives;
- a quality tier and availability state;
- independent, exactly-one, or at-most-one selection policy;
- realization IDs;
- dependency group IDs and optional fallback group;
- total unique realization byte size;
- runtime capabilities and profiles materialized;
- cache eviction policy.

The dependency graph MUST be acyclic. Fallback edges MUST resolve and MUST NOT form a cycle. A fallback cannot silently substitute a realization of another historical state or incompatible scientific meaning. Selection constraints apply within a `selectionSetId`; a client MUST NOT combine mutually exclusive groups from that set.

### 5.7 Profiles

VAO 0.3 reserves new IRIs:

- `https://w3id.org/modavis/vao/profile/core/0.3`
- `https://w3id.org/modavis/vao/profile/research/0.3`
- `https://w3id.org/modavis/vao/profile/playable/0.3`
- `https://w3id.org/modavis/vao/profile/spatial/0.3`
- `https://w3id.org/modavis/vao/profile/acoustics/0.3`
- `https://w3id.org/modavis/vao/profile/preservation/0.3`
- `https://w3id.org/modavis/vao/profile/experiential/0.3`
- `https://w3id.org/modavis/vao/profile/orgrec-capture/0.3`
- `https://w3id.org/modavis/vao/profile/dynamic-delivery/0.3`
- `https://w3id.org/modavis/vao/profile/repository/zenodo/0.3`

`profiles` contains only claims satisfied by the embedded bootstrap carrier. Every VAO claims Core and Dynamic Delivery; Dynamic Delivery supplies the carrier/realization model and does not imply network use. `materializableProfiles` contains claims that become complete after all named groups and dependencies have been acquired and verified. A profile MUST NOT be simultaneously declared embedded and materializable. The Zenodo profile MUST be claimed only when at least one Zenodo binding is present, and MUST NOT be required otherwise.

Conformance states are intentionally separate:

1. package-valid;
2. embedded-profile-valid;
3. repository-binding-valid;
4. resolvable-at-time-T;
5. selected-groups-hydrated;
6. materialized-profile-valid;
7. preservation-closed.

Unavailability, authentication requirements, and local-policy rejection are operational states. A mismatched version PID, record ID, file identifier, byte size, or SHA-256 is an integrity failure.

### 5.8 Rights and integrity

Rights records explicitly cover the conceptual VAO, logical assets, and realizations. Repository record-level licenses do not replace this graph. Material with materially different access or licensing SHOULD be placed in separate repository records.

The manifest cannot contain a digest of its own serialization. Its `integrity` object therefore declares SHA-256 and locates the exact manifest digest in the carrier and release descriptors.

## 6. Repository release descriptor

`vao-release.json` is a small repository-neutral discovery and publication descriptor. It declares either `single-record` or `record-family`, assigns an internal ID to every publication record, and records repository type/instance, exact version PID, optional concept PID, repository record ID, and a role/size/SHA-256 inventory of every file except `vao-release.json` itself. The self-exclusion prevents a circular digest. The root MUST inventory exactly one `vao-manifest.json` and at least one bootstrap carrier.

`single-record` is the default. It represents one modular repository record containing separately downloadable manifest, carrier, model, audio/pack, metadata, checksum, documentation, and preview files as applicable. It does not require one combined archive. `familyMembers` MUST be empty.

`record-family` requires at least one justified member. An `exclusive` member uses root `hasPart` and reciprocal member `isPartOf`. A `shared` member uses the relation that expresses its actual semantics—such as `requires`, `references`, `isSupplementedBy`, `isDocumentedBy`, or `isDerivedFrom`—and MUST NOT claim exclusive `isPartOf` ownership. Runtime dependencies and family links use exact version PIDs; concept PIDs remain discovery channels.

The Zenodo metadata projection is defined separately because Zenodo is an optional adapter. It binds an API-ready nested `metadata` object to the VAO release and publication-record ID. Relation projections MUST agree with `vao-release.json`. Other repositories MAY define their own mappings without changing VAO Core.

The descriptor is publication metadata, not the semantic manifest. Repository metadata MAY change without changing a release; the pinned files MUST NOT. The VAO publication policy forbids post-publication byte replacement under the same version PID even if a repository permits a correction window. A byte change requires a new repository version and VAO release.

## 7. Materialization algorithm

A conforming resolver performs these steps outside real-time rendering callbacks:

1. Validate archive safety, schemas, graph closure, manifest/carrier binding, and all embedded hashes before network access.
2. Determine locally trusted adapters, capabilities, consent, storage limits, and selected groups.
3. Expand dependency groups and enforce selection-set constraints.
4. Resolve only repository bindings supported by local policy.
5. Fetch the exact record, and confirm version PID, record identifier, file identifier, and declared access state.
6. Download into a private temporary file with redirect, size, time, and decompression limits.
7. Verify exact byte size and VAO SHA-256. Repository MD5 or ETag values are supplementary only.
8. For packs, verify the outer pack, exact pack-manifest bytes, safe member inventory, and every extracted member; reject unlisted members.
9. Atomically commit verified bytes to a content-addressed cache keyed by SHA-256.
10. Emit a separate materialization receipt. Never rewrite the semantic manifest.

Credentials, signed URLs, cache locations, and client host allowlists MUST NOT appear in a receipt intended for exchange.

## 8. Preservation closure

A preservation-closure carrier embeds all required realization bytes and pack manifests for every group it marks complete. It includes representation information needed to interpret preservation formats. The carrier descriptor lists the complete groups and maps every embedded realization. A closure validator MUST prove group completeness, payload closure, and exact fixity without network access.

Repository availability is not preservation closure. Communities SHOULD maintain an independent institutional or archival copy in addition to Zenodo and SHOULD prefer preservation-friendly encodings.

## 9. Compatibility and migration

VAO 0.2.2 packages remain valid under the 0.2 line. Migration to 0.3 preserves source evidence:

- each 0.2 `asset` becomes one logical asset and one exact realization;
- its `path` moves to the carrier descriptor;
- roles and subjects move to the logical asset;
- media type, size, hash, representation status, rights, provenance, and technical metadata belong to the realization;
- a bootstrap group contains all migrated realizations;
- the 0.2 manifest SHA-256 is retained as `release.migratedFromManifestSHA256`;
- 0.2 profile IRIs are mapped to their 0.3 equivalents;
- no remote file is invented and no materializable profile is inferred.

For a 0.2 acoustic response, migration also creates stable top-level measurement IDs and moves format/index/channel layout into realization-level impulse-response metadata. If exact sample count, channels, encoding convention, or coordinate transform cannot be established from the source bytes and manifest, an automated migrator MUST stop for producer enrichment or preserve the source record only as migration evidence without claiming the affected Spatial/Acoustics capability. It MUST NOT invent physical metadata merely to satisfy 0.3.2.

Migration MUST NOT overwrite the source. The resulting workspace is a new release and MUST be validated before packing.

VAO 0.3.2 intentionally replaces the unpublished 0.3.1 editor snapshot and the earlier 0.3.0 snapshot. It changes exact `formatVersion`, closes the previously opaque 0.3 acoustics object, and separates logical response measurements from realization-specific storage layout. No public 0.3 compatibility promise exists. Historical Sandbox 0.3.0 bytes remain immutable evidence and are not relabeled. Producers MUST regenerate 0.3.0/0.3.1 draft manifests, carriers, and publication descriptors as 0.3.2 before treating them as current.

## 10. Security and resource limits

Implementations MUST defend against path traversal, link attacks, duplicate names, compression bombs, oversized manifests/entries, integer overflow, invalid Unicode, JSON duplicate-key ambiguity, non-finite numbers, unsafe media decoders, malicious archive members, DNS rebinding, redirect escape, credential leakage, and unbounded cache growth.

Clients SHOULD require explicit policy approval for unfamiliar repositories, restricted assets, large downloads, or executable/software realizations. Verification happens before decoding. No network, extraction, hash computation, allocation, or filesystem mutation may occur in a hard-real-time audio callback.

## 11. Normative artifacts

- `Schemas/vao-manifest-0.3.schema.json`
- `Schemas/vao-carrier-0.3.schema.json`
- `Schemas/vao-release-0.3.schema.json`
- `Schemas/vao-pack-manifest-0.3.schema.json`
- `Schemas/vao-materialization-receipt-0.3.schema.json`
- `Schemas/vao-zenodo-metadata-0.3.schema.json`
- `Schemas/vao-context-0.3.jsonld`
- `Schemas/vao-vocabulary-0.3.ttl`
- `Docs/VAO_CONFORMANCE_0.3.md`
- `Docs/VAO_ZENODO_PROFILE_0.3.md`
- `Tools/vao03.py`

## 12. Publication status

The 0.3 source set is an implemented editor's draft and Sandbox-tested release candidate. It MUST NOT be described as an approved public standard until W3ID ownership, media-type registration, governance review, checksum-pinned MODAVIS dependencies, public conformance artifacts, and production repository publication are complete.
