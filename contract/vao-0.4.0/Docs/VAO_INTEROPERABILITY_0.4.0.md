# VAO 0.4.0 interoperability bindings

VAO composes established domain standards by binding their exact files and identifiers to one release graph. It does not claim wire compatibility with a standard merely because that standard is named.

| Domain | VAO binding | Boundary |
| --- | --- | --- |
| Research object | RO-Crate JSON-LD projection | derivative catalogue; VAO remains fixity authority |
| Transport/preservation | BagIt payload or OCFL inventory/version | storage layer; does not redefine VAO release |
| Citation/discovery | DataCite 4 projection; Zenodo adapter | repository metadata derived from discovery/rights |
| Presentation/alignment | IIIF Presentation 3 and Web Annotation | presentation/annotation IDs map to exact Tracks/selectors |
| Score/performance | MEI realization and element selector | score semantics stay in MEI; VAO binds clock/evidence |
| Spatial acoustics | exact AES69-SOFA realization and response mapping | VAO relates measurements, poses, entities, provenance |
| Object audio | ADM realization and object/channel references | VAO adds release-wide identity and evidence |
| Geometry/scenes | glTF/IFC realization plus coordinate frame | explicit axis/unit/frame prevents implicit transform |
| Control | MIDI 1.0, MIDI 2.0 UMP/MIDI-CI, OSC, host, electrical, custom | VAO declares binding and key/value meaning |
| Provenance | PROV-O | semantic projection; closed JSON evidence remains required |
| Measurement | SOSA/SSN, QUDT, CRMsci/CRMdig | IRIs refine typed VAO records and units |
| Cultural governance | CARE and Local Contexts identifiers | rights/authority/consent still enforced by policy |

## Projection rules

1. Validate the source VAO release first.
2. Preserve source release ID, exact manifest digest, creator order, rights, and representation status.
3. Record projection software, version, parameters, and Activity.
4. If the projection is preserved, create a new logical asset/realization with exact fixity.
5. Never overwrite canonical VAO JSON with a lossy round trip.

`Tools/vao04_interop.py` provides reference RO-Crate, DataCite, IIIF, and OCFL projections. They are informative implementation examples and must be validated against the target standard/version before public deposit. The separately versioned Zenodo companion schema is intentionally labelled as a legacy Depositions API compatibility contract; current Zenodo/InvenioRDM submissions require the live current model, multiple-rights handling, and a repository preview.

The helper is currently written against these explicit targets:

| Projection | Target | Authority |
| --- | --- | --- |
| RO-Crate | 1.3 Recommendation and its versioned JSON-LD context | [RO-Crate 1.3](https://www.researchobject.org/ro-crate/specification/1.3/) |
| DataCite | Metadata Schema 4.7 JSON/API mapping; review against current 4.x rules before deposit | [DataCite metadata mapping](https://support.datacite.org/docs/datacite-xml-to-json-mapping) |
| IIIF | Presentation API 3 | [IIIF Presentation API 3.0](https://iiif.io/api/presentation/3.0/) |
| OCFL | 1.1 inventory model | [OCFL 1.1](https://ocfl.io/1.1/spec/) |

These versions describe the informative projector, not hidden VAO conformance dependencies. A future change to a projection target can be released independently unless it changes normative VAO fields or semantics.

## Format-specific guidance

### RO-Crate

Represent the VAO release as the root Dataset and exact realizations as file-like entities where their access semantics permit. The reference projection uses explicit `discovery.publicationYear` for RO-Crate `datePublished` and rejects its absence; it never mislabels the release-modification instant as publication. It carries every applicable VAO Rights record with a human-readable description, describes each asserted VAO profile as a `Profile`, and links provenance Activities from the root. When packaging a real crate, retain the exact VAO manifest as a first-class file and keep any restricted realization out of a publicly distributed crate. Generic placeholder entities preserve otherwise-unmapped Activity references but do not reproduce their full VAO semantics; the VAO manifest remains authoritative for nested scientific status and carrier fixity.

### BagIt and OCFL

A VAO workspace may be a BagIt payload, or a `.vao` may be a payload file. Avoid conflicting assumptions about which manifest is authoritative. In OCFL, each VAO semantic change is a new immutable VAO release; OCFL inventory history does not authorize in-place VAO mutation.

### DataCite and Zenodo

Map creators/contributors through Agents, `affiliationAgentIds` through organization Agents (including ROR where present), funding/subjects/related identifiers through discovery, and license/access through rights. Use DataCite 4.7 controlled relation/resource types and supply `relationTypeInformation` for `Other`. Check ORCID/ROR check digits and verify attribution/existence against the authoritative registries before deposit. Supply explicit discovery publisher and publication year; the projector rejects their absence instead of inventing them. A concept DOI identifies a family; a version DOI identifies one immutable deposit. Record exact files separately.

### IIIF and Web Annotation

Map presentation ranges/canvases to VAO Tracks and Timebases; map bodies/targets to Annotation selectors. Preserve synchronization uncertainty and discontinuities that IIIF may not express directly.

### AES69-SOFA and ADM

Bind exact media files as realizations. VAO response measurements, source/receiver poses, coordinate frames, channel mappings, and provenance provide cross-file context; do not rewrite standardized internal metadata without a new derivative realization.

### glTF and geometry

Record the glTF exact bytes, coordinate unit/frame, geometry role, selectors, and transform/registration Activity. Do not assume glTF axes/units equal an instrument measurement frame. Convert geodetic coordinates through a documented CRS-aware operation before applying an affine local-frame transform.

### MIDI

Declare protocol version and numbering bases. MIDI note/control identifiers are control-domain values until an explicit VAO tuning/key transform establishes another meaning. MIDI 2 processors validate UMP group/function-block/message/resolution/JR information and optional MIDI-CI identifiers.
