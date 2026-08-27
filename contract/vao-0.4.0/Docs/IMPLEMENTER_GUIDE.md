# VAO 0.4.0 implementer guide

This guide is informative. Normative requirements are in the standard, schemas, conformance document, and claimed profiles.

## 1. Choose an implementation role

Start with the smallest honest role: validator, reader, writer, carrier writer, extractor, materializer, linked-data projector, repository projector, deterministic runtime, or profile processor. Publish exact role/profile/capability IRIs and resource limits.

A metadata catalogue may need only Core reading and fixity. A preservation system may need carrier validation/extraction and closure. An instrument simulator may additionally need Playable and deterministic runtime.

## 2. Build a manifest

Use the [minimal workspace](../Fixtures/VAO04/workspaces/minimal) for structure, the [Kinoorgel descriptor](../Fixtures/VAO04/descriptors/kinoorgel-multimodal-scientific.example.json) for multimodal/scientific/playable/runtime registries, and the [Cuntz–Positiv descriptor](../Fixtures/VAO04/descriptors/cuntz-positiv-acoustic.example.json) for a positive spatial/acoustic contract. Fixture values are conformance data, not scientific reference results.

Recommended order:

1. Create the release ID, dates, localized title, profile records, and MODAVIS binding.
2. Define semantic Entities and relations.
3. Define rights, scientific Agents/Protocols/Activities, discovery creators, and—when repository projection is intended—publisher/publication year.
4. Define logical assets.
5. Hash each exact file and create its realization with technical metadata.
6. Add distributions and repository bindings where applicable.
7. Group realizations for delivery and compute each direct `totalByteSize`.
8. Add spatial/acoustic, playable/interaction/capture, scientific, multimodal, physical, and runtime records.
9. Resolve every reference and profile trigger.
10. Validate before writing a carrier.

Do not use filenames as semantic identifiers. Prefer stable HTTP(S) IRIs for public objects and UUID-based URNs for locally minted immutable identities. Never reuse an ID for changed meaning.

Treat all `*Id`/`*Ids` fields as local resolvable record references except the explicitly exempt token/cross-release fields in section 4 of the standard. Use dedicated IRI/classification/external-identifier fields for external concepts.

For measurement data, preserve numeric shape and component order. Non-covariance uncertainty follows the quantity shape; covariance is symmetric positive semidefinite and dimensioned by the flattened component count. Use `axisUnits` for heterogeneous coordinates, compare symmetric pairs only within their shared product unit, and normalize covariance to a dimensionless correlation matrix before PSD testing. A scalar registration RMS instead carries its own unit and names the coordinate/metric residual convention in `method`. Put covariance beyond the inline dimension/cell limits in an exact realization. Do not turn missing uncertainty, calibration, standard edition, or validation into an invented default.

For geodetic data, resolve the pinned CRS definition and preserve its axis order. Do not infer longitude-first or latitude-first from the numeric values; CRS84-family and EPSG definitions may not share the same order. Preserve any reordering or projection as a provenance-bearing conversion.

Parse manifest numbers as finite binary64 and reject non-zero underflow, overflow, and integers outside `±(2^53-1)`. Reject escaped unpaired UTF-16 surrogates in strings and property names. Keep higher-precision arrays in an exact domain realization instead of silently rounding them into manifest JSON. Treat fixed-width random-source hex fields as bit patterns, not numbers.

For timed media, treat `unit` as the coordinate unit and `rate`/`rateUnit` as a dimensioned rate. Use lowest-terms rational rates for values such as 30000/1001. Identify the time scale of wall clocks and external timecode; never collapse UTC, TAI, GPS, POSIX, or SMPTE semantics into a bare timestamp. Compare RFC 3339 fractions exactly through 18 digits and route leap-sensitive series through an explicit Timebase/mapping. Keep Track modality, realization technical kind, sample/frame rate, Timebase, and Coordinate Frame mutually consistent. Synchronization residual/jitter values use the target coordinate unit.

