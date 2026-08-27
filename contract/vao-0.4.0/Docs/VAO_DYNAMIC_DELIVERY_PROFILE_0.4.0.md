# VAO Dynamic Delivery profile 0.4.0

Profile IRI: `https://w3id.org/modavis/vao/profile/dynamic-delivery/0.4.0`

## Applicability

Every VAO 0.4.0 manifest embeds and claims this profile, even when its only distribution is an embedded preservation closure. This guarantees a common model for carriers, exact acquisition, and materialization.

## Requirements

- Asset groups state selection set, quality tier, availability, selection policy, realization IDs, dependencies, total byte size, capabilities, materialized profiles, and cache policy. Every materialized-profile IRI resolves to an embedded Profile record.
- Dependency and fallback graphs are resolvable and acyclic.
- Repository distributions identify immutable record/file versions; pack members identify exact pack and pack-manifest digests.
- A carrier maps every embedded file exactly once and verifies it against the realization.
- Complete groups include their transitive dependencies.
- Bootstrap carriers embed at least one realization; preservation closures embed all and mark all groups complete.
- Materialization verifies decoded byte size and SHA-256 before making data available.
- Receipts describe local acquisition results without mutating the release. They pin the producing implementation and exact source-carrier descriptor (plus the complete packed-container identity when applicable), distinguish attempt from successful verification, and use status-dependent evidence. An acquisition Distribution resolves through the acquired Realization; already embedded bytes are carrier evidence rather than a fabricated Distribution acquisition. Inaccessible/policy-blocked outcomes carry diagnostics but never acquired-byte identity.

## Capability negotiation

Groups list the capabilities needed to use their realizations. Materializable profiles list the groups required to activate a profile. A client may choose a compatible quality tier based on capability, access, byte budget, and cache policy, but must not relabel a fallback as the selected exact realization.

Network acquisition is optional. Offline validation of embedded data remains possible.

## Mandatory capability IRIs

- `https://w3id.org/modavis/vao/vocab/capability/immutable-release`
- `https://w3id.org/modavis/vao/vocab/capability/carrier-mapping`
