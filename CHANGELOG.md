# Changelog

All notable changes are documented here. The project follows semantic versioning
for the Blender extension; supported VAO format versions remain exact contract
identities.

## 0.4.0-rc.1 — Unreleased

- Added exact offline validation for the VAO 0.5.0 candidate at standard commit
  `d17b3f188fdf7fadd01ba025383e4feca8def935`.
- Added bootstrap and preservation-closure carrier inspection, including
  cross-carrier distribution metadata without claiming network retrieval.
- Added a Kinoorgel-compatible metadata path for scientific measurements,
  physical MIDI-interface topology, playable mappings, rights, and provenance
  when no 3D realization is present.
- Retained isolated exact support for 0.2.2, 0.3.2, and published 0.4.0.
- Made payload verification and archive hashing independently visible completeness
  gates; opted-out validation is now non-valid and non-materializable.
- Hardened bounded archive parsing, duplicate-key JSON, MIME preflight, validated
  manifest-byte reuse, command-line exit semantics, and extraction provenance.
- Added unique live-session and durable materialization identities, multi-scene
  lifecycle reconciliation, relink/remove workflows, and exact source checks.
- Added complete paged explorer and diagnostics views instead of silently dropping
  records beyond the first page.
- Added an owned, bounded, concurrency-safe cache with atomic writes, quarantine,
  active-path protection, and safe custom-root/deletion rules.
- Restricted legacy audio execution to fully compiled semantics and made gate
  polyphony atomic; added decoded-sound bounds and failure-safe device/timer cleanup.
- Centralized extension/release/standard identity, expanded the SBOM and both
  modern contract inventories, and separated clean untagged staging builds from
  immutable annotated-tag builds.

## 0.3.0-rc.1 — 2026-08-27

- Added exact support for the published VAO Standard 0.4.0 and pinned the signed
  upstream release archive, normative artifact inventory, schemas, reference
  validator, fixtures, license, notice, and provenance.
- Added strict 0.4.0 carrier and manifest validation, immutable context and release
  binding, closed-schema enforcement, archive path hardening, carrier-closure
  checks, streaming byte-size/SHA-256 verification, and parity tests against the
  upstream reference validator.
- Added read-only inspection for 0.4.0 logical assets and realizations, exact GLB
  selection, coordinate-frame transforms, 2D/3D poses, measurements, response
  sets, RIR metadata, provenance, and rights records.
- Added explicit capability reporting. Interaction/runtime execution and acoustic
  rendering remain unsupported for 0.4.0 and 0.3.2.
- Kept the 0.2.2 and 0.3.2 readers isolated behind exact version dispatch.
- Corrected the rights gate so media access remains blocked whenever the validation
  result requires acknowledgement, independently of the headline outcome state.
- Bundled and checksum-pinned validator dependencies for Windows x64, macOS x64,
  macOS Apple Silicon, and Linux x64.
- Added VAO 0.4.0 conformance, adversarial, visual-acoustic, and Blender integration
  tests.
- Added deterministic release auditing and ZIP normalization, split-platform
  packaging, artifact validation, checksums, release evidence, public repository
  governance files, and updated user/developer documentation.
- Added a deterministic tagged-source archive, SPDX SBOM packaging, GitHub release
  notes, Zenodo metadata, DOI `10.5281/zenodo.22134389`, and a coordinated manual
  publication checklist for the GitHub prerelease and Zenodo record.

## 0.2.0 — 2026-08-24

- Added separate exact readers for the private VAO 0.2.2 development format and
  VAO 0.3.2 editor draft.
- Added 0.3.2 carrier validation, logical-asset/realization inspection, coordinate
  frames, source/receiver poses, RIR metadata, and visual import.
- Added asynchronous validation, cancellation, cache hardening, rights gating,
  diagnostics, audio cleanup, and Blender 5.1 integration tests.

## 0.1.1 — 2026-08-23

- Hardened cache extraction and GLB rewriting.

## 0.1.0 — 2026-08-22

- Initial Blender extension implementation for VAO 0.2.2 development packages.
