# Mechanical Music Information Carriers — MMIC 1.0.0

Status: **final specification**, 10 October 2026. Envelope: VAO
`0.6.0`. Profile specification: `1.0.0`. Profile identifier:
`https://w3id.org/modavis/vao/profile/mmic/1.0.0`.
Versioned identifiers define the released contract; 0.6.0 resolver routing is
pending. The immutable release includes the complete local dependency catalog. Historical fidelity and physical playability are not certified.

The normative machine contract is [the closed domain schema](../Profiles/MMIC/1.0.0/mmic.schema.json),
[dependency catalog](../Profiles/MMIC/1.0.0/dependencies.json),
[registry](../Profiles/MMIC/1.0.0/registry.json), and the requirements below.
The normalized JSON sidecar is authoritative for operational fields. RDF is a
lossless, ordered projection of that model, not a separately authored competing
interpretation. JSON object property order is insignificant; arrays retain order.
Unknown information belongs in qualified documentary values or namespaced
`extensions`, never guessed executable notes or controls.

## Profile and module ownership

VAO maintainers govern this profile and the bundled, standalone mechanical-music
module. Its stable term namespace is `https://w3id.org/modavis/vao/mmic#`; its exact
ontology version IRI is the profile identifier followed by `/ontology`.
This module is **not an accepted MODAVIS Ontology Network module**. The existing
MODAVIS 0.1.0 binding remains unchanged. A future network adoption needs its own
review and version. The catalog declares the complete local normative import
closure: the self-contained mechanical-music module. There are no remote imports.

CRM 7.1.3 and EDM 5.2.8 mappings are separately identified, informative
`skos:closeMatch`/`relatedMatch` statements. They create no subclass entailment
and do not assert receiving-profile compliance. CRM E84 mapping cannot be treated
as an already accepted MODAVIS dependency. QUDT unit IRIs are exact identifiers;
this profile does not import or reason over a moving QUDT ontology.

## Core integration

**CORE-01.** Both embedded and materializable profile records MAY contain an
independent `specificationVersion`. MMIC records MUST use `1.0.0`; their
existing `version` MUST remain the envelope version `0.6.0`. Exactly one MMIC
profile record, its `conformsTo` entry, extension descriptor and trusted registry
MUST agree. No duplicated profile identifier expresses partial support.

**CORE-02.** Entity `kind` is an open nonempty coarse label. Normative classification
uses ontology `types` and profile rules. A carrier or design may be the primary
entity without inventing an instrument. Technical metadata `kind` retains its
separate closed media contract.

The MMIC extension MUST bind its exact profile/ontology versions, semantic
realization and SHA-256, local dependency-catalog SHA-256, levels and core subject
entity IDs. An incoming URL cannot select executable validation code.

## Required domain behaviour

**MMIC-01 — identities and lifecycle.** Physical carrier, digital surrogate, state,
programme, observation, feature, reading model, model role, binding, assignment,
native event, interpretation, playback, comparison, design and fabrication have
distinct identities. Cross-view reuse is allowed only for the same typed carrier
or design represented in the core. Core realization/activity/agent references
resolve to their declared registries. External identifiers retain issuer, scheme,
lexical value and claim scope. State, model and interpretation predecessors MUST
be acyclic; state predecessors retain carrier scope. Physical interventions name
their activity. Ordered parts and separate collection members retain identities.

**MMIC-02 — documentary minimum.** Every physical subject MUST bind a separately
identified digital surrogate, carrier/encoding classification, qualified state,
geometry status, observational coverage and evidence. Undetermined geometry MAY
omit physical units and bounds; unknown programme extent is `null`. It MUST NOT
acquire invented measured dimensions. Design subjects instead bind purpose,
source, target model/status, layout, report, activity and evidence. They need no
fictitious physical object. Missing or partial coverage remains explicit.

**MMIC-03 — serialization and references.** Closed normative records use the schema.
Namespaced extension values survive projection and migration. The RDF encoding
uses typed objects, ordered indexed arrays, explicit field keys, literals and
qualified IRI references. Inversion MUST reject ambiguity, extra or unreachable
claims, cycles and inconsistent types; re-projection MUST be isomorphic. All
normative JSON fields round-trip, including clocks, native signals, geometry,
lineage and ordering. Core byte digests bind the actual stored bytes.
Declared `subjectEntityIds` MUST resolve to represented carriers, their digital
surrogates or designs in the normalized domain document.

