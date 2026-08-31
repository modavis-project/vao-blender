# Test strategy

> This document records the broad 0.2.0 test program and historical Cuntz golden
> package plan. The executable release commands and exact VAO 0.4.0/0.5.0 gates are
> maintained in [RELEASE.md](RELEASE.md) and [CONFORMANCE.md](CONFORMANCE.md).

Status: historical strategy with current principles
Applies to: standalone core, Blender extension, and Cuntz golden package

## 1. Test objectives

The suite must prove five independent properties:

1. valid VAOs are recognized against the pinned contract;
2. invalid/untrusted archives fail before unsafe extraction or decode;
3. valid but unsupported content remains distinguishable from invalid content;
4. compiled scene/interaction/audio behavior matches the explicit graph; and
5. Blender lifecycle operations leave no stuck audio, stale worker, timer,
   handler, partial file, or unintended scene mutation.

Passing a schema test alone is never a release signal. Passing Cuntz playback
alone is also insufficient because a package-specific happy path can conceal an
incorrect general reader.

## 2. Test layers

| Layer | Runtime | Purpose |
| --- | --- | --- |
| Pure unit | System CPython | Paths, limits, hashing, JSON, graph, diagnostics, compilers, cache policy |
| Contract/conformance | System CPython | Schema + semantic parity against pinned VAO fixtures/mutations |
| Blender background | Supported Blender builds | Registration, operators, glTF import, scene mapping, teardown, extension package |
| Audio integration | Blender with audio backend or controlled offline backend | Voice plan execution, handle/envelope/cleanup behavior |
| Manual/UI | Supported OS/Blender UI | Panels, drag/drop, modal events, picking, accessibility, error clarity |
| Golden/end-to-end | Cuntz package in controlled storage | Full 3.68 GB validation, 3D, five stops, 45 keys, 225 voices |

Pure tests must dominate so most failures are fast and independent of Blender.
Blender tests verify the adapter boundary rather than re-testing every semantic
rule through UI clicks.

## 3. Fixture policy

### 3.1 Vendored positive fixtures

Copy, with source checksums, from the pinned VAO 0.2.2 release bundle:

- `minimal-string-instrument.vao`;
- `minimal-playable-string-instrument.vao`;
- `minimal-experiential-instrument.vao`;
- `minimal-acoustic-room.vao`.

The release bundle checksum is the repository contract pin. Fixture bytes must
not be regenerated silently.

### 3.2 Synthetic runtime fixture

Create a small redistributable `minimal-playable-keyboard.vao` specifically for
VAO-Blender integration tests. It contains:

- one glTF/GLB with stable node-index selectors for two or three keys;
- two independent selections and a small explicit key/selection voice matrix;
- short generated WAVE assets with known sample rate/duration/amplitude;
- linear attack/release and preserve-pitch parameters;
- one glTF key animation;
- clear permissive rights.

It exercises the same general compiler path as Cuntz without placing Cuntz
evidence in source control.

### 3.2a Pinned VAO 0.3.2 visual-acoustic fixture

`tests/fixtures/vao-0.3.2/acousticrooms-bathrooms-idx-0.vao` is immutable test
evidence with carrier SHA-256
`54aef8656162f485a0c4aa37dca56accc909284db4f746b33f85500749da2286`.
Its adjacent oracle pins carrier/payload counts, GLB mesh identity/counts, the
row-major GLB-to-dataset transform, source/receiver poses, and fixed-pair RIR
metadata. Mutation tests rebuild temporary carriers; they never rewrite the
prepared fixture.

The pure suite asserts exact dispatch, closed schemas, ZIP64 processing,
manifest/carrier/release binding, one-to-one payload mapping, corrupt-fixity and
unindexed-payload rejection, singular-transform rejection, stable logical
binding selection, frame/full-pose algebra, RIR status/fixity/provenance, direct
report parity with the pinned OrgRec validator, and the retained 0.2.2
regression. The Blender 5.1.1 background suite asserts the
17,429-vertex/21,760-polygon GLB, exact placement, stable trace tags,
metadata-only audio boundary, rollback, session teardown, and explicit
materialization cleanup.

### 3.3 Negative/mutation fixtures

Generate one focused mutation per rule from known-valid bases. Mutations are
named by expected diagnostic code and stage, for example
`CNT-unsafe-dotdot.vao` or `SEM-unindexed-payload.vao`. Keep the mutation recipe
in source so intent remains reviewable.

Required families:

- entry order, exact MIME bytes, compression, encryption, duplicates, normalized
  collisions, case-fold collisions, invalid UTF-8, links/special files, root
  path policy, ZIP64 and inconsistent size/CRC;
