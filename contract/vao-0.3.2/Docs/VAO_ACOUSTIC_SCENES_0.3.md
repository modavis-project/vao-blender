# VAO 0.3.2 visual-acoustic scene implementation guide

## Goal

A conforming scene can answer, without filename inference:

1. Which exact room geometry and RIR bytes are available?
2. Where were the emitter and receiver, in which coordinate frame and unit?
3. How does a visualization model transform into that acoustic frame?
4. Which logical source–receiver measurement occupies which response-array item and channels?
5. Was the response measured, simulated, hybrid, inferred, or learned, and what generated it?

This enables documentation, inspection, fixed convolution, response-field lookup, and renderer hand-off. It does not guarantee that a mesh is watertight, that a simulation is accurate, or that interpolation beyond sampled positions is scientifically valid.

## Reference flow

```text
room/source/receiver entities
        │
        ├── poses ──> dataset coordinate frame
        │                       ▲
        │                       │ declared 4×4 transform
        ├── geometry binding ─> logical room asset ─> OBJ + GLB realizations
        │
        └── measurement ID ──> logical response set ─> WAV/SOFA realization mapping
```

Logical records remain stable across encodings. Exact byte realizations carry format-specific facts. A consumer may therefore choose the GLB for visualization and the OBJ for simulation/preservation, or choose a fixed WAV derivative while retaining a multidimensional SOFA source.

## Dataset evaluation

### Selected: AcousticRooms

The official [AcousticRooms repository](https://github.com/facebookresearch/AcousticRooms) provides 260 room geometries, more than 300,000 hybrid simulated RIRs, OBJ models, and per-pair source/receiver XYZ metadata under CC BY 4.0. It is the best reference-fixture fit because its geometry and response coordinates are directly paired, its terms permit redistribution with attribution, and one room/pair can be extracted into a small deterministic fixture.

The fixture is `Fixtures/VAO03/valid/acousticrooms-scene`. `payload/evidence/fixture-provenance.json` records the upstream commit, Git LFS object identities and nested members, derivative software, transformation matrix, and hashes. The selected audio is mono PCM16 WAVE at 22,050 Hz with 11,864 samples. It represents one fixed pair and therefore exercises the strict WAVE rule rather than pretending to be a response field.

### Evaluated alternatives

- [SoundSpaces](https://soundspaces.org/) couples RIR simulation with scanned/replica 3D scenes and is valuable for larger renderer evaluation, but its scene dependencies and download/licensing chain are less suitable for a small redistributable conformance fixture.
- [dEchorate](https://www.sofaconventions.org/data/database/dechorate/) provides measured RIRs/SOFA data with accurately measured source and microphone positions. It is strong future measured-data evidence, but the complete source campaign is large and does not offer as direct a small matched visual-mesh fixture.
- [Real Acoustic Fields](https://github.com/facebookresearch/real-acoustic-fields) includes real RIRs, 6DoF poses, and reconstructed meshes. Its non-commercial license and multi-gigabyte size make it useful for research evaluation but less suitable for the distributable core fixture.

## Producer rules

- Preserve upstream bytes and provenance. Put a runtime conversion in another realization and link its generating activity.
- Give each encoding a declared coordinate frame. Do not “correct” vertices silently.
- Give every source and receiver an entity and pose. Keep unknown orientation absent; do not manufacture an identity quaternion.
- Give every source–receiver pair a stable measurement ID. Put SOFA/WAVE array and channel indices only in the exact realization.
- Keep simulation geometry/material assumptions distinct from runtime visual geometry. Bind each purpose explicitly.
- Use a response-field capability only when interpolation and a valid domain are actually declared. A sparse list of fixed RIRs is not automatically a continuous field.
- Preserve exact license and attribution evidence for incorporated public data.

## Consumer and Blender workflow

A visualization client selects a geometry realization it supports, resolves the realization's coordinate frame to the scene frame, loads the model, and instantiates source/receiver markers from poses. It may label or audition the RIR associated with the chosen measurement. If it cannot evaluate a declared transform, it must report the scene as unsupported rather than place markers in guessed coordinates.

The current Blender add-on can remain a 0.2.2 importer while VAO 0.3.2 standardizes the information it will need. A future add-on update should add 0.3.2 dispatch, choose a `runtime-visual` glTF realization, evaluate the frame graph, create source/receiver objects keyed by stable entity IDs, and expose measurement/response links. None of those application behaviors are required to validate or preserve a VAO.
