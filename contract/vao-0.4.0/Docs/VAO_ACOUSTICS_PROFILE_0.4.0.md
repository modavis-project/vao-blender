# VAO Acoustics profile 0.4.0

Profile IRI: `https://w3id.org/modavis/vao/profile/acoustics/0.4.0`

## Applicability

This profile is required when material models, response measurements or sets, acoustic metric sets, audio scenes, or render configurations are present. It also requires the VAO Spatial profile and at least one declared acoustic capability IRI.

## Frequency-band and material contract

- Band centre frequencies are positive, unique, and strictly ascending.
- Lower and upper edges occur together, match the number of centres, bracket their respective centres, and do not overlap adjacent bands.
- Explicit centre/edge arrays are the computational authority. The `scale` label is descriptive classification, not an assertion that the values conform to a particular nominal/rounded IEC, ISO, ANSI, ERB, Bark, or other definition. Record any such claim with the exact standard/edition and method in protocol/evidence metadata.
- Absorption, scattering, transmission-loss, metric-value, and corresponding uncertainty vectors have exactly one value per band where present. Material uncertainties are property-specific: absorption/scattering use QUDT `UNITLESS`; transmission-loss uncertainty uses `DeciB`.
- Absorption and scattering coefficients are dimensionless values in `[0, 1]`; transmission loss is non-negative and expressed in decibels; a supplied thickness is strictly positive. A Material Model resolves its material Entity, provenance Activity, and any exact surface-impedance asset. Missing properties are not inferred from absorption, and structural conformance alone does not establish passivity or energy conservation.
- Measured, simulated, inferred, learned, authored, and hybrid status remain distinct. Status labels do not themselves prove accuracy.

## Measurement and response contract

- Each Response Measurement resolves source and receiver Entities and matching Poses. Both Poses share a common coordinate-frame root. Optional space, configuration, state, separating element, and transmission-path references resolve typed semantic records.
- Validity bounds are chronological RFC 3339 instants. A measurement record without a time bound does not assert temporal invariance.
- A Response Set resolves its response Entity, exact logical response asset, measurement records, provenance Activity, and optional Calibration records/delay asset.
- Interpolation identifies its valid domain and outside-domain policy. Fallback links are policy-specific and acyclic; seeded determinism has a seed; method `none` rejects out-of-domain queries. Neural fields require an exact model, non-empty training/validation evidence, quality metric, and determinism. A learned Response Set uses a neural-field or hybrid contract with all such evidence. A renderer must not infer an undocumented extrapolation rule.
- Impulse-response technical metadata records encoding, sample count, time-zero policy, normalization, and channel/measurement mapping. It covers every Response Set measurement exactly once without reusing a data/channel address. AES69-SOFA additionally identifies its convention.

## Metric, scene, and rendering contract

- A Metric Set identifies a standard IRI, edition, method, exact inputs, Entity subjects, band axis, units, status, and generating Activity. Each optional metric uncertainty uses the general structured uncertainty contract, matches the band vector, and uses the metric's unit; it may therefore retain its kind, method, confidence or coverage factor, and covariance where applicable.
- Naming a standard is provenance, not certification. A record may claim conformity or an accepted scientific result only when the cited method, scope, calibration, and evidence actually justify that claim.
- An Audio Scene resolves its semantic scene Entity, coordinate frame, media assets, bindings, and optional content Timebase. Because a binding names a logical media asset, selected channel indices MUST exist in every one of that asset's exact audio realizations and those realizations MUST have one common channel count; otherwise the channel selection is ambiguous and the asset must be split or the variants normalized.
- A Render Configuration resolves its scene, coordinate frame, exact inputs, listener references, feature inputs, valid domain, and fallbacks. Fallback graphs are acyclic; `fallback` outside-domain policy requires at least one fallback.
- The profile defines interchange semantics for renderer inputs and policies. It does not require perceptual equivalence or bit-identical audio unless a separately defined capability and evidence explicitly establish it.

## Acoustic capability IRIs

An Acoustics profile record includes at least one applicable capability from the controlled VAO capability vocabulary, such as measured/simulated impulse response, spatial response field, spatial audio scene, source directivity, room-acoustic metrics, building-acoustic performance, tracked convolution, geometry-acoustic rendering, hybrid rendering, or learned acoustic field.

Acoustics-profile conformance proves structural and semantic consistency of the recorded evidence. It does not prove that a simulation is physically valid, that a measurement follows the named standard, or that a result is scientifically true; those conclusions require documented protocols, calibration, uncertainty, validation, review, and domain expertise.
