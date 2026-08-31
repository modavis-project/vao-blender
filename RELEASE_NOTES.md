# VAO Blender 0.4.0-rc.1

Current release state: **unreleased**. These notes describe the source freeze
prepared for a staged release candidate; no tag, canonical artifact set, DOI,
GitHub release, or Zenodo publication has been created for it.

Status: **unreleased**.

VAO Blender 0.4.0-rc.1 is a major correctness, safety, lifecycle, and usability
release. It supports the published
[VAO Standard 0.4.0](https://github.com/modavis-project/vao-standard/releases/tag/v0.4.0)
and the exact 0.5.0 candidate at commit
`d17b3f188fdf7fadd01ba025383e4feca8def935`, while retaining isolated 0.3.2
and 0.2.2 compatibility readers.

## Highlights

- Added complete, exact 0.5.0 candidate validation and inspection with a full
  checksum inventory for the vendored candidate contract.
- Made validation completeness explicit. Skipping either archive hashing or
  payload verification now produces a non-valid `INCOMPLETE` outcome and cannot
  unlock media, visual materialization, or performance actions.
- Removed archive time-of-check/time-of-use gaps by retaining and using the exact
  validated manifest bytes and by binding extraction to validated source state.
- Hardened JSON, MIME, archive-member, payload, and command-line behavior. Invalid,
  unsupported, incomplete, and resource-limited results remain diagnosable without
  being misreported as usable success.
- Reworked Blender sessions around unique live-session and durable
  materialization identities. Multi-scene and repeated-package sessions no longer
  collide; load/save/undo handlers reconcile stale state safely.
- Added ownership-preflighted, undoable visual removal and explicit relinking for
  traceable VAO materializations saved in `.blend` files.
- Replaced silently truncated explorer and diagnostic views with paging, counts,
  stable selection, and complete detail access.
- Preserved unsupported and invalid state through rights acknowledgement instead
  of presenting acknowledgement as validation success.
- Restricted audio preview to the semantics actually implemented: independent
  selection, recorded pitch, stereo preservation, validated gain/envelopes, and
  atomic polyphony. Unsupported exclusivity, resampling, pitch, channel, and
  component mappings are rejected with actionable diagnostics.
- Added lifecycle-safe audio cleanup, balanced device locking, timer-failure
  handling, decoded-sound bounds, and cache protection for active media.
- Replaced permissive cache adoption with an owned cache layout, atomic extraction,
  cross-process locking, quarantine, active-file protection, bounded cleanup, and
  safer custom-root and deletion behavior.
- Centralized the release identity in `release_metadata.toml`, made the same
  SemVer prerelease identity authoritative across the Blender manifest,
  packaging metadata, RC label, and intended tag, added staging versus tagged
  build modes, expanded SBOM coverage to both modern standards, and made
  artifact contents part of the release gate.

## Deliberate boundaries

VAO 0.4.0 and 0.5.0 runtime/interaction programs are inspected but not executed.
Remote carrier-member acquisition, RIR convolution, acoustic simulation, and
acoustic rendering remain unsupported. The 0.5.0 pin is a reviewed standard
candidate, not a published-standard claim. VAO validation establishes structural
and cryptographic consistency, not rights clearance, malware safety, scientific
truth, or perceptual quality.

## Verification gates

The release gate includes all Python unit/contract/security tests; compilation
and Ruff checks; Blender extension source validation; Blender lifecycle,
detached/reopen, VAO 0.3.2, 0.4.0, and 0.5.0 source integration; fake-device
audio policy/failure tests; the optional full Cuntz audio/visual workflow; exact
0.4.0 and 0.5.0 contract inventories; wheel and release-set SBOM hash parity;
deterministic archive normalization; per-platform package validation; and
installed-extension smoke tests.

Local source validation, local package experiments, and host-native development
passes are not canonical release artifacts. The release set must be assembled on
Linux x86_64 by Python 3.13.13 with the exact official Blender 5.2.1 Linux x64
archive at
`https://download.blender.org/release/Blender5.2/blender-5.2.1-linux-x64.tar.xz`
(archive SHA-256
`a31f524fa99a527d3d52b7f5aaa68c34e1a19d5a1c9473f79c5cc610fd5b10e9`,
Blender executable SHA-256
`c2fd82553c979a7f6ba85202c487aa1173c90db588a67d74d70cc7b0c2bea01c`,
build hash `9e2066aef7ef`, Blender Python 3.13.13). The builder records the
observed values in `RELEASE_EVIDENCE.json` and rejects any mismatch.

Native installed-extension execution on Blender 5.1.2 and 5.2.1 across Windows
x64, macOS ARM64, and Linux x64 must be recorded before publication. This
source-freeze table is deliberately explicit and remains unchanged after the
canonical artifacts are built:

| Blender | Native platform | Exact ZIP under test | Source-freeze state |
| --- | --- | --- | --- |
| 5.1.2 | Windows x64 | `vao_blender-0.4.0-rc.1-windows_x64.zip` | Not run |
| 5.1.2 | macOS ARM64 | `vao_blender-0.4.0-rc.1-macos_arm64.zip` | Not run |
| 5.1.2 | Linux x64 | `vao_blender-0.4.0-rc.1-linux_x64.zip` | Not run |
| 5.2.1 | Windows x64 | `vao_blender-0.4.0-rc.1-windows_x64.zip` | Not run |
| 5.2.1 | macOS ARM64 | `vao_blender-0.4.0-rc.1-macos_arm64.zip` | Not run |
| 5.2.1 | Linux x64 | `vao_blender-0.4.0-rc.1-linux_x64.zip` | Not run |

Configured CI jobs, successful package construction, and source-tree validation
are not native installed-extension evidence. A local Blender 5.1.1/macOS ARM64
development pass exercised source integration and an installed-extension smoke
during preparation, but it is outside the pinned release-target matrix and does
not certify the final candidate artifacts. No target cell may change to “Pass”
without evidence tied to the exact candidate commit and artifact checksum.

Post-build results are authoritative only in `NATIVE_TEST_EVIDENCE.json`. Each
of its six passing cells must bind the run URL and observation time to the exact
source commit, ZIP filename, ZIP SHA-256, Blender version, native platform, and
complete required-test set. The manual `native-release-evidence.yml` workflow
also pins and verifies each official Blender archive, probes its build, Python,
system and machine, hashes its executable, records the hosted runner image, and
forces the six tests to import installed artifact bytes. `PUBLICATION_SHA256SUMS`
then binds that detached attestation to the unchanged canonical build. Until both
files verify and all six cells pass, this candidate is not publication-ready;
the source-freeze table above stays “Not run” by design.

## Install

After publication, download `PUBLICATION_SHA256SUMS` and the ZIP matching the
host platform from the same release, verify the checksum, and install the ZIP
without unpacking it through **Edit → Preferences → Get Extensions → Install
from Disk**. The package names begin `vao_blender-0.4.0-rc.1-`; see
[Installation](docs/INSTALLATION.md).

## Citation and research record

This candidate has no DOI yet. The prior release DOI
[10.5281/zenodo.22134389](https://doi.org/10.5281/zenodo.22134389) does not
identify 0.4.0-rc.1. The published VAO Standard 0.4.0 is separately archived as
[10.5281/zenodo.22122774](https://doi.org/10.5281/zenodo.22122774). A new VAO
Blender version DOI will be inserted only after a maintainer creates the correct
new-version Zenodo draft.
