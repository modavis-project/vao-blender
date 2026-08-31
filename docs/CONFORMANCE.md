# VAO 0.4.0 and 0.5.0 conformance

VAO Blender retains two independent modern contract pins:

- the signed VAO Standard 0.4.0 release archive, SHA-256 `2acbda0a257c7f71e2b57e01617678745de2ecf11197b4687aa623f71d23955d`;
- VAO Standard 0.5.0 candidate commit `d17b3f188fdf7fadd01ba025383e4feca8def935`, whose normative release-bundle inventory has SHA-256 `82efb6ee31353e72c81671e2c6500c51dc223d7f21af4983705933ea6caa5c96`.

The 0.5 pin is explicitly a candidate, not a published-standard claim. Its source commit, normative artifacts, reference validator, local dependencies, licence, and provenance are vendored and verified before use.

For an embedded 0.4 or 0.5 carrier, validation proceeds in this order:

1. preflight archive paths, entry kinds, counts, compression ratios, and size limits;
2. read bounded `META-INF/vao-carrier.json` and `vao-manifest.json` bytes and parse them as strict duplicate-key-free finite JSON;
3. dispatch only on the exact `formatVersion` and apply the matching vendored reference validator;
4. verify immutable manifest identity, carrier ID/mode, complete groups, and one-to-one embedded-realization closure;
5. stream each embedded payload while checking size, SHA-256, and declared chunks;
6. build read-only entity/relation, logical-asset, realization, scientific, physical, and visual-acoustic inspection records;
7. retain the exact validated manifest bytes for session/materialization use and report rights and unsupported runtime capabilities without executing package code.

Both the source-archive hash and every declared embedded payload must be verified
for the result to be valid. Diagnostic or developer calls that skip either pass
produce an explicit `INCOMPLETE` outcome. They cannot authorize cache extraction,
visual materialization, or runtime actions.

VAO 0.5 `carrier-member` distributions may point to another carrier in the same release. Blender validates and exposes those semantic records, but it does not perform network retrieval. Use VAO CLI to retrieve or materialize a local carrier, then open that verified `.vao` in Blender. Bootstrap carriers remain useful for Kinoorgel measurements, MIDI/interface metadata, provenance, and rights even though the release contains no 3D scene.

Unit tests compare the extension and upstream reference validator on the official
minimal 0.5 carrier. The optional Kinoorgel integration gate additionally opens
the final DOI-bound bootstrap carrier, verifies every embedded evidence
realization, checks carrier mode and manifest identity, and installs a metadata
session. Prior verification performed by another tool is not silently trusted as
a substitute for this extension's own requested complete pass.

## Deliberate non-claims

VAO Blender is a conforming consumer only for the capabilities it reports. It is not the VAO standard, a general authoring tool, a certification authority, a malware scanner, a rights-clearance service, or a scientific-validity reviewer. It does not implement modern interaction/runtime execution, remote carrier-member acquisition, or acoustic rendering. Conformance does not establish the truth or adequacy of a measurement, simulation, reconstruction, or rights assertion.

The authoritative 0.4 release is at [VAO Standard 0.4.0](https://github.com/modavis-project/vao-standard/releases/tag/v0.4.0). The exact 0.5 candidate used here is [commit d17b3f1](https://github.com/modavis-project/vao-standard/tree/d17b3f188fdf7fadd01ba025383e4feca8def935).
