# Dependency and external-standard policy

VAO aims to remain validatable offline from one versioned specification bundle.

## Normative dependencies

- JSON and URI processing as referenced by the schemas/specification;
- JSON Schema Draft 2020-12;
- ZIP and Deflate/Stored container processing;
- SHA-256 and optional SHA-512;
- RFC 8785 for deterministic trace digest input;
- BCP 14 for requirement terminology.

The pinned VAO schemas and semantics are self-contained. The MODAVIS binding records ontology provenance and can be developmental, released, or embedded; it is not a hidden network dependency for core validation.

## Interoperability dependencies

External formats/vocabularies—such as AES69-SOFA, ADM, glTF, MEI, MIDI, IIIF, RO-Crate, OCFL, DataCite, PROV-O, SOSA/SSN, and QUDT—are used through explicit media types, version IRIs, exact realization bytes, or projections. A processor claims support only for versions it implements.

## Reference-tool dependencies

Python dependencies are declared in `pyproject.toml` and `requirements-dev.txt` with compatible upper bounds. `requirements-lock.txt` freezes the complete cross-platform Python 3.11-or-newer release-gate environment, including the wheel build backend, and authenticates every permitted distribution with SHA-256. CI installs only that lock with `--require-hashes`; release validation and its isolated wheel smoke test perform no network acquisition.

Regenerate the lock deliberately with the command recorded in its header, review the dependency and hash diff, verify both supported Python endpoints, and run the full release gate. Dependency updates require tests and security/license review. The lock is a reproducible test environment, not a normative VAO dependency.

Legacy VAO 0.3 files are internal compatibility dependencies of migration/retained semantic checks and are not normative 0.4 artifacts.
