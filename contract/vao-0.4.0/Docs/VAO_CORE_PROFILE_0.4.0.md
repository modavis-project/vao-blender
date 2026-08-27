# VAO Core profile 0.4.0

Profile IRI: `https://w3id.org/modavis/vao/profile/core/0.4.0`

## Applicability

Every VAO 0.4.0 manifest embeds and claims this profile.

## Requirements

A Core release:

1. uses the immutable 0.4.0 schema, context, type, and version identifiers;
2. identifies one immutable release and at least one semantic Entity;
3. separates logical assets from exact realizations;
4. gives every realization media type, byte size, SHA-256, representation status, rights, provenance, technical metadata, and distribution references;
5. resolves primary/focus entities, asset/realization, rights/provenance, relation, and release references;
6. embeds an IRI/version/capability record for Core and includes the profile IRI in `conformsTo`;
7. includes the required closed registries even when empty;
8. supplies an integrity contract and explicit MODAVIS binding status;
9. preserves unsupported extension data without treating it as core semantics;
10. passes strict JSON, JSON Schema, and semantic validation.

## Processor behaviour

A Core reader may display or inventory a realization without decoding its media, but it must preserve exact identity and report unsupported media/capabilities. A Core writer creates a new release when any semantic assertion or referenced exact byte sequence changes.

Core conformance does not establish scientific validity, authenticity, rights clearance, renderer support, or complete offline availability.

## Mandatory capability IRIs

- `https://w3id.org/modavis/vao/vocab/capability/core-graph`
- `https://w3id.org/modavis/vao/vocab/capability/fixity`