- entry count, manifest, per-entry, total-expanded, compression-ratio, disk, and
  cancellation limits;
- duplicate JSON keys, invalid/non-finite JSON, closed-schema fields, URI/date
  formats, version dispatch;
- duplicate IDs, dangling subjects/objects, asset/path cardinality, byte/hash
  mismatch, rights coverage, invalid relation status/scope;
- false core/playable/spatial/experiential claims and unknown required
  capability;
- cyclic/singular coordinate frames, invalid quaternion, unsupported stable
  selector;
- ambiguous sample mapping, missing playback parameters, unreviewed parameter
  set, missing selection scope, unsupported pitch/timing/loop/release policy;
- glTF external URI, malicious extras text, missing node selector, duplicate
  node names, and import failure after staging;
- tampered cache file/symlink/index and unsafe cache-root preference.

## 4. Pure unit coverage

### 4.1 Archive/path tests

- Normalize and reject Unix, Windows, Unicode, case-fold, dot, empty, NUL, and
  separator variants.
- Decode external attributes for regular/link/special modes.
- Enforce limits before extraction and during bounded streaming.
- Verify that destination containment uses resolved paths and exact managed
  roots.
- Inject I/O, CRC, hash, cancellation, disk-full, and atomic-rename failures and
  assert partial cleanup.

### 4.2 Contract/graph tests

- Validate all schema `$defs`, format checks, and duplicate-key behavior.
- Build deterministic maps/indexes and compare snapshots.
- Resolve every local reference and active relation rule.
- Retain unknown optional absolute-URI properties exactly in JSON meaning.
- Confirm invalid, unsupported, limited, blocked-rights, and warning outcomes are
  different typed results.
- Compare diagnostics in deterministic code/pointer/ID order.

### 4.3 Capability/compiler tests

- Property-based generation covers selection sets, gate domains, scoped sample
  matrices, duplicate/ambiguous plans, velocity bounds, pitch ratios, and
  release policies.
- Every `VoicePlan` trace resolves back to exact interaction/relation/component/
  parameter/asset IDs.
- Unsupported required action prevents package runtime support; optional
  unsupported inventory does not.
- Filename and label changes leave compiled identity/behavior unchanged.
- Missing notes remain missing; no domain min/max expands them.

### 4.4 Cache tests

- Keys depend on SHA-256, not filenames.
- Existing regular/size/hash match is reused; mismatch is quarantined.
- Quota/LRU never evicts an active-session asset.
- Clear cache rejects root/home/project/unmarked paths and deletes only managed
  entries.
- Concurrent requests for one asset coalesce or serialize without corrupting the
  final file.

## 5. Reference conformance parity

For every pinned positive and generated negative fixture:

1. run `python3 ../orgrec/Tools/vaom.py validate <fixture>` against the pinned
   source or release-bundle VAOM;
2. run the standalone VAO-Blender validator;
3. compare validity, profile-claim outcome, verified asset count/bytes, and
   relevant error class;
4. manually review intentional diagnostic wording differences.

A validity disagreement is release-blocking until traced to a documented
normative interpretation and resolved. The project does not copy test expected
values from its own validator output without independent review.

## 6. Blender-background tests

Invoke each supported Blender binary with `--background --factory-startup` and
a test script. Cover:

- install/build/manifest validation and extension enable/disable twice;
- class/menu/file-handler/property/keymap/timer/handler registration symmetry;
- validate a fixture without creating scene geometry;
- import glTF into staging, inject/resolve node-index extras, tag data-blocks,
  apply root transform, and commit collection;
- rollback on missing selector/import exception without touching pre-existing
  same-name objects;
- load two VAOs with colliding titles/Blender names and retain distinct IDs;
- save/reopen `.blend`, discover detached collections, relink exact source, and
  reject a changed revision;
- close one of two sessions without affecting the other;
- cancel validation and unregister/load a new Blender file while work is active;
- diagnostic JSON export with absolute paths redacted by default.

Tests inspect data-block ownership and custom trace tags directly. Screenshots
are supplemental, not assertions for semantic state.

## 7. Audio tests

### 7.1 Pure engine adapter tests

Wrap `aud` behind a small interface and use a fake device/handle in unit tests.
Assert:

- one handle per selected/resolved voice;
- device lock/unlock balance, even on play failure;
- preserve/resample/disabled pitch behavior;
- attack/release volume progression and end-state cleanup;
- release affects the correct gate handles;
- repeat key-down is ignored or handled by declared retrigger policy;
- voice limit and stealing order;
- close/unregister stops owned handles only;
- failed/stopped handles leave maps/LRU clean.

