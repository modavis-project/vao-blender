# Registry and persistent-identifier plan

VAO 0.4.0 establishes its versioned GitHub release and Zenodo record before external format-registry submissions are made. The responsible editor has prepared the supporting registration material separately from the standard's versioned source. This document records the intended publication sequence and the scope of each registration.

## Publication status

| System | Planned record | Status for 0.4.0 |
| --- | --- | --- |
| GitHub | signed tag, release archive, and publication site | prepared for author-approved publication |
| Zenodo | version DOI `10.5281/zenodo.22122774` | DOI reserved; metadata and exact-file deposit prepared |
| W3ID | `w3id.org/modavis/vao/` | redirect set prepared; submission follows stable public targets |
| IANA | `application/vnd.modavis.vao+zip` | application prepared; submission follows public specification review |
| PRONOM | VAO format and container signature | proposal and signature evidence prepared |
| Shared MIME-info | `.vao` and internal `mimetype` recognition | draft prepared; upstream submission follows identifier review |
| Wikidata and catalogues | version, license, and identifier statements | deferred until the corresponding public records resolve |

## IANA media type

The editor plans to submit `application/vnd.modavis.vao+zip` through the IANA media-type process using the immutable public specification URL. The prepared application covers binary encoding, the absence of parameters and fragment syntax, ZIP interoperability, security considerations, the `.vao` extension, first-member identification, applications, contact details, and change control.

Submission is scheduled after the public specification and durable contact route resolve and after the subtype collision search has been repeated against the current IANA registry. Until IANA assigns or confirms the media type, VAO 0.4.0 identifies it as provisional.

## W3ID

The prepared W3ID proposal establishes `w3id.org/modavis/vao/` through the `perma-id/w3id.org` repository. Versioned routes are designed to remain immutable. VAO 0.4.0 intentionally defines no normative `/latest/` route; the unversioned project root is a moving discovery location only.

The proposal will be submitted after the GitHub release and publication site provide stable public targets. Redirect responses and versioned artifact routes will be tested before the W3ID change is treated as complete.

## PRONOM

The planned PRONOM proposal describes the format name and version, extension, media type, project, ZIP container structure, internal `mimetype` signature, attribution, and openly licensed sample carriers. Because the acronym and extension have unrelated uses, the proposal requests container-aware identification rather than an extension-only signature.

PRONOM samples have licensing requirements separate from the repository's documentation and implementation licenses. The editor will provide purpose-made samples under suitable terms if the registry cannot accept the existing fixtures without a separate dedication.

## Desktop MIME databases

The prepared Shared MIME-info description combines the `.vao` glob, ZIP magic, and first-member `mimetype`. Upstream submission is planned after the IANA review so that the desktop record does not establish a conflicting identifier prematurely.

## Wikidata and other catalogues

Wikidata statements and possible catalogue entries in FAIRsharing, Research Data Alliance resources, library registries, and preservation-community directories are planned only where the registry's scope matches VAO. These records will cite stable public URLs, the release date, licenses, and assigned identifiers rather than unpublished working locations.

## Zenodo deposit

The version DOI is `10.5281/zenodo.22122774`. The editor reserved it in a manually managed Zenodo record because automatic GitHub ingestion cannot retain a separately reserved DOI. The planned deposit uses the exact deterministic ZIP attached to the GitHub `v0.4.0` release. Byte size and SHA-256 will be compared before the Zenodo record is published, after which the GitHub release can be recorded as an identical representation.

The repository contains both CC BY 4.0 and Apache-2.0 material. `.zenodo.json` therefore uses the truthful `other-open` compatibility value rather than mischaracterizing the entire deposit under one license. The Zenodo record is planned to state both rights and to refer to `REUSE.toml` for the authoritative per-file mapping.

Across these systems, the project uses the same format name, version, media type, extension, editor and change controller, licenses, public specification URL, and security description. Assigned identifiers and registry decisions will be added to the public release record without retroactively changing the immutable 0.4.0 artifacts.
