# VAO Zenodo repository profile 0.4.0

Profile IRI: `https://w3id.org/modavis/vao/profile/repository/zenodo/0.4.0`

## Scope

This optional compatibility adapter projects a VAO release to the legacy Zenodo Depositions API documented at `https://developers.zenodo.org/#deposition-metadata`. Zenodo's current interface and InvenioRDM records model use different creator, rights, and access structures and support multiple rights statements. This profile does not claim conformance to that current model. Repository-free, embedded, BagIt, OCFL, and other exact distributions remain valid.

## Requirements

- Repository binding identifies the Zenodo instance and supported API profile; the companion projection has the exact legacy `targetAPIProfile` value required by its schema.
- Exact acquisition uses the version record and file identity, not a mutable concept DOI alone.
- Creators and contributors resolve to typed Agents; ORCID and affiliation are projected where present.
- Funding, subjects, related identifiers, access, license, and description derive from VAO discovery/rights without changing them. A mixed-license release MUST NOT be collapsed into the legacy projection's single `license` field; use separate correctly licensed records or the current Zenodo/InvenioRDM workflow with all rights statements.
- A concept DOI may identify the release family; the version DOI identifies one immutable deposited release.
- Deposited carrier and any modular members have independently recorded exact byte size and checksums.
- Legacy projection validation uses `vao-zenodo-metadata-0.4.0.schema.json` before deposit. A current Zenodo/InvenioRDM submission MUST instead be validated against the live target service/API and manually previewed before publication.

The adapter can support one complete carrier deposit or an explicitly described modular record family. Repository metadata is derivative and cannot redefine release identity, creator ordering, consent, rights, or representation status.

The repository's `.zenodo.json` is a separate GitHub-integration artifact, not an instance of this companion schema. Publication and DOI reservation are external side effects and require explicit authorization; the reference repository preparation does not perform them.
