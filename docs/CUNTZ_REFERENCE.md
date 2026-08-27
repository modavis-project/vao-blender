# Cuntz Positiv reference design

> Historical package-specific design record. The Cuntz package is not included
> in the public VAO Blender extension release.

Status: source-audited target design; golden VAO not yet built  
Audit date: 2026-08-24  
Source record boundary: musiXplora/BACCAE source record `4010243`, not a
canonical MODAVIS identifier

## 1. Why Cuntz is the first case

The PositivXR source exercises the complete value of VAO-Blender in a bounded
instrument:

- a segmented 3D representation and legacy animations;
- an irregular historic keyboard that must not be normalized;
- five independently selectable stops;
- 225 high-resolution isolated samples;
- concurrent voices when multiple stops are selected;
- presentation audio and spatial/viewing context that must remain distinct from
  playable samples;
- legacy behavior distributed across filenames, Unity objects, C# code, scenes,
  and `.meta` GUIDs;
- incomplete identity, rights, and acquisition evidence that must remain
  explicit rather than “fixed” by the importer.

The extension must support this through general VAO graph compilation. There is
no Cuntz package-ID branch or filename parser in runtime code. Cuntz-specific
assertions belong in the golden tests only.

## 2. Audited sources

### 2.1 Local evidence locations

| Evidence | Audited location |
| --- | --- |
| Isolated WAVE corpus | `/Volumes/UkolovMac/IADs/RAW/PositivXR` |
| Unity source | `/Volumes/UkolovXfer/Ukolov_Transfer_2026-08-11/Applications/Cuntz_Positiv_Unity_AR_VAOrgan/VAOrgan` |
| Machine inspection | [`inspection.json`](../../orgrec/Artifacts/PositivXR/inspection.json) |
| Case study | [`POSITIVXR_CASE_STUDY.md`](../../orgrec/Docs/POSITIVXR_CASE_STUDY.md) |
| VAO migration design | [`POSITIVXR_VAO_MIGRATION.md`](../../orgrec/Docs/POSITIVXR_VAO_MIGRATION.md) |
| Analysis summary | [`ANALYSIS_RESULTS.md`](../../orgrec/Artifacts/PositivXR/ANALYSIS_RESULTS.md) |

The mounted paths are workstation evidence locations, not paths that may appear
as runtime dependencies in VAO-Blender. The finished `.vao` is self-contained.

### 2.2 Audio facts

| Property | Audited value |
| --- | --- |
| WAVE masters | 225 |
| Stops | 5 |
| Masters per stop | 45 |
| Total bytes | 3,683,539,636 |
| Total duration | 2,398.131 s (39 min 58.131 s) |
| Format | RIFF/WAVE, IEEE 32-bit float |
| Sample rate | 192,000 Hz |
| Channels | 2 |
| Filename grammar | `4010243_<stop>_<midi>[_variant].wav` |
| Ignored raw entry | `.DS_Store`, recorded in inspection |

Every stop has exactly this observed key set:

```text
36, 38, 40, 41, 43, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55,
56, 57, 58, 59, 60, 61, 62, 63, 64, 65, 66, 67, 68, 69, 70, 71,
72, 73, 74, 75, 76, 77, 78, 79, 80, 81, 82, 83, 84
```

MIDI 37, 39, 42, and 44 are absent. They encode the short/broken bass octave
and are not errors. The control surface, interaction plans, and tests must keep
them absent.

### 2.3 Stop interpretation

| Unity control | Token | Reviewable display label | Sounding-pitch prior |
| --- | --- | --- | --- |
| `bt.reg.1` | `ged` | Gedackt 8′ | key pitch |
| `bt.reg.2` | `princ4` | Principal 4′ | key + 12 semitones |
| `bt.reg.3` | `princ2` | Principal 2′ | key + 24 semitones |
| `bt.reg.4` | `qui223` | Quint 2 2/3′ | key + 19 semitones |
| `bt.reg.5` | `reg8` | Regal 8′ | key pitch |

The labels and offsets are qualified import interpretations, not evidence for
historical tuning, A4=440, or equal temperament. Playback preserves recorded
pitch unless reviewed VAO playback parameters explicitly say otherwise.

### 2.4 Unity multimedia facts

The source inventory contains seven FBX files, six `.anim` files, five
presentation MP3 files, an animator controller, textures/materials, Unity
scenes/prefabs, scripts, and `.meta` files. Not all are instrument evidence:
three FBX files live in the bundled Resonance Audio demos and must not be
promoted into the Cuntz object merely because they are present.

Relevant first-party model candidates include:

- `Assets/Models/4010243_segmented.fbx`;
- `Assets/Models/4010243_segmented_03b2.fbx`;
- `Assets/positiv_keys.fbx`;
- `Assets/ariston_remap_v2.fbx` (identity/relevance requires curatorial review).

