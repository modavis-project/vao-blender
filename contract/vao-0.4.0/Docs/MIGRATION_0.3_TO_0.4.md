# Migrating unpublished VAO 0.3 drafts to 0.4.0

VAO 0.4.0 is a breaking successor to unpublished 0.3 development snapshots. There is no public compatibility promise, but the reference migrator preserves original bytes and provenance.

## Major changes

- patch-specific immutable 0.4.0 IRIs;
- typed scientific registries instead of open paradata/analysis objects;
- mandatory multimodal, physical, runtime, and discovery containers;
- stronger playable/interaction execution semantics and trace model;
- richer digest/chunk, rights/consent, discovery, and repository contracts;
- corrected linked-data projection semantics;
- hardened carrier closure and archive rules.

## Procedure

```sh
python Tools/vao04.py migrate-0.3 old-workspace new-workspace
python Tools/vao04.py validate new-workspace --json
```

The destination must not exist. The migrator copies payload bytes, records the original manifest SHA-256, updates version IRIs, supplies required 0.4 registries/profiles, and promotes recognizable provenance into typed records. Original legacy records are retained as migration evidence where automatic typing would be uncertain.

The parsed-manifest API requires the caller to supply the SHA-256 of the original exact manifest bytes. It never substitutes the digest of a normalized in-memory reserialization. The workspace command computes the digest directly from `vao-manifest.json` before rewriting it.

VAO 0.3 trajectory references named a logical asset. VAO 0.4 requires one exact `trajectoryRealizationId` for Pose interpolation and trajectory listeners. The migrator promotes the reference only when that asset has exactly one trajectory-capable realization; zero or multiple candidates stop migration with a curator-selection error rather than silently choosing bytes.

VAO 0.3 oriented Poses did not identify their subject-local Coordinate Frame. Because guessing that basis can reverse or rotate scientific geometry, automatic migration stops on an oriented Pose and requests curator selection of `localFrameId`.

## Required manual review

1. Verify every Entity/type/relationship and primary/focus identity.
2. Replace developmental MODAVIS binding values with a released or embedded snapshot only when such an artifact exists.
3. Review representation status and derivation lineage.
4. Resolve Agents, Protocols, Software Environments, Activities, Observations, Claims, Reviews, and Consent.
5. Add explicit clocks/coordinate frames instead of inferred filename conventions.
6. Review Playable state, key meaning, loops, timing, transfer, process bounds, and source evidence.
7. Review rights, performer/community authority, privacy, embargo, and redaction.
8. Verify distributions are immutable and exact.
9. Recompute descriptor manifest pin after any edit.
10. Build and independently validate a new carrier.

An automated migration being valid means the data fit the 0.4 exchange contract. It does not prove that promoted scientific semantics, rights, or ontology mappings are correct.

## Legacy files in this repository

The 0.3 schemas and tools are compatibility dependencies only. They are not an alternative published standard and are excluded from the 0.4 specification bundle.
