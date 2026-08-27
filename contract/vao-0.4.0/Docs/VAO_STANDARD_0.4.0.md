# Virtual Acoustic Object (VAO) Standard 0.4.0

- Status: final 0.4.0 specification
- Format version: `0.4.0`
- Public release date: 2026-08-27
- DOI: `10.5281/zenodo.22122774`
- Change controller: VAO project, initially represented by responsible editor Dominik Ukolov
- Provisional media type: `application/vnd.modavis.vao+zip`
- Recommended extension: `.vao`
- Version namespace: `https://w3id.org/modavis/vao/0.4.0/`

## 1. Status and conventions

This document defines the final VAO 0.4.0 specification. Publication or registration status does not change the conformance meaning of a document that explicitly claims `formatVersion: "0.4.0"`, and no institutional endorsement is implied.

The key words **MUST**, **MUST NOT**, **REQUIRED**, **SHALL**, **SHALL NOT**, **SHOULD**, **SHOULD NOT**, **RECOMMENDED**, **NOT RECOMMENDED**, **MAY**, and **OPTIONAL** are to be interpreted as described in [BCP 14](https://www.rfc-editor.org/info/bcp14) when, and only when, they appear in all capitals.

Examples and notes are informative unless explicitly identified as normative.

### 1.1 Normative artifacts and precedence

The versioned specification bundle contains:

- this document, for data-model and processing semantics;
- the manifest and descriptor JSON Schemas, for JSON structure and datatypes;
- [VAO_CONFORMANCE_0.4.0.md](VAO_CONFORMANCE_0.4.0.md), for conformance roles and validation order;
- claimed profile documents, for profile-specific requirements;
- the JSON-LD context, RDF vocabulary, and SHACL shapes, for the linked-data projection only;
- [SECURITY_CONSIDERATIONS.md](SECURITY_CONSIDERATIONS.md), for normative processor safety and privacy requirements;
- `Schemas/vao-release-bundle-0.4.0.json`, for artifact fixity.

The JSON Schemas control syntactic validity. This document and an applicable profile control semantic validity. A package MUST satisfy both. The linked-data artifacts do not weaken core JSON conformance. Reference software is informative: a defect in a tool does not redefine the standard.

Any contradiction between normative artifacts is an erratum and MUST NOT be resolved by silently choosing the less restrictive interpretation. Implementers SHOULD report it and preserve the original bytes pending clarification.

## 2. Purpose and scope

VAO exchanges a scientific virtual representation of a musical instrument or another acoustic object. A release can describe exact audio, images, video, geometry, depth, motion capture, event streams, scores, annotations, acoustic responses, observations, physical topology, instrument state, interaction behaviour, renderer expectations, derivation, rights, consent, and discovery metadata.

VAO is an integration, exchange, and preservation envelope. It does not replace media, research-object, repository, or domain standards. A VAO realization binds exact bytes in formats such as AES69-SOFA, ADM, WAVE, FLAC, glTF, MEI, MIDI, IIIF, HDF5, netCDF, or Zarr; the VAO graph states what those bytes represent, how they were produced, how they relate, and under which conditions they may be used.

VAO does not define a renderer executable, repository service, ontology-reasoning regime, cryptographic trust infrastructure, or rights decision engine. Implementations may supply these capabilities under explicit local policy.

## 3. Core concepts

### 3.1 Semantic release

A **semantic release** is an immutable manifest together with the exact realizations it identifies, whether embedded or remotely distributed. Its identity is independent of a filename, ZIP file, repository deposit, or renderer.

### 3.2 Logical asset and realization

A **logical asset** is an intellectual or functional unit, such as a source recording, mesh, score, calibration certificate, or event log. A **realization** is one exact byte sequence representing a logical asset. Two encodings, resolutions, edits, or derivatives are different realizations even when they describe the same logical asset.

### 3.3 Distribution and materialization

A **distribution** tells a processor where exact realization bytes may be acquired. **Materialization** acquires and verifies those bytes. A location, filename, DOI, or server checksum is not realization identity; the manifest byte size and SHA-256 are authoritative.

### 3.4 Asset group

An **asset group** is a declared delivery unit with quality, availability, dependency, selection, capability, and cache semantics. Group completeness means the carrier embeds every realization in the group and all recursively required groups.

### 3.5 Carrier

A **carrier** is a transport container or workspace that embeds the manifest, a carrier descriptor, and zero or more exact realizations. A semantic release may have multiple carriers with different embedded subsets without changing the release.

### 3.6 Profile and capability

A **profile** is a versioned set of additional requirements. A **capability** is an atomic feature that an implementation may need to satisfy. Profiles are embedded in `profiles` or `materializableProfiles`; their IRIs also occur in `conformsTo` when claimed.

## 4. Versioning and immutable identifiers

A VAO 0.4.0 manifest MUST contain:

```json
{
  "$schema": "https://w3id.org/modavis/vao/0.4.0/schema/manifest.json",
  "@context": ["https://w3id.org/modavis/vao/0.4.0/context.jsonld"],
  "type": "VirtualAcousticObject",
  "formatVersion": "0.4.0"
}
```

The immutable VAO context IRI is the first context. Additional contexts MAY follow but MUST NOT remap VAO terms in a way that changes the normative JSON meaning. The canonical context marks its terms protected; a linked-data processor MUST reject a later context that attempts to redefine them. Network-independent conformance requires every additional context to be locally pinned and reviewed. Moving aliases such as `latest` MUST NOT replace versioned schema, context, profile, or vocabulary IRIs in preserved releases.

`release.id` identifies the immutable release. `release.revision` is a non-negative revision number within the publisher's release family. `release.contentVersion` is the publisher's human-facing version. `supersedesReleaseId` creates release lineage and never makes the earlier release mutable. A migration records the original exact manifest digest in `migratedFromManifestSHA256`.

Identifiers MUST be absolute `urn:`, `http:`, or `https:` identifiers without whitespace. All declared identifiers in one manifest MUST be globally unique unless a schema explicitly defines a value as an external reference rather than a declared record.

Every field named `*Id` or `*Ids` denotes a local declared-record reference except `scoreElementId`, `selectionSetId`, `softwareHeritageId`, `supersedesReleaseId`, and `variantSetId`, whose schemas define external/local tokens or cross-release identity. Local references MUST resolve and MUST satisfy the record class stated by this standard/profile. External ontology, registry, and protocol identities use explicitly IRI-valued fields such as `types`, `crs`, `predicate`, `observedProperty`, `standard`, classifications, and external identifiers; processors MUST NOT accept an unresolved local reference merely because it is syntactically an absolute IRI.

## 5. JSON processing model

Manifest and descriptor files MUST be strict UTF-8 JSON objects. Processors MUST reject:

- invalid UTF-8;
- a byte-order mark;
- duplicate object member names;
- `NaN`, positive/negative infinity, or other non-JSON numeric tokens;
- values that fail their Draft 2020-12 JSON Schema;
- unknown members in objects whose schema sets `additionalProperties: false`.

For VAO conformance, every JSON Schema `format` keyword is an assertion, not
annotation-only metadata. A validator MUST enable Draft 2020-12 format
assertion and reject values that fail a declared format such as `uri`.

Object member order is not semantically significant. Array order is significant unless a field is explicitly defined as a set by its schema or context. An empty required registry means that no records of that class are asserted; it does not imply that such records do not exist in reality.

The carrier descriptor hashes the **exact manifest bytes**, not a parsed and reserialized equivalent. A processor MUST preserve those bytes for fixity verification. VAO does not require one serialization layout for the manifest, although the reference writer uses sorted, indented UTF-8 JSON with one final line feed.

For cross-language interoperability, VAO numbers use finite IEEE 754 binary64 semantics and JSON integers are restricted to the exactly interoperable range `-(2^53-1)..2^53-1`. A non-zero decimal token that underflows to binary64 zero and a token that overflows to infinity are invalid. Strings and property names contain Unicode scalar values only; escaped unpaired UTF-16 surrogates are invalid. Fixed-width hexadecimal strings carry larger bit fields, such as random-generator state/stream values. Exact rational structures are used where division must remain exact. A writer MUST NOT imply more numerical precision than this contract supplies; higher-precision or raw scientific arrays belong in an exactly identified realization with an explicit external format, while the manifest records a supported summary and uncertainty.

Conformance-trace digests are different: they use the [RFC 8785 JSON Canonicalization Scheme](https://www.rfc-editor.org/rfc/rfc8785) as specified in section 17.

All VAO date-time values use an exact-comparison subset of RFC 3339 with an explicit known UTC offset, seconds `00` through `59`, and zero to 18 decimal fractional-second digits. The unknown-local-offset form `-00:00` and leap-second lexical form `:60` are invalid. Ordering applies the offset and compares the complete decimal fraction without binary floating-point or microsecond rounding; lexical comparison is conforming only in the limited cases where RFC 3339 guarantees the same ordering. Unless a field explicitly says otherwise, an end equal to its start is permitted for an instantaneous record; half-open intervals that require duration use a strictly later end. A leap-sensitive observation is represented on a Timebase with an explicit time scale and synchronization/discontinuity evidence rather than by discarding or normalizing the leap second.

## 6. Root manifest contract

The complete property contract is in `vao-manifest-0.4.0.schema.json`; the generated [schema reference](VAO_SCHEMA_REFERENCE_0.4.0.md) lists every object and required member. The root contains:

- identity and version fields;
- `release`, title/description, creation/modification dates, profiles, and MODAVIS binding;
- semantic `entities` and `relations`;
- optional `acoustics`, `playable`, `interactionModel`, and `captureDocumentation` records;
- required closed `scientific`, `multimodal`, `physicalSystem`, `runtime`, and `discovery` registries, which may be empty;
- logical assets, exact realizations, distributions, repository bindings, asset groups, rights, and integrity;
- an optional IRI-keyed extension object.

`createdAt` describes initial creation of the semantic object. `modifiedAt` describes the immutable release being serialized and MUST NOT be changed in place after publication; an update creates another release.

`primaryEntityId` MUST resolve to an Entity. Each `focusEntityIds` value MUST resolve. At least one Entity, logical asset, realization, asset group, and rights record is required.

## 7. Profiles and capability negotiation

Every VAO 0.4.0 manifest MUST embed and claim:

- `https://w3id.org/modavis/vao/profile/core/0.4.0`;
- `https://w3id.org/modavis/vao/profile/dynamic-delivery/0.4.0`.

A non-empty profile-specific registry requires its corresponding embedded profile record and `conformsTo` claim. A profile record declares its exact `id`, `version`, and `requiredCapabilities`. A materializable profile additionally declares the asset groups that must be acquired before the profile can be satisfied.

Core records MUST include the `core-graph` and `fixity` capabilities. Dynamic Delivery records MUST include `immutable-release` and `carrier-mapping`. Scientific, Multimodal, Physical Instrument, Playable, Spatial, and Deterministic Runtime records respectively include their profile's mandatory capability stated in the versioned profile document. An Acoustics record includes at least one applicable controlled acoustic capability and also claims Spatial. Additional capabilities are permitted only as absolute IRIs and do not weaken these minima.

A reader that lacks a required capability MUST NOT claim full support for that profile. It MAY still perform lower-level operations—such as fixity validation or metadata display—when it reports the limitation without discarding unknown evidence.

## 8. Entities, relations, and ontology binding

Entities identify instruments, components, spaces, people-as-subjects, interactions, sources, receivers, and other semantic subjects. `kind` provides a closed coarse class; `types` supplies one or more ontology IRIs; localized labels are required. Classifications, external identifiers, and IRI-keyed properties may refine the entity.

Relations link a subject to exactly one object identifier or literal. Status, confidence, scope, evidence, generating activities, and properties prevent an inferred or disputed relationship from being confused with an asserted fact. Rejected and superseded relations remain evidence and MUST NOT be treated as active assertions.

`modavisBinding` records which MODAVIS ontology/mapping informed a release. Its `ontologyStatus` is one of `development`, `released`, or `embedded-snapshot`. A `development` binding is explicit provenance and MUST NOT be interpreted as a stable external dependency. A `released` binding requires version and mapping IRIs. VAO 0.4.0's final co-release binding identifies MODAVIS Ontology Network `0.1.0`, its immutable version IRI `https://w3id.org/modavis/ontology/0.1.0`, and the VAO-owned mapping `https://w3id.org/modavis/vao/0.4.0/modavis-mapping`. The mapping makes only conservative universal claims; VAO manifests use exact MODAVIS instrument and organ term IRIs directly. A vocabulary release digest, when supplied, binds the exact external vocabulary manifest. Core VAO validity remains self-contained in the versioned VAO schemas and semantics.

## 9. Logical assets, realizations, and exact bytes

A logical asset declares its role, subject entities, and realization IDs. Every realization:

- resolves `assetId` to its logical asset;
- has a variant set and quality tier;
- has an IANA-compatible media type string;
- states an exact non-negative `byteSize` and lowercase SHA-256;
- distinguishes source, processed, simulated, inferred, reconstructed, and creative representation status;
- resolves rights and provenance records;
- has typed technical metadata;
- lists its distributions, which may be empty when it is embedded-only.

Filename, media type, repository checksum, ETag, and transport encoding MUST NOT substitute for the required byte size and SHA-256. A processor MUST hash the decoded realization bytes. It MUST NOT hash a ZIP member header, HTTP content encoding, filesystem metadata, or text after newline conversion.

`contentDigests` MAY add SHA-512 or repeat SHA-256. A repeated SHA-256 MUST equal `sha256`. Authenticity envelopes and signatures supplement fixity; they never replace it.

`representationStatus` uses the closed VAO concept scheme. `captured` is direct output of a documented capture/measurement; `authored` is intentionally created content; `converted` changes encoding/container without an asserted substantive derivation; `derived` is processed from identified inputs; `simulated` is generated by an explicit model; `inferred` is estimated from evidence; `reconstructed` recreates missing/earlier state; `redacted` deliberately removes/replaces content; `hybrid` combines more than one of these origins; `undetermined` honestly records that origin cannot be classified. These terms describe provenance class, not quality or truth. A converted, derived, simulated, inferred, reconstructed, redacted, or hybrid realization MUST have provenance adequate to identify its transformation/input basis.

Technical metadata `kind` selects a closed cross-media contract. Media-specific fields describe audio frames/channels/sample format, geometry coordinates and complexity, images/video dimensions and coding, event/sensor encoding, score format, duration, timebase, or trajectory. A technical `timebaseId`, `coordinateFrameId`, or `trajectoryTrackId` MUST resolve to a Timebase, Coordinate Frame, or trajectory Track respectively, even when no other Track cites the realization; a `trajectoryTrackId` Track MUST bind that same realization. Channel labels match channel count. A complete ACN Ambisonics stream has `(order+1)^2` channels in 3D or `2×order+1` in 2D. Geometry unit, handedness, and positive up-axis metadata MUST agree with its Coordinate Frame. An audio-sample or video-frame Timebase rate MUST agree with the exact realization's sample/frame rate; video frame rate may use the same lowest-terms rational representation as a Timebase. Technical claims MUST describe the exact realization, not an unrecorded source.

## 10. Distribution, repositories, and asset groups

A repository distribution identifies an immutable repository record and file under a repository binding. Exact acquisition MUST use a version record/file identity rather than a mutable concept or collection identifier. A pack-member distribution names the exact pack realization, safe member path, and pack-manifest SHA-256.

A repository binding declares repository type, instance, API profile, and resolution policy. Network resolution is OPTIONAL. Implementations MUST be able to validate an embedded preservation closure without network access.

An asset group's `totalByteSize` MUST equal the sum of its direct realization byte sizes. Every `materializesProfileIds` value resolves to an embedded Profile record. Dependencies form an acyclic graph. A fallback group MUST be compatible with the selection set. Cache priority and eviction are delivery hints and MUST NOT change semantic identity.

Materialization MUST:

1. resolve the selected group's transitive dependencies;
2. enforce local network, authorization, redirect, and size policy;
3. acquire into a temporary non-executable location;
4. verify exact byte size and SHA-256 before exposing the file;
5. record a materialization receipt when an auditable workflow is claimed;
6. never rewrite the immutable manifest to record local cache state.

## 11. Rights, consent, ethics, and discovery

Every realization and relevant semantic subject MUST resolve to a rights record. A rights record declares scope, statement, and access; a license IRI is optional because unknown or withheld rights must be representable. Absence of a license or consent MUST NOT be interpreted as permission.

Performer agents, consent records, community authorities, Traditional Knowledge label IRIs, CARE principles, privacy class, embargo, and redaction lineage are explicit. `community-governed` requires at least one authority. An embargo date requires a rationale. Redaction creates a derivative realization and MUST NOT overwrite or misidentify its source.

Discovery metadata is repository-neutral and targets DataCite Metadata Schema 4.7. Creator/contributor IDs resolve to Agents; Agents may carry ORCID/ROR identifiers. ORCID and ROR strings MUST pass their respective check-digit algorithms, but checksum validity alone does not establish ownership, current affiliation, or registry existence. A depositing workflow SHOULD verify identifiers against the authoritative registries and obtain contributor confirmation. Related-identifier relation/resource types use the DataCite 4.7 controlled values; `Other` carries `relationTypeInformation`. Funding, subjects, related identifiers, instrument identifiers, and facility identifiers are explicit. `publisher` and `publicationYear` SHOULD be supplied when a deterministic DataCite projection is intended; a projector MUST request them rather than fabricate repository metadata. A repository projection MUST NOT change creator order, rights, release identity, or exact-byte assertions.

Implementations displaying sensitive records SHOULD minimize disclosure and honor access/consent decisions before dereferencing or previewing content.

## 12. Scientific profile

The Scientific profile is required when any scientific registry is non-empty. It defines typed Agents, Activities, Protocols, Software Environments, Calibrations, Observations, Analyses, Claims, Reviews, and Consents. ORCID identifies only a person Agent; ROR identifies only an organization Agent. A person's institutional affiliation is an `affiliationAgentIds` reference to an organization Agent rather than an ROR attached directly to the person.

Every Software Environment states the exact scope of its primary digest and describes the bytes or declaration covered. `executable`, `source-file`, `source-bundle`, and `environment-lock` identify materially different artifacts and MUST NOT be conflated. `declaration` identifies only the recorded software declaration; it MUST NOT be presented as an executable or source identity. Dependencies are structured records with their own digest, role, scope, and coverage statement. A `source` dependency uses `source-file` or `source-bundle`; an `environment-lock` dependency uses `environment-lock`. Container and model-weight digests remain separate assertions. A reproducibility claim SHOULD additionally preserve all behaviorally relevant code, dependencies, models, configuration, runtime, operating environment, and hardware constraints; a lone entry-point hash does not prove that an execution can be reproduced.

An Activity records time bounds, agents, protocol, exact inputs and outputs, and optional software environment, parameters, environmental observations, and random source. End time MUST NOT precede start time. Its immutable input and output ID sets are disjoint: an in-place transformation receives a new output identity. References MUST resolve to records in the same release or to explicitly external identifiers where the schema permits. Whenever an identified record names `generatedById` or `generatedByIds`, every named Activity MUST list that record in `outputIds`; one-sided provenance links are invalid. When one Activity produces a record consumed by another, the producer MUST end no later than the consumer starts, and the resulting Activity dependency graph MUST be acyclic. Equal boundary instants are permitted because acquisition resolution may be coarser than execution order; the acyclic dependency edge remains authoritative.

An Observation identifies the observed property, feature of interest, result time, activity, protocol, quantity value and unit, status, and optional sensor, calibration, raw/processed realization, uncertainty, sample count, censoring, flags, and outlier policy. It is listed as an output of a `capture`, `measurement`, `processing`, or `simulation` Activity; its Protocol equals the Activity Protocol and its result time falls within the inclusive Activity bounds. A raw-result realization occurs in that Activity's inputs or outputs. A processed-result realization is an Activity output, and one realization MUST NOT be labelled as both raw and processed. When a Sensor is named, observed property and Protocol agree; a calibration declared by that Sensor is explicitly cited. A cited Calibration predates the result, has not expired at result time, and—when a Sensor is named—calibrates that Sensor component's Entity. Units and quantity kinds are IRIs. Original anomalous or contradictory measurements SHOULD remain preserved; Claims and Reviews express interpretation rather than silently changing evidence.

A quantity `value` is a JSON number, non-empty numeric vector, or non-empty rectangular numeric matrix. Its shape is part of the assertion. Boolean values and numeric strings are not quantities. A non-covariance uncertainty is a non-negative magnitude with the same shape as its quantity, except `registration-rms`, which is a non-negative scalar. A `registration-rms` value has its own scalar `unit`; it does not inherit heterogeneous `axisUnits`. Its `method` MUST identify the coordinate/metric space and residual convention in which the scalar RMS was calculated, especially when the registered quantity is geodetic or otherwise has heterogeneous axes. `expanded` uncertainty requires a coverage factor greater than one. Confidence, when supplied, is in `(0, 1]`.

Unit and optional `quantityKind` IRIs are semantic assertions, not proof that an external vocabulary term exists or that a unit is dimensionally compatible with the measured property. A processor MUST NOT claim external-vocabulary or dimensional validation merely because IRI syntax passed. Such a claim requires a pinned vocabulary definition and an explicit compatibility check; a depositing scientific workflow SHOULD perform that check for every quantity and preserve the vocabulary version used.

A covariance uncertainty is a non-empty square, symmetric, positive-semidefinite matrix. For a scalar quantity it is 1×1; for a vector/matrix quantity its dimension equals the number of flattened components. `unit` denotes the common component unit, so covariance cell `(i,j)` is expressed in the product of the corresponding component units. `axisUnits` supplies ordered component units for heterogeneous axes and covariance cells use `axisUnits[i] × axisUnits[j]`. Symmetric cells, which have the same product unit, use a pair-relative `10^-12 × max(abs(Cij), abs(Cji))` tolerance. Variances MUST be non-negative; a zero variance has exactly zero cross-covariance. Positive-variance cells are normalized to a dimensionless correlation matrix before a `10^-12` scale-relative semidefinite test, avoiding comparisons across heterogeneous physical units. Inline covariance dimension is at most 64 and all inline covariances together contain at most 262,144 cells; larger exact matrices belong in an identified domain realization. Uncertainty values characterize the recorded measurement/model result; conformance does not prove that the uncertainty method or distribution is scientifically adequate.

An Analysis binds its activity, inputs, outputs, software environment, parameters, validation evidence, and reproducibility class. Its Activity MUST be `processing`, `simulation`, or `inference`; Analysis inputs/outputs MUST be subsets of the corresponding Activity lists. The Activity declares the same Software Environment and Random Source, and every Analysis parameter occurs identically in the Activity parameter values. Validation IDs are not self-references and occur in the Activity inputs/outputs; evidence used as an input MUST be available by the Activity start, while evidence emitted during the Activity MUST be available by its end. That structural and temporal link alone does not establish independent validation. An output Observation MUST name that Activity, and an output Claim MUST name it as `generatedById`. A random source MUST be a declared runtime/interaction Random Source. `deterministic` MUST NOT name a random source. `seeded` MUST name one. Either claim requires a stated runtime plus one of: an exact container digest; an executable primary identity; a source-file/source-bundle primary identity with an exact environment-lock dependency; or an environment-lock primary identity with an independently hashed source dependency. An environment lock without separate code identity and a source identity without an environment lock are both insufficient. Otherwise the Analysis is `non-reproducible`. These classes concern repeatability under the recorded inputs, parameters, runtime, and environment and do not assert method validity, independent replication, or bit-identical cross-platform output. A result without minimum evidence SHOULD be represented as an unreviewed Claim or source document rather than overstated as a reproducible Analysis.

A Claim has exactly one identifier object or literal, evidence, and epistemic status. Claim evidence is non-self-referential and the Claim-to-Claim evidence graph is acyclic. Evidence for a generated Claim occurs in its generating Activity's inputs/outputs and MUST be available no later than the applicable Activity start/input or end/output boundary; a Claim does not use its own Review as evidence. An `inferred` Claim MUST name an inference Activity. An `accepted` or `rejected` Claim MUST cite at least one Review with the matching decision; a `reviewed` Claim MUST cite at least one assessed Review. Claim-to-Review references are reciprocal: every cited Review targets that Claim, and every Review of a Claim is listed by it. A Review names its reviewer, target, time, decision, and optional rationale; it neither reviews itself nor predates a temporally identified target, including a target made available by an Activity. A Consent records grantor, scope, decision, time, conditions, and optional evidence realization and cannot apply to itself. Observation/metric evidence status remains a quality/provenance classification and MUST NOT be read as peer-review or scientific-truth certification without an explicit review/evidence chain.

PROV-O, SOSA/SSN, QUDT, CRMsci, and CRMdig mappings enrich interoperability but do not relax the closed VAO JSON contract.

## 13. Multimodal timeline profile

The Multimodal profile is required when any timebase, track, synchronization mapping, or annotation exists.

A Timebase defines clock kind, coordinate `unit`, positive `rate`, `rateUnit`, origin, and optional epoch/wrap period. `rate` is either a positive JSON number or an exact positive rational `{numerator, denominator}` whose integers are in `1..2^53-1` and are in lowest terms; an exact rate such as 30000/1001 SHOULD use the rational form. The coordinate/rate-unit pairs `SAMPLE`/`SAMPLE-PER-SEC`, `FRAME`/`FRAME-PER-SEC`, and VAO `midi-tick`/`midi-tick-per-quarter-note` are fixed. A wall-clock Timebase requires an RFC 3339-subset epoch and an absolute `timeScale` IRI; an external-timecode Timebase also requires `timeScale`. VAO supplies identifiers for UTC, TAI, GPS, POSIX, and SMPTE timecode, while permitting a precisely defined external scale. Implementations MUST NOT treat these scales as interchangeable. UTC leap behaviour or another clock discontinuity that affects conversion MUST be represented in synchronization segments; a leap-sensitive coordinate MUST NOT be silently coerced to POSIX time.

A Track binds one exact realization—not merely a logical asset—to one declared Timebase and modality. Modality MUST be compatible with the realization's technical kind; any technical timebase or coordinate frame MUST equal the Track value. Audio sample rate and video frame rate equal the Timebase rate exactly under the declared binary64 or rational representation; an undocumented tolerance does not make two clocks identical. A spatial Track SHOULD identify its coordinate frame. `continuity` is exactly `continuous`, `segmented`, or `sparse`; sampling/event semantics come from modality and exact technical metadata, not additional continuity values.

A synchronization mapping relates two distinct timebases using ordered, non-overlapping, half-open source segments:

```text
target = source × scale + offset
```

`sourceStart` and `sourceEndExclusive` are in the source Timebase coordinate unit; `scale` is target-coordinate units per source-coordinate unit; and `offset` is in the target coordinate unit. Each segment records scalar residual uncertainty in the target coordinate unit and explicitly declares `discontinuityAfter`, including `none`. Adjacent segments marked continuous have touching source bounds and exactly equal mapped target boundary values when every safe integer/binary64 operand is interpreted as its exact rational value; a source gap or target jump requires an explicit non-`none` discontinuity. Mapping `jitter`, when present, is likewise a scalar uncertainty in the target coordinate unit. The mapping names a method-compatible Activity and that Activity lists the mapping as an output. A global offset is a one-segment special case. A processor MUST NOT interpolate across an explicit reset, dropout, pause, or unknown discontinuity.

An Annotation targets a track using temporal, spatial-fragment, SVG, event, or score selectors and records motivation, body, creating Agent, creation time, and provenance Activity. The Activity kind MUST support authoring/annotation/processing/inference, MUST list the Annotation as an output, MUST include the creating Agent, and MUST contain the creation instant. `start` and `endExclusive` occur together and form a non-empty half-open interval in the target Track's Timebase coordinate unit.

IIIF Canvas, Web Annotation, and MEI identifiers may be projected from these records; the VAO release retains exact realization identity and synchronization evidence.

## 14. Spatial and acoustics profiles

The normative details are in the [Spatial profile](VAO_SPATIAL_PROFILE_0.4.0.md) and [Acoustics profile](VAO_ACOUSTICS_PROFILE_0.4.0.md).

Coordinate frames state dimension, coordinate type, unit or ordered axis units, handedness, axes, optional CRS, parent transform, registration uncertainty, and generating Activity. Parent links are acyclic and join equal dimensions. `transformToParent` is an invertible, row-major 4×4 affine matrix applied to a homogeneous column vector, `p_parent = M × p_child`; translation occupies indices 3, 7, and 11 and the last row is exactly `[0, 0, 0, 1]`. A linear coefficient from child axis `j` to parent axis `i` has the dimensional meaning `parentUnit[i]/childUnit[j]`, and translation row `i` is in `parentUnit[i]`; this remains true when one scalar frame unit supplies every axis. Two-dimensional coordinates use `[x, y, 0, 1]`; the six coefficients that mix X/Y with Z or move Z from zero (`M02`, `M12`, `M20`, `M21`, `M22-1`, `M23`) have absolute error at most `10^-12`. The 2×2 or 3×3 linear part is normalized by its largest absolute coefficient and MUST have an infinity-norm reciprocal condition estimate greater than `10^-12`; this scale-invariant rule rejects singular and severely ill-conditioned transforms without rejecting a well-conditioned change of scale. Transforms MUST NOT be applied across frames without an explicit path.

A geodetic frame states a CRS and one ordered unit IRI per axis. Pose components and `axisUnits` follow the authoritative CRS axis order exactly; a consumer MUST NOT silently substitute an assumed longitude/latitude, latitude/longitude, or generic X/Y order. An alternate order requires an explicitly identified frame/conversion rather than an undocumented array permutation. The geodetic frame is a root with non-applicable handedness/up/forward directions and does not participate directly in an affine parent edge. A documented Activity converts geodetic positions into an appropriate projected/local Cartesian frame before affine transforms, orientations, or rendering.

A Pose identifies an Entity in a target `frameId` with a position whose length equals the frame dimension and optional extent/uncertainty/configuration/state/time validity/trajectory. Extent has the same dimension and contains only non-negative values. Any orientation additionally identifies `localFrameId`, and an unoriented Pose omits that unused field; local and target frames are Cartesian/projected, have equal dimensions, exactly equal units, and the same applicable handedness. Scale changes and reflections therefore require an explicit frame transform rather than being hidden in a rotation. A 3D orientation is the active Hamilton unit-quaternion rotation in `x,y,z,w` order from local-frame numeric coordinates into target-frame numeric coordinates and is conformant exactly when `abs(x²+y²+z²+w²-1) <= 10^-9`. Quaternion trajectories use `step` or `spherical-linear`; the latter linearly interpolates position and applies shortest-arc SLERP to orientation, treating `q` and `-q` as equivalent. A 2D orientation is the active counter-clockwise angle in radians from the local numeric X axis into the target numeric X–Y plane and cannot use a quaternion; `linear` follows the shortest signed angular difference, with an exactly half-turn tie represented as `-π`. `cubic` applies only when orientation is absent. Orientation is not asserted directly in a geodetic frame. Non-`none` interpolation requires `trajectoryRealizationId` to identify one exact trajectory, motion-capture, or sensor-data realization whose technical `coordinateFrameId` equals the Pose target frame and whose Timebase defines sample coordinates; `none` forbids that unused reference, and a logical asset with several possible realizations is insufficient. A listener trajectory is present exactly in `trajectory` mode and applies the same exact-realization and frame-agreement rule.

Geometry bindings connect semantic subjects to logical assets and type-correct optional selectors. Material models bind band axes and measured or modelled acoustic properties with representation status and provenance. Band centres are strictly ascending; paired edges bracket their centres and do not overlap. The explicit centre/edge arrays are the computational authority. A `scale` label classifies the organization only and MUST NOT by itself be interpreted as conformance to an IEC, ISO, ANSI, or other named band definition; intended standards conformance requires an exact standard/edition and method in the surrounding protocol/evidence. Every band-valued property/uncertainty has exactly the axis length. Absorption/scattering coefficients are in `[0,1]`, transmission loss is non-negative, and a supplied physical thickness is strictly positive. Uncertainty is property-specific: `absorptionUncertainty` and `scatteringUncertainty` use QUDT `UNITLESS`, while `transmissionLossUncertainty` uses `DeciB`; a generic uncertainty cannot ambiguously cover several properties. VAO does not infer missing transmission/scattering properties from absorption or claim an energy-conserving boundary without the additional incidence, phase, and impedance evidence needed to justify it.

Measurements identify source/receiver/pose/configuration/state and optional space/transmission topology. Source and receiver Poses describe the corresponding Entities and have a common frame root. Response sets bind measurements to exact response assets and optional delays, calibration, interpolation, and quality evidence. Exact impulse-response metadata covers every Response Set measurement exactly once and does not reuse a `(dataIRIndex, channelIndex)` address. Interpolation fallback links are acyclic; a fallback policy names a fallback set, other policies do not; seeded determinism names a seed; and method `none` rejects outside-domain queries. A neural field records its exact model, non-empty training and validation evidence, quality metric, and determinism. A `learned` Response Set uses a neural-field or hybrid contract and supplies all of that evidence. Metric sets identify standard/edition/method, exact inputs, Entity subjects, band axis, dimension-matched values, units, status, and provenance. Optional metric uncertainty uses the structured uncertainty contract, has the band-vector shape and the metric's component unit, and retains its kind, method, confidence or coverage factor, and covariance where applicable. Merely naming an ISO or other standard MUST NOT be interpreted as a conformity certificate.

Audio scenes bind entities, media assets/channels, optional content Timebase, and matching Poses in a coordinate frame. A channel selection on a logical asset applies to every exact audio realization of that asset: all such realizations MUST have one channel count and every selected index MUST exist, or the binding is ambiguous. Render configurations identify strategy, exact inputs, listener mode, required features, valid-domain policy, fallbacks, transitions, levels of detail, and renderer requirements. Fallback graphs are acyclic, and the `fallback` outside-domain policy requires an explicit fallback. A renderer MUST honor outside-domain and fallback policy rather than silently extrapolating.

## 15. Playable, interaction, and capture profiles

Playable data distinguish exact signal regions, loop sets, tuning maps, perspectives, sample variants, and sample mappings. Frame intervals are zero-based and half-open. Regions MUST lie within the referenced audio realization. A mapping's control key, source key, actuator key, and sounding key are distinct meanings; implementations MUST NOT assume a MIDI key number is sounding pitch.

Evidence status and source accompany authored, embedded, documented, and algorithmic playback metadata. Algorithmic/inferred records require generating evidence. Rejected, superseded, or unreviewed inferred records MUST NOT be used as accepted playback mappings.

The interaction model separates:

- controls and typed events;
- protocol bindings (MIDI 1.0, MIDI 2.0 UMP/MIDI-CI, OSC, host, electrical, or custom);
- persistent state and guarded transitions;
- routing and key transforms;
- bounded/timed/stochastic processes;
- timing constraints and transfer functions;
- render selection.

Opening or validating a VAO MUST NOT execute active package content. Actions are declarative. External renderers are identified by capability and software environment and run only under explicit local policy.

Zero-delay `copies` and `transposes` routing edges MUST be acyclic. A cycle is permitted only when every cyclic path contains an explicit delay constraint. A stochastic Process uses stochastic ordering and declares a Random Source and distribution; a non-stochastic Process MUST NOT do so. Process termination MUST be bounded by completion, control release, maximum iterations, duration, or external cancellation as declared. Only `maximum-iterations` supplies `maximumIterations`, only `duration-bound` supplies `durationConstraintId`, and only control-release/external-cancel supplies `cancellationControlId`.

MIDI 1.0 bindings state numbering bases. MIDI 2.0 bindings additionally require UMP group, function block, message type, data resolution, and JR timestamp handling; optional per-note controller, MIDI-CI Profile, and Property Exchange IRIs preserve richer semantics.

Capture documentation records instrument state, event/audio frame alignment, take sets, and derivation operations. A derivative realization MUST identify its source, ordered operations, and any frame/channel selection. Derivation never changes source bytes.

## 16. Physical instrument profile

The Physical Instrument profile is required when physical-system registries are non-empty. Components reference semantic Entities and form an acyclic parent hierarchy. Each component's `portIds` is exactly the set of Ports that name it as `componentId`. Ports have direction, signal kind, and optional quantity kind. Connections link an output/bidirectional source to an input/bidirectional target, resolve both Ports, and describe signal, energy, material, or mechanical coupling. A Connection marked `bidirectional: true` requires both endpoints to be bidirectional Ports.

Sensors identify observed properties, output ports, protocols, and optional calibrations. Actuators identify acted-on properties, input ports, protocols, and optional transfer functions. State bindings connect declarative interaction state to a component as commanded, observed, estimated, or simulated state and may cite an Observation.

Topology records do not replace semantic entity relations; they provide a systems view with resolvable links and measurable interfaces.

## 17. Deterministic runtime profile

`interactionModel.executionSemantics` and `runtime.executionSemantics` MUST be equal. VAO 0.4.0 fixes the following event contract:

1. input timestamps are processed in ascending order;
2. equal timestamps order by descending event priority, ascending event-type ID, then ascending `sequence`;
3. guards read one pre-event state snapshot;
4. matching transitions order by descending transition priority then ascending transition ID;
5. actions order by ascending execution-group string, the transition rank from rule 4, then action array index;
6. one input event runs to completion before the next;
7. re-entrant and late events follow the declared policies;
8. each input event's run-to-completion cycle stops at `maximumMicrosteps`;
9. a live host's voice allocation follows the declared policy and bound where voice creation/lifecycle applies.

All string comparisons in this execution contract use ascending UTF-8 byte order over valid Unicode scalar strings, without locale or case folding. This is equivalent to Unicode scalar-value order for conforming strings. Different writes to one state variable during one input event are a conflict. All conflicting transitions MUST declare the same policy. `reject` rejects the event; `priority` keeps the highest-ranked transition's write; `last-event-wins` keeps the last write in the action order above; `merge-disjoint` permits writes to different targets but rejects different writes to the same target. Repeated identical writes are not a conflict. One microstep is consumed for each transition action, each expanded Process action, and each stochastic generator draw, including every rejected redraw. The counter resets before each input event; it is not a lifetime trace counter. Retrigger, cancellation, release, iteration, duration, routing delay, live late/re-entrant arrival, and voice lifecycle remain explicit; a conforming live host MUST apply them, but the offline trace verifier has the narrower scope defined below. A host MUST NOT substitute an undocumented policy when deterministic conformance is claimed.

A Renderer with `deterministic: true` MUST meet the same exact-identity/runtime threshold as a deterministic Analysis. A declaration-only name/version record, an environment lock without separate code identity, or source without an environment lock cannot support that claim. Renderer determinism is bounded by the advertised capabilities and does not imply bit-identical media, perceptual equivalence, or scientific validity unless those outputs and comparison criteria are separately specified and tested.

### 17.1 Random sources

Random source IDs are part of release identity. `pcg32` uses a 64-bit lowercase-hex seed and a stream in `0..2^63-1`, encoded as exactly 16 lowercase hexadecimal digits with a leading nibble in `0..7`. Initialization and output use PCG XSH RR 64/32. The stream is part of PCG state selection and MUST NOT be converted through an imprecise JSON number.

`xoshiro256-star-star` uses exactly one non-zero 256-bit lowercase-hex seed split into four big-endian 64-bit words. It has no `stream` member: inventing a stream transform would define a different generator. State transition and star-star output follow the published xoshiro256** algorithm. When a binary64 uniform value is needed, a processor uses `(word >> 11) × 2^-53`, yielding `[0,1)` without rounding the maximum word to `1.0`.

For a stochastic Process, the candidate sequence consists of its direct `actions` in array order followed by its direct `childProcessIds` in array order. The Process draws first and selects exactly one candidate. A selected direct action is emitted; a selected child is then expanded recursively. Unselected children are not expanded and consume no random words. A non-stochastic Process serializes its direct actions first and then expands each child depth-first in declared order; this serialization order does not turn `simultaneous` actions into different logical times.

Uniform stochastic selection uses rejection sampling over raw unsigned generator words, without binary floating point. For `N` candidates and word width `b`, set `R = 2^b` and `L = R - (R mod N)`; redraw while `W >= L`, then choose `floor(W / (L/N))`. A categorical distribution maps zero-based candidate-index strings to positive integer weights; omitted indices have zero weight and the total `T` is in `1..2^53-1` and no greater than `R`. Set `L = R - (R mod T)`, redraw the high tail, set `ticket = floor(W / (L/T))`, and choose the first cumulative weight strictly greater than `ticket`. This produces exact equal/proportional probabilities rather than a modulo or floating-point bias. An out-of-range key or all-zero distribution is invalid.

### 17.2 Conformance traces

A trace binds initial state, ordered input events, expected final state, emitted events, and render-binding IDs. Its SHA-256 input is the RFC 8785 canonical byte sequence of:

```json
{
  "initialState": {},
  "inputEvents": [],
  "expected": {
    "state": {},
    "emittedEvents": [],
    "renderBindingIds": []
  }
}
```

The actual values replace the example values; absent `initialState` is canonicalized as `{}`. A deterministic-runtime processor MUST verify the stored digest and execute every claimed trace. Input events MUST have a unique `(timestamp, priority, eventTypeId, sequence)` ordering tuple. Initial-state entries and all event/action values obey their declared domains; expected state covers every State Variable exactly once. The offline verifier covers ordered, already-available input events, guards, transition state/actions, immediate Process expansion and stochastic selection, emitted records, and render-binding selection. Process actions are recorded as requests rather than applied as transition effects; their record preserves the actual source Process, originating transition, operation, target, timestamp, and any value/key offset. Explicit render-selection actions retain action order; afterwards, matching Render Bindings are considered in manifest array order, and duplicate selected IDs retain their first occurrence. An expanded Process and every selected descendant MUST use `terminationPolicy: "completed"`, have no timing constraints, and use kind `one-shot`, `compound`, or `stochastic`; every delayed transition or Process action is rejected. The verifier does not simulate live arrival, queue timing, delay scheduling, sustained/repeating/sequenced lifecycle, voice creation/lifecycle, media rendering, or bit-identical audio because 0.4.0 defines no trace scheduler/clock advance for those operations. Schema validation alone is insufficient. Values outside the RFC 8785/I-JSON numeric domain cannot form a conforming trace.

## 18. Chunking, Merkle roots, and authenticity

Chunking strategies are fixed-size, content-defined, external-index, Zarr, or pack-shard. Inline chunks MUST:

- be indexed consecutively from zero;
- be ordered by index;
- begin at offset zero and cover the realization contiguously with no gap or overlap;
- end exactly at `byteSize`;
- carry a supported lowercase digest.

An external index is itself an exact realization. Range-addressable use MUST verify each received chunk before exposing it. Whole-realization SHA-256 remains required after complete materialization.

For an inline Merkle tree, all chunk digests use the root algorithm. A leaf is `H(0x00 || chunkDigestBytes)`. An internal node is `H(0x01 || left || right)`. An unpaired node is duplicated. The final lowercase hexadecimal digest is `merkleRoot.value`.

An authenticity or signature envelope MUST be a referenced realization with its own fixity and rights. Trust in its signer, certificate, timestamp, or transparency log is local policy. A valid signature does not make unsafe or unauthorized content acceptable.

## 19. Carrier and workspace format

### 19.1 Media type and layout

A packed carrier is a ZIP file conforming to the `+zip` structured syntax. Its first entry MUST be:

```text
name: mimetype
compression: stored
bytes: application/vnd.modavis.vao+zip
```

There is no byte-order mark, whitespace, or final line feed in `mimetype`. The only permitted regular-file entries are:

```text
mimetype
vao-manifest.json
META-INF/vao-carrier.json
payload/<safe-relative-path>
```

Directory entries under `payload/` MAY occur. Unknown root or `META-INF` entries are invalid in 0.4.0. Exact ZIP entry spelling remains case-sensitive evidence, but no two names may collide after Unicode NFC normalization or after NFC plus Unicode default case folding; this keeps the carrier representable on common case-insensitive filesystems.

### 19.2 ZIP safety requirements

Processors MUST reject:

- absolute names, empty/dot/parent segments, ASCII control/DEL characters, or backslash separators;
- duplicate raw names or names that collide after NFC normalization or NFC plus Unicode default case folding;
- symbolic links and other special-file entries;
- encrypted entries;
- compression methods other than Stored and Deflate;
- missing structural files or a non-first/non-stored `mimetype`;
- carrier contents that exceed declared local entry, byte, recursion, time, or compression-ratio budgets.

Resource-budget values are implementation policy because legitimate preservation packages vary greatly in size. A processor MUST apply finite budgets before decompression and MUST report a budget failure separately from a schema defect where its API permits.

### 19.3 Carrier descriptor

`META-INF/vao-carrier.json` contains the exact release ID, exact manifest byte size and SHA-256, carrier mode, realization-to-payload mappings, and complete group IDs. Paths must be safe `payload/` members and distinct under both NFC and NFC-plus-case-fold comparison. Every payload file MUST have exactly one mapping; every mapping MUST resolve to exactly one manifest realization; byte size and SHA-256 MUST match.

A `bootstrap` carrier MUST embed at least one realization. A `custom` carrier embeds an explicit subset. A `preservation-closure` carrier MUST embed every realization and mark every asset group complete. Declaring a group complete requires all its direct and transitive dependency realizations.

### 19.4 Workspace form

The unpacked workspace uses the same relative layout and exact structural bytes. It MUST contain only regular files/directories and MUST NOT contain links or special files. Validation MUST occur before packing. A conforming writer produces deterministic entry order, timestamps, permissions, UTF-8 names, compression choices, and comment for identical workspace bytes.

Safe extraction is not required for validation. An extractor MUST validate first, create files without following links, prevent overwrite/races, enforce destination containment, and preferably write into a fresh temporary directory before an atomic handoff.

## 20. Release, pack, receipt, and repository descriptors

The release, pack-manifest, materialization-receipt, and legacy-Zenodo-projection schemas are versioned companion contracts:

- a release descriptor publishes manifest fixity and carrier/distribution topology;
- a pack manifest indexes exact safe members in a pack realization;
- a materialization receipt records selected groups, acquisition attempts, status-dependent byte verification, time, exact producer identity, and exact source-carrier evidence;
- the explicitly scoped legacy Zenodo projection maps discovery metadata without redefining the VAO release; it MUST NOT be presented as a schema for the current InvenioRDM records API.

Receipts are operational evidence, not mutations of the semantic release. Every attempt records `attemptedAt`. Its `distributionId` MUST resolve to a manifest Distribution named by the corresponding Realization's `distributionIds`; inspection of bytes already embedded in the source carrier is not a Distribution acquisition. A verified acquisition additionally records acquired byte size, SHA-256, and a `verifiedAt` instant no earlier than the attempt. An integrity failure records a diagnostic plus at least one observed byte size/digest that actually differs from the expected realization, but never a verification instant. An unavailable, authentication-required, or policy-blocked attempt records a diagnostic and MUST NOT claim acquired byte identity or verification. No attempt/verification instant follows receipt creation.

The receipt pins its producing implementation with a SHA-256 and a precise executable/source/container scope; a name/version alone is insufficient. `sourceCarrier` MUST pin the exact carrier-descriptor bytes. For a packed carrier it additionally MUST pin the byte size and SHA-256 of the complete `.vao` container; a workspace source omits a nonexistent container identity. Consequently, an `embedded-valid` state remains attributable to the exact carrier that was inspected.

All companion descriptors use the VAO strict JSON/numeric domain and their explicit immutable schema IRI. A release descriptor has one manifest and at least one bootstrap carrier in its root record, does not self-inventory `vao-release.json`, uses unique record/version identifiers and NFC/case-fold-distinct file identifiers, and uses the defined relation/inverse pairs. A pack has NFC/case-fold-distinct member paths and lists each realization at most once. A receipt has at most one acquisition per realization/distribution pair and one state per profile; an acquisition cannot be verified after the receipt was created. Cross-validation additionally resolves release identity and manifest fixity, pack members, receipt distributions/groups/profiles/software, and carrier evidence against exact bytes. Publication-set validation requires one correctly scoped legacy Zenodo projection for each Zenodo record and exact version-PID relations across a record family.

## 21. Linked-data projection

Canonical VAO JSON is authoritative. The versioned JSON-LD context maps registries to RDF properties and records to nodes. `Tools/vao04_rdf.py` creates an annotated JSON-LD view by adding class types and `vao:jsonPointer`; removing only those annotations restores the parsed manifest object.

An RDF dataset is a semantic projection. It does **not** preserve object-member order, registry array order, JSON number lexical form, whitespace, or original bytes. Therefore:

- RDF round trip MUST NOT be used to verify or recreate `manifestSHA256`;
- unmapped or extension semantics MUST be preserved from canonical JSON;
- a linked-data projector claim requires successful JSON validation, RDF parsing, and SHACL validation;
- an RDF consumer MUST NOT infer that an absent triple proves an absent VAO JSON value.

The vocabulary declares every VAO term emitted by the versioned context. Detailed domains, ranges, cardinalities, ordering, numeric constraints, and cross-record rules remain governed by canonical JSON and the normative profiles. The SHACL graph is a supplemental projection-integrity layer, including profile-container, exact-realization, runtime, and spatial/acoustic shapes; it is not a substitute for JSON Schema or semantic validation.

## 22. Extensions

The root `extensions` object and extension-bearing records use absolute IRI keys. An extension MUST NOT redefine, contradict, or weaken a core field. Its owner SHOULD publish a versioned schema, semantics, security considerations, and profile/capability IRI.

A processor that does not understand an extension MAY preserve and ignore it only when no claimed profile declares that extension as required. It MUST report inability to satisfy the associated capability. Implementations MUST preserve unknown extension values exactly when rewriting a manifest; otherwise they MUST create a new release and disclose the loss.

## 23. Conformance

Conformance is role-specific. A validator, reader, writer, extractor, materializer, linked-data projector, repository projector, runtime, and profile processor make different claims. No implementation should claim generic “VAO 0.4.0 support” without listing roles and profiles.

A package is conforming only when it passes strict parsing, JSON Schema, identifier/reference, profile, semantic, carrier, exact-byte, and claimed-capability checks in the order defined by [VAO_CONFORMANCE_0.4.0.md](VAO_CONFORMANCE_0.4.0.md).

Warnings identify preservation or availability risks that are not currently invalid. An implementation MUST NOT convert an error into a warning to claim conformance.

## 24. Security and privacy considerations

VAO content is passive data. Validation MUST NOT execute renderer code, scripts, macros, models, plugins, or media decoders. Preview and rendering happen only after validation, rights checks, and explicit user/local-policy authorization.

Threats include ZIP bombs, path traversal, link races, parser differentials, duplicate JSON members, hash confusion, mutable remote records, SSRF, malicious redirects, credential leakage, media decoder vulnerabilities, oversized graphs, cyclic references, stochastic denial of service, signature overtrust, and disclosure of performer/research data.

Processors MUST follow [SECURITY_CONSIDERATIONS.md](SECURITY_CONSIDERATIONS.md). In particular they enforce finite resources; keep network resolution off by default; verify decoded bytes; isolate external renderers; avoid logging secrets or sensitive metadata; and distinguish fixity, authenticity, authorization, scientific validity, and safety.

## 25. Interoperability and external standards

Informative binding guidance is provided in [VAO_INTEROPERABILITY_0.4.0.md](VAO_INTEROPERABILITY_0.4.0.md). External standard identifiers and media types SHOULD be versioned where the external ecosystem supports it. A VAO profile may require a specific external version, but the core does not claim ownership of external terms.

Projections are derivatives. If preserved as realizations, they receive their own exact identity and generating Activity. They MUST NOT silently overwrite the canonical VAO manifest.

## 26. Media-type registration considerations

The intended registration is in the IANA vendor tree because VAO is currently maintained by a project rather than an IETF stream or recognized standards body:

- type name: `application`;
- subtype name: `vnd.modavis.vao+zip`;
- required parameters: none;
- optional parameters: none;
- encoding: binary;
- file extension: `.vao`;
- magic: a ZIP container whose first stored member is `mimetype` with exact VAO media-type bytes;
- fragment identifiers: none defined by 0.4.0.

Generic ZIP processors can inspect the container but do not thereby understand VAO semantics. Sniffing the extension or ZIP signature alone is insufficient. Registry submission does not establish scientific validity, safety, endorsement, or intellectual-property clearance.

## 27. Change control and future versions

Published version namespaces and bundle bytes are immutable. Corrections that alter validation or serialized meaning require another version. Deprecation MUST preserve a migration path and retained evidence where technically possible.

Future minor versions SHOULD accept earlier valid 0.4 documents when feasible. A breaking change uses a new major version and new immutable schema/context/profile IRIs. Governance and release approval are defined in the repository root.

## Appendix A. Design invariants

1. Semantic release identity is independent of carrier, repository, and runtime.
2. Logical identity is separate from exact byte identity.
3. Raw evidence, derivatives, simulation, inference, reconstruction, and creative transformation are distinguishable.
4. Filenames are never the only copy of a scientific or playable relationship.
5. Units, clocks, coordinate frames, protocols, uncertainty, and provenance are explicit when scientifically claimed.
6. Interaction is declarative and bounded; validation is passive.
7. Determinism is tested by canonical traces.
8. No license or consent means no inferred permission.
9. Remote bytes remain untrusted until exact local verification.
10. JSON is authoritative; semantic projections do not rewrite fixity history.

## Appendix B. Minimal carrier tree

```text
example.vao
├── mimetype
├── vao-manifest.json
├── META-INF/
│   └── vao-carrier.json
└── payload/
    └── evidence/
        └── source.txt
```

A complete synthetic workspace and deterministic packed carrier are available under `Fixtures/VAO04/`.