Make provenance reciprocal: an identified record naming a generating Activity is listed in that Activity's outputs, and immutable input/output IDs do not overlap. Keep Observation/Analysis Activity I/O, parameters, software, random source, Sensor, and Calibration timing consistent. Keep Claim evidence acyclic and Review times after their timed targets. Use Claim/Review records for epistemic acceptance or rejection instead of treating an evidence-status label as scientific certification.

State exactly what every Software Environment digest covers. Hash executables, source files/bundles, environment locks, containers, and model weights as separate assertions; do not relabel a name/version or parameter declaration hash as executable identity. Give each dependency a role, scope, digest, and coverage statement. An environment lock without code identity and source without an environment lock do not meet the deterministic/seeded threshold. Use `non-reproducible` for an Analysis, or `deterministic: false` for a Renderer, when only declaration-level software evidence survives.

## 3. Exact bytes and hashing

Hash files as binary streams. Do not normalize line endings, decompress media, decode text, or apply filesystem metadata.

```python
import hashlib
from pathlib import Path

def exact_identity(path: Path) -> tuple[int, str]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
            size += len(block)
    return size, digest.hexdigest()
```

Manifest fixity is over exact `vao-manifest.json` bytes. Trace digests instead use RFC 8785 canonicalization of the trace tuple specified in the standard.

## 4. Workspace creation

Write only:

```text
mimetype
vao-manifest.json
META-INF/vao-carrier.json
payload/...
```

`mimetype` contains exactly `application/vnd.modavis.vao+zip` with no newline. The carrier descriptor records manifest byte size/SHA-256 and maps every payload file to its realization. Use forward slashes, relative `payload/` names, and NFC-distinct names. Avoid names that differ only by case for portability even though the normative comparison is case-sensitive.

Validate the workspace before packing:

```sh
python Tools/vao04.py validate path/to/workspace --json
```

## 5. Deterministic packing

The reference writer validates, streams each file into a stored ZIP member, fixes metadata, verifies the final archive, and deletes partial output on failure:

```sh
python Tools/vao04.py pack path/to/workspace output.vao
```

It refuses to overwrite. Repeating the command to two new output paths over unchanged bytes must produce identical SHA-256.

## 6. Validation API

The reference CLI recognizes:

- a `.json` path as a manifest descriptor;
- a directory as an unpacked workspace;
- another regular file as a packed carrier.

Companion contracts use an explicit kind so that a release/pack/receipt cannot be mistaken for a manifest:

```sh
python Tools/vao04.py validate-descriptor release vao-release.json
python Tools/vao04.py validate-descriptor pack vao-pack-manifest.json
python Tools/vao04.py validate-descriptor receipt vao-materialization-receipt.json
python Tools/vao04.py validate-descriptor zenodo-metadata zenodo-legacy.json
python Tools/vao04.py validate-publication vao-release.json zenodo-legacy.json
python Tools/vao04.py validate-release vao-release.json vao-manifest.json
python Tools/vao04.py validate-pack vao-pack-manifest.json vao-manifest.json
python Tools/vao04.py validate-receipt vao-materialization-receipt.json vao-manifest.json source.vao
```

The companion validator applies the same bounded strict-JSON, nesting, Unicode-scalar, finite-binary64, and safe-integer domain as manifest validation. It also checks publication topology, exact/NFC/NFC-plus-case-fold file and path uniqueness, relation inverses, receipt chronology/uniqueness, and the legacy Zenodo projection scope. The cross-document commands additionally compare release/pack/receipt assertions with exact manifest and carrier bytes. The examples in `Fixtures/VAO04/companions` are conformance contracts, not publication instructions; the cross-document examples are bound to the maintained minimal fixture while the failure-status receipt remains explicitly synthetic.

Human output is default; `--json` produces a stable report object. Exit codes are 0 valid, 1 invalid, and 2 operational/invocation failure.

For embedding, import from `Tools`:

```python
from pathlib import Path
import sys

sys.path.insert(0, "Tools")
import vao04

report = vao04.validate(Path("example.vao"))
if not report["valid"]:
    raise ValueError(report["errors"])
```

Production applications should wrap calls with their own elapsed-time/memory/process isolation and report their configured budgets.

## 7. Safe reading and extraction

