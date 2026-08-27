# Compatibility

VAO Blender 0.3.0 supports Blender 5.1+ on Windows x64, macOS x64, macOS Apple
Silicon, and Linux x64. Each release artifact contains the pure-Python validator
dependencies plus the `rpds-py` wheel for exactly one platform.

## VAO format matrix

| Capability | 0.2.2 | 0.3.2 editor draft | 0.4.0 published standard |
| --- | :---: | :---: | :---: |
| Exact pinned contract validation | Yes | Yes | Yes |
| Carrier/manifest/release binding | Legacy rules | Yes | Yes |
| Streaming payload size and SHA-256 | Yes | Yes | Yes |
| Graph/entity/asset inspection | Yes | Yes | Yes |
| Logical asset and realization model | No | Yes | Yes |
| Exact embedded GLB realization import | Yes | Yes | Yes |
| Coordinate frames and poses | No | Yes | Yes, including 2D orientation |
| Measurement, response-set, and RIR metadata | No | Yes | Yes |
| Supported instrument interaction/audio preview | Limited | No | No |
| Acoustic rendering, convolution, simulation | No | No | No |
| Package scripts or runtime programs | Never executed | Never executed | Never executed |

The three readers are independent. Only the literal format versions shown above
are accepted. VAO 0.3.0, 0.4.1, a prerelease label, or a missing version is not
interpreted as a supported version.

## What “supported” means

Supported validation means the package passed the extension's security preflight
and the exact vendored contract/reference checks implemented for that format.
Supported materialization means an exact verified embedded visual realization can
be copied to the cache and imported with trace metadata. Neither statement
certifies content truth, perceptual quality, rights, or scientific fitness.

The 0.3.2 compatibility line is retained for existing editor-draft packages; new
VAOs should target the published 0.4.0 standard. The 0.2.2 line is legacy and its
audio preview covers only the explicitly compiled subset reported by Diagnostics.
