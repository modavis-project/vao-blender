# VAO 0.5.0 conformance

This document is normative. It defines what an implementation or package must prove before claiming VAO 0.5.0 conformance.

## 1. Role-specific claims

An implementation MUST identify every role it claims:

| Role | Minimum responsibility |
| --- | --- |
| validator | strict JSON, schemas, semantics, references, profiles, and claimed capabilities |
| reader | validator checks for interpreted content; preserves unsupported data |
| writer | emits valid immutable manifests/descriptors and reports profiles/capabilities |
| carrier writer | creates a deterministic safe carrier and verifies its final bytes |
| extractor | validates before safe bounded extraction |
| materializer | resolves groups/distributions and verifies exact acquired bytes |
| linked-data projector | creates a valid semantic projection and runs SHACL |
| repository projector | maps discovery/release metadata without changing core assertions |
| deterministic runtime | implements scheduling/random semantics and passes all claimed traces |
| profile processor | satisfies every requirement and capability of named profile versions |

“VAO compatible” without roles, version, profiles, and limitations is not a complete conformance claim.

## 2. Package validation order

A validator MUST perform checks in an order that prevents unsafe or ambiguous content from reaching later processing:

1. Apply finite local resource, recursion, entry-count, and elapsed-time budgets.
2. Inspect carrier metadata without extracting; reject unsafe/control-character paths, duplicates after NFC or NFC-plus-case-fold normalization, links/special files, encryption, unknown entries, and unsupported compression.
3. Require the exact first stored `mimetype` member and required structural files.
4. Bound descriptor sizes before decompression, then parse strict UTF-8 JSON with duplicate-name, non-scalar-Unicode, non-finite/overflow/underflow-number, and unsafe-integer rejection.
5. Require the immutable 0.5.0 schema/context/version identifiers.
6. Validate every JSON document against its Draft 2020-12 schema with every `format` keyword enabled as an assertion; annotation-only format handling is non-conforming.
7. Build a global declared-identifier registry; reject collisions and unresolved required references.
8. Validate Core and Dynamic Delivery semantics, including release, logical assets, realizations, distributions, groups, rights, profiles, and repository bindings.
9. Validate Spatial/Acoustics, Playable, interaction, capture, Scientific, Multimodal, Physical Instrument, runtime, rights/consent, and discovery semantics when present.
10. Reject invalid quantity/uncertainty shapes, non-PSD covariance, inexact/ambiguous timestamp ordering, chronological intervals, scientific provenance/review chains, time-scale/clock/rate/modality/technical-metadata contradictions, affine/frame/pose contracts, acoustic band/response/interpolation dimensions, topology cycles/port inverses, zero-delay cycles, and invalid/unbounded process, transfer, random, or MIDI 2 contracts.
11. Verify alternate digests, chunk coverage/digests, Merkle roots, indices, and trace canonical digests.
12. Verify carrier manifest pin, exact payload closure, every embedded byte size/SHA-256, group completeness, and carrier-mode requirements.
13. Execute every conformance trace when validating a deterministic-runtime claim.
14. Perform RDF parsing and SHACL only when validating a linked-data projection claim.

A processor MAY stop after an error makes later processing unsafe. Its report SHOULD distinguish checks not run from checks that passed.

## 3. Manifest conformance

A manifest conforms when:

- strict parsing succeeds;
- the normative manifest schema succeeds;
- all identifiers and required references resolve according to the model;
- Core and Dynamic Delivery profile records are embedded and claimed;
- every non-empty optional registry has its required profile claim;
- every mandatory profile capability is present and Acoustics includes Spatial plus an applicable acoustic capability;
- all cross-record semantic invariants in the standard and claimed profiles succeed;
- every claimed capability is either validated or explicitly outside the processor's claim.

JSON Schema success alone is insufficient.

## 4. Carrier conformance

A workspace or archive additionally conforms when:

- its structural layout and exact `mimetype` bytes are valid;
- its manifest and carrier descriptor are conforming;
- the descriptor has an absolute carrier ID and pins the exact manifest bytes and release ID;
- payload paths are safe, NFC- and NFC-plus-case-fold-distinct, and closed under the mappings;
- every embedded realization matches manifest byte size and SHA-256;
- inline chunk digests match embedded ranges when declared;
- complete groups include transitive dependencies;
- bootstrap embeds at least one realization;
- preservation closure embeds all realizations and marks all groups complete.

A release/manifest set additionally conforms when every `carrier-member` Distribution matches one carrier inventory entry by carrier ID, immutable version PID, record ID, and filename, and all carrier IDs are unique throughout the publication topology.

Failure caused solely by a declared implementation resource budget SHOULD be reported as `resource-limit` in addition to a non-conforming result for that processing attempt.

## 5. Writer conformance

A writer MUST validate its output using an independent read path before reporting success. A carrier writer MUST:

- write `mimetype` first and stored;
- use safe UTF-8 entry names and stable ordering;
- emit deterministic timestamps, permissions, compression, flags, and comment for identical input bytes;
- stream payloads rather than loading unbounded content into memory;
- remove a partial output after any failure;
- refuse to overwrite an existing target unless a separate explicit application policy authorizes it.

Two reference-writer invocations over unchanged workspace bytes MUST produce byte-identical carriers.

## 6. Materializer and extractor conformance

A materializer MUST keep remote data untrusted until decoded byte size and SHA-256 match. It MUST enforce a network policy for schemes, hosts, redirects, credentials, timeouts, and maximum bytes. Mutable concept records do not satisfy exact acquisition.

An extractor MUST validate the carrier first and MUST prevent path escape, link traversal, overwrite races, special-file creation, and resource exhaustion. Validating a carrier without extracting it is conforming validator behaviour.

## 7. Deterministic-runtime conformance

A full deterministic-runtime role MUST implement section 17 of the standard, including:

- input/transition/action ordering;
- snapshot guards and run-to-completion;
- state conflict, reentrancy, late-event, microstep, and voice policies;
- process termination and explicit delays;
- PCG32 streams and stream-free non-zero xoshiro256** initialization/output when claimed;
- unbiased raw-integer rejection/interval uniform and categorical selection exactly as defined, without modulo or floating-point bias;
- typed state/event/action domains, exact conflict policy, and rejection of delayed actions in offline traces;
- RFC 8785 trace canonicalization and SHA-256;
- exact comparison of final state, emitted event order/content, and render-binding order.

The supplied offline trace verifier tests only already-available ordered input, guards, transition state/actions, immediate completed one-shot/compound/stochastic Process expansion/selection, emitted records, and render-binding selection. String tie-breaks are locale-independent UTF-8 byte order. Stochastic candidates are direct actions followed by direct children, and selection precedes expansion of the selected child. Expanded Process actions are losslessly recorded requests, not applied transition effects. The verifier rejects delayed actions, timing-constrained Processes, and sustained/repeating/sequenced lifecycle, and does not exercise live late/re-entrant arrival, queue timing, delay scheduling, voice lifecycle, media rendering, or bit-identical audio. A tool MUST NOT infer a full runtime-role claim from passing that subset. Passing traces demonstrates only behaviour covered by those traces; it is not evidence that a renderer reproduces undocumented acoustic output.

## 8. Linked-data conformance

A linked-data projector claim requires:

1. a conforming canonical manifest;
2. the versioned VAO context first in the context array and an exact locally pinned copy for processing;
3. RDF dataset construction without network-dependent context ambiguity;
4. successful parsing under JSON-LD 1.1;
5. successful VAO 0.5.0 SHACL validation;
6. preservation of the canonical JSON and exact manifest bytes as the fixity authority.

The context maps declared-record references and IRI-valued scientific/registry fields to RDF IRIs, with scoped mappings where one JSON key has context-dependent meaning. The vocabulary covers every VAO term emitted by the context. Additional contexts require independently pinned and reviewed processing; the reference offline projector refuses them rather than dereferencing the network. SHACL tests important projection structure but does not re-express the complete JSON/semantic contract.