`Assets/Scripts/KeyHandler.cs` establishes the legacy register order, constructs
sample resource names, falls back to `_0`, plays one sample per active register,
and starts a 0.3-second fade on pointer-up. Its implementation fades the shared
active-source list, so releasing one key may affect other active voices. That is
source evidence, not automatically the desired portable semantic policy.

## 3. Evidence and identity boundary

The Cuntz VAO must use:

| Layer | Required representation |
| --- | --- |
| Root package/instrument ID | Local persistent UUID URN until governed identity resolution |
| Source identity | `SOURCE:musixplora:4010243` and/or source-record locator |
| Canonical MDVS ID | Absent/null until an owner-governed record supplies it |
| Imported assertions | Source-bound/inferred/reviewed status as applicable |
| Rights | Unknown or explicit evidence-backed statement; availability is not permission |

The extension displays this boundary. It does not upgrade `4010243`, merge
conflicting external descriptions, or label a reconstruction as captured fact.

## 4. Golden VAO target graph

The complete first golden package must contain at least:

| Node/record class | Count or rule |
| --- | --- |
| Root musical instrument | 1 |
| Stop components | 5 |
| Sounding-position components | 225, one per stop/key pair |
| Key interaction entities | 45, one per observed physical key/control domain |
| Stop-selection interactions | 5, independent toggles |
| Stop selection/configuration/state nodes | Explicit, governed model chosen at authoring gate |
| Sample playback parameter sets | 225 unless a reviewed, lossless shared structure is normatively valid |
| WAVE master assets | 225, byte-identical |
| Sample voice interactions | 225 resolvable key + active-stop combinations, each resolving exactly one WAVE asset and one playback-parameter set |
| Relevant source models | Preserved FBX plus reviewed glTF derivatives |
| Control/model geometry bindings | Every pickable key and stop, using stable selectors |
| Relevant animations | Preserved Unity source plus open derivatives for runtime use |
| Presentation audio | 5 MP3 assets, role-distinct from isolated samples |
| Source evidence | `KeyHandler.cs`, relevant scenes/prefabs/controller and required `.meta` records |
| Paradata | Import, hashing, FBX→glTF, animation conversion, mapping, review, exclusion, and validation activities |
| Rights records | Package-level unknown/known statement plus narrower evidence-backed records |

Required relation families include instrument/component membership,
control-to-component activation, stop selection/configuration, `usesSample`,
`usesPlaybackParameters`, representation/model binding, `drivesAnimation`,
source/derivative provenance, and evidence links. Filenames remain provenance
only.

### 4.1 Sample resolution model

For a key `K` and active stop `S`, one compiled voice must resolve through graph
records equivalent to:

```text
key interaction K
  -> activates sounding component (S, K)
  -> usesSample WAVE asset (S, K), under explicit selection scope S
  -> usesPlaybackParameters accepted parameter set (S, K)
```

The exact governed predicates and configuration/selection scope must be agreed
with the pinned VAO contract. The current migration document names
`selectsConfiguration`, but that term is not present in the audited 0.2.2 VAO
vocabulary snapshot. This is a real authoring blocker: the golden package must
choose a valid existing governed pattern or add a reviewed absolute-URI
extension with matching semantic validation. The Blender runtime must not
invent the missing term privately.

## 5. Cuntz runtime design

### 5.1 Initial presentation

After full validation and rights acknowledgement, **Load Recommended
Representation** selects the reviewed glTF derivative whose roles and geometry
bindings identify it as the runtime visual. The root collection is placed using
declared units, axes, frame, and transform. Source FBX and Unity assets remain
visible in the asset inventory but are not preferred runtime representations.

The Overview panel shows:

- Cuntz Positiv / qualified source title;
- source-bound `4010243` identity and absent canonical binding;
- five stops and 45-key observed compass;
- 225/225 sample fixity result;
- private VAO 0.2.2 snapshot warning;
- rights/access status and acknowledgement state;
- supported/unsupported capability result.

### 5.2 Stop controls

The Play panel presents five independent toggles in documented order:

```text
Gedackt 8′ | Principal 4′ | Principal 2′ | Quint 2 2/3′ | Regal 8′
```

- Default state comes from the manifest; the runtime does not assume a stop is
  selected.
- Zero selected stops is valid and produces no sample voice on gate-open.
- Multiple stops create one voice per resolved selected stop.
- Changing a stop affects future gate opens. Whether it affects sounding voices
  must be explicit in the interaction policy; version 0.1 otherwise leaves
  already-started gate voices unchanged.
- Toggle state is host/session state, not a new instrument assertion.

### 5.3 Key controls

Preferred pointer interaction uses stable selectors for the imported key model.
If those selectors are absent or unsupported, the generated interaction board
shows the 45 declared keys only.

Computer-keyboard performance uses a movable 12-semitone piano layout:

```text
Lower row: A S D F G H J ...
Upper row: W E   T Y U ...
```

