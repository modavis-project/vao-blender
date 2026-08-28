# VAO Scientific profile 0.5.0

Profile IRI: `https://w3id.org/modavis/vao/profile/scientific/0.5.0`

## Applicability

This profile is required when any list in `scientific` is non-empty. Empty scientific registries alone do not trigger it.

## Minimum evidence contract

The profile uses ten typed registries: Agents, Activities, Observations, Analyses, Calibrations, Protocols, Software Environments, Claims, Reviews, and Consents. A reusable Analysis normally identifies:

- exact inputs and outputs;
- its Activity and Protocol;
- responsible Agent(s);
- exact Software Environment;
- parameters and reproducibility class;
- random source for seeded work;
- validation evidence and residual/uncertainty where applicable.

An Observation identifies feature, property, result, unit, result time, Activity, Protocol, and status; sensor, calibration, raw/processed realization, uncertainty, sample count, censoring, flags, and outlier policy are retained when known.

## Semantic rules

- Activities cannot end before they start or use the same immutable ID as both input and output. An identified record with `generatedById`/`generatedByIds` is listed in every named Activity's outputs. Every temporally identified input is available by the consumer start, every declared producer ends no later than that boundary, and the Activity dependency graph is acyclic.
- All local references resolve to their permitted registry classes.
- An Observation is an output of a capture/measurement/processing/simulation Activity, uses its Protocol, and occurs within its inclusive bounds. Raw evidence occurs in Activity I/O; processed evidence is an output and is distinct from raw evidence.
- A named Sensor agrees on observed property/Protocol and its declared calibration is cited. A cited Calibration applies to the Sensor component Entity and is temporally valid at the result time.
- An Analysis uses a processing/simulation/inference Activity, and its I/O, software environment, random source, parameters, validation evidence, output Observation/Claim provenance, and Activity are mutually consistent. Validation cannot self-reference, belongs to Activity I/O, and is available by the applicable input-start or output-end boundary. `deterministic` Analyses have no random source; `seeded` Analyses have a declared runtime/interaction Random Source.
- Every Software Environment identifies and describes the exact scope of its primary digest. Declaration hashes are not executable identities. Dependencies have independent roles, scopes, coverage statements, and digests; source and environment-lock roles use their corresponding identity scopes.
- A `deterministic` or `seeded` Analysis has a stated runtime and an exact container/executable identity, or independently hashed code and environment-lock identities. An environment lock without code and source without an environment lock are insufficient. Otherwise it is `non-reproducible`; the class does not establish scientific validity or cross-platform bit identity.
- Claims have exactly one object identifier or literal and retain non-circular evidence/status. Generated-Claim evidence belongs to generating Activity I/O and is chronologically available at the applicable Activity boundary. Inferred Claims have an inference Activity; accepted/rejected Claims have a matching linked Review; reviewed Claims have an assessed linked Review.
- Claim/Review links are reciprocal. A Claim cannot use its own Review as evidence. Reviews identify target, reviewer, date, and decision, do not self-review or predate a timed target, and give rationale for rejection/revision.
- Consents identify grantor, scope, decision, time, and optional evidence and do not apply to themselves.
- Original observations are not rewritten to hide anomalies or disagreement.
- Units and quantity kinds are IRIs; free-text units do not satisfy the quantity contract.
- IRI syntax alone does not establish external-term existence or unit/quantity-kind dimensional compatibility. A processor reports those checks as verified only against a pinned vocabulary definition; scientific deposit workflows should perform and record them.
- Quantity values are numeric scalar/vector/rectangular-matrix values. Uncertainty magnitudes are non-negative and shape-compatible; covariance is dimension-compatible, symmetric, and positive semidefinite. Symmetry uses pair-relative tolerance; PSD is tested after dimensionless correlation normalization, with non-negative variances and exact zero-variance cross-covariance. Inline covariance is bounded to 64 dimensions and 262,144 total cells per manifest.
- `unit` gives a common component unit. Heterogeneous axes use ordered `axisUnits`; covariance cells use the product of their corresponding component units.
- RFC 3339 bounds are compared as instants after applying offsets; `-00:00` is not an admissible known offset.
- ORCID and ROR check digits are validated. A depositing workflow still verifies registry existence, attribution, and current affiliation with the responsible person/organization.
- ORCID is permitted on person Agents and ROR on organization Agents. Affiliations resolve through `affiliationAgentIds` to organization Agents, preserving the distinction between a person identifier and an institution identifier.

Conformance establishes that evidence and provenance are structurally and internally consistent. It does not certify a protocol, calibration, measurement, statistical model, causal interpretation, peer review, or scientific truth. Evidence statuses on Observations and Metrics are not substitutes for Claim/Review records.

PROV-O, SOSA/SSN, QUDT, CRMsci, and CRMdig are mapping targets. External ontology triples cannot replace required VAO JSON records.

## Capability IRI

Implementations processing this profile MUST include `https://w3id.org/modavis/vao/vocab/capability/typed-scientific-provenance` in a claimed profile record and advertise it only when they validate the complete evidence chain rather than merely parse it.