Prefer in-place validation; extraction is not needed to inspect JSON or hash entries. If extracting:

1. validate central-directory metadata and structural descriptors first;
2. reject links/special files/encryption/unknown compression/unsafe or colliding names;
3. create a fresh temporary destination not controlled by the archive;
4. open destination files with exclusive creation and without following links;
5. stream while enforcing per-entry/total budgets and verifying digest;
6. atomically hand off only after all checks pass.

Do not call a generic `extractall` on untrusted input.

## 8. Remote materialization

Keep resolution disabled by default. When enabled, restrict schemes and hosts, resolve DNS/redirects under SSRF policy, isolate credentials, limit redirects/time/bytes, and write to temporary storage. Verify decoded byte size and SHA-256 before cache visibility. Repository concept identifiers are discovery aids, not exact file identity.

Record success/failure in a receipt. Separate the attempt time from successful verification, preserve a bounded diagnostic for failure, do not fabricate byte observations for policy/authentication/unavailable outcomes, and pin both the receipt-producing implementation and exact source carrier. An acquisition names a Distribution declared by the acquired Realization; do not invent a distribution identifier for bytes already embedded in the source carrier. Do not modify the immutable manifest with a local path.

## 9. Profiles and graceful degradation

Read `profiles`, `materializableProfiles`, and their required capability IRIs before preview or rendering. An implementation may inventory unsupported records, but it must not claim the profile or discard them on rewrite.

When a profile is materializable, acquire all declared groups plus dependencies before claiming it is active. A fallback is a different declared realization, not a transparent substitution.

## 10. Linked data

Place the canonical VAO context first. Use the locally pinned context in deterministic/offline pipelines; never fetch an unreviewed context during validation. The reference helper embeds the repository copy, adds RDF types/JSON pointers, and refuses additional contexts that it cannot independently pin:

```sh
python Tools/vao04_rdf.py manifest.json --annotation-round-trip-check > projected.jsonld
```

Parse that projection as JSON-LD and run the supplied SHACL graph. Retain canonical JSON and exact manifest bytes. Never use RDF serialization to recompute carrier manifest fixity.

## 11. Deterministic traces

Use `rfc8785.dumps` (or a conforming RFC 8785 implementation) and SHA-256. Do not replace canonicalization with ordinary sorted JSON. Implement PCG32 streams and stream-free non-zero xoshiro256** initialization exactly. Map raw integer words with the specified high-tail rejection and equal/proportional intervals; modulo and floating-point scaling are biased. Cross-check rejection boundaries and test vectors before advertising the runtime profile.

The supplied offline interpreter is not a live scheduler, voice engine, or media renderer. It admits only immediate completed one-shot/compound/stochastic Process expansion and rejects delayed, timed, sustained, repeating, or sequenced lifecycle. Stochastic candidates are direct actions followed by direct children; selection occurs before a selected child expands, and unselected children consume no random words. It cannot establish late/re-entrant arrival handling, delayed action timing, voice lifecycle, or bit-identical audio; test those with an independent host harness before claiming the full runtime role.

## 12. Extensions

Mint an HTTPS IRI owned by the extension publisher. Publish a versioned schema, semantics, capability/profile IRI, examples, migration, and security considerations. Put extension values only under permitted IRI-keyed extension/property objects; never add unknown members to closed objects.

## 13. Migration

The reference migrator copies to a new workspace, preserves legacy source data as migration evidence, updates immutable IRIs, and records the original manifest digest:

```sh
python Tools/vao04.py migrate-0.3 old-workspace new-workspace
```

Review migrated representation status, rights, scientific typing, profiles, and developmental ontology bindings manually. Migration validity does not prove scientific equivalence.

## 14. Release checklist for implementers

- Run the official valid and invalid fixture suite.
- Publish role/profile/capability and resource-limit statements.
- Fuzz strict JSON, ZIP metadata, paths, graph references, and media boundaries.
- Test without network and with hostile redirects/oversized streams.
- Verify deterministic archives on at least two clean runs.
- Verify trace outputs against an independent implementation.
- Preserve unknown extension data and original invalid evidence.
- Document decoder/runtime sandboxing and vulnerability reporting.
