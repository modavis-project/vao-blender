# Product and UX specification

> Historical 0.2.0 product baseline. For the current 0.3.0 release scope and
> exact VAO 0.4.0/0.5.0 capability matrix, see [COMPATIBILITY.md](COMPATIBILITY.md).

Status: proposed implementation baseline  
Date: 2026-08-24  
Product name: VAO-Blender  
Initial extension identifier: `vao_blender`

## 1. Product statement

VAO-Blender makes a validated Virtual Acoustic Object usable inside Blender
without turning Blender into a VAO authoring system or a general-purpose audio
workstation. It gives researchers, curators, 3D artists, and instrument builders
one place to inspect the semantic graph, place verified visual representations
in a scene, audition declared media, and operate explicitly declared
interactions.

The initial success case is the Cuntz Positiv / PositivXR instrument. A user can
open the finished Cuntz `.vao`, review its identity and rights status, load its
instrument model, select any combination of five stops, and press/release any of
the 45 observed keys. The runtime resolves the selected key/stop combination to
the declared sample relations; it never constructs a chromatic range or derives
a resource path from `4010243_<stop>_<note>.wav`.

## 2. Users and jobs

| User | Primary job | Required outcome |
| --- | --- | --- |
| Researcher or organologist | Explore a VAO while retaining evidence boundaries | Entities, assertions, provenance, unknowns, and analytical facts remain distinguishable |
| Curator or preservation specialist | Check package integrity and inspect its contents | Validation, rights, fixity, source/derivative status, and unsupported content are visible |
| Blender artist | Bring a documented instrument representation into a scene | Verified geometry, materials, units, axes, and component identity survive import |
| Interaction designer | Exercise declared controls and animations | Only supported declarative actions run, with traceable targets and no bundled code execution |
| Audio user | Audition a sample-based virtual instrument | Gate, selection, sample, tuning, gain, loop, release, and voice policies come from the graph |

## 3. Product boundaries

### 3.1 In scope for version 0.2.0

- Import by **File → Import → Virtual Acoustic Object (.vao)** and drag/drop in
  the 3D Viewport.
- Offline validation against the vendored exact VAO 0.2.2 and VAO 0.3.2
  contract snapshots.
- Read-only 0.2.2 instrument/capture behavior plus read-only 0.3.2 visual-
  acoustic scene inspection and materialization.
- Complete package inventory and graph inspection.
- embedded GLB visual import with explicit coordinate handling and stable selector
  binding.
- Declarative sample playback for packages whose complete interaction plan is
  supported.
- Declarative selection/configuration state; GLB animation data may import with
  the model, but interaction-driven animation triggering remains deferred.
- A viewport performance mode for press/release events plus an interaction-board
  fallback when a model has no usable control geometry binding.
- Safe, lazy extraction to a managed cache after full package verification.
- Reimport, close, cache cleanup, and detached-source recovery.
- Diagnostics export as JSON; this records the reader result and does not write
  to the VAO.

### 3.2 Deferred

- VAO creation, editing, repacking, migration, or signing.
- Recording or analysis inside Blender.
- General room-acoustics simulation, SOFA/HRTF convolution, ambisonic rendering,
  or learned acoustic fields.
- AR placement, image targets, OpenXR execution, and remote asset groups.
- MIDI hardware input. The logical MIDI/key domain is supported, but physical
  MIDI I/O requires a later optional backend and platform test matrix.
- USD/IFC/CityGML semantic editing and Blender-to-VAO round trip.
- Interaction-driven animation action/clip triggering.
- Network resolution of W3ID, MODAVIS, media, or identity resources.

### 3.3 Non-goals

- Reproducing arbitrary Unity projects or Unity engine bugs.
- Treating a valid VAO as historically true, scientifically authoritative, or
  licensed for every use.
- Treating a visual mesh or PBR material as acoustic geometry/material evidence.
- Inferring missing samples, keyboard compass, component identity, or playback
  behavior from names.
- Hiding unsupported content in order to present a cleaner UI.

## 4. Compatibility and capability policy

### 4.1 Format

- Dispatch is exact: only `formatVersion` `0.2.2` and `0.3.2` are accepted.
  Each uses its own model and validator; no version is decoded through the
  other's compatibility path.
- The first writer role is **none**; the source archive remains immutable.
- The exact local contract is identified by the release-bundle checksum in the
  repository README.
- Another minor line, such as 0.1 or 0.3, is rejected as incompatible rather
  than guessed or relabeled.
- Unknown optional URI-keyed extension data is retained in the in-memory graph
  and manifest text. Unknown required capabilities are reported as unsupported.

### 4.2 Blender

