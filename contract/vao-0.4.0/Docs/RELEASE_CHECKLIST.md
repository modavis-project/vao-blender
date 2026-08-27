# VAO 0.4.0 publication operations

This document records the release preparation completed by the responsible editor and the publication operations planned for VAO 0.4.0. Technical readiness does not itself enact repository visibility, tagging, deployment, DOI publication, or registry submission.

## Release design and controls

| Operation | Recorded handling |
| --- | --- |
| Normative specification and schemas | complete |
| Conformance, security, fixture, RDF/SHACL, and reproducibility validation | complete |
| Deterministic publication site and versioned artifact routes | complete |
| Citation, licensing, governance, and release metadata | complete |
| Private GitHub repository and validation matrix | complete |
| Final author inspection | author-controlled release gate |
| Public visibility and signed `v0.4.0` tag | manual operation assigned to the responsible editor |
| GitHub Release and Pages deployment | automated from the approved tag |
| Zenodo record publication | author-managed operation after GitHub artifact verification |
| W3ID and format-registry submissions | follow stable public release targets |

## Technical preparation completed

The reviewed source is validated from a clean checkout with the hash-locked dependency set. The recorded gate is equivalent to:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --require-hashes -r requirements-lock.txt
python Tools/check_release.py
git status --short
git diff --check
```

The gate covers schema validity, maintained fixtures, conformance and security rules, deterministic carriers, RDF/SHACL, metadata, licensing, the installed tools wheel, dependency locks, and the publication surface. The responsible editor's review additionally covers normative prose, affiliations, media-type and extension wording, the DOI and repository identity, W3ID targets, the MODAVIS binding, and release notes.

`Tools/build_release.py` produces the source archive used for release review. It accepts only a clean repository, refuses existing output targets and non-regular tracked inputs, and writes fixed stored ZIP entries. As a result, identical tracked bytes produce identical archives independently of host zlib behaviour. The private release record retains the reviewed commit, tree, archive size and SHA-256, validation result, and accepted limitations.

## GitHub preparation completed

The reviewed baseline has been pushed to `modavis-project/vao-standard` while the repository remains private. Repository description, homepage metadata, topics, issue templates, public policies, and validation workflows are present. No final tag, GitHub Release, Pages deployment, or public artifact has been created during this preparation stage.

The publication workflow accepts only the signed annotated tag `v0.4.0`. It verifies the tag and target commit against the editor's allowed SSH signing key, repeats the release gate, rebuilds the deterministic source archive and site, and refuses publication while repository visibility is private.

## Planned GitHub publication

After the responsible editor approves the reviewed baseline, the repository is planned to become public and GitHub Pages will use GitHub Actions as its source. The editor will then create the signed annotated `v0.4.0` tag from the reviewed commit. A fresh tag-triggered workflow run—not a rerun created under earlier repository settings—will carry out the publication.

The workflow creates a draft GitHub Release, attaches the deterministic ZIP and checksum, deploys the verified Pages artifact, and publishes the GitHub Release only after deployment succeeds. A failed Pages deployment therefore leaves an inspectable draft rather than a public release that lacks its intended specification site.

The editor's post-deployment review will compare the public versioned artifacts and `release-site-manifest.json` with the tagged source and will independently download and verify the GitHub Release archive.

## Planned Zenodo publication

The prepared Zenodo record owns DOI `10.5281/zenodo.22122774`. It is planned to receive the exact ZIP downloaded and verified from the GitHub Release. Automatic GitHub ingestion is not used because it cannot preserve the separately reserved DOI.

Before the Zenodo record is published, the editor will confirm byte-for-byte identity, creator and affiliation metadata, version and date, the relation to the GitHub release, and the CC BY 4.0 / Apache-2.0 per-file rights statement. Publication of the DOI follows that comparison rather than merely matching filenames.

## Planned persistent identifiers and registrations

Once the GitHub and Zenodo records resolve, the prepared W3ID redirects are planned for submission and response testing. The IANA media-type application follows the public specification and collision review. PRONOM, Shared MIME-info, Wikidata, and other appropriate catalogue records follow with the same identifiers, version, licensing, change-control, and security description.

Registry decisions may affect the future status of the provisional media type or extension. Such assignments will be recorded through the public change-control process; they will not silently rewrite the immutable VAO 0.4.0 record.
