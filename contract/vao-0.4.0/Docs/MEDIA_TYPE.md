# VAO media type and file identification

Status: provisional pending IANA review and registration.

## Intended registration

| Field | Value |
| --- | --- |
| Type | `application` |
| Vendor-tree subtype | `vnd.modavis.vao+zip` |
| Full media type | `application/vnd.modavis.vao+zip` |
| Required parameters | none |
| Optional parameters | none |
| Encoding considerations | binary |
| Recommended extension | `.vao` |
| Structured suffix | `+zip` |
| Fragment identifiers | none defined |

The vendor tree is appropriate for an open project/non-commercial organization submitting directly for Expert Review. A future standards-tree registration would require the process and change control expected by RFC 6838 and is not implied by this release.

`VAO` and `.vao` have unrelated informal uses. The project does not claim exclusivity over the acronym or extension. Strong identification always combines the full media type, constrained ZIP structure, exact internal `mimetype`, and VAO manifest identifiers.

## Identification

Extension and generic ZIP magic are weak indicators. Strong identification checks:

1. ZIP structure is valid;
2. first entry is stored and named `mimetype`;
3. its exact 31 bytes are `application/vnd.modavis.vao+zip`;
4. `vao-manifest.json` parses as strict JSON with VAO version identifiers;
5. `META-INF/vao-carrier.json` pins the manifest and release.

The first-member convention provides container signature material for format registries without relying on payload filenames.

## Interoperability and security

Generic ZIP software can list entries but does not understand VAO semantics, safety, rights, profiles, or fixity. VAO processors reject unsafe/duplicate names, links/special entries, encryption, unsupported compression, unknown roots, budget violations, invalid descriptors, and digest mismatch. See [SECURITY_CONSIDERATIONS.md](SECURITY_CONSIDERATIONS.md).

No content-transfer encoding is inherent. HTTP uses binary transfer. The media type has no parameters and no defined fragment syntax in 0.4.0.