**MMIC-04 — complete model identity.** `model.spec` is the sole operational model.
It binds geometry, complete reader trajectory/response/delay, timing, roles,
bindings, initial state, constraints and exact code/environment/evidence inputs.
The model uses RFC 8785 canonicalization and an explicit digest scope. An
interpretation or design binds that complete digest. Selected state geometry
agrees with its model; no unverified redundant reader copy exists. Model artifact
pins agree with core realization fixity. Exact-byte and canonical model digests
are distinct. Reject duplicate keys, nonfinite numbers and unsafe integers.
[RFC 8785](https://www.rfc-editor.org/rfc/rfc8785).

**MMIC-05 — observation and role.** A feature binds its actual source observation,
state/programme/track, morphology, selector and evidence. Selectors remain within
declared acquisition bounds. Model roles classify notes, performance controls,
registration, transport, synchronization, guidance, auxiliary functions or
unknowns. Rejected/unselected assignments cannot produce output. Explicitly
selected hypotheses remain experimental interpretations. Unknown, print, damage
and guidance observations cannot silently become sounding notes. Every observed
feature in the interpreted programme is included or explicitly excluded.

**MMIC-06 — native actuation and exports.** Preserve gates, impulses, latches and
continuous envelopes with roles, source features, clocks, values and units.
Latch state and commands are explicit. Physical engagement, actuator command and
acoustic/export duration are distinct. An impulse has no measured note-off.
Native-only output is conforming: MIDI is optional.

Each selected SMF binding names role, message, channel, target/controller, clock,
rounding, initial/reset state and duration policy where applicable. Validation
MUST connect role → binding → native signal → exact SMF messages. Sustain uses
CC64; Soft Pedal uses CC67. Unknown functions need explicit model-qualified
bindings. A mutually consistent sidecar/MIDI substitution cannot bypass the
selected binding. A loss/assumption report accompanies every MIDI export.
[MIDI controller definitions](https://midi.org/midi-1-0-control-change-messages).

The initial binding supports SMF types 0/1, PPQN, an explicit fixed initial tempo,
note messages and ordinary CC0–119. Wire channels are 0–15. Simultaneous commands
are ordered by tick, command, channel, target and value; note-off precedes note-on.
Tick rounding is nearest, ties to even. SMPTE, variable tempo, SysEx, MPE,
channel-mode and implicit tuning require another declared binding. Preserve the
native data and report unsupported processing instead of inventing an export.

**MMIC-07 — geometry and traversal.** Coordinates bind topology, origin, face/
orientation, direction, units and domain. Periodic coordinates use normalized
principal positions, signed turns and consistent seam flags. A point MUST coincide
on every applicable axis. Directed intervals have positive extent. Cylindrical
coordinates include axial units/domain. The complete, ordered helical reader path
MUST cover the programme/reader domain and intersect interpreted features.
Part identity, sequence, faces, joins and incomplete regions are retained.
Segmented stops/reversals or unresolved paths may be documented; the current
reference algorithm reports their execution as unsupported.

**MMIC-08 — timing.** Piecewise-linear calibrated/estimated/assumed anchors explicitly
bind coordinate units, seconds, uncertainty, interpolation, forbidden extrapolation,
delay and numeric tolerance. Anchor ordering agrees with transport direction.
Every supported carrier-derived signal MUST match the recomputed engagement time.
Per-track offsets and units belong to the hashed model roles. They apply to every
envelope sample as well as its onset. Envelope samples follow traversal direction
and produce increasing event times during forward or reverse playback.
MIDI messages match the declared PPQN/tempo/rounding policy. Changing 3 seconds to
300 seconds cannot leave unchanged events conforming. Uncalibrated execution is
unsupported; a claimed complete clock/path that fails to cover an emitted event
is invalid. Synthetic assumed clocks are not historical calibration.

**MMIC-09 — evidence and reproducibility.** Evidence names exact source/locator,
scope, measured/estimated/assumed/synthetic/unknown basis, responsible core Agent
and review status. Optional exact source snapshots/fragments remain byte pinned.
Execution names its core Activity and fixed code/environment/model artifacts.
Research accuracy requires separately qualified references, metrics and reviews;
structural validity is not an empirical accuracy result.

**MMIC-10 — playback and comparison.** Physical, simulated and unknown recordings
are distinct. A physical take requires instrument, carrier state/programme,
operator, protocol, conditions and recording identity. A known synthetic asset
cannot masquerade as a physical take. Comparison binds independent inputs,
exact alignment bytes, ordered anchors, domain, one-to-one event pairs, explicit
unmatched events, tolerance and recomputed coverage/residuals. No automatic
ground-truth flag is accepted. Corrections name prior/replacement interpretations,
exact prior and replacement interpretation/event targets, agent, evidence and
matching changed value fields, retaining immutable originals.

**MMIC-11 — generation and fabrication.** Generation binds source instructions,
target model, ambitus, repetition/clearance constraints, material/tool assumptions,
execution, layout and exclusion/adaptation report. The reference algorithm
recomputes linear layout coordinates from supported MIDI notes; unsupported
controls/targets require rejection or exact reported exclusions. No clipping or
silent reassignment is permitted. A layout is first a CarrierDesign. Actual
fabrication separately binds fixed design, activity, physical carrier/state and
inspection bytes. Intended dimensions are not substituted for inspected geometry.
Synthetic fabrication fixtures test this structure; they claim no real production.

**MMIC-12 — levels.** Documentation is required for all claims. Decoding adds a
selected complete model, fixed inputs/native output and validated optional exports.
Comparison additionally requires decoding and qualified independent alignment.
Generation adds source/model/layout/report lineage and does not require historic
carrier decoding. Each level has its own exact capability IRI. A processor MUST
declare its implemented role/topology/message coverage.

**MMIC-13 — registry and materialization.** Use exact locally trusted schema,
context, module, SHACL and catalog hashes. Complete transitive asset dependencies
belong to the selected profile's group closure. A partial bootstrap retains the
same manifest bytes and reports unmaterialized capabilities; documentary checks
may be separately reported as passed. Preservation closure still embeds every
manifest realization, including unselected ones.

**MMIC-14 — reports.** Distinguish core validity, MMIC validity/invalidity,
unsupported execution, unmaterialized capability and access-unavailable inputs.
Reports name validator/version, input hash, exercised requirements and effective
limits. Descriptor-only checking cannot claim materialized MMIC validity.
The JavaScript consumer is a second implementation for selected reference traces,
not a complete conformance validator or an independent human standards review.

**MMIC-15 — safety and rights.** Processing uses a trusted isolated worker, never
incoming code. Network resolution is disabled. Effective limits are 8 MiB per
parsed domain asset, 32 JSON levels, 50,000 records, 100,000 SMF events, 250,000 RDF triples,
32 MiB worker asset snapshot, 64 MiB request and 15-second wall time. A POSIX
512 MiB address-space limit is used where supported; macOS relies on bounded
inputs and wall time. Protected contexts/import catalogs are local. Preserve
core archive path, duplicate-member, decompression and fixity controls. Per-asset
rights apply independently to metadata, images, recordings, code and designs.
Opaque image/audio acquisitions use the core's streamed byte-fixity checks and
availability proofs; their sizes do not consume the domain parse budget. A
declared redaction MUST identify a restricted core realization and omit its bytes
from the carrier. Missing restricted inputs report `access-unavailable`.
Public fixtures contain only original synthetic material; literature and museum
images are cited without redistribution.

## Conformance and operation

```sh
python Tools/vao.py validate path/to/carrier.vao --json
python Tools/vao06.py validate Fixtures/MMIC/1.0.0/roll/preservation-closure --json
python Tools/vao06.py pack path/to/workspace path/to/new-carrier.vao
node Tools/mmic_consumer.mjs path/to/workspace
python -m unittest discover -s tests -p test_mmic.py -v
```

A `valid` transport result does not erase the separate domain status. Require
`mmic.status == "valid"` and the requested level result for full MMIC conformance.
Bootstrap partial results are intentional, and a processor does not fetch assets
without a separately governed acquisition decision. RDF tooling uses the optional
`rdf` dependencies; the core/JSON validator does not require an RDF engine.
The domain API assumes the core manifest and carrier fixity have already passed.
Opaque availability proofs are produced only by that trusted core verification.
Direct domain or RDF checks do not replace complete core/carrier validation.

Candidate-to-stable transition creates new immutable specification/profile IDs,
manifests and carriers. Preserve physical and unchanged exact-byte realization
identities; never rewrite published 0.5 files. External maintainer review,
publication, deployment and resolver changes are separate operations.

## Informative modelling sources

These sources inform the separation of observations, reading mechanics, actuation
and interpretation. Their object-specific measurements do not set universal model
values; the conformance fixtures use explicitly synthetic assumptions.

- Judith Kemp, ed., *Digitising Piano Rolls: History – Foundations – Methods*,
  Deutsches Museum Studies 17 (2026), ISBN 978-3-948808-38-9. Robinson p. 59,
  Phillips pp. 69–70, Stahnke pp. 77–79 describe reading and interpretation stages.
  [Publisher PDF](https://www.deutsches-museum.de/assets/Verlag/Download/Studies/Studies_17_download.pdf).
- [Stanford Piano Roll Archive MIDI specification](https://supra.stanford.edu/midi-spec/)
  distinguishes raw proof and expressive outputs. Preserve its source convention
  through qualified inputs; select explicit destination bindings before export.
- Paul Ehrlich, [US290672A](https://patents.google.com/patent/US290672A/en)
  (25 December 1883), Figs. 4/6: perforated disk and interchangeable parts;
  [US546133A](https://patents.google.com/patent/US546133A/en)
  (10 September 1895), Figs. 1–5: raised tongue/projection variants.
- Johan Norrback, *The Pinned Barrel as Music Archive* (2019), pp. 10–11, 13–14:
  [University publication](https://gupea.ub.gu.se/server/api/core/bitstreams/521b8423-b4e5-4c76-b17e-4260fbac4d88/content)
  describes multi-lap and axial movement in the studied Strand barrels.
- [MIDI Association controller table](https://midi.org/midi-1-0-control-change-messages)
  supplies the meanings used for CC64 sustain and CC67 soft pedal.

Third-party publications and museum images are linked, not bundled. Structural
conformance does not authenticate an attribution, calibrate a historical reader
or certify an instrument's physical performance.
