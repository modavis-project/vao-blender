# Installation

Current release state: **prerelease**. The filenames below identify the frozen
candidate. Public downloads remain unavailable until the exact native evidence
matrix is complete and the GitHub prerelease is published.

## Release package

1. Use Blender 5.1.x or 5.2.x on Windows x64, macOS Apple Silicon, or Linux x64.
   Blender 5.3+ is deliberately outside the manifest range until
   its Python ABI and integration behavior have been tested.
2. After publication, download `PUBLICATION_SHA256SUMS`, `SHA256SUMS`,
   `NATIVE_TEST_EVIDENCE.json`, and the matching
   `vao_blender-0.4.0-rc.2-<platform>.zip` from the same
   [GitHub release](https://github.com/modavis-project/vao-blender/releases).
   Blender uses the suffixes `windows_x64`, `macos_arm64`, and `linux_x64` in
   the generated filenames.
3. Verify the package before installing it. On macOS or Linux:

   ```console
   grep 'vao_blender-0.4.0-rc.2-<platform>.zip' PUBLICATION_SHA256SUMS | shasum -a 256 -c -
   ```

   On Windows PowerShell:

   ```powershell
   Get-FileHash .\vao_blender-0.4.0-rc.2-windows_x64.zip -Algorithm SHA256
   ```

   Compare that value with the matching line in `PUBLICATION_SHA256SUMS`. Do not
   install a file whose checksum differs.
4. In Blender choose **Edit → Preferences → Get Extensions**, open the menu, and
   choose **Install from Disk**.
5. Select the ZIP without unpacking it and enable **VAO Blender** if necessary.
6. Open a 3D Viewport, press **N**, and select the **VAO** tab.

The GitHub prerelease tag and Blender extension version are both `0.4.0-rc.2`
(the tag adds the conventional `v` prefix). The candidate metadata carries the
Zenodo-reserved version DOI and remains private until the release records are
published by a maintainer.
`SHA256SUMS` binds the immutable canonical build set.
`NATIVE_TEST_EVIDENCE.json` binds six installed-extension test cells to those
exact platform ZIP hashes, and `PUBLICATION_SHA256SUMS` binds the base inventory
plus that detached attestation as the complete publication set.

## Update or remove

Stop performance mode and close open VAO sessions before updating. If Blender
reports a conflict, remove the old extension in Preferences, restart Blender,
and install the new package. Removing the extension never modifies source `.vao`
packages. Geometry already saved in a `.blend` remains ordinary Blender data with
VAO provenance and can be explicitly relinked after reinstalling the extension.

The verified media cache is separate from installed extension files. Its default
location is under Blender's user-data directory; a custom location must be an
explicitly managed cache root. Cache cleanup skips files protected by active
sessions. Deleting the extension does not silently delete the cache; use the
preference controls described in [Privacy](PRIVACY.md).

## Source checkout

Developers can validate a checkout with a local compatible Blender:

```console
/path/to/blender --command extension validate /path/to/vao-blender
```

That command validates source compatibility only. It does not create or certify
canonical release artifacts. Canonical artifacts require Linux x86_64,
Python 3.13.13 for both driver and Blender, and the exact official Blender 5.2.1
Linux x64 archive
`https://download.blender.org/release/Blender5.2/blender-5.2.1-linux-x64.tar.xz`
(archive SHA-256
`a31f524fa99a527d3d52b7f5aaa68c34e1a19d5a1c9473f79c5cc610fd5b10e9`,
executable SHA-256
`c2fd82553c979a7f6ba85202c487aa1173c90db588a67d74d70cc7b0c2bea01c`,
build hash `9e2066aef7ef`).

A clean, untagged staging build is intentionally distinct from a final tagged
release build:

```console
python3.13 scripts/build_extension.py \
  --blender /absolute/path/to/blender-5.2.1-linux-x64/blender \
  --staging --overwrite
```

The staging command writes `dist/release-candidate/0.4.0-rc.2/`. The final
command omits `--staging` and refuses a dirty checkout, a missing or lightweight
tag, or a tag that does not point to `HEAD`. Copying the source tree into
Blender's legacy `scripts/addons` directory is not a supported installation
method.
