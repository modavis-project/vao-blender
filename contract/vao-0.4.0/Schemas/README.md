# VAO schemas and semantic artifacts

## Normative 0.4.0 artifacts

- `vao-manifest-0.4.0.schema.json`
- `vao-carrier-0.4.0.schema.json`
- `vao-release-0.4.0.schema.json`
- `vao-pack-manifest-0.4.0.schema.json`
- `vao-materialization-receipt-0.4.0.schema.json`
- `vao-zenodo-metadata-0.4.0.schema.json`
- `vao-context-0.4.0.jsonld`
- `vao-vocabulary-0.4.0.ttl`
- `vao-shapes-0.4.0.ttl`
- `vao-release-bundle-0.4.0.json`

The versioned 0.4.0 artifact bytes are immutable in the release. Candidate changes are accompanied by regeneration through `python Tools/update_release_bundle.py`; CI uses `--check` to reject stale fixity records.

## Legacy compatibility artifacts

The `0.3` schemas and unversioned `vao-manifest.schema.json` are private-draft compatibility dependencies used by migration and retained-semantic regression checks. They are not part of the 0.4.0 specification bundle and must not be advertised as the current public standard.

JSON Schemas use Draft 2020-12. JSON-LD is the semantic projection; canonical VAO JSON controls core syntax and fixity.

The Zenodo companion schema is a deliberately explicit legacy Depositions API compatibility contract, not a current InvenioRDM records-API schema. Its required `targetAPIProfile` prevents an implementation from silently confusing the two interfaces.