The reversible annotation check in `vao05_rdf.py` proves only that adding/removing projection annotations preserves the parsed JSON object. It does not prove a lossless RDF-to-JSON round trip.

## 9. Reference commands

From the repository root:

```sh
python Tools/vao05.py validate Fixtures/VAO05/descriptors/kinoorgel-multimodal-scientific.example.json
python Tools/vao05.py validate Fixtures/VAO05/descriptors/cuntz-positiv-acoustic.example.json
python Tools/vao05.py validate Fixtures/VAO05/workspaces/minimal
python Tools/vao05.py validate Fixtures/VAO05/carriers/minimal.vao
python Tools/vao05.py validate-descriptor release Fixtures/VAO05/companions/release.example.json
python Tools/vao05.py validate-descriptor pack Fixtures/VAO05/companions/pack-manifest.example.json
python Tools/vao05.py validate-descriptor receipt Fixtures/VAO05/companions/materialization-receipt.example.json
python Tools/vao05.py validate-descriptor zenodo-metadata Fixtures/VAO05/companions/zenodo-metadata-legacy.example.json
python Tools/vao05.py validate-publication Fixtures/VAO05/companions/release.example.json Fixtures/VAO05/companions/zenodo-metadata-legacy.example.json
python Tools/vao05.py validate-release Fixtures/VAO05/companions/release.example.json Fixtures/VAO05/workspaces/minimal/vao-manifest.json
python Tools/vao05.py validate-pack Fixtures/VAO05/companions/pack-manifest.example.json Fixtures/VAO05/workspaces/minimal/vao-manifest.json
python Tools/vao05.py validate-receipt Fixtures/VAO05/companions/materialization-receipt-minimal.example.json Fixtures/VAO05/workspaces/minimal/vao-manifest.json Fixtures/VAO05/carriers/minimal.vao
python Tools/vao05_rdf.py Fixtures/VAO05/descriptors/kinoorgel-multimodal-scientific.example.json --annotation-round-trip-check
python -m unittest discover -s tests -v
python Tools/check_release.py
```

`vao05.py validate --json` exits 0 for valid input, 1 for a completed invalid report, and 2 for invocation or operational failure. The reference validator's finite safety limits are implementation limits, not universal maximum VAO package sizes.

## 10. Conformance statement template

Implementations SHOULD publish a statement containing:

```text
Implementation: <name and version>
VAO format: 0.5.0
Roles: <validator/writer/...>
Profiles: <exact profile IRIs>
Capabilities: <exact capability IRIs>
Test bundle digest: <SHA-256>
Resource limits: <entries, descriptor bytes, entry bytes, total bytes, ratio, depth/time>
External standards: <supported versions>
Known limitations: <explicit list>
```

## 11. Test data

Official fixtures are synthetic and test exchange semantics, not scientific truth or decoder security. A conforming test suite SHOULD include:

- minimal valid manifest descriptor, each companion descriptor kind, workspace, and archive;
- complex valid multimodal/scientific/playable/physical/runtime manifest and a positive spatial/acoustic manifest;
- every schema boundary and enum;
- unresolved, mistyped, and duplicate identifiers across modules;
- unsafe/overflow/underflow numbers and rounded PCG stream attempts, negative/non-numeric uncertainty, scale-sensitive non-PSD covariance, offset/sub-microsecond/leap-form timestamp cases, provenance/review mismatches, time-scale/rational/rate/unit and modality/technical contradictions, singular/ill-conditioned transforms, non-unit quaternions, invalid geodetic axes, acoustic band/response/interpolation mismatches, and topology cycles;
- bad digests, byte sizes, chunks, Merkle roots, groups, and traces;
- raw/NFC/case-fold path collisions, controls, traversal, links, special files, encryption, unknown roots, duplicate entries, and decompression-budget cases;
- deterministic writer repetition;
- RDF parsing and both conforming/non-conforming SHACL data;
- 0.3 migration with original-source digest provenance.

An implementation MUST NOT modify an invalid fixture to make its own test pass; expected results are part of the test bundle.
