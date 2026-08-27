# VAO versioning and stability policy

VAO versions the complete specification bundle using `MAJOR.MINOR.PATCH`.

## Version classes

- **Patch:** compatible clarification, additional invalid test for a requirement already stated, tooling fix, or metadata correction that does not intentionally invalidate a conforming release.
- **Minor:** backward-compatible optional fields, profiles, capabilities, vocabulary, or projection behaviour.
- **Major:** required-field, datatype, identifier, archive, semantic, or processing changes that can invalidate or reinterpret earlier conforming releases.

If an apparent erratum changes conformance, it requires a new version even when the editor considers the old text mistaken.

## Three distinct versions

- `formatVersion` identifies serialized VAO contract (`0.4.0`).
- `release.contentVersion` identifies the publisher's acoustic-object release.
- repository candidate labels such as `0.4.0-rc.2` identify pre-publication review of the specification and never appear as `formatVersion`.

## Immutable namespaces

After publication, every artifact below `https://w3id.org/modavis/vao/0.4.0/` is immutable. A moving `/latest/` alias may aid discovery but must redirect to a versioned target and must not be serialized into a preserved release.

Schema/context/profile IRIs change with any conformance-changing version. Release-bundle checksums pin the exact normative bytes.

## Compatibility expectations

A reader should reject an unknown major version for semantic processing while preserving/inventorying it where safe. It may accept a later minor/patch only when it explicitly implements that version; string-prefix guessing is not conformance.

Writers should produce one exact version and never mix schema, context, descriptor, or profile IRIs from different bundles.

## Deprecation

Deprecation is documented in changelog and migration guidance for at least one subsequent release when feasible. Fields are not repurposed. Removal or semantic reuse requires a major version.

## Candidate and release process

Candidates use repository labels/tags such as `0.4.0-rc.2` and remain unpublished drafts until approval. A final release requires clean conformance, immutable artifact digests, citation/license review, registry preparation, responsible-editor approval, and a signed/tagged release according to the recorded publication process.