The exact map is configurable and displayed as an overlay. Octave/base controls
move the window; absent short-octave notes remain disabled rather than mapped to
neighbors. Auto-repeat is ignored. Key-down opens one gate and key-up closes the
same gate even if the visible octave changes while held.

### 5.4 Audio behavior

- Cuntz voices use the 192 kHz stereo WAVE masters through Blender `aud`; the
  audio device may resample for output, but no derivative replaces the master.
- A gate starts all selected stop voices as one synchronized group to the extent
  supported by `aud.Device.lock()`.
- The runtime uses declared gain, pitch mode, attack, release, channel, priority,
  and note-off policy. There is no baked-in footage transposition.
- Gate release is scoped to the gate's handles unless the approved golden graph
  explicitly requests and the runtime supports another behavior.
- The legacy 0.3-second fade is a candidate value for review, not a hidden
  default.
- Voice factory caching is lazy and bounded. A Cuntz load never decodes or
  buffers all 225 recordings.

### 5.5 Animation behavior

When the golden package provides glTF animation channels and declared target
relations, key/stop actions may trigger them. The runtime does not parse Unity
`.anim` or controller logic. If a key animation is unavailable, audio playback
can remain supported when animation is not a required part of the interaction;
if the graph requires it, compilation fails visibly.

## 6. Golden-package creation plan

This content work is Milestone 0 and may proceed in parallel with the standalone
reader, but it is a gate for Cuntz runtime completion.

1. Freeze a checksum inventory of the two audited source locations and record
   intentional exclusions, especially third-party demos/caches/AppleDouble.
2. Resolve or explicitly retain unknown rights/access for audio, models,
   textures, scripts, presentation media, and third-party dependencies.
3. Reconcile the relevant model set and Unity GUID/object bindings.
4. Convert reviewed FBX representations to glTF/GLB without overwriting sources;
   record Blender/converter version, settings, axes, units, transforms, inputs,
   outputs, and reviewer.
5. Convert required animations to glTF channels or an open timestamped
   representation; retain Unity source evidence.
6. Assign stable glTF node-index or supported feature selectors to the root,
   each physical key/control, stop control, and animated target.
7. Author the root, five stops, 225 sounding positions, configurations/states,
   275 interactions (45 key controls, 5 stop controls, 225 scoped voices), 225
   sample parameters, relations, rights, and paradata. The 225-way interaction
   expansion is required because VAO 0.2.2 permits exactly one `usesSample`
   target for each conforming sampled interaction.
8. Decide and encode stop-selection semantics, gate-release scope, fade curve,
   velocity behavior, channel policy, and whether any loops/releases are
   reviewed for direct playback.
9. Add every retained byte once under `payload/` and compute final size/SHA-256.
10. Validate the workspace, pack a new archive, validate the finished bytes with
    VAOM, independently spot-check hashes/bindings, and record the external
    archive checksum in the golden-test metadata.

The original Unity tree and WAVE corpus remain untouched. The golden `.vao` is a
new immutable revision and must not become the only copy of the evidence.

## 7. Golden acceptance assertions

- VAOM reports a valid core and claimed-profile graph with 225/225 verified
  WAVE assets.
- VAO-Blender independently reports the same validity outcome.
- Exactly five independently selectable stop controls compile.
- Exactly 45 key gates compile; 37, 39, 42, and 44 do not.
- Exactly 225 voice plans resolve, one per `(stop, key)` pair, with no filename
  fallback.
- Every voice trace names its interaction, active selection condition,
  component, sample relation, parameter relation, asset ID, and SHA-256.
- All required glTF node selectors resolve after Blender import.
- Imported scale/orientation is checked against a documented reference view and
  dimensions.
- Press/release of single notes, repeated notes, overlapping notes, and
  multi-stop chords produces no stuck or cross-gate voices.
- Stop changes during sounding notes follow the documented state-transition
  rule.
- Presentation MP3 files never appear as playable isolated-stop samples.
- Unity/C# content remains non-executable and visible as evidence.
- Unknown rights require a session acknowledgement and remain unknown in all UI
  and reports.

## 8. Open content decisions

| ID | Decision needed | Owner/gate |
| --- | --- | --- |
| C-01 | Which FBX/texture/material records are first-party Cuntz evidence? | Curatorial review before graph authoring |
| C-02 | Which source model becomes the runtime glTF derivative? | 3D/domain review before selector work |
| C-03 | Governed representation for independent stop selection in VAO 0.2.2 | VAO contract review before golden manifest |
| C-04 | Voice-scoped versus legacy global release; fade duration/curve | Domain/audio review before interaction acceptance |
| C-05 | Any accepted loop/release regions or preserve whole recordings only? | Audio review; unsupported features may defer playback |
| C-06 | Channel policy for stereo samples | Audio evidence review |
| C-07 | Rights/access conditions for each asset group | Rights holder/curatorial review before runtime gate |
| C-08 | Relevance/redistribution of third-party SDKs and `.meta` files | Legal/reproducibility review |

None of these gaps is permission for VAO-Blender to infer an answer.
