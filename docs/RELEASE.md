# Release engineering

This runbook covers extension version `0.4.0-rc.2` and its intended tag
`v0.4.0-rc.2`. `release_metadata.toml` is the canonical, machine-audited identity.

Current release state: **prerelease**. The reserved version DOI is
`10.5281/zenodo.22210517` and the intended publication date is 2026-08-31. The
annotated Git tag and canonical artifact set are prepared locally; no public
GitHub release or Zenodo publication is assumed to exist.

## Immutable inputs

- Blender 5.1.x and 5.2.x, whose Python runtime is compatible with the pinned
  CPython 3.13 wheels;
- published VAO Standard 0.4.0, DOI `10.5281/zenodo.22122774`, release archive
  SHA-256 `2acbda0a257c7f71e2b57e01617678745de2ecf11197b4687aa623f71d23955d`;
- VAO Standard 0.5.0 candidate commit
  `d17b3f188fdf7fadd01ba025383e4feca8def935`, normative bundle SHA-256
  `82efb6ee31353e72c81671e2c6500c51dc223d7f21af4983705933ea6caa5c96`;
- every wheel declared by both `blender_manifest.toml` and
  `wheels/WHEELS_SHA256`;
- the official Blender 5.2.1 Linux x64 archive
  `https://download.blender.org/release/Blender5.2/blender-5.2.1-linux-x64.tar.xz`,
  SHA-256
  `a31f524fa99a527d3d52b7f5aaa68c34e1a19d5a1c9473f79c5cc610fd5b10e9`;
- its extracted Blender executable, SHA-256
  `c2fd82553c979a7f6ba85202c487aa1173c90db588a67d74d70cc7b0c2bea01c`,
  build hash `9e2066aef7ef`, running Blender Python 3.13.13;
- a Linux x86_64 release host running driver Python 3.13.13;
- a clean Git commit for staging and a clean annotated-tag checkout for the final
  artifact set.

Do not edit vendored standard/reference files in place. A reviewed upstream
update replaces its provenance, commit/release pin, normative bundle, complete
file inventory, critical hashes, fixtures, tests, SBOM entry, and documentation
as one change.

## Source gate

```console
python -m pip install -e '.[dev]'
python -m compileall -q vao_blender tests scripts
python -m unittest discover -s tests/unit -v
ruff check vao_blender tests scripts
ruff format --check vao_blender tests scripts
python -m json.tool .zenodo.json >/dev/null
python scripts/release_audit.py
/path/to/blender --command extension validate .
```

These checks may run on a compatible development host and establish source-level
evidence only. They do not certify canonical release bytes. The audit checks one
release identity across the manifest, package, project,
README, citation, Zenodo draft, SBOM, notes, and release tooling. It also checks
the exact wheel inventory and hashes, every historical contract pin, both modern
normative bundles, and complete 0.4.0 and 0.5.0 vendored-file inventories.

## Blender source-integration gate

Extract the pure wheels plus the host's exact pinned `rpds-py` wheel into a
temporary directory. Do not install arbitrary dependencies into Blender's
bundled Python. Replace the `native_wheel` value below with the one wheel whose
tag matches the host under test.

```console
deps_dir="$(mktemp -d)"
native_wheel="wheels/rpds_py-2026.6.3-cp313-cp313-<host-tag>.whl"
for wheel in wheels/*-none-any.whl; do
  unzip -q "$wheel" -d "$deps_dir"
done
unzip -q "$native_wheel" -d "$deps_dir"
for test_path in \
  tests/blender/test_lifecycle.py \
  tests/blender/test_detached_reopen.py \
  tests/blender/test_vao03_integration.py \
  tests/blender/test_vao04_integration.py \
  tests/blender/test_vao05_integration.py \
  tests/blender/test_audio_engine_policy.py
do
  PYTHONPATH="$deps_dir" /path/to/blender --background --factory-startup \
    --python-use-system-env --python "$test_path"
done
```

Run `test_integration.py` and `test_audio_decode.py` only when the separately
generated Cuntz VAO is available under `dist/`. Run `test_kinoorgel_vao05.py`
only with `KINOORGEL_VAO_BOOTSTRAP` set to the reviewed DOI-bound carrier. These
large research artifacts are deliberately not smuggled into the Git repository
or ordinary CI.

The required native matrix is Blender 5.1.2 and 5.2.1 on Windows x64, macOS
ARM64, and Linux x64. The six exact ZIP-bound rows in `RELEASE_NOTES.md` are a
source-freeze record and remain **Not run** after artifact construction. CI
configuration, source validation, or an unbound local run cannot change a row.
Detached post-build evidence is assembled only after the canonical artifacts are
immutable, as described below.

## Staging build

Before creating a tag, commit the reviewed tree and run:

```console
python3.13 scripts/build_extension.py \
  --blender /absolute/path/to/blender-5.2.1-linux-x64/blender \
  --staging --overwrite
(cd dist/release-candidate/0.4.0-rc.2 && shasum -a 256 -c SHA256SUMS)
```

Staging writes `dist/release-candidate/0.4.0-rc.2/` and still requires a clean
checkout. The explicit `--blender` path must resolve to the immutable builder
described above; the script probes the executable, build hash, platform, Blender
Python, and driver Python before building. Its source archive is generated from
the exact `HEAD` commit and its evidence records a null release tag and DOI. This
supports full package inspection without pretending that publication occurred.

