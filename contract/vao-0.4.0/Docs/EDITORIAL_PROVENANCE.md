# Editorial provenance of VAO 0.4.0

This final specification consolidates the reviewed VAO development line as `formatVersion: "0.4.0"`, with immutable 0.4.0 schema/context/profile IRIs and an implemented 0.4.0 fixture/runtime/migration path.

Earlier 0.3.x material was an unpublished development contract. It remains only as compatibility input for migration and retained-semantic regression tests. It is not the public baseline and is excluded from the 0.4.0 specification bundle.

During release preparation, the 0.4.0 material was audited for self-containment, archive safety, deterministic serialization/runtime, scientific quantity and provenance semantics, multimodal clock dimensions, spatial/acoustic validity boundaries, linked-data claims, schemas, fixtures, profiles, licensing, governance, citation, and registry readiness. Corrections are recorded in the root changelog and format changelog.

The final cross-standard audit replaced three obsolete fixture IRIs with the released MODAVIS 0.1.0 organ terms and added the checksum-pinned VAO-owned mapping graph. This change corrects interoperability metadata without changing VAO's JSON record model or serialized `formatVersion`.

The `rc.2` hardening pass specifically closed cross-module typed-reference and reciprocal-provenance gaps; corrected random-generator and unbiased-selection semantics; added dimension/PSD/chronology/rate/coordinate and registration-method checks; made oriented local frames and trajectory bytes exact; rejected ambiguous channel layouts and non-portable path collisions; bound receipts to exact source carriers; repaired fixture lineage; completed vocabulary coverage; and distinguished offline trace verification from unimplemented live scheduling/media claims. These are editorial and implementation conformance controls, not independent empirical validation of any represented instrument, measurement, simulation, or inference.

The `0.4.0-rc.2` label identified the final hardening candidate and was never a serialized VAO format version. The approved repository metadata and serialized VAO documents now both use exact `0.4.0`; an RC string as `formatVersion` remains incompatible and undefined.

No earlier public VAO standard release is claimed by this document. The public release date is 2026-08-27 and the reserved version DOI is `10.5281/zenodo.22122774`; it becomes registered only when the prepared Zenodo record is published. Final publication provenance must also record the approved Git commit, signed `v0.4.0` tag, specification-bundle digest, source-archive digest, and assigned registry identifiers.
