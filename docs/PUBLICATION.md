# Publish a VAO Blender prerelease

Current release state: **prerelease**. Version 0.5.0-rc.1 is dated 2026-11-19 and uses
the Git tag `v0.5.0-rc.1`.

Dispatch `native-release-evidence.yml` from the annotated tag. The workflow
builds the three extension ZIPs on the pinned Blender 5.2.1 Linux host and tests
the exact ZIPs on Blender 5.1.2 and 5.2.1 for each supported platform.

To review the assembled release, download the workflow artifact and run:

```console
python scripts/native_evidence.py verify --release-dir dist/release-candidate/0.5.0-rc.1
cd dist/release-candidate/0.5.0-rc.1
shasum -a 256 -c PUBLICATION_SHA256SUMS
```

For a local rerun, collect the six cell files and use `scripts/native_evidence.py merge`
followed by `assemble` and `verify`. Keep the ZIPs and `SHA256SUMS` unchanged.

Attach the verified extension ZIPs, source archive, release metadata, SBOM,
`SHA256SUMS`, `PUBLICATION_SHA256SUMS`, `RELEASE_EVIDENCE.json`,
`NATIVE_TEST_EVIDENCE.json`, and `RELEASE_NOTES.md` to the GitHub prerelease.
Download the published assets and check the public hashes against the verified
set.