The builder validates the source and every artifact with Blender, canonicalizes
ZIP ordering and timestamps, verifies manifest/platform/native-wheel contents,
and emits:

- `vao_blender-0.4.0-rc.2-windows_x64.zip`;
- `vao_blender-0.4.0-rc.2-macos_arm64.zip`;
- `vao_blender-0.4.0-rc.2-linux_x64.zip`;
- `vao-blender-0.4.0-rc.2-source.zip`;
- standalone release assets `SBOM.spdx.json`, `RELEASE_NOTES.md`, and
  `release_metadata.toml`;
- `SHA256SUMS` and `RELEASE_EVIDENCE.json`.

`SBOM.spdx.json` describes the complete three-platform release set and is not
embedded in any platform-specific extension ZIP. Each extension ZIP contains
only its own native `rpds-py` wheel; the standalone SBOM records the hashes of
all three release-set variants.

Inspect the evidence and archive contents. Install the host package in an empty
Blender profile; validate a modern fixture, acknowledge rights, import, remove,
relink, save/reopen, and uninstall. Repeat on each advertised native platform.

## Final tagged build

The publication metadata transition records prerelease status, reserved DOI
`10.5281/zenodo.22210517`, and intended publication date 2026-08-31. After every
pre-build gate passes, rerun the full audit, commit, and create the exact
annotated tag `v0.4.0-rc.2`. Detached native gates run against the resulting
immutable ZIPs. Build them with:

```console
python3.13 scripts/build_extension.py \
  --blender /absolute/path/to/blender-5.2.1-linux-x64/blender \
  --overwrite
```

Without `--staging`, the builder refuses a dirty worktree, a lightweight or
missing tag, a mismatched tag name, or a tag not pointing to `HEAD`. Compare the
tagged result with the approved staging evidence; any source change requires a
fresh staging review.

## Detached native-test evidence

Do not edit or rebuild the tagged base set to record native results.
`SHA256SUMS` and the source-freeze table in `RELEASE_NOTES.md` remain immutable.
The preferred path is the manual **Native release evidence** workflow in
`.github/workflows/native-release-evidence.yml`, dispatched from the exact
annotated tag. It rebuilds the canonical base on the pinned Linux builder, then
runs all six native jobs against the transferred, checksum-verified platform
ZIPs. Every non-smoke test is forced to import the installed package bytes and
dependencies rather than the source checkout. The workflow only uploads Actions
artifacts; it does not create a GitHub release or publish anything.

For inspection or recovery, generate a six-cell input template outside the
release directory:

```console
python scripts/native_evidence.py template \
  --release-dir dist/release-candidate/0.4.0-rc.2 \
  > /absolute/path/to/native-test-input.json
```

Run every cell with the exact ZIP named in the template. Each run must execute
`installed-extension-smoke`, `lifecycle`, `detached-reopen`, `vao-0.3.2`,
`vao-0.4.0`, `vao-0.5.0`, and `audio-policy` on its declared native host. The
provided harness verifies the pinned official Blender archive, probes the exact
Blender/build/Python/system/machine tuple, hashes the extracted executable, and
records the hosted-runner image/version. All six cells must carry the same
`https://github.com/modavis-project/vao-blender/actions/runs/<id>/attempts/<n>`
URL from this repository. Artifact names and downloads are scoped to that attempt.
If an attempt must be repeated, rerun **all jobs** so the current attempt rebuilds
the base and all six cells; a partial-job rerun fails closed. The workflow emits
one complete cell JSON per job; do not hand-edit generated
commit, artifact, archive, host, runner, or hash fields.

The completed `...native-verified-publication-set-attempt-<n>` artifact is the
only canonical publication input. Download and verify that exact directory, and
attach its members without substituting files from the earlier local tagged build
or from another workflow attempt. A local set is useful for byte-for-byte
comparison, never for mixing release lineage.

Merge the six downloaded cell JSON files, then preverify and transactionally
replace the detached evidence set:

```console
python scripts/native_evidence.py merge \
  --release-dir dist/release-candidate/0.4.0-rc.2 \
  --input-dir /absolute/path/to/native-cell-json \
  > /absolute/path/to/completed-native-test-input.json
python scripts/native_evidence.py assemble \
  --release-dir dist/release-candidate/0.4.0-rc.2 \
  --input /absolute/path/to/completed-native-test-input.json
python scripts/native_evidence.py verify \
  --release-dir dist/release-candidate/0.4.0-rc.2
(cd dist/release-candidate/0.4.0-rc.2 && \
  shasum -a 256 -c PUBLICATION_SHA256SUMS)
```

The assembly adds `NATIVE_TEST_EVIDENCE.json` and
`PUBLICATION_SHA256SUMS`. The former is the authoritative native-test
attestation; the latter covers every base release member, the immutable
`SHA256SUMS` file itself, and the attestation. It deliberately does not contain a
self-hash. Use `--overwrite` only to replace an already valid assembled evidence
set with a newly completed, fully verifiable input. Replacement rolls back
ordinary errors. If a process or host stops between directory renames, the next
run restores the one verified hidden backup when the canonical path is absent;
if both generations remain, it preserves both and requires manual recovery.

Pushing commits or tags, creating releases, assigning a DOI, and publishing on
GitHub or Zenodo are separate maintainer actions. The local scripts never perform
them. Continue with [Publication](PUBLICATION.md) only after explicit approval.
