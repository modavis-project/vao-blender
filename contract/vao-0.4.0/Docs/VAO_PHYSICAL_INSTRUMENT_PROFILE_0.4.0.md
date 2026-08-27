# VAO Physical Instrument profile 0.4.0

Profile IRI: `https://w3id.org/modavis/vao/profile/physical-instrument/0.4.0`

## Applicability

This profile is required when any component, port, connection, sensor, actuator, or state binding exists.

## Requirements

- Components resolve to semantic Entities; parents form an acyclic hierarchy.
- A component's `portIds` is exactly the inverse set of Ports whose `componentId` names it.
- Ports resolve to components and declare direction and signal kind.
- Connections resolve source/target ports, use output/bidirectional to input/bidirectional directions, and declare the coupling kind. `bidirectional: true` requires two bidirectional Ports.
- A delayed cyclic path resolves its delay Timing Constraint; zero-delay cycles are invalid where the interaction/routing rules apply.
- Sensors resolve component, output port, scientific Protocol, observed property, and optional Calibration.
- Actuators resolve component, input port, scientific Protocol, acted-on property, and optional Transfer Function.
- State bindings resolve interaction state and component, distinguish commanded/observed/estimated/simulated state, and resolve an Observation when supplied.

The topology is a systems view and does not replace semantic entity relations. SOSA/SSN, MIMO, CIDOC CRM, and domain ontologies may refine types through stable IRIs.

## Capability IRI

Full profile records and processors include `https://w3id.org/modavis/vao/vocab/capability/physical-system-topology`.
