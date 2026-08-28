# Virtual Acoustic Object (VAO) Standard

[![VAO 0.5.0 persistent identifier](https://img.shields.io/badge/W3ID-VAO%200.5.0-2C5F73.svg)](https://w3id.org/modavis/vao/0.5.0/)

The Virtual Acoustic Object (VAO) Standard is an open exchange and preservation standard for digital representations of musical instruments and other acoustic objects. A release can connect descriptive metadata, measurements, recordings, images, 3D models, interaction data, provenance, rights, and exact file identities without replacing the established formats used for those resources.

**Version 0.5.0 · candidate specification · 28 August 2026**

VAO 0.5 adds cross-carrier delivery: a small bootstrap carrier can describe and selectively materialize exact members of a complete preservation carrier deposited in the same immutable release. The finalized [VAO 0.4.0](https://doi.org/10.5281/zenodo.22122774) release remains immutable and available under its versioned paths.

## Start here

| If you want to… | Start with… |
| --- | --- |
| understand the format | [VAO Standard 0.5.0](Docs/VAO_STANDARD_0.5.0.md) |
| implement dynamic delivery | [Dynamic Delivery profile](Docs/VAO_DYNAMIC_DELIVERY_PROFILE_0.5.0.md) |
| prepare a Zenodo record | [Zenodo profile](Docs/VAO_ZENODO_PROFILE_0.5.0.md) |
| migrate a 0.4 release | [0.4 to 0.5 migration](Docs/MIGRATION_0.4_TO_0.5.md) |
| assess conformance | [Conformance specification](Docs/VAO_CONFORMANCE_0.5.0.md) |
| process an untrusted carrier | [Security and privacy requirements](Docs/SECURITY_CONSIDERATIONS.md) |

The [schema reference](Docs/VAO_SCHEMA_REFERENCE_0.5.0.md) provides a field-by-field view of the manifest. The [profile index](Docs/VAO_PROFILE_INDEX_0.5.0.md) defines optional domain contracts.

## Release and carrier model

A semantic release is one immutable manifest and the exact realizations it identifies. It can be transported by multiple carriers without changing that release:

- a `bootstrap` carrier is the small entry point and embeds discovery/evidence groups;
- a `preservation-closure` embeds every realization and completes every group;
- a `custom` carrier is materialized locally for a use case or byte budget.

The `carrier-member` Distribution allows the bootstrap manifest to locate one exact realization inside the preservation carrier. Resolution is pinned by carrier ID, version persistent identifier, repository record ID, filename, carrier-descriptor digest, member mapping, realization byte size, and SHA-256. When the repository supports byte ranges, a client may retrieve one stored ZIP member without downloading the complete carrier.

Every `.vao` carrier has this root layout:

```text
mimetype                         first entry; stored; exact media-type bytes
vao-manifest.json                canonical semantic manifest
META-INF/vao-carrier.json        carrier ID, manifest pin, payload mapping
payload/...                      exact embedded realization bytes
```

The provisional media type is `application/vnd.modavis.vao+zip`; the recommended extension is `.vao`.

## Validation

Python 3.11 or newer is recommended. From a source checkout:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --require-hashes -r requirements-lock.txt
python Tools/vao05.py validate Fixtures/VAO05/workspaces/minimal
python Tools/vao05.py validate-release \
  Fixtures/VAO05/companions/release.example.json \
  Fixtures/VAO05/workspaces/minimal/vao-manifest.json
```

To create a deterministic carrier:

```sh
python Tools/vao05.py pack path/to/workspace path/to/output.vao
```

The installed tools package provides `vao04` for the finalized 0.4 contract and `vao05` for the current contract.

## Scientific boundary

Conformance establishes that a record follows its declared structural, semantic, fixity, and profile rules. It does not certify that a measurement, simulation, interpretation, attribution, or rights assertion is empirically true or scientifically adequate. Those judgments remain attributable to documented evidence and qualified review.

VAO is an integration envelope, not a replacement for media formats, repository systems, research-object standards, or domain ontologies. VAO 0.5 binds to the MODAVIS Ontology Network 0.1.0 through its versioned [VAO–MODAVIS mapping](Schemas/vao-modavis-mapping-0.5.0.ttl); core validation remains self-contained.

## Repository layout

```text
Docs/          specification, profiles, guides, and policy
Schemas/       versioned schemas and linked-data artifacts
Tools/         validators, writers, migration, and projections
Fixtures/      conformance records and sample carriers
Tests/         release, security, semantic, and runtime tests
knowledge/     informative Open Knowledge Format companion
```

The 0.4.0 artifacts are retained byte-for-byte. The 0.3 schemas are private-draft compatibility dependencies only.

## Governance, citation, and license

The responsible editor and main developer is **Dominik Ukolov** ([ORCID](https://orcid.org/0000-0002-7904-3892)). VAO was developed in the MODAVIS doctoral research project (2022–2026), supported by the German Academic Scholarship Foundation (*Studienstiftung des deutschen Volkes*).

Project policies are documented in [CONTRIBUTING.md](CONTRIBUTING.md), [GOVERNANCE.md](GOVERNANCE.md), [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md), [SECURITY.md](SECURITY.md), and [SUPPORT.md](SUPPORT.md). Documentation, schemas, semantic artifacts, fixtures, and knowledge documents are CC BY 4.0; reference software, tests, and automation are Apache-2.0. The authoritative mapping is in [LICENSE](LICENSE) and [REUSE.toml](REUSE.toml).
