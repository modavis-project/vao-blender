# VAO 0.5.0 security and privacy considerations

This document expands the normative security requirements. VAO files must be treated as untrusted passive data, even when their fixity or signature is valid.

## Trust distinctions

Do not conflate:

- **fixity:** bytes match a declared digest;
- **authenticity:** a recognized principal signed or issued them;
- **authorization:** policy permits this user/action;
- **scientific validity:** claims and methods are sound;
- **safety:** parsing/rendering will not compromise the system;
- **consent/ethics:** use is permitted and appropriate.

Evidence for one does not prove the others.

## Threats and controls

| Threat | Required or recommended control |
| --- | --- |
| path traversal/absolute/control-character names | reject before extraction; enforce destination containment; escape names in diagnostics |
| Unicode/case collisions | reject NFC and NFC-plus-default-case-fold collisions; exclusive file creation |
| symlink/hardlink/device/FIFO | reject all links and special entries/workspace nodes |
| ZIP bomb/oversized headers | finite entry, size, ratio, time, memory, and recursion budgets before decompression |
| duplicate ZIP/JSON names | reject raw and normalized ZIP duplicates and duplicate JSON members |
| encrypted/unknown compression | reject; VAO 0.5 supports Stored/Deflate only |
| TOCTOU during extraction | fresh private directory, no-follow/exclusive opens, atomic handoff |
| digest confusion | hash decoded exact member bytes; require algorithm and lowercase length |
| mutable repository target | resolve immutable record/file; verify local size/SHA-256 |
| SSRF/DNS rebinding/redirect | network off by default; scheme/host/IP/redirect policy; revalidate each hop |
| credential leakage | scope credentials to repository; never forward across origins or log them |
| malicious media | validate bytes first; decode/render in isolated low-privilege process |
| executable realization | never execute on open/validate; explicit user/policy authorization and sandbox |
| graph/algorithm DoS | bound IDs, depth, cycles, segments, trace events, microsteps, voices, and elapsed time |
| malicious RDF/context | pin local context; disable arbitrary remote context/import fetching |
| signature overtrust | validate signer/purpose/time/revocation separately; still enforce all safety checks |
| privacy/consent leak | apply rights/consent before preview, indexing, export, or logging |

## Reference-validator safety limits

The reference implementation currently defaults to 100,000 archive/workspace entries, 128 path segments, 128 JSON container levels, 64 MiB manifest, 16 MiB carrier descriptor, 1 TiB per payload entry, 4 TiB declared total, and a 1,000:1 ratio limit for compressed entries of at least 64 MiB. Its offline interpreter additionally limits one trace to 100,000 input events and 100,000 total microsteps while still enforcing the manifest's lower per-event `maximumMicrosteps`, if lower. Standalone descriptors and unpacked workspaces receive the same applicable structural limits before whole-file reads. These are implementation safeguards, not normative format maxima. Deployments should choose substantially smaller limits where their use case permits and add wall-clock/memory/process isolation.

Central-directory sizes and pre-open filesystem metadata are attacker-controlled or raceable. Limits must be checked again while streaming. The reference validator checks the exact declared `mimetype` size before reading it and bounds every structural read. Its workspace reader/writer opens final path components without following links, requires an unshared regular file, and stops one byte beyond the realization's declared size; it also rechecks the aggregate budget. A truncated stream, replacement race, CRC error, digest mismatch, or budget overrun fails validation/packing. Validate an untrusted workspace in an isolated process against a quiescent snapshot: portable filesystem APIs cannot make an attacker-controlled ancestor-directory tree race-free on every supported platform.

## Strict JSON and parser differentials

Use one strict parser configuration across validation and processing. Duplicate names, non-finite/overflow/underflow numbers, and integers outside the VAO safe range are invalid. Avoid validating with one library and interpreting with another that resolves duplicates, numbers, Unicode, or URI formats differently. Preserve exact manifest bytes for the carrier pin.

## Identifier and graph safety

Identifiers are data, not automatically fetchable URLs. URI parsing must not trigger network requests. Bound registry sizes and graph traversal; detect cycles where prohibited; use iterative algorithms or depth limits on untrusted graphs.

Extension IRIs do not authorize code loading. Unknown extensions are inert.

## Materialization and network acquisition

Apply policy before any request:

- allowed schemes (normally HTTPS only), origins, ports, and IP ranges;
- redirect count and cross-origin credential stripping;
- DNS and resolved-address checks at every connection;
- connect/read/total timeouts and decoded-byte limit;
- TLS certificate validation and repository authentication;
- safe temporary filename independent of remote `Content-Disposition`;
- exact size/SHA-256 verification before rename/cache;
- cleanup and auditable failure receipt.

Receipt diagnostics are public-or-shareable metadata unless a deployment applies stronger controls. They MUST NOT contain access tokens, signed URLs, cookies, filesystem secrets, credential-bearing headers, or unnecessary personal data. Record a policy/authentication outcome and a safe bounded explanation, not the secret that caused it.

Do not treat repository-provided checksums as a replacement for manifest identity. Never execute post-download hooks from a carrier.

## Rendering and active content

The manifest is declarative. Media codecs, geometry importers, ML model runtimes, plugins, shaders, scripts, and renderers enlarge the attack surface. Run them after conformance/rights checks with least privilege, no inherited secrets, read-only inputs, bounded CPU/GPU/memory/output, controlled filesystem/network, and explicit output paths.

`isolated-external-renderer` describes a requirement; it is not evidence that isolation exists. The host owns enforcement.

## Privacy, cultural governance, and sensitive research data

Names, contacts, ORCIDs, performer data, consent evidence, location, instrument ownership, embargo details, and community-governed knowledge can be sensitive. Systems should support field/content access control, redacted derivatives, minimal search indexing, log scrubbing, retention policy, and withdrawal workflows without rewriting already published evidence.

When access or consent is unclear, deny or defer. Do not infer permission from a public identifier, absent license, technical accessibility, or a valid signature.

## Vulnerability response

Follow the repository [security policy](../SECURITY.md). A parser vulnerability may affect downstream implementations even if the reference validator is not used; coordinate disclosure with affected maintainers and registries when appropriate.
