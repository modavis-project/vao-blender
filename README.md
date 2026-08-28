# VAO Blender: A Blender Extension for Virtual Acoustic Objects

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.22134389.svg)](https://doi.org/10.5281/zenodo.22134389)
[![VAO 0.4.0 persistent identifier](https://img.shields.io/badge/W3ID-VAO%200.4.0-2C5F73.svg)](https://w3id.org/modavis/vao/0.4.0/)

VAO Blender lets you open a Virtual Acoustic Object (`.vao`) in Blender, verify
that the package is internally consistent, inspect its metadata, and import a
supported 3D scene. The extension works offline and treats every VAO as untrusted
input.

This repository is prepared for the `v0.3.0-rc.1` prerelease. The extension
implements the published
[VAO Standard 0.4.0](https://github.com/modavis-project/vao-standard/tree/v0.4.0)
and keeps separate compatibility readers for two older formats. The standard's
source repository is [modavis-project/vao-standard](https://github.com/modavis-project/vao-standard).

## What it does

- validates the carrier, manifest, release binding, file inventory, byte sizes,
  and SHA-256 fixity before making packaged media available;
- shows logical assets, realizations, coordinate frames, poses, measurements,
  response sets, room-impulse-response metadata, provenance, and rights records;
- imports a verified embedded GLB realization into a traceable Blender collection;
- leaves the source `.vao` unchanged and stores extracted files in a managed,
  content-addressed cache;
- requests file access only: there is no telemetry, network permission, or
  packaged-script execution.

## Compatibility

VAO versions are matched exactly. A future or otherwise unreviewed version is
rejected instead of being passed to a similar reader.

| VAO format | Status | Available behavior |
| --- | --- | --- |
| 0.4.0 | Published standard | Strict validation, metadata inspection, and exact embedded visual-realization import |
| 0.3.2 | Historical editor draft | Pinned compatibility validation, visual-acoustic inspection, and exact embedded visual-realization import |
| 0.2.2 | Historical development format | Pinned compatibility validation, visual import, supported instrument-interaction compilation, and bounded audio preview |

VAO 0.4.0 interaction/runtime programs and acoustic rendering are not supported.
The extension does not run package code, convolve impulse responses, simulate
acoustics, or invent fallback behavior. See the full
[compatibility matrix](docs/COMPATIBILITY.md) and [0.4.0 conformance statement](docs/CONFORMANCE.md).

## Install

You need Blender 5.1 or newer on one of these platforms:

- Windows x64;
- macOS x64;
- macOS Apple Silicon;
- Linux x64.

Download the ZIP for your platform and `SHA256SUMS` from the same GitHub release.
Verify the ZIP, then in Blender choose **Edit → Preferences → Get Extensions →
Install from Disk** and select it without unpacking it. Detailed macOS, Linux, and
Windows verification commands are in [Installation](docs/INSTALLATION.md).

The release filenames are:

```text
vao_blender-0.3.0-windows_x64.zip
vao_blender-0.3.0-macos_x64.zip
vao_blender-0.3.0-macos_arm64.zip
vao_blender-0.3.0-linux_x64.zip
```

## Open a VAO

1. Open a 3D Viewport, press **N**, and select the **VAO** tab.
2. Choose **Open VAO**, or drag a `.vao` file into the viewport.
3. Wait for validation, then review **Overview**, **Explore**,
   **Visual-Acoustic Scene**, and **Diagnostics**.
4. If the package has unknown or restricted rights, review the notice. You must
   acknowledge it for the current session before accessing media; acknowledgement
   does not grant a license or permission.
5. Choose **Load Visual-Acoustic Scene** when a supported verified GLB realization
   is available.

Imported objects retain package, manifest, entity, asset, realization, frame, and
pose provenance so they can be traced back to the VAO.

## Documentation

- [Installation and updates](docs/INSTALLATION.md)
- [Compatibility](docs/COMPATIBILITY.md)
- [VAO 0.4.0 conformance](docs/CONFORMANCE.md)
- [Troubleshooting](docs/TROUBLESHOOTING.md)
- [Security model](docs/SECURITY_AND_TRUST.md) and [security reporting](SECURITY.md)
- [Privacy and local data](docs/PRIVACY.md)
- [Support](SUPPORT.md) and [contributing](CONTRIBUTING.md)
- [Changelog](CHANGELOG.md)

## Citation

This release candidate is archived at
[10.5281/zenodo.22134389](https://doi.org/10.5281/zenodo.22134389). Citation
metadata is available in [`CITATION.cff`](CITATION.cff). The source repository is
[modavis-project/vao-blender](https://github.com/modavis-project/vao-blender).
The exact VAO Standard 0.4.0 reference is a separate citation with DOI
[10.5281/zenodo.22122774](https://doi.org/10.5281/zenodo.22122774).

## Development and release builds

Create a Python 3.11+ environment, then run the local checks:

```console
python -m pip install -e .
python -m unittest discover -s tests/unit -v
ruff check vao_blender tests scripts
ruff format --check vao_blender tests scripts
python scripts/release_audit.py
```

Build the four platform packages, a deterministic source archive, checksums, the
SBOM, and release evidence with Blender 5.1 installed:

```console
python scripts/build_extension.py --overwrite
```

The exact test, packaging, signing, GitHub, and Zenodo procedures are in
[Release engineering](docs/RELEASE.md) and [Publication](docs/PUBLICATION.md).

## Project context and acknowledgement

This work was developed as part of the **MODAVIS** doctoral research project
(2022–2026). Dominik Ukolov's doctoral research was supported by the German
Academic Scholarship Foundation (*Studienstiftung des deutschen Volkes*).
Funding and affiliations do not imply endorsement of the project's technical
or scientific claims.

## License

VAO Blender is licensed under GPL-3.0-or-later. Vendored VAO Standard material
and Python wheels retain their respective licenses; see
[Third-party notices](THIRD_PARTY_NOTICES.md).
