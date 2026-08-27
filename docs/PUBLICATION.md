# GitHub and Zenodo publication

This is the maintainer checklist for publishing `v0.3.0-rc.1`. Repository
metadata treats the Zenodo record as published at the final release DOI; the
existing Zenodo deposition is published manually immediately after the GitHub
prerelease.

## DOI route for this release

The release is archived at `10.5281/zenodo.22134389`. This record is maintained
separately from Zenodo's automatic GitHub integration, which would create another
deposit and DOI. Therefore:

- use the existing Zenodo deposition and upload this release manually;
- do not enable automatic GitHub ingestion for this first release;
- do not create a second Zenodo deposit;
- do not put the Zenodo release DOI in the `.zenodo.json` `doi` field, which is
  for a DOI assigned by an external publisher. The release DOI is recorded in
  `CITATION.cff`, the README, and the Zenodo record itself.

The repository still includes `.zenodo.json` because it is a reviewable source of
Zenodo-specific descriptive metadata. Zenodo uses `.zenodo.json` instead of
`CITATION.cff` when both are present during automatic GitHub ingestion; GitHub
uses `CITATION.cff` for its citation panel.

## Prepared record metadata

Use `.zenodo.json` and `CITATION.cff` to verify the release record:

- **Title:** VAO Blender: A Blender Extension for Virtual Acoustic Objects
- **Resource type:** Software
- **Version:** 0.3.0-rc.1
- **Publication date:** 2026-08-27
- **Creator:** Dominik Ukolov; ORCID 0000-0002-7904-3892; Digital Humanities
  (Image/Object), Friedrich Schiller University Jena and Research Group DIGITAL
  ORGANOLOGY, Leipzig University
- **License:** GNU General Public License v3.0 or later
- **Access:** Open access
- **DOI:** 10.5281/zenodo.22134389
- **Related software:** `https://github.com/modavis-project/vao-blender`
- **References:** VAO Standard 0.4.0 at
  `https://github.com/modavis-project/vao-standard/tree/v0.4.0` and
  `https://doi.org/10.5281/zenodo.22122774`

Do not add another creator, funder, grant, or community unless it has been reviewed
and supplied by the responsible maintainer.

## Final local gate

1. Confirm `main` contains the intended single root commit and no uncommitted
   files.
2. Confirm annotated tag `v0.3.0-rc.1` points to `main`.
3. Run the automated source and Blender integration gates in `RELEASE.md`.
4. Run `python scripts/build_extension.py --overwrite` from the tagged commit.
5. Verify every line in `dist/release-candidate/SHA256SUMS` and review
   `RELEASE_EVIDENCE.json` and `SBOM.spdx.json`.
6. Install, open/import, and uninstall the host-matching ZIP in a clean Blender
   profile. Keep the other native-host smokes clearly listed as outstanding RC
   work in `RELEASE_NOTES.md`.

## Prepare both release records

1. Confirm `modavis-project/vao-blender` is public and its description, DOI
   homepage, and topics are correct.
2. Push `main` and annotated tag `v0.3.0-rc.1`. Do not move the tag after the
   GitHub release is published.
3. Create a **draft GitHub prerelease** from the tag, title it
   `VAO Blender 0.3.0-rc.1`, and use `RELEASE_NOTES.md` as the description.
4. Attach the four platform ZIPs and these common files from
   `dist/release-candidate`:
   - `vao-blender-0.3.0-rc.1-source.zip`;
   - `SHA256SUMS`;
   - `RELEASE_EVIDENCE.json`;
   - `SBOM.spdx.json`;
   - `RELEASE_NOTES.md`.
5. Open the existing Zenodo deposition for DOI `10.5281/zenodo.22134389`. Verify
   its DOI and metadata before replacing or adding files.
6. Upload only `vao-blender-0.3.0-rc.1-source.zip` to the Zenodo software record.
   Keeping one source ZIP makes the record eligible for Software Heritage
   archival. The platform packages, checksums, SBOM, release notes, and evidence
   remain attached to the GitHub release and are linked from Zenodo metadata.
7. Preview both drafts. Check titles, version, creator order, license, description,
   related identifiers, filenames, file sizes, and checksums.

## Publish and verify

1. Publish the GitHub release as a **prerelease**.
2. Download every GitHub attachment, re-check it against `SHA256SUMS`, and confirm
   the tag still resolves to the audited commit.
3. Publish the existing Zenodo deposition immediately after the GitHub prerelease.
   Zenodo publication is irreversible; confirm the DOI once more immediately
   before clicking **Publish**.
4. Confirm `https://doi.org/10.5281/zenodo.22134389` resolves and that the Zenodo
   record links to the public repository and VAO Standard 0.4.0.
5. Download the Zenodo source ZIP and compare its SHA-256 value with the matching
   GitHub release asset. Correct metadata-only mistakes through Zenodo's edit
   workflow; create a new version for changed files.

For a later release, use Zenodo's **New version** action from this record so the
version DOI changes while the concept record groups the releases. Decide whether
to keep the manual route or switch to GitHub integration before that release; do
not combine both routes for the same tag.
