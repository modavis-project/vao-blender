# VAO Spatial profile 0.5.0

Profile IRI: `https://w3id.org/modavis/vao/profile/spatial/0.5.0`

## Applicability

This profile is required when coordinate frames, poses, geometry bindings, or a spatial multimodal track is present. Spatial content is not inferred from an unqualified numeric array.

## Coordinate contract

- Every Pose and spatial Track resolves a declared Coordinate Frame. Pose positions have exactly the frame dimension.
- Frame-parent links are acyclic, join frames of equal dimension, and carry one invertible affine transform.
- `transformToParent` is a row-major 4×4 matrix applied to a homogeneous column vector: `p_parent = M × p_child`. Translation is in indices 3, 7, and 11; the last row is `[0, 0, 0, 1]`.
- Linear coefficient `(i,j)` has dimensional meaning `parentUnit[i]/childUnit[j]`, and translation row `i` is in `parentUnit[i]`; one scalar frame unit supplies every axis where `axisUnits` is absent.
- A two-dimensional transform uses the canonical `[x, y, 0, 1]` embedding, preserves `z = 0`, and has a nonsingular 2×2 linear part. The six forbidden/must-be-one embedding coefficients have absolute error at most `10^-12`; the affine last row remains exact. A three-dimensional transform has a nonsingular 3×3 linear part. After normalization by its largest absolute coefficient, the linear part has an infinity-norm reciprocal condition estimate greater than `10^-12`; the scale-invariant test accepts well-conditioned very small/large scales while rejecting singular or severely ill-conditioned transforms.
- Cartesian, projected, screen, and parametric frames state one unit IRI. A geodetic frame instead states a CRS IRI and one ordered unit IRI per coordinate axis. Pose values and units use that CRS's authoritative axis order exactly; longitude/latitude and latitude/longitude MUST NOT be interchanged by convention. A geodetic frame is a root, has non-applicable handedness/direction axes, and is not connected by an affine parent edge; conversion to a local Cartesian/projected frame requires an explicit, provenance-bearing operation.
- Non-applicable axes are explicit. Otherwise up and forward axes are non-collinear, and a two-dimensional frame cannot use a Z axis.

## Pose and uncertainty contract

- Any orientation names both a local and target Coordinate Frame. They are Cartesian/projected, have equal dimensions and exact units, and share the same applicable handedness; scaling and reflection require an explicit frame transform.
- A three-dimensional orientation is the active Hamilton unit-quaternion rotation in `x, y, z, w` order from local-frame numeric coordinates into target-frame numeric coordinates. Its squared norm differs from one by at most `10^-9`. Quaternion trajectories use `step` or `spherical-linear`; SLERP linearly interpolates position, treats sign-equivalent quaternions identically, and follows the shortest orientation arc without linearly interpolating quaternion components.

- `registration-rms` is a scalar in its explicitly stated unit. It does not inherit heterogeneous axis units; its method states the metric/coordinate space and residual convention used, such as metres after a documented local projection of geodetic control points.
- A two-dimensional orientation is the active counter-clockwise angle in radians in `[-π, π]` from the local numeric X axis into the target numeric X–Y plane; it cannot use a quaternion. Linear angular interpolation uses the shortest signed difference and resolves an exact half-turn as `-π`. Cubic interpolation is position-only and therefore forbids orientation. Orientation must not be asserted directly in a geodetic frame.
- Pose validity bounds denote instants and are compared chronologically after applying their RFC 3339 offsets.
- Pose extent has exactly the frame dimension and only non-negative components.
- Position uncertainty uses the frame unit or the frame's ordered axis units. A covariance matrix has one row and column per position component. Orientation covariance uses a one-dimensional tangent angle in 2D or a three-dimensional tangent rotation vector in 3D; non-covariance orientation uncertainty is scalar.
- A non-`none` interpolation requires `trajectoryRealizationId` to resolve one exact trajectory, motion-capture, or sensor-data realization. Its technical Coordinate Frame equals the Pose target frame and its Timebase defines sample coordinates. `none` forbids an unused trajectory reference. A logical asset reference is insufficient because it may have several realizations. Static-pose interpolation does not authorize inventing trajectory samples.

## Geometry binding

A Geometry Binding resolves one semantic Entity and one logical geometry asset. Selectors use the datatype required by their selector kind. The binding role distinguishes semantic authority, simulation geometry, visual geometry, collision, occlusion, and navigation; these roles are not interchangeable.

## Capability IRI

Full profile records and processors include `https://w3id.org/modavis/vao/vocab/capability/spatial`.

Spatial-profile conformance establishes an explicit and internally consistent coordinate contract. It does not establish survey accuracy, CRS correctness, physical scale, registration quality, or suitability of a geometry for acoustic simulation without supporting evidence.
