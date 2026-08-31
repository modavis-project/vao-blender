# GitHub and Zenodo publication

Current release state: **unreleased**.

This checklist is intentionally manual. The prepared identity is
`v0.4.0-rc.1`, but its status is `unreleased` and it has no DOI. Do not push,
tag, create a remote release, reserve or publish a deposition, or change that
status without the responsible maintainer's explicit approval.

The DOI `10.5281/zenodo.22134389` identifies the previous 0.3.0-rc.1 release.
It must never be reused as the DOI for this code. The DOI
`10.5281/zenodo.22122774` identifies VAO Standard 0.4.0, not VAO Blender.

## Prepare a new-version draft

1. Complete every pre-build source, Blender, package, and installed-extension
   gate in [Release engineering](RELEASE.md). The detached native-host gate runs
   only after the exact tagged ZIPs exist.
2. In Zenodo's GitHub settings, verify that automatic ingestion is **disabled**
   for this repository. This runbook uses a controlled manual new-version draft;
   an enabled integration automatically ingests GitHub releases and could create
   a second Zenodo version. Stop if that state cannot be verified. Do not enable
   it again for this tag. See Zenodo's
   [integration behaviour](https://help.zenodo.org/docs/github/enable-repository/).
3. From the existing VAO Blender Zenodo record, use **New version** to create a
   draft. Do not publish it. In the DOI field answer **No** to “Do you already
   have a DOI?” and choose **Get a DOI now!**. Record that newly reserved version
   DOI. See Zenodo's
   [DOI reservation procedure](https://help.zenodo.org/docs/deposit/describe-records/reserve-doi/).
4. Update `release_metadata.toml` to `status = "prerelease"` and set only that new
   DOI as `release_doi`. Update the README badge/citation section,
   `CITATION.cff`, `.zenodo.json`, and release notes consistently. Add the actual
   intended publication date only after it is known. Keep the `.zenodo.json`
   `doi` field absent: it means an existing externally assigned DOI, whereas the
   Zenodo-generated value is the draft's reserved DOI.
5. Rerun the release audit. It must reject the previous release DOI if it is
   presented as the current identifier.

Use the prepared metadata as the authoritative transcription source:

- **Title:** VAO Blender: A Blender Extension for Virtual Acoustic Objects
- **Resource type:** Software
- **Version:** 0.4.0-rc.1
- **Creator:** Dominik Ukolov, ORCID 0000-0002-7904-3892
- **License:** GNU General Public License v3.0 or later
- **Access:** Open access
- **Related version:** previous VAO Blender release DOI
  `10.5281/zenodo.22134389`
- **Reference:** VAO Standard 0.4.0 DOI `10.5281/zenodo.22122774`
- **Reference:** VAO Standard 0.5.0 candidate commit
  `d17b3f188fdf7fadd01ba025383e4feca8def935`

Do not add creators, funders, grants, communities, dates, or identifiers from
assumption. In this manual-deposit path, `.zenodo.json` is a reviewed
transcription source only; automatic GitHub ingestion is disabled and is not
relied upon. `CITATION.cff`, the draft UI, and the transcription source must
describe the same release without conflating the software and standard records.

## Publication-state transition gate

The unreleased claim is duplicated intentionally so a partial metadata edit is
detectable. Before the tagged build, update every current-state surface in one
reviewed commit:

- set `release_metadata.toml` to `status = "prerelease"` and add only the actual
  reserved DOI and intended publication date;
- update the README release badge, current-state paragraph, and citation text;
- update the status/current-state text in `RELEASE_NOTES.md` while retaining its
  source-freeze evidence table as an immutable pre-build record;
- update the current-state/download wording in `docs/INSTALLATION.md`;
- update the current-state and tagged-build wording in `docs/RELEASE.md`;
- update this `docs/PUBLICATION.md` current-state marker;
- add the same DOI/date/release state to `CITATION.cff` as allowed by its schema;
- update `.zenodo.json` to the same version, publication date, and exact intended
  GitHub release relationship, while keeping both the current reserved DOI and a
  top-level `doi` field absent; verify the reserved DOI directly in the draft UI.

Rerun `python scripts/release_audit.py` after this coordinated edit and before
committing or tagging. A stale `unreleased` claim, reused prior DOI, omitted
surface, or inconsistent date blocks the tagged build.

## Freeze and build

1. Confirm a clean `main`, review `git diff` and the generated staging evidence,
   and rerun all gates.
2. Commit the publication-metadata update.
3. Create the exact annotated tag `v0.4.0-rc.1` at that commit. Do not move or
   reuse it.
4. On the canonical Linux x86_64 release host, run Python 3.13.13 with the exact
   verified Blender 5.2.1 executable:

   ```console
   python3.13 scripts/build_extension.py \
     --blender /absolute/path/to/blender-5.2.1-linux-x64/blender \
     --overwrite
   ```

   The final mode verifies the annotated tag at `HEAD`, refuses the `unreleased`
   state, and rejects a builder that differs from the pinned archive SHA-256
   `a31f524fa99a527d3d52b7f5aaa68c34e1a19d5a1c9473f79c5cc610fd5b10e9`,
   executable SHA-256
   `c2fd82553c979a7f6ba85202c487aa1173c90db588a67d74d70cc7b0c2bea01c`,
   build hash `9e2066aef7ef`, Blender Python 3.13.13, or driver Python 3.13.13.
5. Verify every `SHA256SUMS` entry and review the SBOM, release metadata, release
   evidence, archive member inventories, native wheel selection, and source
   commit.
6. Keep the canonical artifacts unchanged while completing every detached
   Blender-version/platform test cell. Any failure stops publication and requires
   a new candidate identity if artifact bytes must change.

## Assemble detached native evidence

Generate the input template outside the release directory after the tagged base
set is complete:

```console
python scripts/native_evidence.py template \
  --release-dir dist/release-candidate/0.4.0-rc.1 \
  > /absolute/path/to/native-test-input.json
```

Dispatch `.github/workflows/native-release-evidence.yml` manually from the exact
annotated tag. It creates no release and publishes nothing; it only uploads a
canonical base set, six cell JSON artifacts, and a verified publication-set
artifact for maintainer review. Complete all six exact artifact-bound cells:
Blender 5.1.2 and 5.2.1 on Windows
x64 using `vao_blender-0.4.0-rc.1-windows_x64.zip`, macOS ARM64 using
`vao_blender-0.4.0-rc.1-macos_arm64.zip`, and Linux x64 using
`vao_blender-0.4.0-rc.1-linux_x64.zip`. Each cell must pass every required test,
import the installed ZIP bytes, verify the pinned official Blender archive, and
record the executable hash, Blender/build/Python/system/machine probe, hosted
runner image/version, UTC time, and this repository's exact Actions run-attempt
URL. All base, cell, and completed-set artifact names are attempt-scoped, and all
six cells must identify one run attempt. If retrying, rerun all jobs; partial-job
reruns intentionally cannot reuse an earlier attempt's base set.

The workflow performs the merge automatically. To reconstruct it from downloaded
cell artifacts, place only the six JSON files in one directory and run:

```console
python scripts/native_evidence.py merge \
  --release-dir dist/release-candidate/0.4.0-rc.1 \
  --input-dir /absolute/path/to/native-cell-json \
  > /absolute/path/to/completed-native-test-input.json
python scripts/native_evidence.py assemble \
  --release-dir dist/release-candidate/0.4.0-rc.1 \
  --input /absolute/path/to/completed-native-test-input.json
python scripts/native_evidence.py verify \
  --release-dir dist/release-candidate/0.4.0-rc.1
(cd dist/release-candidate/0.4.0-rc.1 && \
  shasum -a 256 -c PUBLICATION_SHA256SUMS)
```

`NATIVE_TEST_EVIDENCE.json` is the authoritative detached attestation and
`PUBLICATION_SHA256SUMS` binds it to the unmodified canonical build. The
source-freeze table embedded in `RELEASE_NOTES.md` deliberately remains “Not
run”; never rewrite a base release asset to record later results.

Download the exact
`vao-blender-0.4.0-rc.1-native-verified-publication-set-attempt-<n>` workflow
artifact from the single accepted run attempt, verify it in a fresh directory,
and use **only its members** for the release attachments below. Compare every
member with any locally built final set, but never mix local base files, cells
from another attempt, or independently assembled evidence into the uploaded set.

The draft GitHub prerelease should be titled `VAO Blender 0.4.0-rc.1` and use
`RELEASE_NOTES.md`. Attach:

- `vao_blender-0.4.0-rc.1-windows_x64.zip`;
- `vao_blender-0.4.0-rc.1-macos_arm64.zip`;
- `vao_blender-0.4.0-rc.1-linux_x64.zip`;
- `vao-blender-0.4.0-rc.1-source.zip`;
- `SHA256SUMS` and `RELEASE_EVIDENCE.json`;
- `NATIVE_TEST_EVIDENCE.json` and `PUBLICATION_SHA256SUMS`;
- `SBOM.spdx.json`, `RELEASE_NOTES.md`, and `release_metadata.toml`.

Upload that workflow set's exact source ZIP to the Zenodo new-version draft. The platform ZIPs
and machine-readable evidence can remain on GitHub when the Zenodo record links
to that exact release. Preview both drafts and compare title, version, creator,
licence, identifiers, filenames, byte sizes, and hashes.

## Publish and verify

1. Publish the GitHub item as a **prerelease**.
2. Download all attachments into a fresh directory. From the exact tag checkout,
   run:

   ```console
   python scripts/native_evidence.py verify \
     --release-dir /absolute/path/to/downloaded-release
   ```

   Verify `PUBLICATION_SHA256SUMS` and confirm the immutable tag resolves to the
   evidence commit. `SHA256SUMS` remains the nested immutable base-build
   inventory.
3. Recheck the reserved Zenodo DOI and publish the new-version draft. Zenodo
   publication is irreversible; never click Publish as a test.
4. Verify DOI resolution, bidirectional repository/release links, both standard
   references, and the source ZIP checksum.
5. In a post-release commit, keep canonical status `prerelease`: it means this
   publicly released software version is an RC, not that its records are still
   private. Stable releases alone use `published`. Do not rebuild or alter the
   tagged artifacts.

Keep automatic GitHub ingestion disabled after this release. Migrating to
integration-driven archiving is a separate release-process change and must first
remove the manual draft/publish path so one GitHub release can never create two
Zenodo versions.

Metadata-only corrections use the repository or Zenodo edit workflow where
permitted. Any file or executable change requires a new version, new tag, fresh
artifacts, fresh evidence, and a new Zenodo-version draft.
