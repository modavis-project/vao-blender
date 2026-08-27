# Release engineering

This document is the maintainer runbook for VAO Blender 0.3.0. A release
candidate is identified by the annotated Git tag `v0.3.0-rc.1`; the extension
manifest remains `0.3.0` because Blender extension versions are strict semantic
versions without a prerelease component.

## Release inputs

- Blender 5.1.1 or a compatible 5.1+ build;
- Python 3.11+ for source checks;
- signed VAO Standard tag `v0.4.0`, source commit `40fc376`, release archive
  SHA-256 `2acbda0a257c7f71e2b57e01617678745de2ecf11197b4687aa623f71d23955d`;
- published Zenodo software record at DOI `10.5281/zenodo.22134389`;
- all wheels listed in `blender_manifest.toml` and `wheels/WHEELS_SHA256`;
- a clean Git worktree on the release-candidate commit.

Do not regenerate or edit the vendored standard/reference files. An intentional
upstream update must replace the release archive, extracted files, provenance,
critical hashes, complete inventory, fixtures, tests, and notices as one reviewed
change.

## Automated source gate

```console
python -m unittest discover -s tests/unit -v
ruff check vao_blender tests scripts
ruff format --check vao_blender tests scripts
python -m json.tool .zenodo.json >/dev/null
python scripts/release_audit.py
/path/to/blender --command extension validate .
```

The release audit requires synchronized versions, public governance/docs and
release metadata, the release DOI and repository/standard links, an exact
manifest/wheel inventory, verified wheel hashes, all historical contract pins,
the 0.4.0 normative inventory, and the complete 0.4.0 local file inventory.

## Blender integration gate

Blender 5.1 uses Python 3.13. For a source checkout, extract the matching pinned
wheels to a temporary directory and expose only that directory to Blender:

```console
deps_dir="$(mktemp -d)"
for wheel in wheels/*-none-any.whl wheels/*macosx_11_0_arm64.whl; do
  unzip -q "$wheel" -d "$deps_dir"
done
PYTHONPATH="$deps_dir" /path/to/blender --background --factory-startup \
  --python-use-system-env --python tests/blender/test_integration.py
PYTHONPATH="$deps_dir" /path/to/blender --background --factory-startup \
  --python-use-system-env --python tests/blender/test_vao03_integration.py
PYTHONPATH="$deps_dir" /path/to/blender --background --factory-startup \
  --python-use-system-env --python tests/blender/test_vao04_integration.py
PYTHONPATH="$deps_dir" /path/to/blender --background --factory-startup \
  --python-use-system-env --python tests/blender/test_audio_decode.py
```

Use the `rpds-py` wheel matching the host platform. Tests cover registration,
validation, rights gating, deterministic visual import, frame/pose trace
metadata, interaction-board creation, audio decode/runtime cleanup, rollback, and
unregistration.

## Build and artifact gate

```console
python scripts/build_extension.py --overwrite
(cd dist/release-candidate && shasum -a 256 -c SHA256SUMS)
```

The script rewrites Blender's timestamped build output into a canonical ZIP
(sorted entries, 1980 ZIP epoch, fixed compression). It refuses a dirty worktree,
a missing annotated release tag, or a tag that does not point at `HEAD`. It then
produces and validates:

- `vao_blender-0.3.0-windows_x64.zip`;
- `vao_blender-0.3.0-macos_x64.zip`;
- `vao_blender-0.3.0-macos_arm64.zip`;
- `vao_blender-0.3.0-linux_x64.zip`;
- `vao-blender-0.3.0-rc.1-source.zip`;
- `SBOM.spdx.json`;
- `RELEASE_NOTES.md`;
- `SHA256SUMS`;
- `RELEASE_EVIDENCE.json`.

Inspect each ZIP to confirm it contains exactly one native `rpds-py` wheel for
its platform and all common wheels/contracts. Install the host-matching ZIP into
a temporary Blender profile, open the official minimal 0.4.0 fixture and the
complex visual-acoustic regression fixture, then uninstall it. A final stable
release additionally requires install/open/import/uninstall smoke tests on each
advertised platform; an RC may publish with missing platform smoke results clearly
identified in its release notes.

## Repository and publication gate

Confirm the tag is annotated with `git cat-file -p v0.3.0-rc.1` (or verify its
signature with `git tag -v v0.3.0-rc.1` when signed), then follow
[GitHub and Zenodo publication](PUBLICATION.md). That checklist coordinates the
draft GitHub prerelease with the manually published Zenodo record so both services
carry the same release files.

Publishing the repository, pushing commits or tags, creating the GitHub
prerelease, and publishing the Zenodo record are intentional maintainer actions.
They are not performed by the local build script.

## Promotion to 0.3.0

Resolve RC defects, run the full matrix, update the changelog and citation version,
create a fresh audited commit/tag, and build artifacts from that tag. Do not
rename RC ZIPs or reuse RC hashes for the stable release.
