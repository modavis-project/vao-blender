# Troubleshooting

## The extension does not load

Confirm Blender 5.1.x or 5.2.x, the correct platform ZIP, and that the release ZIP
was installed without unpacking. Remove older copies, restart Blender, reinstall,
and check Blender's system console for the first Python import error. A failure
naming `rpds` commonly means the wrong platform artifact was installed. Blender
5.3+ is intentionally excluded until a compatible native wheel/API matrix exists.

## “Unsupported VAO format version”

Only exact VAO 0.2.2, 0.3.2, 0.4.0, and the pinned 0.5.0 candidate packages are
accepted. Do not edit the version field to force a match: schemas, carrier
rules, contexts, and semantics may differ. Migrate the source with tools
appropriate to its actual format.

## Validation fails

Open **VAO → Diagnostics** and record the first diagnostic code. Common causes are
an unsafe archive path, invalid strict JSON, schema failure, carrier/manifest
mismatch, undeclared payload, missing payload, wrong byte size, or wrong SHA-256.
Validation never repairs the source. Re-export from the authoring system or verify
the package with the reference tools matching its declared contract.

## Validation says “Incomplete”

The diagnostic/CLI caller skipped archive hashing, payload verification, or both.
This is useful only for bounded inspection and is never a valid or media-ready
result. Re-run the ordinary **Open VAO** workflow or the CLI without shortcut
flags. Rights acknowledgement cannot promote an incomplete result.

## Media remains blocked after validation

First resolve any invalid, incomplete, unsupported-runtime, detached-source, or
cache-integrity diagnostic. If only rights remain, read the displayed statement
and choose **Acknowledge for This Session** only if you have a lawful basis to use
the media. Acknowledgement does not change the underlying validation state, grant
rights, or persist across sessions.

## Visual import is unavailable

The package may be structurally valid but lack a supported embedded runtime-visual
GLB realization, or its declared runtime capability may be unsupported. Inspect
logical assets, exact realizations, and capability diagnostics. External URLs are
not downloaded.

## A saved materialization is detached

This is expected after reopening a `.blend`; live VAO sessions are not serialized.
Choose **Relink Materialization** and select the original or an exact verified
copy of the source VAO. Relinking fails closed if package/manifest/asset or
realization identity differs. Use **Remove Materialization** when the source is no
longer available or the imported data is no longer needed.

## RIR audio does not play

For VAO 0.3.2/0.4.0/0.5.0, RIRs are inspected as metadata/filter-kernel records only.
Convolution, simulation, interpolation, and program-audio playback are explicitly
out of scope for this release.

## Reporting a problem

Follow [SUPPORT.md](../SUPPORT.md). Never publish a restricted VAO or sensitive
absolute paths solely to demonstrate a bug.
