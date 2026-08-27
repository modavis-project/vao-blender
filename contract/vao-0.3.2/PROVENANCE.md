# Pinned private VAO 0.3.2 contract

These files were copied byte-for-byte on 2026-08-24 from the authoritative
implemented source at `/Users/dominik/Desktop/Projects/orgrec`. The release
bundle is an implemented editor draft, not an approved or published standard.

- Release bundle SHA-256: `fd4bf15b316b21cd926d7bc70d538951c36fee329d91f7b26ee601c38539f340`
- Manifest schema: `651cfe6b060cf2a4eb735c4b73446cbb84073095fde0995977c4d86293023fdd`
- Carrier schema: `b4bcc49aec153182885f67694f7031ef585bf997b5cf3ee12e08387e0211443e`
- Standard: `e6f64933ca2e17f664e1f91ff39e9e351584c2053ccc2cb2ef0ed3eb3cba3abb`
- Conformance: `014a9fdfcaaf68d3e1447abe17b8838d355e64f24c27d29549f8e404d7d4ef29`
- Acoustic scene guide: `e15d372bb1f334875a4aa3c1fbda18331d27e214ff8f74414acaefdbf3833647`
- OrgRec compatibility statement: `b81a455399cbac2a72a63945cefa347a3e1db1c1bf248ff2d62cca6eb89d3ca7`
- Reference validator: `383ddd889386a32fe50200eb06862191356f6a607c4e405c0d2a2aacbda4f37b`
- Reference schema helper (`Tools/vaom.py`):
  `fb0c27e5f5efa0fe1689fa01789a7f2985d8380669d558804e5bb90f498b024c`
- Release build metadata:
  `5e5ef0785c6f5ab33bb10aec7e6af9474589424dd5849e7dd32dfbb87ecb431d`

VAO-Blender validates the vendored bundle and every listed runtime/reference
artifact at registration. Runtime schema loading is offline; no remote schema
resolution occurs. The add-on executes the pinned reference validator and
schema helper without editing their contract logic; its wrapper only supplies
bounded carrier bytes and a streaming payload digest/size reader.
