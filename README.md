# VAO Blender: A Blender Extension for Virtual Acoustic Objects

[![Release candidate](https://img.shields.io/badge/release-0.4.0--rc.1%20prerelease-D97706.svg)](RELEASE_NOTES.md)
[![VAO 0.4.0](https://img.shields.io/badge/VAO-0.4.0%20published-245B78.svg)](https://github.com/modavis-project/vao-standard/releases/tag/v0.4.0)
[![VAO 0.5.0 candidate](https://img.shields.io/badge/VAO-0.5.0%20candidate-2C5F73.svg)](https://github.com/modavis-project/vao-standard/tree/d17b3f188fdf7fadd01ba025383e4feca8def935)

Current release state: **prerelease**. Version 0.4.0-rc.1 has reserved DOI
[`10.5281/zenodo.22210517`](https://doi.org/10.5281/zenodo.22210517) and intended
publication date 2026-08-31. Its GitHub release and Zenodo record remain
unpublished until the exact native evidence matrix is complete.

VAO Blender opens a Virtual Acoustic Object (`.vao`) in Blender, verifies its
carrier and payload, presents the package as inspectable research data, and can
materialize a supported 3D realization. It works offline and treats every VAO as
untrusted input.

The current extension candidate is 0.4.0-rc.1, targeting the 0.4.0 release line.
It implements the published [VAO Standard 0.4.0](https://github.com/modavis-project/vao-standard/releases/tag/v0.4.0),
adds exact support for the 0.5.0 candidate at commit
`d17b3f188fdf7fadd01ba025383e4feca8def935`, and keeps isolated compatibility
readers for VAO 0.3.2 and 0.2.2. The 0.5.0 line is explicitly a pinned candidate,
not a claim that 0.5.0 has been published.

## What it does

- rejects ambiguous archives, duplicate JSON keys, incomplete verification,
  unsupported versions, broken release binding, inventory mismatches, and payload
  fixity failures before enabling media actions;
- shows carrier and package identity, logical assets and realizations, spatial and
  scientific records, provenance, rights, complete diagnostics, and exact
  capability limitations;
- imports only a verified embedded GLB realization, transactionally, and attaches
  durable package, asset, realization, frame, pose, session, and materialization
  provenance to the resulting Blender data;
- supports explicit removal and relinking of a managed materialization without
  confusing another scene or another instance of the same VAO;
- maintains a bounded content-addressed cache with atomic writes, cross-process
  locking, active-file protection, quarantine, and safe cleanup controls;
- executes only the fully compiled VAO 0.2.2 interaction/audio subset and rejects
  undeclared selection, resampling, pitch, channel, envelope, or polyphony behavior;
- requests file access only: no telemetry, network permission, source-package
  mutation, or packaged-script execution.

## Compatibility

VAO versions are matched exactly. A future or otherwise unreviewed version is
rejected instead of being passed to a similar reader.

| VAO format | Status | Available behavior |
| --- | --- | --- |
| 0.5.0 | Commit-pinned standard candidate | Strict carrier validation, paged metadata inspection, and exact embedded visual-realization import |
| 0.4.0 | Published standard | Strict carrier validation, paged metadata inspection, and exact embedded visual-realization import |
| 0.3.2 | Historical editor draft | Pinned compatibility validation, visual-acoustic inspection, and exact embedded visual-realization import |
| 0.2.2 | Historical development format | Pinned compatibility validation, visual import, supported instrument-interaction compilation, and bounded audio preview |

Modern VAO interaction/runtime programs, remote carrier-member retrieval, RIR
convolution, acoustic simulation, and acoustic rendering are not executed. See
the [compatibility matrix](docs/COMPATIBILITY.md) and
[conformance statement](docs/CONFORMANCE.md) for the precise boundary.

## Install

The candidate manifest targets Blender 5.1.x and 5.2.x on Windows x64, macOS
Apple Silicon, and Linux x64. Its native dependency wheels target
Blender's Python 3.13 runtime; the manifest deliberately excludes Blender 5.3+.
Candidate-specific native execution evidence is recorded explicitly in the
[release notes](RELEASE_NOTES.md) and is required before publication.

After publication, download `PUBLICATION_SHA256SUMS` and the ZIP for your
platform from the same release, verify the checksum, then choose **Edit →
Preferences → Get Extensions → Install from Disk** in Blender. Do not unpack the
ZIP.

```text
vao_blender-0.4.0-rc.1-windows_x64.zip
vao_blender-0.4.0-rc.1-macos_arm64.zip
vao_blender-0.4.0-rc.1-linux_x64.zip
```

For a published candidate, `PUBLICATION_SHA256SUMS` is the complete release-set
checksum inventory and `NATIVE_TEST_EVIDENCE.json` is the authoritative detached
record for the six Blender-version/platform installed-extension cells.
`SHA256SUMS` remains the immutable canonical-build inventory.
The manual `native-release-evidence.yml` workflow produces and merges those
exact-artifact cells without creating or publishing a release.

Platform-specific verification and update instructions are in
[Installation](docs/INSTALLATION.md).

## Open a VAO

1. Open a 3D Viewport, press **N**, and select the **VAO** tab.
2. Choose **Open VAO**, or drag a `.vao` file into the viewport.
3. Review the overview, explorer, visual-acoustic scene, and diagnostics. Large
   packages are paged rather than silently truncated.
4. If rights are unknown or restricted, review and acknowledge the session
   notice. Acknowledgement does not grant a licence or permission.
5. Load a supported visual realization. Use **Remove** to delete its managed
   Blender data or **Relink** when reopening a `.blend` whose VAO session is gone.
6. For a fully supported playable VAO 0.2.2 package, start performance mode and
   use the reported MIDI-key mapping or pointer controls.

Invalid or incompletely verified packages expose diagnostics only and never
enable payload media. A valid rights-blocked package waits for explicit
per-session acknowledgement; acknowledgement neither changes its validity nor
grants rights. Unsupported operations remain disabled, while an independently
supported, verified visual realization in the same valid package may still be
available.

## Documentation

- [Installation and updates](docs/INSTALLATION.md)
- [Compatibility](docs/COMPATIBILITY.md)
- [VAO 0.4.0/0.5.0 conformance](docs/CONFORMANCE.md)
- [Troubleshooting](docs/TROUBLESHOOTING.md)
- [Security model](docs/SECURITY_AND_TRUST.md) and [security reporting](SECURITY.md)
- [Privacy and local data](docs/PRIVACY.md)
- [Support](SUPPORT.md) and [contributing](CONTRIBUTING.md)
- [Changelog](CHANGELOG.md)

## Citation

Version 0.4.0-rc.1 has reserved DOI
[10.5281/zenodo.22210517](https://doi.org/10.5281/zenodo.22210517) and intended
publication date 2026-08-31. The DOI will resolve after the reviewed Zenodo draft
is published; until then, use [`CITATION.cff`](CITATION.cff) as the authoritative
citation metadata. The prior release remains archived at
[10.5281/zenodo.22134389](https://doi.org/10.5281/zenodo.22134389).

The published VAO Standard 0.4.0 is a separate work with DOI
[10.5281/zenodo.22122774](https://doi.org/10.5281/zenodo.22122774). The exact
0.5.0 candidate source is the commit-pinned
[standard tree](https://github.com/modavis-project/vao-standard/tree/d17b3f188fdf7fadd01ba025383e4feca8def935).
The source repository is [modavis-project/vao-blender](https://github.com/modavis-project/vao-blender).

## Development and release builds

Create a Python 3.11+ environment and run:

```console
python -m pip install -e '.[dev]'
python -m unittest discover -s tests/unit -v
ruff check vao_blender tests scripts
ruff format --check vao_blender tests scripts
python scripts/release_audit.py
```

`release_metadata.toml` is the canonical release identity. Local or host-native
Blender validation is useful development evidence, but it does not create
canonical release artifacts. Canonical bytes must be assembled on Linux x86_64
with both the driver and Blender using Python 3.13.13 and the exact official
[Blender 5.2.1 Linux x64 archive](https://download.blender.org/release/Blender5.2/blender-5.2.1-linux-x64.tar.xz):

- archive SHA-256:
  `a31f524fa99a527d3d52b7f5aaa68c34e1a19d5a1c9473f79c5cc610fd5b10e9`;
- extracted Blender executable SHA-256:
  `c2fd82553c979a7f6ba85202c487aa1173c90db588a67d74d70cc7b0c2bea01c`;
- Blender build hash: `9e2066aef7ef`.

A non-publishing staging build from a clean commit must pass the exact verified
Blender executable path explicitly:

```console
python3.13 scripts/build_extension.py \
  --blender /absolute/path/to/blender-5.2.1-linux-x64/blender \
  --staging --overwrite
```

The staging command writes the versioned candidate directory
`dist/release-candidate/0.4.0-rc.1/`. The final command omits `--staging` and
therefore requires the exact annotated tag at `HEAD`. The build creates three
platform packages, a deterministic source archive, checksums, release evidence,
and a standalone release-set SBOM. The SBOM is a release asset, not a member of
any platform-specific extension ZIP. See
[Release engineering](docs/RELEASE.md) and [Publication](docs/PUBLICATION.md).

## Project context and acknowledgement

This work was developed as part of the **MODAVIS** doctoral research project
(2022–2026). Dominik Ukolov's doctoral research was supported by the German
Academic Scholarship Foundation (*Studienstiftung des deutschen Volkes*).
Funding and affiliations do not imply endorsement of the project's technical
or scientific claims.

## License

VAO Blender is GPL-3.0-or-later. Vendored VAO Standard material and Python wheels
retain their respective licences; see [Third-party notices](THIRD_PARTY_NOTICES.md).
