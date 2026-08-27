# OrgRec compatibility with VAO 0.3.2 visual-acoustic scenes

## Scope

OrgRec supports VAO 0.3.2 as an instrument-neutral, read-only inspection and workspace-import format. This is separate from OrgRec's editable VAO 0.2.2 capture-project round trip. A visual-acoustic scene whose primary entity is a room is not converted into a pipe-organ recording project and is not silently rewritten to 0.2.2.

## Supported operations

`VAO03PackageReader` provides:

- exact format dispatch from `vao-manifest.json`;
- stored ZIP/ZIP64 safety checks through the existing VAO archive reader;
- exact `mimetype`, manifest, and carrier-descriptor verification;
- streaming CRC-32, byte-size, and SHA-256 verification for every embedded realization without loading the complete payload into memory;
- rejection of unknown or unindexed carrier entries;
- extraction of a complete embedded workspace without changing the manifest;
- extraction of one embedded realization by stable realization ID;
- typed inspection of coordinate frames, parent transforms, poses, source–receiver measurements, geometry realizations, and impulse-response realizations.

The macOS import action dispatches exact VAO `0.3.2` carriers to this reader. A valid carrier is extracted below `Application Support/OrgRec/VAOWorkspaces` and summarized in the project-library screen. The summary reports geometry, RIR, measurement, and frame counts and can reveal the verified workspace in Finder. Existing VAO 0.2.2 OrgRec-profile packages continue through the editable capture-project importer.

## Acoustic-scene projection

OrgRec exposes, without inference:

- each coordinate frame's dimension, unit, handedness, axes, parent, and row-major transform;
- each pose's subject, frame, position, and optional XYZW orientation;
- stable measurement IDs with source/receiver entities and pose IDs;
- geometry realization media type, frame, binding purposes, fixity, and carrier path;
- RIR realization encoding, sample rate/count, channels, measurement mapping, fixity, and carrier path;
- audio-scene and render-configuration counts.

The semantic validator remains authoritative for coordinate closure, transform invertibility, pose/subject agreement, RIR mappings, and capability truth. The access layer exposes only records from a carrier that has passed those checks.

## Processing boundary

OrgRec does not claim native acoustic simulation, convolution, response interpolation, 3D rendering, or Blender scene construction. These are renderer/application responsibilities. OrgRec's compatibility claim is validation, lossless embedded import, safe extraction, and typed metadata access. Unsupported remote realizations remain governed by the side-effect-free materialization planner and locally trusted repository adapters; the workspace importer does not initiate network access.

## Reference test

The test carrier is `dist/acousticrooms-bathrooms-idx-0.vao`. The native suite proves that OrgRec:

1. validates all eight embedded files and 1,722,650 payload bytes;
2. exposes two frames, two poses, one source–receiver measurement, two geometry realizations, and one RIR realization;
3. reports the exact 11,864-sample RIR layout;
4. imports the full workspace and independently verifies the GLB hash;
5. extracts the RIR by realization ID and verifies its hash; and
6. rejects a carrier whose RIR bytes do not match the manifest.

## Compatibility table

| Input | OrgRec behavior |
| --- | --- |
| VAO 0.2.2 with OrgRec Capture profile | Editable OrgRec project import and preservation-aware round trip |
| Other valid VAO 0.2.2 | General validation/workspace and asset access APIs |
| Exact VAO 0.3.2 | Read-only validated workspace import and typed visual-acoustic inspection |
| Unpublished VAO 0.3.0 or 0.3.1 | Rejected with an explicit exact-version message; regenerate as 0.3.2 |
| Unknown future version | Not decoded under another schema |

This support statement is for the implemented private 0.3.2 editor's-draft checksum, not a promise of forward compatibility with future 0.3 snapshots.
