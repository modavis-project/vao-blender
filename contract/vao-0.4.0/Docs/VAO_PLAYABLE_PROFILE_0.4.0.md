# VAO Playable profile 0.4.0

Profile IRI: `https://w3id.org/modavis/vao/profile/playable/0.4.0`

## Applicability

This profile is required for `playable`, `interactionModel`, or `captureDocumentation` content and for a release claiming playable capabilities.

## Sample and playback contract

- Signal regions use exact audio realization IDs and zero-based half-open frame ranges.
- Loop sets resolve sustain-loop regions from one realization and keep selection, exit, crossfade, evidence, and review policy.
- Tuning maps distinguish reference pitch, MIDI reference note, original/source frequency, target frequency, correction, and harmonic interpretation.
- Perspective groups bind exact realizations/channels/poses and geometry status.
- Variants bind trigger, signal role, regions, loop sets, perspective, round robin/weight, source locator, and evidence.
- Sample mappings bind instrument/component/rank, key/velocity ranges, variants, selection, tuning, pitch/gain, note-off policy, source locator, and evidence.

Played key, source-definition key, actuator key, sample root key, and sounding key are distinct. A processor must apply explicit transforms and must not infer pitch from a control number.

## Interaction contract

Controls, events, protocol bindings, state, transitions, routing, timing, processes, transfer functions, and render bindings remain separate registries. MIDI 2 bindings include UMP group/function-block/message/resolution/JR metadata. Zero-delay routing is acyclic. Timed and stochastic processes are bounded and reproducible as applicable. Multivariate transfer functions declare ordered inputs, valid domain, extrapolation, and evidence.

Content is declarative and never authorizes execution during validation. A renderer is an external capability descriptor.

## Capture contract

Capture states record explicit state assignments. Event alignments map event locators to audio frames with offset/drift/uncertainty. Take sets group exact realizations and selection status. Derivation maps preserve source, destination, frame/channel subset, and ordered operations.

Capabilities such as sampled playback, looping, tuning, multi-perspective sampling, recorded release, source-sampler semantics, stateful interaction, conditional routing, composite actuation, timed process, transfer, and capture-event alignment are individually negotiable.

Every Playable profile record includes the mandatory `https://w3id.org/modavis/vao/vocab/capability/interaction` capability in addition to any more specific capabilities it claims.
