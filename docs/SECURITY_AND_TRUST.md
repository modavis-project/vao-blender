# Security and trust model

Status: maintained threat model for version 0.3.0
Primary threat: an untrusted `.vao` supplied to a Blender process with access to
the user's files and current scene

## 1. Security objectives

- Opening a malicious or malformed VAO must not write outside the managed cache,
  overwrite user files, execute active content, fetch network resources, or
  mutate a scene before validation.
- Resource exhaustion must be bounded, cancellable, and reported as local-limit
  refusal rather than semantic invalidity.
- A package must not be called valid merely because its manifest parses or its
  ZIP CRC passes.
- Unknown rights, access restrictions, provenance status, and unsupported
  capabilities must remain visible.
- Cleanup must target only exact resources owned by the operation/session.

## 2. Trust boundaries

| Boundary | Untrusted | Trusted only after |
| --- | --- | --- |
| `.vao` bytes and ZIP metadata | All paths, flags, sizes, methods, JSON, media | Complete applicable validation stage |
| Manifest identifiers and URIs | Data, not locations to open/fetch | Never made executable; resolution is local graph lookup only |
| Payload media | Encoders/containers may be malformed | Container + schema + semantic + size/CRC/hash, then decoder limits |
| glTF extras/names | Descriptive/untrusted strings | Stable selector mapping and Blender-safe tagging; still not code |
| Bundled scripts/scenes/controllers | Evidence bytes | Never executable by the extension |
| Cache | May contain stale/tampered entries | Regular-file, size, and SHA-256 recheck |
| Saved `.blend` VAO metadata | May be stale or source-detached | Source `.vao` revalidation |
| Rights statement | Evidence about authorization, not enforcement code | Applicable record evaluation plus user/environment policy |

The Blender process and extension are not a strong sandbox. Prevention therefore
comes from a narrow parser, no active-content execution, strict file handling,
and explicit capability adapters.

### VAO 0.3.2 boundary

The exact 0.3.2 reader is a separate model and never falls through to the 0.2.2
decoder. It requires the closed manifest and carrier schemas, the exact
`META-INF/vao-carrier.json` binding to manifest bytes/release ID, and a one-to-one
mapping from payload files to exact realizations. `preservation-closure` is
proved locally before any decoder is called. Distribution records are retained
as metadata only; validation and import initiate no network access.

Only a verified embedded `model/gltf-binary` realization selected through a
`runtime-visual` logical geometry binding reaches Blender's glTF decoder. RIR
realizations never reach the program-audio engine. Their measurement layout,
encoding, fixity, rights, and provenance are inspectable metadata; convolution,
simulation, interpolation, and acoustic rendering remain unsupported.

### VAO 0.4.0 and 0.5.0 boundaries

The exact 0.4.0 reader verifies the signed published release pin. The 0.5.0
candidate reader verifies the recorded upstream commit and normative-bundle
digest. Both verify the machine-readable artifact inventory before loading the
vendored reference validator. They apply the upstream closed carrier/manifest
schemas, immutable context and release identities, carrier closure, exact
embedded realization mapping, and streamed size/SHA-256 checks. ASCII control
characters and archive paths with more than 128 segments are rejected during
preflight.

Only verified embedded runtime-visual GLB realizations reach Blender. VAO 0.4.0
and 0.5.0 runtime/interaction declarations, scientific observations, protocol
bindings, physical components, and acoustic payloads remain inspection data;
the extension does not execute them or perform convolution, simulation, or
interpolation. Rights acknowledgement is tracked independently of the headline
validation state so a limited/unsupported capability result cannot bypass the
media gate.

## 3. Archive defenses

Before reading payload bytes, reject:

- encrypted entries or encrypted central directory;
- absolute, drive-prefixed, UNC, backslash, NUL, empty-component, `.`, or `..`
  paths;
- duplicate normalized paths or overlapping file/directory names;
- symbolic/hard links, devices, sockets, FIFOs, or other special Unix file
  modes encoded in external attributes;
- unsupported compression methods or inconsistent central/local metadata;
- missing/incorrect first uncompressed `mimetype` bytes;
- unknown root entries outside `mimetype`, `vao-manifest.json`, `payload/`, and
  permitted `META-INF/` records;
- structural files represented as assets or unindexed payload files;
- case-fold collisions as an error for preservation claims and warning
  otherwise.

Do not call `extractall()`. Read one validated `ZipInfo` stream at a time and
write to an extension-chosen temporary path. Re-resolve the destination beneath
the exact managed root before opening and before atomic rename. Refuse overwrite
except replacement of the extension's own verified cache key.

## 4. Default resource limits

The default add-on limits are deliberately stricter than the VAO 0.3 reference
guidance and produce a resource-limited result, not contract invalidity:

| Limit | Default |
| --- | --- |
| Entries | 20,000 |
| Manifest expanded bytes | 32 MiB |
| VAO 0.3.2/0.4.0/0.5.0 carrier descriptor | 16 MiB |
| One entry expanded bytes | 8 GiB |
| Total expanded package | 64 GiB |

Additional local safety controls:

- maximum compression ratio per entry of 2,000:1; stored media is normally
  close to 1:1;
- configurable cache quota, default 20 GiB;
- bounded I/O chunks and progress queue;
- disk free-space check before extraction;
- maximum diagnostic count with a final truncation diagnostic, while retaining
  the first actionable errors;
