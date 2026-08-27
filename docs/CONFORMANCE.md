# VAO 0.4.0 conformance

VAO Blender pins the signed VAO Standard 0.4.0 release archive at SHA-256
`2acbda0a257c7f71e2b57e01617678745de2ecf11197b4687aa623f71d23955d`.
The vendored normative release-bundle inventory, critical reference-tool hashes,
and a complete local file inventory are verified before a 0.4.0 package is read.

For an embedded carrier, validation proceeds in this order:

1. preflight archive paths, entry kinds, counts, compression ratios, and size
   limits;
2. parse `META-INF/vao-carrier.json` and the manifest as duplicate-key-free,
   finite strict JSON;
3. apply the exact 0.4.0 carrier and manifest schemas and immutable context/release
   identities through the vendored upstream reference validator;
4. prove carrier closure and one-to-one embedded realization mapping;
5. stream every declared payload once while checking byte size and SHA-256;
6. build the inspection graph, realization index, visual-acoustic records,
   capability outcomes, rights gate, and deterministic diagnostics.

Unit tests run the extension and upstream reference validator over official
positive fixtures and local negative/adversarial mutations. A complex
visual-acoustic fixture verifies exact realization choice, frames, transforms,
poses, measurements, response sets, RIR fixity/provenance, and Blender trace
metadata.

## Deliberate non-claims

VAO Blender is a conforming consumer only for the capabilities it reports. It is
not the VAO standard, a general authoring tool, a certification authority, a
malware scanner, a rights clearance service, or a scientific-validity reviewer.
It does not currently implement 0.4.0 interaction/runtime execution or acoustic
rendering. Machine conformance never establishes the truth or adequacy of a
measurement, simulation, reconstruction, or rights assertion.

The authoritative specification and conformance rules are in the
[VAO Standard 0.4.0 release](https://github.com/modavis-project/vao-standard/releases/tag/v0.4.0).
