# VAO 0.4.0 release record

- Repository version: **0.4.0**
- VAO format version: **0.4.0**
- Specification status: **final**
- Publication date: **2026-08-27**
- DOI: **[10.5281/zenodo.22122774](https://doi.org/10.5281/zenodo.22122774)**
- Repository: **[modavis-project/vao-standard](https://github.com/modavis-project/vao-standard)**

VAO 0.4.0 is the first public edition of the Virtual Acoustic Object Standard. The release binds the normative specification, schemas, linked-data artifacts, profiles, reference implementation, fixtures, and tests to one version and citation record.

## Release contents

- self-contained normative specification and profile documentation;
- Draft 2020-12 JSON Schemas, JSON-LD context, RDF vocabulary, and SHACL shapes;
- hardened validator and deterministic carrier writer;
- exact release, pack, and receipt cross-validation;
- positive, negative, adversarial, migration, linked-data, and reproducibility fixtures and tests;
- explicit separation between machine conformance and empirical or scientific validity;
- contribution, governance, security, citation, licensing, and release metadata;
- hash-locked validation environment and immutable CI dependencies;
- installable reference-tools wheel with bundled schemas;
- optional Open Knowledge Format 0.2 knowledge bundle;
- version-specific mapping to MODAVIS Ontology Network 0.1.0;
- deterministic source archive and publication-site builders.

## Release integrity

The authoritative release is identified by the signed annotated Git tag `v0.4.0`. The GitHub release carries the deterministic source archive `vao-standard-0.4.0.zip` and its SHA-256 checksum. The same ZIP is deposited under the DOI above; consumers should verify byte equality rather than infer identity from matching filenames.

The machine-readable publication site is generated from the tagged source. Its `release-site-manifest.json` records the exact file inventory, byte sizes, and SHA-256 values. Versioned artifacts remain available below the `/0.4.0/` path.

## Scientific scope

Conformance establishes that a VAO object satisfies the declared structural, semantic, fixity, and profile requirements. It does not certify the truth, adequacy, or scholarly interpretation of a measurement, simulation, reconstruction, rights assertion, or scientific claim. Those judgments remain attributable to the relevant evidence and qualified reviewers.

The prepared and planned publication operations are recorded in [Docs/RELEASE_CHECKLIST.md](Docs/RELEASE_CHECKLIST.md).