- no recursive media discovery or nested archive extraction.

The 64 GiB package ceiling admits a 50 GB repository record with room for its
structural metadata while retaining a finite preflight bound. A limit failure
returns `resource-limited`; it does not state that the VAO is invalid. Callers
can supply stricter `ValidationLimits` for subsequent validations.

## 5. JSON, schema, and semantic defenses

- Decode strict UTF-8; reject BOM when prohibited, duplicate JSON object keys,
  excessive manifest bytes, invalid numbers, and non-finite values.
- Use the locally vendored schema selected by the declared compatibility line.
  Never resolve `$schema`, `@context`, vocabulary, or identifier URIs over the
  network.
- Enable/assert required format checks rather than assuming JSON Schema's
  `format` annotation enforces them.
- Build ID maps only after schema validation; reject duplicate IDs and dangling
  local references.
- Recalculate every payload byte size/SHA-256 and require CRC success before
  media decode.
- Apply profile semantic validation independently. A false claim is invalid; a
  valid unknown required capability is unsupported.
- Preserve diagnostic JSON pointers and related IDs, but avoid displaying
  unbounded untrusted strings in operator toasts.

## 6. Active content and decoder policy

The extension never:

- executes Python, C#, JavaScript, drivers, expressions, shaders as code,
  executable files, macros, Unity scenes/controllers, or embedded add-ons;
- follows external glTF/media/resource URLs;
- invokes a shell command named by a manifest;
- opens a web URI automatically;
- installs another extension or dependency from a VAO;
- enables network access.

glTF import uses only locally indexed/extracted resources. All external URI
references must resolve to safe indexed package assets via the adapter or the
model is unsupported. Blender's importer runs only after validation and within a
staging collection. Media decoder failures are contained as unsupported/runtime
diagnostics and roll back required materialization.

## 7. Rights and access gate

VAO validation requires applicable rights statements but does not grant rights.
The runtime classifies the requested action:

- **Explicitly permitted for local use:** proceed and show required credit/access
  conditions.
- **Restricted:** block unless the access condition is supported and satisfied.
- **Unknown/unavailable:** allow metadata inspection; require a per-session
  acknowledgement before visual/audio extraction or playback.
- **Explicitly prohibited:** block the prohibited action.

The acknowledgement says the user is responsible for having authority for the
local action. It is not a license, is not persisted as package evidence, does
not change the manifest, and does not unlock network sharing/export. More
specific asset/entity rights records override the package-level display for the
applicable action.

## 8. Cache and deletion safety

- Cache roots are created through Blender's per-extension user storage or an
  explicit user preference.
- Startup validates that the root is absolute, exists/is creatable as a normal
  directory, is not `/`, a drive root, a home directory, or the extension/source
  project root, and contains the VAO-Blender cache marker/version.
- Managed entries are named by a 64-character lowercase SHA-256 directory and
  recorded in `index.json`; deletion rejects names outside that shape.
- Clear/evict deletes individual validated managed entries, not a broad recursive
  user-provided path.
- Partial files use unpredictable operation IDs and restrictive permissions
  where the platform permits.
- Cache re-use checks type, expected size, and hash. A mismatch quarantines the
  entry under the managed root and re-extracts it.

## 9. Scene and runtime isolation

- All scene objects/data-blocks created by an operation are recorded by pointer
  and unique operation ID. Rollback uses this ownership set, not names/globs.
- Imported objects receive no auto-run handlers or drivers from the manifest.
- Performance mode handles events only in the active 3D Viewport/session and
  exits on context loss.
- Audio cleanup stops handles owned by VAO-Blender only; it never calls a global
  stop that affects unrelated Blender audio.
- Worker results carry immutable data only. No worker touches Blender RNA.
- Stored manifest text is read-only through the VAO UI; editing a Blender Text
  block does not alter the validated in-memory session.

## 10. Privacy and diagnostics

- Version 0.3.0 has no telemetry and no network permission.
- Diagnostic JSON includes package/revision IDs, contract/manifest hashes,
  validation results, and relative archive paths.
- Absolute source/cache paths, user names, host names, and acknowledgement state
  are redacted by default. A local-only verbose report is an explicit option.
- Manifest personal/sensitive content is not copied wholesale into crash/toast
  messages.
- The extension never republishes or uploads package data.

## 11. Security test requirements

Release tests cover path traversal in Unix/Windows forms, duplicate and
case-fold paths, symlink/special-file attributes, wrong entry order/content,
encryption flags, unsupported compression, ZIP64 boundaries, high ratios,
declared-size/fixity mismatch, unindexed/duplicate payloads, duplicate JSON
keys, invalid UTF-8, URI/schema/profile failures, external glTF references,
tampered cache entries, cancellation at every stage, and teardown during active
audio/import.

A security defect that permits arbitrary file write/read beyond explicitly
selected input and managed cache, code execution, network access, or silent
rights bypass blocks release.

## 12. Release/security governance

Public distributions ship under GPL-3.0-or-later with third-party licensing,
standard/wheel provenance, SHA-256 inventories, and an SPDX SBOM. Supported
Blender/platform versions and a private GitHub security-advisory reporting route
are documented in the repository. The release audit makes these files and pins
mandatory.

An independent threat-model review and host-platform install smoke tests are
stable-release gates. The rights-restricted Cuntz golden package is not shipped
with the extension; its separate distribution status does not weaken the public
synthetic/reference-fixture test gate.
