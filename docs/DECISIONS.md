# Architecture decision record

> Historical decisions through the 0.2.0/0.3.2 development period. Current
> public VAO 0.4.0 and candidate VAO 0.5.0 support and release policy are documented in
> [COMPATIBILITY.md](COMPATIBILITY.md) and [RELEASE.md](RELEASE.md).

Status: proposed baseline decisions  
Date: 2026-08-24

This file records choices that shape implementation. “Accepted” means the
development plan is built around the choice; it can still be superseded by a
new recorded decision. “Blocked” identifies an input that must be resolved
before its named gate.

## ADR-001 — Ship as a Blender Extension

Status: accepted

Use `blender_manifest.toml` and Blender's Extension system, not only legacy
`bl_info` add-on packaging. The package is self-contained, declares file
permission, vendors its dependencies, and is built/validated with Blender's
extension commands.

Why: Extensions are the supported distribution model from Blender 4.2 onward,
provide explicit metadata/permissions/dependency packaging, and match the
target Blender 5.x line.

Consequence: build tooling, wheels, license metadata, and relative imports are
release-critical artifacts.

## ADR-002 — Version 0.1 is read-only

Status: accepted

The extension validates, reads, caches verified copies, and materializes host
scene/runtime state. It does not edit/repack/migrate/sign a VAO.

Why: a correct writer must preserve unknown extensions, provenance, fixity,
profiles, revisions, and source bytes. Combining that with the first safe reader
and audio runtime would multiply risk and delay the Cuntz proof.

Consequence: Blender edits affect the `.blend`, not the source VAO. Exporter and
round-trip roles require a later explicit project.

## ADR-003 — Pin the private VAO 0.2.2 release candidate

Status: accepted

The contract source is
`vao-specification-0.2.2-rc.zip` with SHA-256
`76b55f33b09c94ad90aac79e8a599d007841e2c11288664f9c67987b4e68f328`.
The original 0.1 reader accepted the 0.2.x compatibility line described by this
bundle. ADR-017 narrows implemented dispatch to the exact pinned 0.2.2 bytes and
adds a separate exact 0.3.2 path; unreviewed patch versions do not fall through.

Why: the identifiers are not publicly deployed or namespace-frozen and runtime
network fetch/substitution would make results irreproducible.

Consequence: contract artifacts are vendored and verified. An update is a
reviewed compatibility change, not a background download.

## ADR-004 — Never execute VAO active content

Status: accepted

C#, Python, JavaScript, Unity scenes/controllers, drivers, macros, and other
bundled code remain evidence/inventory only. Behavior is compiled solely from
the supported declarative VAO graph into registered host actions.

Why: Blender add-ons run with user privileges and are not a security sandbox;
legacy executable behavior also defeats application-neutral VAO semantics.

Consequence: a package requiring unknown behavior is valid-but-unsupported, not
partially executed.

## ADR-005 — No network in version 0.1

Status: accepted

Do not request Blender network permission. Do not resolve W3ID, context,
vocabulary, asset, identity, or media URIs at import time.

Why: the VAO is self-contained, the pinned private identifiers may not resolve,
and offline determinism narrows the trust boundary.

Consequence: remote/offline-optional asset groups are inspectable metadata only.

## ADR-006 — Full validation precedes media use

Status: accepted

Complete container, schema, semantic, profile, payload cardinality, byte-size,
CRC, and SHA-256 checks before decoding/import/playback.

Why: this is the pinned VAO reader contract and prevents malformed or hidden
payload use.

Consequence: first Cuntz load must stream about 3.68 GB. Work happens in a
cancellable worker with progress; performance optimization may not remove the
gate.

## ADR-007 — Separate validity, support, local limits, and rights

Status: accepted

Use typed result states rather than one success Boolean or generic error list.

Why: a valid package may require an unsupported renderer, codec, or interaction;
a local size limit does not prove invalidity; a rights statement can block an
otherwise valid/supported action.

Consequence: UI, reports, tests, and compiler APIs carry these states explicitly.

## ADR-008 — Keep the conformance core independent of Blender

Status: accepted

Archive/schema/semantic validation, graph indexing, capability negotiation, and
plan compilation do not import `bpy` or `aud`.

Why: correctness testing is faster and reference parity is easier; Blender API
changes remain isolated in adapters.

Consequence: no worker thread returns/mutates Blender objects, and runtime plans
are immutable boundary values.

## ADR-009 — Use glTF/GLB as the first runtime visual format

Status: accepted

Preserve any source formats in the VAO inventory, but load reviewed glTF/GLB for
runtime viewing, selectors, and animation.

Why: VAO recommends glTF 2.x, Blender has an official importer, and the Cuntz
migration already calls for open derivatives alongside FBX sources.

Consequence: a complete Cuntz gate includes reviewed FBX→glTF conversion
paradata. Source FBX is not silently replaced.

## ADR-010 — Inject node-index extras into a temporary import derivative

Status: accepted, implementation spike required

Create a cache-temporary glTF/GLB copy that adds a namespaced node-index extra,
then import with extras enabled and map created Blender objects back to stable
VAO selectors.

Why: glTF names are explicitly non-unique and Blender's public import API does
not guarantee a durable node-index mapping.

Alternatives rejected for 0.1:

- match object names (semantically unsafe);
- fork Blender's full glTF importer (large maintenance/security surface);
- require source authors to mutate every original model (changes evidence and
  cannot support existing conforming assets).

