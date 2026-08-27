# Troubleshooting

## The extension does not load

Confirm Blender 5.1+, the correct platform ZIP, and that the release ZIP was
installed without unpacking. Remove older copies, restart Blender, reinstall, and
check Blender's system console for the first Python import error. A failure naming
`rpds` commonly means the wrong platform artifact was installed.

## “Unsupported VAO format version”

Only exact VAO 0.2.2, 0.3.2, and 0.4.0 packages are accepted. Do not edit the
version field to force a match: schemas, carrier rules, contexts, and semantics
may differ. Migrate the source with tools appropriate to its actual format.

## Validation fails

Open **VAO → Diagnostics** and record the first diagnostic code. Common causes are
an unsafe archive path, invalid strict JSON, schema failure, carrier/manifest
mismatch, undeclared payload, missing payload, wrong byte size, or wrong SHA-256.
Validation never repairs the source. Re-export from the authoring system or verify
the package with the VAO 0.4.0 reference tools.

## Media remains blocked after validation

The package contains an unknown or restricted rights/access statement. Read the
displayed statement and choose **Acknowledge for This Session** only if you have a
lawful basis to use the media. The acknowledgement does not grant rights and is
not persisted across sessions.

## Visual import is unavailable

The package may be structurally valid but lack a supported embedded runtime-visual
GLB realization, or its declared runtime capability may be unsupported. Inspect
logical assets, exact realizations, and capability diagnostics. External URLs are
not downloaded.

## RIR audio does not play

For VAO 0.3.2/0.4.0, RIRs are inspected as metadata/filter-kernel records only.
Convolution, simulation, interpolation, and program-audio playback are explicitly
out of scope for this release.

## Reporting a problem

Follow [SUPPORT.md](../SUPPORT.md). Never publish a restricted VAO or sensitive
absolute paths solely to demonstrate a bug.
