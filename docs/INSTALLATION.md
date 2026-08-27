# Installation

## Release package

1. Confirm Blender 5.1+ and your platform: Windows x64, macOS x64, macOS Apple
   Silicon, or Linux x64.
2. Download the matching `vao_blender-0.3.0-<platform>.zip` and `SHA256SUMS` from
   the same [GitHub release](https://github.com/modavis-project/vao-blender/releases).

   Blender normalizes the filename platform suffixes to `windows_x64`,
   `macos_x64`, `macos_arm64`, and `linux_x64`.
3. Keep only the checksum line for the downloaded ZIP, then verify SHA-256.
   On macOS or Linux:

   ```console
   grep 'vao_blender-0.3.0-<platform>.zip' SHA256SUMS | shasum -a 256 -c -
   ```

   Replace `<platform>` with the suffix from the downloaded filename. On Windows
   PowerShell, run:

   ```powershell
   Get-FileHash .\vao_blender-0.3.0-windows_x64.zip -Algorithm SHA256
   ```

   Compare the printed value with the matching `SHA256SUMS` entry. A mismatch
   means the file must not be installed.
4. In Blender choose **Edit → Preferences → Get Extensions**, open the menu, and
   choose **Install from Disk**.
5. Select the ZIP without unpacking it and enable **VAO Blender** if Blender does
   not enable it automatically.
6. In a 3D Viewport press **N** and open the **VAO** tab.

Use only a package matching the current operating system. An architecture mismatch
usually appears as a dependency import error during add-on registration.

The `v0.3.0-rc.1` GitHub prerelease corresponds to extension version `0.3.0` in
Blender. Blender's extension manifest accepts strict semantic versions and does
not include the release-candidate suffix.

## Update or remove

Close open VAO sessions and save any Blender file containing imported geometry
before updating. Install the new release ZIP from disk; if Blender reports a
conflict, remove the old extension in Preferences, restart Blender, and install
the new one. Removing the extension does not modify source `.vao` packages or
delete geometry already saved into `.blend` files.

The verified media cache is stored in Blender's user data directory unless a
custom location is selected in add-on preferences. Cache deletion is a separate,
explicit operation; see [Privacy](PRIVACY.md).

## Source checkout

Developers can validate a checkout with:

```console
/path/to/blender --command extension validate /path/to/vao-blender
```

Use `python scripts/build_extension.py` to produce installable artifacts. Copying
the source tree directly into Blender's legacy `scripts/addons` directory is not a
supported release installation method.
