# VAO-Blender 0.2.0 implementation report

> Historical evidence for the 0.2.0 development build. It is not the current
> release report; see [CHANGELOG.md](../CHANGELOG.md),
> [CONFORMANCE.md](CONFORMANCE.md), and [RELEASE.md](RELEASE.md).

Date: 2026-08-24  
Host: macOS ARM64  
Blender: 5.1.1 (`b70da489d7f4`)  
Python: standalone 3.14.5; Blender 3.13.9

## Delivered implementation

The repository contains an installable Blender Extension and Blender-neutral
core with exact dispatch for two independent private contracts. VAO 0.2.2
retains the capture/instrument graph, interaction compiler, and scoped `aud`
voices. VAO 0.3.2 adds a separate carrier-independent logical-asset model,
exact realizations/carrier mappings, coordinate frames, poses, measurements,
response sets, and metadata-only RIR inspection.

The 0.3.2 reader loads the checksum-verified offline reference validator,
validates the closed manifest/carrier and semantic invariants, binds exact
manifest bytes and release ID, proves carrier closure, and streams every
embedded realization for size/SHA-256 before Blender decode. Runtime geometry
is selected only through `runtime-visual` binding → logical asset → supported
embedded GLB realization. The row-major frame graph is composed around the
inverse Blender glTF import basis, preventing double axis conversion.

The implementation does not add a Cuntz adapter. Its 5 × 45 matrix is compiled
from the same URI-keyed entity/relation/property rules used for another package.

## Recorded verification

### Core/unit

`python3 -m unittest discover -s tests/unit -v`

- 31 tests passed.
- Strict duplicate/non-finite JSON, unsafe paths, positive pinned fixture,
  schema and payload mutations, cache tamper/quarantine/clear protection, GLB
  duplicate-name node-index injection, forbidden external glTF resources,
  both vendored contract pins, exact/nearby-version dispatch, closed VAO 0.3.2
  schemas, synthetic ZIP64, carrier-manifest binding, unindexed payload closure,
  singular transforms, corrupt RIR fixity, logical binding selection, frame and
  full-pose algebra, exact RIR metadata, direct pinned-OrgRec report parity, and
  the Cuntz plan matrix were exercised.

### Blender extension

- `blender --command extension validate .` passed.
- The exact extension ZIP built, passed final-ZIP validation, verified its
  embedded contract pins, and smoke-registered from an extracted artifact.
- Registration/unregistration symmetry passed twice, including properties,
  operators, FileHandler, panels, menus, and load handlers.
- Cuntz `positiv_keys.glb`: 6 imported objects.
- Cuntz `4010243_segmented.glb`: 46 imported objects; the declared
  `gltf-node-index` geometry binding resolved through injected extras.
- 45 key and 5 selection control proxies were generated.
- A `.blend` saved successfully and runtime teardown completed cleanly.
- Blender `aud` accepted and fully decoded a verified 192 kHz stereo IEEE-float
  Cuntz WAVE master.
- The VAO 0.3.2 fixture materialized one `Bathrooms_idx_0` mesh with 17,429
  vertices and 21,760 polygons from the contract-selected GLB realization.
- The declared GLB-to-dataset row-major transform was retained and realized
  exactly once. Full source and receiver XYZW poses were composed into the
  common root; helpers were created at `[2.3496, 0.7269,
  1.353]` and `[2.8176, 0.9871, 1.4665]`, with stable entity, pose, frame,
  measurement, response, RIR realization, and fixity tags.
- Forced GLB preparation failure left object/collection/mesh counts unchanged;
  explicit materialization cleanup restored the same baseline after success.
- Registration/unregistration and built-artifact registration both passed.

### VAO 0.3.2 pinned fixture

| Check | Result |
| --- | --- |
| Carrier SHA-256 | `54aef8656162f485a0c4aa37dca56accc909284db4f746b33f85500749da2286` |
| Manifest SHA-256 | `8bf67a8240db327d481bcc23f532ba2c198c8a886f5659efcab909a9273ab652` |
| Carrier files / payloads | 11 / 8 |
| Verified payload bytes | 1,722,650 |
| Logical assets / realizations | 7 / 8 |
| Frames / poses / measurements | 2 / 2 / 1 |
| Geometry / RIR realizations | 2 / 1 |
| Runtime visual GLB SHA-256 | `03e1bb41f2db881da22212184baa765a71ae9e3248ef610237f67322b039798a` |
| RIR | WAV, 22,050 Hz, 11,864 samples, mono, hybrid |
| Acoustic runtime | metadata/filter-kernel only; no playback/convolution/simulation |

### Built extension

`dist/vao_blender-0.2.0.zip` was built by Blender 5.1.1, validated both as a
source extension and as the final ZIP, and smoke-registered from an extracted
artifact. Size: 773,913 bytes. SHA-256:
`266ef11ccf2b780ac8aed78ab017eba90c3be2d3fe10d06111f57ea724fad81a`.

### Complete Cuntz VAO

VAO-Blender independently read the archive bytes and then every payload stream:

| Check | Result |
| --- | --- |
| Archive SHA-256 | `0d9517b8d16e3833e639258c9dae8325867f9579c58c53a05197e301dc29494a` |
| Manifest SHA-256 | `6965e9066438ac55f0c624b4d9cb13efa2a12e55cdc2997322d3a6a547f5a71c` |
| Assets | 385 / 385 |
| Payload bytes | 4,177,117,166 / 4,177,117,166 |
| Schema/semantic/fixity/compiler diagnostics | 0 |
| Entities / relations / assets | 783 / 1,691 / 385 |
| Selections / gates / voices | 5 / 45 / 225 |
| Runtime support | all concretely claimed capabilities supported |
| Rights result | `blocked-rights` (intended; session acknowledgement required) |

The independently generated report is
`dist/Cuntz-Positiv-4010243-VAO-0.2.2.vao-blender-validation.json`.

## Release boundary

This is a working development alpha against a checksum-pinned private contract,
not a public release or certification. The following gates require external
evidence and cannot truthfully be closed by the implementation host alone:

- approval to redistribute the private VAO contract files;
- project security contact and governance approval;
- independent conformance/security review;
- Blender 5.1/5.2 tests on macOS ARM64, Windows x64, and Linux x64;
- manual real-device audio, accessibility, UI, cancellation, and long-soak
  sign-off on the supported platform matrix.

No network, writer/exporter, MIDI hardware, room-acoustics renderer, RIR
convolution/playback, acoustic simulation/interpolation, arbitrary active
content, sample-accurate timing, or public-standard compatibility claim is
included. The prepared fixture and OrgRec source were not modified.