| Stage | Blender versions | Platforms |
| --- | --- | --- |
| Developer alpha | 5.1.1 | macOS ARM64 |
| Release candidate | 5.1 latest and 5.2 LTS latest | macOS ARM64/x64, Windows x64, Linux x64 |
| Later compatibility | 4.5 LTS | Only after automated and manual compatibility tests pass |

The initial `blender_manifest.toml` should use `blender_version_min = "5.1.0"`.
There is no maximum until a known incompatible version exists.

### 4.3 Media/runtime support

Support is decided per package after validation and compilation:

| Area | Version 0.2.0 support | Behavior outside support |
| --- | --- | --- |
| Geometry | Verified embedded `model/gltf-binary` (GLB) | Keep asset visible; do not import it |
| Animation | Animation channels may arrive with an imported GLB; no interaction-driven trigger runtime | Report declared animation actions as unsupported |
| Sample audio | Verified local WAVE required for Cuntz; other Blender-decodable formats are experimental until tested | Keep visible; do not instantiate a voice |
| Interaction binding | `host-note-gate` and reviewed declarative selection/actions defined by the support matrix | Package remains valid but runtime is unsupported |
| Spatial | Coordinate frames, full position/XYZW poses, runtime-visual geometry binding, source/receiver markers, and RIR metadata | No acoustics-profile rendering claim |
| Research/preservation/OrgRec | Inspect metadata and inventory | No profile-processor claim |
| Bundled scripts | None | Never execute |

A profile is shown as **supported for this package** only if every required
capability and every runtime binding used by that package compiles. Otherwise
the UI separates **valid package** from **unsupported execution**.

## 5. Core workflows

### 5.1 Open and validate

1. The user selects or drops a `.vao`.
2. A preflight dialog shows source path, archive size, configured limits, and
   that the content is untrusted until validation completes.
3. The sidebar reports progress through container, schema, semantic, fixity,
   and capability stages. Cancel remains available.
4. No payload is decoded, no model is imported, and no audio is played before
   successful validation.
5. The result is one of:
   - **Valid and supported** — available operations are enabled;
   - **Valid with unsupported capabilities/media** — inspection is enabled and
     unsupported operations stay disabled;
   - **Invalid** — diagnostics are available, but payload use is disabled;
   - **Blocked by local limit** — not a semantic-invalidity claim;
   - **Cancelled** — no new scene data or incomplete cache entry remains.

### 5.2 Review and load

1. The Overview panel displays title, package/revision identity, format, primary
   entity, claimed profiles, capability result, and a prominent rights/access
   summary.
2. Unknown or restricted rights require a per-session acknowledgement before
   asset extraction or playback. This acknowledgement is not written into the
   VAO and is not presented as permission.
3. The user chooses one or more runtime visual assets. Recommended defaults are
   based on declared asset roles and geometry bindings, not filename order.
4. Imported data appears below a new `VAO::<title>` collection and receives
   non-semantic host tags linking it back to package, entity, asset, and stable
   selector identifiers.
5. **Frame Selected** focuses the primary representation; **Select Entity**
   selects every bound Blender object for the chosen entity.

### 5.3 Explore

The Explore panel provides:

- text search and filters by entity kind, type, representation status, role,
  relation status, and supported/unsupported state;
- an entity list with incoming/outgoing relations and linked assets;
- an asset list with media type, byte size, hash verification, roles, original
  filename, representation status, and support result;
- a read-only property viewer that shows full URI keys and JSON values;
- evidence/provenance links and warnings without editorial reinterpretation;
- **Focus**, **Select**, **Hide/Show representation**, **Audition**, and
  **Open diagnostics** actions only when meaningful.

### 5.4 Interact

1. The Play panel lists compiled interactions grouped by declared label and
   control domain.
2. Selection interactions update a visible runtime state. For Cuntz, the five
   stops are independent toggles; zero or multiple stops may be active.
3. **Enter Performance Mode** starts a modal 3D Viewport operator. It captures
   mapped keyboard events and mouse press/release over bound control geometry or
   generated UI proxies.
4. A gate-open event resolves the current state, selects only matching accepted
   relations/parameters, verifies that required cached assets still match, and
   starts the resulting voices and animations.
5. Gate-close applies the declared note-off/release behavior to the voices for
   that gate. Unsupported or ambiguous behavior prevents compilation rather
   than falling back to a guess.
6. Escape exits performance mode and stops/fades every owned handle. Unregister,
   file load, package close, and Blender shutdown perform the same cleanup.

### 5.5 Save, reopen, and close

- Imported Blender objects and a read-only copy of the manifest may be saved in
  the `.blend` file.
- Audio handles, decoded buffers, background workers, and acknowledgement state
  are never serialized.
- On reopening a `.blend`, the collection is **detached** until the original VAO
  is found and revalidated. Existing geometry remains visible, but playback and
  fresh extraction stay disabled.
