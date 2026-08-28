# VAO Zenodo repository profile 0.5.0

Profile IRI: `https://w3id.org/modavis/vao/profile/repository/zenodo/0.5.0`

## Scope

This optional profile maps one immutable VAO release to one Zenodo record. It uses Zenodo as a byte repository and DOI authority while keeping the VAO manifest and `vao-release.json` authoritative for VAO structure and fixity.

## Required record structure

The preferred record has one semantic release and exactly two deposited `.vao` carriers:

1. `<slug>-bootstrap-<content-version>.vao` — the small entry point, containing the full manifest, measurements, signal maps, documentation/evidence needed for discovery, and other explicitly selected bootstrap groups;
2. `<slug>-preservation-<content-version>.vao` — the preservation closure, containing every declared realization, including all normalized access and mobile representations selected for preservation.

It also contains these predictable companions:

- `README.pdf` — human-readable scope, credits, rights, use instructions, and file guide;
- `vao-manifest.json` — the exact manifest bytes embedded in both carriers;
- `vao-release.json` — the publication topology and fixity record;
- `SHA256SUMS` — SHA-256 checksums for deposited content files, excluding itself and `vao-release.json` to avoid checksum cycles.

No measurement workbook, signal map, audio derivative, or miscellaneous supplementary file is deposited loose at the record root. Such content is represented as a Realization inside both the manifest and the appropriate carrier. A source workbook may be preserved as evidence inside the preservation closure even when normalized observations are already semantic manifest records.

## Identity and resolution

- The version DOI identifies the immutable deposited release. The concept DOI identifies the version family and MUST NOT be used as the sole byte-resolution target.
- The release descriptor uses `single-record` topology and inventories every deposited file except itself. Its carrier entries record carrier ID/mode, full-file SHA-256, manifest fixity, carrier-descriptor fixity, and complete groups.
- Every `carrier-member` Distribution resolves to the preservation carrier through the exact version DOI, record identifier, filename, and carrier ID.
- Both carriers contain byte-identical `vao-manifest.json` members. The semantic release does not change when a user downloads a different carrier or creates a custom local carrier.
- A resolver SHOULD use HTTP byte ranges to inspect the preservation carrier and retrieve an individual stored ZIP member when the repository supports ranges. It MUST fall back to downloading the carrier when ranges are unavailable and clearly report that transfer cost before doing so.

## Representation policy

The preservation closure SHOULD contain the authentic/source representation where rights permit, a broadly supported lossless access representation when it adds interoperability, and one documented mobile/audition representation when useful. These are distinct Realizations of the same Logical Asset with explicit derivation provenance and representation status. Lossy encodings MUST NOT inherit sample-loop boundaries unless those boundaries were validated on the encoded bytes.

The record does not deposit separate “lossless”, “mobile”, or application-specific VAO editions. The CLI materializes a custom carrier from the preservation closure according to requested groups, capabilities, media types, or byte budgets. Arbitrary transcoding is a derivation operation and produces new realization identities; it cannot be presented as retrieval of deposited VAO bytes.

## Metadata, rights, and credits

- Zenodo resource type is `dataset` unless another type is demonstrably more accurate.
- The title identifies the instrument, the VAO content version, and the release as a virtual acoustic object.
- Creators and contributors follow the VAO discovery order and typed roles; affiliations and ORCIDs are supplied where known and verified.
- The record license and every governed realization use compatible rights. Mixed-license content is partitioned into separate records or described with all applicable rights; it is never collapsed into one inaccurate license.
- Funding awards, hosting institution, project leadership/coordination, recording, measurements, restoration, production/maintenance, and VAO development acknowledgments appear in the record description and `README.pdf`.
- The musiXplora instrument identifier is a related identifier with a descriptive relation, and project/funding identifiers are represented as funding or related identifiers as supported by the live form.

## Operational requirements

Zenodo currently documents a 50 GB total/per-file limit and 100 files per record. A release exceeding either limit requires an explicitly related record family or a different repository; it MUST NOT silently change this profile's one-record semantics. The uploader validates the prepared metadata against the live target service and previews the complete draft before publication. Publication is an external, irreversible action and requires explicit human approval.

The versioned `vao-zenodo-metadata-0.5.0.schema.json` remains a compatibility projection for the documented Depositions API. It is not a substitute for validation by the current Zenodo service.
