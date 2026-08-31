# Compatibility

VAO Blender 0.4.0-rc.1 supports Blender 5.1.x and 5.2.x on Windows x64,
macOS Apple Silicon, and Linux x64. Each split release artifact contains the
pure-Python validator dependencies plus exactly one CPython 3.13 `rpds-py` wheel.
The manifest excludes Blender 5.3+ until that runtime and API line is tested.
Intel macOS is not advertised because Blender 5.1 and 5.2 have no official
macOS x64 host build on which the release can pass the same native evidence gate.

## VAO format matrix

| Capability | 0.2.2 | 0.3.2 editor draft | 0.4.0 published | 0.5.0 candidate |
| --- | :---: | :---: | :---: | :---: |
| Exact pinned contract validation | Yes | Yes | Yes | Yes, by commit |
| Carrier/manifest/release binding | Legacy rules | Yes | Yes | Yes |
| Bootstrap/preservation carrier modes | No | Yes | Yes | Yes |
| Streaming payload size and SHA-256 | Yes | Yes | Yes | Yes |
| Archive hash and payload completeness gate | Yes | Yes | Yes | Yes |
| Graph/entity/asset inspection | Yes | Yes | Yes | Yes |
| Logical asset and realization model | No | Yes | Yes | Yes |
| Exact embedded GLB realization import | Yes | Yes | Yes | Yes |
| Coordinate frames and poses | No | Yes | Yes, including 2D | Yes, including 2D |
| Measurement, response-set, and RIR metadata | No | Yes | Yes | Yes |
| External carrier-member network retrieval | No | No | No | No; use VAO CLI first |
| Supported instrument interaction/audio preview | Exact compiled subset | No | No | No |
| Acoustic rendering, convolution, simulation | No | No | No | No |
| Package scripts or runtime programs | Never | Never | Never | Never |

The four readers are independent. Only the literal format versions shown above
are accepted. VAO 0.3.0, 0.4.1, a prerelease label, or a missing version is not
interpreted as a supported version. The 0.5 reader is pinned to standard commit
`d17b3f188fdf7fadd01ba025383e4feca8def935` and must be repinned when the candidate changes.

## What “supported” means

Supported validation means the package passed the extension's security preflight
and the exact vendored contract/reference checks implemented for that format,
with both archive hashing and payload verification complete. A caller-requested
shortcut is reported as `INCOMPLETE`, never valid.
Supported materialization means an exact verified embedded visual realization can
be copied to the cache and imported with trace metadata. Neither statement
certifies content truth, perceptual quality, rights, or scientific fitness.

The 0.3.2 compatibility line is retained for existing editor-draft packages. The
0.5.0 line exists for reviewed candidate data such as the Kinoorgel VAO; production
authors should account for its candidate status. The 0.2.2 line is legacy and its
audio preview covers only the explicitly compiled subset reported by Diagnostics.
That subset currently requires independent selections, recorded pitch, stereo
preservation, bounded declared gain/envelopes, unambiguous declared gate and voice
component mappings, and an atomic gate within configured polyphony. The compiler
rejects behavior it cannot reproduce exactly.