### 7.2 Real backend integration

With short generated WAVE fixtures:

- `aud.Sound.file` can decode/play the format on each platform;
- 192 kHz 32-bit float stereo Cuntz-format smoke sample decodes on supported
  builds;
- start/stop/repeat/chord stress creates no stuck handles;
- measured onset grouping and release ramp are characterized. The release does
  not claim sample accuracy.

Where CI has no audio device, run the fake/offline tests and mark real-device
coverage as a required manual release check rather than pretending it ran.

## 8. Manual/UI checklist

- Import through menu, file browser, and drag/drop.
- Cancel at preflight and each progress stage.
- Read status without relying on color and navigate all panels with keyboard.
- Search/filter entities/assets and copy a full identifier.
- Review rights statement and exercise allowed/unknown/restricted/prohibited
  gates.
- Load, frame, select, show/hide, and remove a visual representation.
- Enter/exit performance mode, use displayed computer-key map, mouse-pick bound
  controls, and use fallback control surface.
- Lose viewport focus/context, load another `.blend`, disable extension, and
  quit while notes are held; confirm silence/cleanup.
- Trigger unsupported media, selector, timing, and capability reports and verify
  the package is still described as valid where appropriate.
- Clear cache and verify the confirmation displays one exact managed root.

## 9. Cuntz golden tests

The 3.68 GB package lives in controlled artifact storage, not Git. A checked-in
metadata file pins its archive SHA-256, manifest SHA-256, expected contract
checksum, size, revision, and permitted test location/scope.

Automated assertions:

- complete validation, 225 assets/bytes/hashes, no unindexed payload;
- graph counts and exact observed key set;
- five selection plans, 45 gate plans, 225 voice plans;
- each stop has all and only the same 45 keys;
- no asset resolution path uses `originalFilename` or archive-name parsing;
- model/selector resolution count and root transform snapshot;
- correct distinction of sample WAVE vs presentation MP3 vs source evidence;
- private identity/rights warnings remain present.

Interactive scenarios:

- each stop alone across low/middle/high keys;
- all five stops on one key;
- overlapping two- and ten-key chords within the voice limit;
- repeated key, rapid release, press one key/release another;
- change stops during held notes according to the accepted policy;
- low short-octave keys and disabled missing positions;
- exit/close/unregister with active chord;
- cold cache, warm cache, and one intentionally tampered cached sample.

The first golden run records baselines rather than inventing hard time limits.
Release criteria require responsive UI, bounded memory, cancellation, no full
corpus buffering, and no performance regression beyond an agreed threshold from
that recorded hardware baseline.

## 10. Performance and reliability measurements

Record for each supported platform/build:

- central-directory/preflight latency;
- full validation wall time and sustained compressed/expanded hashing throughput;
- peak Python/process memory above Blender baseline;
- progress cadence and cancellation latency;
- glTF staging/import/selector resolution time and object/data-block count;
- first cold and warm sample-to-sound latency;
- 1, 5, 32, and 64 voice CPU/memory behavior;
- cache extraction throughput/quota eviction;
- 30-minute interaction soak with random valid state/gate events.

No validation benchmark is allowed to disable fixity. Performance work changes
streaming, caching, and UI scheduling—not the conformance result.

## 11. CI and release matrix

| Gate | Every change | Release candidate |
| --- | --- | --- |
| Pure lint/type/unit | Yes | Yes |
| Contract checksum + positive/negative conformance | Yes | Yes |
| Blender 5.1.1 macOS ARM64 development smoke | Development host only | Does not satisfy a release-target cell |
| Blender 5.1.2 and 5.2.1 native targets | Targeted smoke | Six detached, exact-artifact installed-extension cells |
| Extension build/validate | Yes | Yes, built artifact revalidated |
| Dependency/SBOM/license scan | Dependency changes | Yes |
| Synthetic playable fixture | Yes | Yes |
| Cuntz full golden | Scheduled/nightly or controlled host | Mandatory |
| Manual UI/audio/security checklist | No | Mandatory, signed record |

Flaky conformance, cleanup, or security tests block release. A platform without
real audio coverage is not listed as fully supported until its manual audio
check is recorded.

## 12. Test completion evidence

Each release stores:

- source commit and extension ZIP SHA-256;
- contract bundle and fixture checksums;
- exact Blender/OS/Python versions;
- test command/results and conformance parity summary;
- Cuntz golden metadata and controlled-run result (without redistributing
  restricted bytes);
- performance baseline/delta;
- manual checklist sign-off;
- known unsupported capabilities and open defects.
