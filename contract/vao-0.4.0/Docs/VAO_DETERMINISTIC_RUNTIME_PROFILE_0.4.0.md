# VAO Deterministic Runtime profile 0.4.0

Profile IRI: `https://w3id.org/modavis/vao/profile/deterministic-runtime/0.4.0`

## Applicability

This profile is required when `runtime.conformanceTraces` is non-empty or deterministic runtime conformance is claimed.

## Requirements

- Runtime and interaction execution-semantics objects are identical.
- Event, transition, and action ordering follows section 17 of the standard.
- Snapshot guards and conflict policies are honoured. A live host also honours reentrancy, late-event, delayed-action, process-lifecycle, and voice policies where those operations apply.
- PCG32 uses its fixed-width 63-bit hexadecimal stream selector without numeric rounding; xoshiro256** has a non-zero 256-bit seed and no invented stream transform.
- Runtime tie-break strings use ascending UTF-8 byte order without locale or case folding.
- A stochastic Process selects first from its direct actions followed by direct children; only a selected child expands. Non-stochastic expansion serializes direct actions then children depth-first in declared order.
- Stochastic selection uses the specified unbiased raw-integer rejection/interval mapping, not modulo or binary floating point; categorical candidate weights are positive integers with a bounded total.
- `maximumMicrosteps` bounds each input-event run-to-completion cycle and resets before the next event. Transition actions, expanded Process actions, and stochastic generator draws (including rejected redraws) each consume one microstep.
- Offline traces reject delayed transition/Process actions and scheduled or lifecycle Processes; admitted Process graphs are immediate, completed, and one-shot/compound/stochastic. Traces use unique input ordering tuples, validate event/state/action domains, and cover every expected state variable.
- An expanded Process action is an emitted request, not an applied transition effect. Its trace record preserves source Process, originating transition, operation, target, timestamp, and any value/key offset.
- Every trace digest is RFC 8785 canonical JSON hashed with SHA-256.
- Every trace executes to the exact final state, emitted-event sequence, and render-binding sequence.
- Renderers identify name/version, exact Software Environment, capabilities, sandbox policy, and deterministic claim. A true deterministic claim requires a stated runtime and exact container/executable identity, or independently hashed code and environment-lock identities.
- `declarative-only` performs no package-supplied execution; `isolated-external-renderer` still requires explicit host authorization and isolation.

The reference offline verifier covers already-available ordered input, guards, state/actions, immediate completed one-shot/compound/stochastic Process expansion/selection, emitted records, and render-binding selection. Its local safety policy limits one trace to 100,000 input events and 100,000 total microsteps in addition to the declared per-event bound. It rejects timed or lifecycle Processes and does not simulate live arrival/queues, delay scheduling, voice lifecycle, media rendering, or bit-identical audio. The profile therefore demonstrates deterministic control/render selection only within the claimed processor scope, not perceptual equivalence or bit-identical audio unless another capability and test explicitly defines that output.

## Capability IRI

Full profile records and processors include `https://w3id.org/modavis/vao/vocab/capability/deterministic-render-trace`.
