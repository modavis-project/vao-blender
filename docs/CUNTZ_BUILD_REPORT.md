# Cuntz Positiv 4010243 VAO build report

> Historical package-specific build evidence. The Cuntz package is not included
> in the public VAO Blender extension release.

Build date: 2026-08-24  
VAO format: 0.2.2  
Package ID: `urn:uuid:e5373268-8e13-5db4-8c1d-65f05278f5a7`

## Deliverable

- Archive: `dist/Cuntz-Positiv-4010243-VAO-0.2.2.vao`
- Archive SHA-256: `0d9517b8d16e3833e639258c9dae8325867f9579c58c53a05197e301dc29494a`
- Indexed assets: 385
- Verified payload bytes: 4,177,117,166
- Entities: 783
- Relations: 1,691
- Playable interactions: 275
- Required capabilities: 7

## Playable model

- 5 independent stop controls;
- 45 observed key controls, preserving the short-octave absence of keys 37,
  39, 42, and 44;
- 225 stop/key sounding positions;
- 225 configuration-scoped sample voice interactions;
- 225 reviewed playback parameter sets;
- 225 byte-identical 192 kHz, stereo, 32-bit IEEE-float WAVE masters;
- exactly one `usesSample` target per sampled voice interaction.

Recorded pitch is preserved. Stop-name pitch offsets and 12-TET A4=440 target
frequencies are editorial playback metadata, not measured historical tuning.
No loop points are asserted. Note-off uses a voice-scoped 0.3-second linear fade,
retaining the source application's nominal duration without its legacy global
release behavior.

## Visual model

Blender 5.1.1 converted and re-imported three retained Cuntz FBX sources:

- `4010243_segmented.glb` — primary runtime model;
- `4010243_segmented_03b2.glb` — alternate instrument model;
- `positiv_keys.glb` — separate keyboard model.

The primary derivative re-imported successfully in Blender with 46 preserved
source-object extras. Geometry is usable for viewing, but the source scale is
not verified by physical survey and is not asserted as dimensional authority.

## Validation

The unpacked workspace and final archive both passed the normative Python VAOM
0.2.2 validator. The independent compiled OrgRec validator then reported:

> Valid VAO 0.2.2 with 385 verified assets and 7 required capabilities.

Its machine-readable report contains no errors or warnings. Additional archive
checks confirmed the required uncompressed first `mimetype` member, 225 WAVE
sample assets, 45 samples for each stop, 275 interactions, 225 parameter sets,
225 sounding positions, and 225 `usesSample` relations. A separate full-source
hash pass confirmed that all 225 indexed WAVE hashes match the authoritative
RAW corpus.

## Standard status and scope

The newest discoverable contract is the repository-local, checksum-pinned VAO
0.2.2 private-development release candidate. No newer public VAO release was
found on 2026-08-24. The exact release bundle pin is
`76b55f33b09c94ad90aac79e8a599d007841e2c11288664f9c67987b4e68f328`.

Rights, canonical historical identity, measured tuning, and physical survey
scale are not established by the supplied evidence. The VAO records those
limitations explicitly and restricts access pending rights review. Unity cache,
duplicated Unity sample copies, AppleDouble data, third-party Resonance Audio
demo content, and the unrelated/uncertain Ariston model were excluded with
reasons recorded in the packaged source inventory.
