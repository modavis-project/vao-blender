# VAO Blender 0.5.0-rc.2

Current release state: **prerelease**.
Status: **prerelease**.
Release date 2026-11-19.

VAO Blender opens 0.6.0 carriers offline, checks their manifests and payload,
and imports supported embedded GLB geometry. MMIC 1.0.0 records appear in the
inspector. Use the VAO reference tools for MMIC domain validation, decoding,
comparison, and generation.

The VAO 0.4.0 reader, the pinned 0.5.0 candidate reader, and the legacy readers
remain available.

## Installation

Download the ZIP for your platform and check it against
`PUBLICATION_SHA256SUMS`. In Blender, choose **Preferences → Get Extensions →
Install from Disk** and select the ZIP.

## Native tests

The `native-release-evidence.yml` workflow records the result for each exact
ZIP in `NATIVE_TEST_EVIDENCE.json`.

| Blender | Platform | Release check |
| --- | --- | --- |
| 5.1.2 | Windows x64 | Required |
| 5.1.2 | macOS ARM64 | Required |
| 5.1.2 | Linux x64 | Required |
| 5.2.1 | Windows x64 | Required |
| 5.2.1 | macOS ARM64 | Required |
| 5.2.1 | Linux x64 | Required |
