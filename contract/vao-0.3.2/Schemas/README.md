# VAO schema routing

- `vao-manifest.schema.json`, `vao-context.jsonld`, and `vao-vocabulary.ttl`
  remain the VAO 0.2 compatibility-line artifacts.
- `vao-manifest-0.3.schema.json`, `vao-context-0.3.jsonld`, and
  `vao-vocabulary-0.3.ttl` are the VAO 0.3.2 editor's-draft artifacts.
- `vao-carrier-0.3.schema.json`, `vao-release-0.3.schema.json`,
  `vao-pack-manifest-0.3.schema.json`,
  `vao-materialization-receipt-0.3.schema.json` define the separate 0.3
  carrier, repository, pack, and runtime records.
- `vao-zenodo-metadata-0.3.schema.json` defines the optional Zenodo deposit
  metadata projection. It is not required by VAO Core or repository-free use.

The 0.3.2 manifest schema closes the Spatial/Acoustics scene model, including
coordinate frames, poses, geometry bindings, stable source/receiver
measurements, response sets, and realization-specific impulse-response layout.

The 0.3.2 release descriptor defaults to one modular publication record and
can instead declare an exact root/member record family. The same `/0.3` schema,
context, vocabulary, and profile IRIs identify this pre-public compatibility
line; exact artifact dispatch uses `formatVersion: "0.3.2"`.

Version dispatch uses the manifest `formatVersion`; processors must not apply
the 0.2 schema to a 0.3 manifest or vice versa.
