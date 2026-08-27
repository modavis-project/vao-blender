# VAO Blender 0.3.0-rc.1

This is the first public release candidate of VAO Blender. It adds exact support
for the published [VAO Standard 0.4.0](https://github.com/modavis-project/vao-standard/tree/v0.4.0)
while preserving isolated readers for the historical VAO 0.3.2 and 0.2.2 formats.

## Highlights

- Validate VAO 0.4.0 carrier structure, manifests, release binding, inventories,
  byte sizes, SHA-256 fixity, and immutable references before media access.
- Inspect logical assets, realizations, coordinate frames, poses, measurements,
  response sets, RIR metadata, provenance, and rights records.
- Import an exact, verified embedded GLB visual realization into Blender with
  source provenance attached to the generated collection and objects.
- Work entirely offline. The extension does not execute active package content
  and never modifies the source VAO.
- Install a self-contained package for Windows x64, macOS x64, macOS Apple
  Silicon, or Linux x64.

VAO 0.4.0 interaction/runtime execution and acoustic rendering are intentionally
not implemented. RIRs are inspected as metadata or filter-kernel records; they
are not convolved or rendered.

## Verification completed

- 41 Python unit, contract, security, and regression tests passed.
- The Blender 5.1.1 source integration suite passed on macOS Apple Silicon,
  including registration, VAO 0.2.2, 0.3.2, and 0.4.0 workflows and audio cleanup.
- Blender validated all four split extension archives.
- The installed-extension open/import/uninstall smoke test passed on macOS Apple
  Silicon.
- Dependency wheels, vendored contracts, source metadata, release metadata, and
  artifact checksums pass the automated release audit.

Native installed-extension smoke tests on Windows x64, macOS x64, and Linux x64
remain release-candidate follow-up work. The packages for those platforms have
been structurally validated by Blender but have not yet been executed on their
native hosts.

## Install

Download `SHA256SUMS` and the ZIP matching your platform from this release. Verify
the checksum, then in Blender 5.1+ choose **Edit → Preferences → Get Extensions →
Install from Disk**. Select the ZIP without unpacking it.

See [Installation](docs/INSTALLATION.md), [Compatibility](docs/COMPATIBILITY.md),
and [Troubleshooting](docs/TROUBLESHOOTING.md) for details.

## Research record

This release is archived at
[10.5281/zenodo.22134389](https://doi.org/10.5281/zenodo.22134389). VAO Blender
0.3.0-rc.1 uses
[VAO Standard 0.4.0](https://github.com/modavis-project/vao-standard/releases/tag/v0.4.0),
archived as [10.5281/zenodo.22122774](https://doi.org/10.5281/zenodo.22122774).
