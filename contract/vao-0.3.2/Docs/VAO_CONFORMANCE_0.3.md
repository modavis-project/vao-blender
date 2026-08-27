# VAO 0.3.2 conformance

## Conformance classes

An implementation declares each class it supports:

1. **Manifest validator** — validates the 0.3 schema and semantic cross-references.
2. **Carrier reader** — safely reads a `.vao`, verifies manifest/carrier binding and embedded realization bytes.
3. **Carrier writer** — produces deterministic, closed carriers without changing manifest semantics.
4. **Repository resolver** — resolves exact version-pinned distributions under local trust policy.
5. **Materializer** — selects groups, validates dependencies and fallbacks, commits verified content, and emits a receipt.
6. **Preservation closer** — proves that a carrier embeds every required realization for declared complete groups.
7. **Migrator** — preserves a 0.2 manifest as evidence and creates an independently valid 0.3 release.
8. **Zenodo adapter** — enforces `version-pid-record-file`, verifies returned record/file metadata, and treats SHA-256 as authoritative.
9. **Publication-profile validator** — validates single-record/family topology and verifies that optional Zenodo metadata projects exact record relations.
10. **Spatial/acoustic-scene validator** — validates closed acoustic registries, coordinate transformations, source/receiver registration, response realization layout, and capability truth.

## Mandatory manifest checks

- JSON Schema validity under Draft 2020-12.
- Exact format, schema, context, Core profile, and Dynamic Delivery profile IRIs.
- No reused 0.2 profile IRI.
- Unique identifiers across graph and delivery registries.
- Resolved primary/focus entities, relation references, asset/realization inverse references, distribution references, repository bindings, group dependencies, fallbacks, rights, and provenance.
- Rights coverage of the conceptual VAO, logical assets, and realizations.
- At least one logical asset, realization, group, and bootstrap realization.
- Accurate group total byte sizes using unique realization IDs.
- Acyclic dependency and fallback graphs.
- No profile duplicated between embedded and materializable claims.
- No requirement for a repository, DOI, network access, or Zenodo when the corresponding binding is absent.
- The Zenodo profile is present if and only if at least one Zenodo binding is used.
- Every materializable profile is enabled by its named groups and those groups declare the profile.
- Ambisonics channel-count consistency: 3D `(order + 1)^2`, 2D `2 * order + 1`.
- The Spatial/Acoustics profiles have a closed `acoustics` object; Acoustics also claims Spatial and at least one standard acoustic capability.
- Acoustic registry identifiers participate in package-wide uniqueness.
- Coordinate-frame parents resolve, have invertible row-major 4×4 transforms, form no cycles, and do not use the same physical axis for up and forward.
- Pose subjects and frames resolve, position dimensions agree, and orientation quaternions are normalized XYZW.
- Geometry bindings resolve to logical spatial-model assets, whose geometry realizations use declared acoustic coordinate frames; glTF selectors address glTF realizations.
- Every response measurement resolves its emitter, receiver, poses, and optional spatial/configuration subjects; pose subjects agree and source/receiver frames share a transformable root.
- Every response set resolves its response entity, impulse-response logical asset, measurement IDs, and generating activity.
- Every response realization has typed audio and impulse-response metadata. Its mapping covers each logical measurement exactly once, uses unique data indices, and stays within declared channels.
- WAVE/FLAC response realizations bind one fixed source–receiver measurement; SOFA names its convention. Response-set and realization representation status agree.
- `position-registered-acoustic-scene`, `visual-acoustic-scene`, measured/simulated response, response-field, spatial-audio-scene, and semantic-building claims are backed by the required records and common coordinate frame.
- Every remote realization has at least one exact distribution.
- Repository concept PIDs are never used as the exact `persistentIdentifier`.

## Mandatory carrier checks

- ZIP safety and first/stored `mimetype` contract.
- Exact manifest bytes match descriptor size and SHA-256.
- Descriptor release ID matches the manifest.
- Every payload file has exactly one mapping and every mapping resolves to a realization.
- Embedded byte size and SHA-256 match the realization.
- Every `completeGroupId` resolves and all of its realizations and dependencies are embedded.
- `bootstrap` includes at least one realization.
- `preservation-closure` proves all declared groups complete without network access.

## Mandatory publication-profile checks

- Publication descriptors are optional for unpublished and repository-free VAOs.
- `single-record` has no family members; `record-family` has at least one.
- Publication-record IDs, version PIDs, and file identifiers within each record are unique.
- A version PID differs from its concept PID; dependency relations never substitute the concept PID.
- The root inventories exactly one manifest and at least one bootstrap carrier.
- `vao-release.json` is excluded from its own digest inventory.
- Every listed file has a role, non-negative byte size, and lowercase SHA-256; a `realization` or `pack` file names the realization IDs it carries.
- Exclusive members use `hasPart`/`isPartOf`; shared records use their real dependency/supplement/source semantics and do not assert false ownership.
- Every Zenodo publication record has one metadata projection bound to the same release and publication-record ID.
- Root metadata uses the VAO content version and the correct `monolithic-root` or `family-root` role; member metadata uses `family-member`.
- Root `related_identifiers` includes every declared exact member version PID and relation. A declared inverse is present in member metadata against the exact root version PID.
- Zenodo metadata includes creators and discoverability fields, explicit access/licensing conditions, and the `Virtual Acoustic Object` and `VAO 0.3` keywords.

## Negative-test minimum

The reference suite covers schema/root closure, wrong 0.2 IRIs, missing Core/Dynamic profiles, duplicate IDs, unresolved references, incorrect group totals, dependency cycles, fallback cycles, rights gaps, illegal package-supplied network policy, concept-DOI acquisition, Ambisonics mismatch, carrier/manifest digest mismatch, hidden payload, unindexed payload, corrupt embedded bytes, incomplete groups, unsafe paths, publication-topology contradictions, incorrect exclusive/shared relations, concept PID substitution, missing Zenodo relation projections, unknown archive entries, non-normalized quaternions, coordinate cycles/non-invertible transforms, pose/subject mismatch, incomplete or out-of-range response mappings, representation-status disagreement, false acoustic capabilities, and visual/acoustic frame-registration failure.

The positive public-data case is `Fixtures/VAO03/valid/acousticrooms-scene`. It fixes one AcousticRooms room mesh, one exact hybrid WAV RIR, exact source/receiver positions, the source simulation metadata and license, and a provenance-recorded OBJ-to-GLB visualization derivative. Both Python and Swift validators MUST accept its preservation-closure carrier without network access.

## Publication gates

A 0.3 candidate is implementation-ready only if all local positive, negative, migration, Python, and Swift tests pass. It is publication-ready only after external dependency pins and governance metadata are complete. A successful Sandbox publication demonstrates repository mechanics; it is not public-standard approval.