- Relinking never changes stored package identity. A different manifest/package
  checksum requires an explicit reimport as another revision.
- Closing a package stops its handles and removes its runtime services. Removing
  imported scene data is a separate, undoable user action.

## 6. Functional requirements

| ID | Requirement |
| --- | --- |
| IMP-001 | Register `.vao` import and 3D Viewport drag/drop handlers |
| IMP-002 | Import into a new, namespaced collection without deleting or renaming unrelated user data |
| VAL-001 | Apply container, schema, semantic, payload-index, byte-size, CRC, SHA-256, rights, and profile checks in the normative order |
| VAL-002 | Distinguish invalidity, local-limit refusal, unsupported capability, unsupported media, warning, and cancellation |
| VAL-003 | Perform full validation offline against vendored artifacts and identify their checksum in the report |
| GRA-001 | Preserve the complete parsed entity/relation/asset graph and unknown optional URI-keyed values |
| GRA-002 | Never derive graph identity or behavior from filenames or Blender object names |
| VIS-001 | Load verified glTF/GLB into a dedicated collection and apply explicit VAO coordinate transforms |
| VIS-002 | Resolve geometry bindings using stable selectors; glTF names alone are never unique selectors |
| UX-001 | Provide Overview, Explore, Visual-Acoustic Scene, Play, and Diagnostics panels in the 3D Viewport sidebar |
| UX-002 | Keep validation responsive and cancellable and expose stage/byte progress |
| INT-001 | Compile supported interactions into typed immutable runtime plans before performance mode can start |
| INT-002 | Support independent configuration/selection state and note/key gate open/close events |
| INT-003 | Prevent one unsupported or ambiguous required interaction from being silently skipped in an otherwise “supported” runtime |
| AUD-001 | Resolve every voice through explicit relations and reviewed playback parameters to one verified indexed audio asset |
| AUD-002 | Apply declared gain, pitch mode, envelope, loop, release, channel, priority, and voice-selection policies within the implemented subset |
| AUD-003 | Limit polyphony, release all owned handles reliably, and avoid buffering the complete Cuntz corpus |
| ANM-001 | Deferred: resolve declared GLB clip/channel targets before claiming synchronized animation actions |
| RGT-001 | Display applicable rights/access records and require acknowledgement when permission is unknown or restricted |
| LIF-001 | Support deterministic close, reload, detach, relink, unregister, and cache-cleanup behavior |
| REP-001 | Export a machine-readable diagnostic report without mutating the source archive |

## 7. Non-functional requirements

- **Safety:** no archive member is extracted before path/type/size checks; no
  active content is executed; network access is absent in version 0.2.0.
- **Responsiveness:** hashing and decompression run outside Blender's data/UI
  mutation path. The main thread consumes bounded progress/results through a
  timer. Cancellation is checked between chunks.
- **Memory:** package validation streams bytes. The runtime never loads all 225
  Cuntz WAVE files; decoded/buffered audio uses an LRU budget with a default no
  greater than 512 MiB.
- **Determinism:** identical verified input and settings produce the same graph,
  capability report, interaction plans, host tags, and diagnostics ordering.
- **Auditability:** every imported object and runtime action can be traced to a
  package ID/revision, asset ID/hash, entity ID, relation IDs, and selector.
- **Accessibility:** status is conveyed by icon/text as well as color; controls
  have labels/tooltips; the full workflow is keyboard reachable except direct
  viewport picking.
- **Privacy:** no telemetry, remote resolution, or package-path disclosure.
  Diagnostics redact absolute source/cache paths by default.
- **Portability:** core parsing/validation/compilation is Blender-neutral Python
  and can be tested outside Blender.

## 8. Version 0.2.0 acceptance

The release is acceptable when:

1. every bundled positive VAO fixture validates and every supported result is
   reproducible in standalone and Blender-background tests;
2. the agreed negative/adversarial fixture suite is rejected before unsafe
   extraction or media decoding;
3. the completed Cuntz golden VAO independently passes VAOM and VAO-Blender;
4. Cuntz produces exactly five stop controls, 45 key gates, and 225 resolvable
   stop/key voice plans, with MIDI 37, 39, 42, and 44 absent;
5. single notes and multi-stop chords start/stop without stuck voices, and
   release behavior follows the manifest rather than the legacy filename/code
   convention;
6. model import preserves declared scale/axes and every required component
   selector resolves;
7. cancelling validation or closing/unregistering leaves no incomplete scene
   collection, partial cache file, live background worker, timer, or audio
   handle;
8. unsupported capabilities remain visible and do not make a valid core package
   appear corrupt;
9. the extension package validates with Blender's extension validator and passes
   the supported Blender/platform matrix; and
10. documentation, license notices, dependency hashes/SBOM, security contact,
    known limitations, and the private-snapshot disclaimer ship with the build.
