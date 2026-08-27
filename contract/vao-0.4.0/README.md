# Virtual Acoustic Object (VAO) Standard

The Virtual Acoustic Object (VAO) Standard is an open exchange and preservation standard for digital representations of musical instruments and other acoustic objects. A VAO release can connect descriptive metadata, measurements, recordings, images, 3D models, interaction data, provenance, rights, and exact file identities without replacing the established formats used for those resources.

VAO defines a JSON manifest, a safe ZIP-based `.vao` carrier, optional domain profiles, and a linked-data projection. Its purpose is to make a complex research object understandable, verifiable, transferable, and preservable as a coherent release.

**Version 0.4.0 · Final specification · 27 August 2026**

[Publication site](https://modavis-project.github.io/vao-standard/) · [DOI 10.5281/zenodo.22122774](https://doi.org/10.5281/zenodo.22122774) · [Release record](RELEASE_STATUS.md)

## Start here

| If you want to… | Start with… |
| --- | --- |
| understand the format and its design | [VAO Standard 0.4.0](Docs/VAO_STANDARD_0.4.0.md) |
| create or process VAO data | [Implementer guide](Docs/IMPLEMENTER_GUIDE.md) |
| inspect a small working record | [Minimal manifest](Fixtures/VAO04/workspaces/minimal/vao-manifest.json) |
| assess a conformance claim | [Conformance specification](Docs/VAO_CONFORMANCE_0.4.0.md) |
| select domain-specific requirements | [Profile index](Docs/VAO_PROFILE_INDEX_0.4.0.md) |
| process an untrusted `.vao` carrier | [Security and privacy requirements](Docs/SECURITY_CONSIDERATIONS.md) |

The [schema reference](Docs/VAO_SCHEMA_REFERENCE_0.4.0.md) provides a field-by-field view of the manifest. The [interoperability guide](Docs/VAO_INTEROPERABILITY_0.4.0.md) explains how VAO composes with formats and vocabularies such as AES69-SOFA, ADM, glTF, MEI, MIDI, IIIF, RO-Crate, BagIt, OCFL, PROV-O, SOSA/SSN, QUDT, DataCite, and Local Contexts.

## Scope and scientific boundary

VAO records how digital resources relate to an acoustic object, how they were produced, which evidence supports a statement, and which exact bytes constitute a release. It supports:

- immutable release identity and exact SHA-256 fixity for every realization;
- provenance, protocols, observations, calibrations, analyses, claims, reviews, rights, and consent;
- audio, video, geometry, depth, motion, sensor, event, score, annotation, and trajectory resources;
- physical components, connections, sensors, actuators, states, and playable behaviour;
- spatial and acoustic scenes, measured responses, rendering information, and deterministic conformance traces;
- partial delivery, repository-neutral discovery, and complete preservation carriers.

Conformance establishes that a record follows the declared structural and semantic rules. It is **not** a certificate that a measurement, simulation, interpretation, attribution, rights assertion, or represented object is empirically true or scientifically adequate. Those judgments remain dependent on evidence, documented methods, and qualified review.

VAO is an integration envelope, not a replacement for media formats, repository systems, research-object standards, or domain ontologies. It does not define a renderer, repository service, ontology-reasoning regime, cryptographic trust infrastructure, or rights decision engine.

## VAO and the MODAVIS Ontology Network

VAO and the [MODAVIS Ontology Network](https://modavis-project.github.io/modavis-ontology-network/) have different roles:

- **VAO** defines the exchange package, manifest structure, fixity, profiles, and conformance rules.
- **MODAVIS** provides stable semantic identifiers for musical-instrument and related concepts.

A VAO manifest can use MODAVIS term IRIs directly and records the ontology release that informed it. VAO 0.4.0 binds to MODAVIS Ontology Network 0.1.0 through the versioned [VAO–MODAVIS mapping](Schemas/vao-modavis-mapping-0.4.0.ttl). The mapping is deliberately conservative, and core VAO validation remains self-contained in the VAO schemas and specification.

## Normative release artifacts

| Area | Artifacts |
| --- | --- |
| Human-readable standard | [Specification](Docs/VAO_STANDARD_0.4.0.md), [conformance](Docs/VAO_CONFORMANCE_0.4.0.md), [security](Docs/SECURITY_CONSIDERATIONS.md), and [profile index](Docs/VAO_PROFILE_INDEX_0.4.0.md) |
| JSON validation | [Manifest schema](Schemas/vao-manifest-0.4.0.schema.json) and [carrier schema](Schemas/vao-carrier-0.4.0.schema.json) |
| Linked-data projection | [JSON-LD context](Schemas/vao-context-0.4.0.jsonld), [vocabulary](Schemas/vao-vocabulary-0.4.0.ttl), [MODAVIS mapping](Schemas/vao-modavis-mapping-0.4.0.ttl), and [SHACL shapes](Schemas/vao-shapes-0.4.0.ttl) |
| Release fixity | [Specification-bundle checksums](Schemas/vao-release-bundle-0.4.0.json) |

JSON Schema is the authoritative machine-validation layer. RDF and JSON-LD provide a semantic projection; they do not preserve JSON member order, array order, number lexical form, or the original manifest bytes. Processors must not reconstruct fixity claims from RDF alone.

The checked-in 0.3 schemas are non-normative compatibility dependencies used by the migrator and retained-semantic tests. They are not part of the 0.4.0 specification bundle; see [Schemas/README.md](Schemas/README.md). The [editorial provenance](Docs/EDITORIAL_PROVENANCE.md) explains the relationship between the unpublished 0.3 development material and this release.

## Validate a VAO record

Python 3.11 or newer is recommended. From a source checkout:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --require-hashes -r requirements-lock.txt
python Tools/vao04.py validate Fixtures/VAO04/workspaces/minimal
```

To create a deterministic `.vao` carrier from a valid workspace:

```sh
python Tools/vao04.py pack path/to/workspace path/to/output.vao
```

An installed tools wheel provides the equivalent `vao04` command and includes the schemas required for offline validation. Deterministic scientific claims should cite a released source bundle together with its dependency lock. Complete validation, migration, safe extraction, materialization, and canonical-byte procedures are documented in the [implementer guide](Docs/IMPLEMENTER_GUIDE.md); the complete repository release gate is `python Tools/check_release.py`.

## Release and carrier model

A VAO semantic release consists of a manifest and the exact realizations it references. A carrier is one transport of that release: `bootstrap` and `custom` carriers may contain selected realizations, while a `preservation-closure` contains every realization and marks every asset group complete.

Every `.vao` carrier is a ZIP container with this root layout:

```text
mimetype                         first entry; stored; exact media-type bytes
vao-manifest.json                canonical semantic manifest
META-INF/vao-carrier.json        manifest pin and payload mapping
payload/...                      exact embedded realization bytes
```

The provisional media type is `application/vnd.modavis.vao+zip`; the recommended extension is `.vao`. Both remain provisional pending review by the relevant registries.

## Additional documentation

The non-normative [Open Knowledge Format companion](knowledge/index.md) provides short, machine-discoverable explanations of VAO concepts and links back to normative sources. It complements the standard and does not replace its schemas or conformance rules.

The repository is organized as follows:

```text
Docs/          specification, profiles, guides, and public policy
Schemas/       normative schemas and linked-data artifacts
Tools/         reference validator, deterministic writer, migration, projections
Fixtures/      conformance records, companion descriptors, and sample carriers
Tests/         release, security, conformance, RDF, and reproducibility tests
knowledge/     optional Open Knowledge Format companion
.github/       validation, publication, and contribution configuration
```

Registry submission working files are maintained separately from the versioned standard. The repository contains the standard, implementation resources, public project policies, and reproducible release automation.

## Governance, citation, and license

The responsible editor and main developer is **Dominik Ukolov** ([ORCID](https://orcid.org/0000-0002-7904-3892)), Digital Humanities (Image/Object), Friedrich Schiller University Jena; also Research Group DIGITAL ORGANOLOGY, Leipzig University. Affiliations identify the editor and do not imply institutional endorsement.

Contribution and project policies are documented in [CONTRIBUTING.md](CONTRIBUTING.md), [GOVERNANCE.md](GOVERNANCE.md), [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md), [SECURITY.md](SECURITY.md), and [SUPPORT.md](SUPPORT.md). Citation metadata is available in [CITATION.cff](CITATION.cff) and [codemeta.json](codemeta.json).

Documentation, schemas, semantic artifacts, fixtures, and the knowledge companion are licensed under [CC BY 4.0](LICENSES/CC-BY-4.0.txt). Reference software, tests, and automation are licensed under [Apache-2.0](LICENSES/Apache-2.0.txt). The authoritative per-file mapping is recorded in [LICENSE](LICENSE) and [REUSE.toml](REUSE.toml).