Consequence: the shim must rebuild GLB headers/padding correctly, never confuse
the temporary bytes with the verified asset, and pass duplicate-name/node-order
tests. If the spike proves unreliable, bound interaction is blocked and a
different stable adapter needs a superseding ADR.

## ADR-011 — Use Blender `aud` for the first audio runtime

Status: accepted for the narrow 0.1 subset

Use `aud.Sound`, `aud.Device`, and owned `aud.Handle` objects for verified WAVE
sample voices, bounded caching, pitch/gain, and control-rate attack/release.

Why: it ships with Blender on every target and avoids a second native audio
stack for the Cuntz proof.

Consequence: do not claim sample-accurate event timing or arbitrary loop/release
regions. Unsupported policies make the concrete playable runtime unsupported.
A future dedicated sampler backend requires measured justification and another
ADR.

## ADR-012 — Compile interactions; do not add a Cuntz adapter

Status: accepted

The runtime supports declared types/bindings/policies and compiles any package
that fits them. Cuntz has no runtime special case or filename grammar.

Why: the product objective is VAO interoperability, and Cuntz is a reference
case rather than the format.

Consequence: golden tests may assert the known 5×45 matrix, but production code
can only see graph identifiers, predicates, scopes, and assets.

## ADR-013 — Use a managed content-addressed cache

Status: accepted

Extract on demand into per-extension writable storage keyed by asset SHA-256,
using partial files and atomic commit. Default quota is 20 GiB.

Why: `aud` and Blender importers need filesystem paths; repeated extraction of
large assets is expensive; content hashes give safe identity.

Consequence: cache reuse rechecks type/size/hash, full package validation still
runs, and clear/eviction uses exact marked managed paths only.

## ADR-014 — Target Blender 5.1 and 5.2 LTS first

Status: accepted

Alpha target is the installed Blender 5.1.1/macOS ARM64. The release target adds
5.2 and covers macOS ARM64, Windows x64, and Linux x64. The manifest minimum is
5.1.0 and its maximum is exclusive 5.3.0.

Why: the development machine and API baseline are concrete, while the current
5.2 LTS is the durable release target. Supporting 4.5 immediately adds Python/
wheel/API matrix cost before the design is proven.

Consequence: 4.5 LTS and Intel macOS are not advertised without their own full
official-host test support. Blender 5.1/5.2 publish no official macOS x64 build,
so that target cannot meet this release's reproducible native-evidence gate.

## ADR-015 — Validate JSON Schema with a bundled standards library

Status: accepted in principle; exact dependency versions pending M0

Bundle `jsonschema` and transitive dependencies as unmodified wheels, and add
explicit URI/date-time format checks. Independently implement the VAO semantic
rules and compare with VAOM.

Why: the manifest uses JSON Schema 2020-12, while reimplementing that standard
inside the add-on is unnecessary risk. JSON Schema still does not cover VAO
semantic/container rules.

Consequence: every supported platform/Python wheel, dependency hash/license,
SBOM, and supply-chain update is a release gate. Copying reference-validator
code is not assumed legally permitted until licensing is approved.

## ADR-016 — Rights acknowledgement is session-only

Status: accepted

Unknown/restricted rights are shown before asset use. Where local policy allows,
the user may acknowledge responsibility for a local action for the current
session. That state is neither package evidence nor permission.

Why: unknown rights must not mean permission, but authorized researchers may
need to use controlled local evidence whose public licensing is unresolved.

Consequence: acknowledgement is not serialized into the VAO/manifest and does
not enable sharing/export/network operations.

## ADR-017 — Exact VAO 0.3.2 visual-acoustic dispatch

Status: accepted

VAO 0.3.2 is implemented as a separate read-only model alongside the pinned
0.2.2 capture/instrument path. Runtime visual geometry resolves from a
`runtime-visual` binding to a logical asset and then a verified embedded GLB
realization. The row-major frame graph is authoritative; filenames are not.

RIR data is exposed as typed response/measurement/fixity/provenance metadata.
Until a separately reviewed renderer exists, it is not played as program audio
and does not imply convolution or simulation support. The 0.3.2 snapshot is an
implemented private editor draft and is not forward-compatible by assumption.

Consequence: 0.3.0/0.3.1 and future 0.3 values are rejected explicitly, and
changing the pin requires a reviewed contract upgrade with new oracle evidence.

## Open/blocked decisions

### ADR-P01 — Cuntz independent stop-selection graph

Status: blocked before Cuntz golden manifest

The migration document names `selectsConfiguration`, but the audited 0.2.2
vocabulary does not define that term. Decide a governed existing graph pattern
or a reviewed absolute-URI extension plus validator/compiler semantics. Do not
invent a Blender-only predicate.

### ADR-P02 — Cuntz release scope and envelope

Status: blocked before Cuntz playable acceptance

Decide whether portable behavior follows per-gate voice release or preserves the
legacy shared/global fade, and record duration/curve. The current design supports
per-gate control-rate release; another required behavior may remain unsupported.

### ADR-P03 — Cuntz rights and redistribution scope

Status: blocked before public golden distribution

Obtain evidence-backed rights/access decisions for audio, models, textures,
presentation media, source code, `.meta` records, and relevant dependencies.
Unknown can remain in a controlled research VAO but may prevent public test
artifact distribution.

### ADR-P04 — Project and vendored-contract licenses

Status: blocked before public extension distribution

Select an approved Blender-compatible SPDX license for extension code and obtain
permission for the private VAO contract artifacts/reference-derived material.
Record third-party dependency notices and security contact.
