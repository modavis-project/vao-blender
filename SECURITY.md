# Security policy

## Supported versions

Security fixes are provided for the latest published VAO Blender release. During
the 0.3.0 release-candidate period, reports against 0.3.0-rc.1 and `main` are in
scope. Older development builds may be used to reproduce a problem but are not
maintained independently.

## Report a vulnerability

Use **Report a vulnerability** in this repository's GitHub **Security** tab to
open a private security advisory. Include the affected version/platform, impact,
minimal reproduction, and whether opening, validating, materializing, or playing
media is required. Do not attach confidential or rights-restricted VAOs unless a
maintainer explicitly arranges a suitable transfer.

Please allow 7 days for acknowledgement and 30 days for an initial assessment.
Timelines for a fix and coordinated disclosure depend on severity and complexity.
If private advisories are unavailable, contact a repository owner privately and
ask for a secure reporting channel; do not put exploit details in a public issue.

## Security model

VAOs are untrusted input. The extension validates archive paths, entry types and
limits, strict JSON, exact contract identity, schemas, carrier closure, release
binding, byte sizes, and SHA-256 fixity before exposing payload media. Extraction
uses a managed cache, glTF import is constrained to verified embedded resources,
and active package content is never executed. Validation is cancellable and does
not request network access.

No parser or media importer is risk-free. Open untrusted packages only with a
supported Blender/extension version, keep Blender and the operating system
patched, and do not treat validation as malware analysis or scientific review.
The detailed threat model is in [docs/SECURITY_AND_TRUST.md](docs/SECURITY_AND_TRUST.md).
