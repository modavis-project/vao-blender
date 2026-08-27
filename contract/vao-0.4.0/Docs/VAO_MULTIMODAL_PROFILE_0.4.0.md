# VAO Multimodal Timeline profile 0.4.0

Profile IRI: `https://w3id.org/modavis/vao/profile/multimodal/0.4.0`

## Applicability

This profile is required when any timebase, track, synchronization mapping, or annotation exists.

## Requirements

- Every Timebase states a coordinate `unit`, positive `rate`, compatible `rateUnit`, and origin. Exact rational rates are reduced to lowest terms. Wall clocks state an epoch and absolute time-scale IRI; external timecode also identifies its time scale/system. UTC, TAI, GPS, POSIX, and SMPTE timecode are not interchangeable.
- Every technical realization `timebaseId`, `coordinateFrameId`, and `trajectoryTrackId` resolves to the corresponding Timebase, Coordinate Frame, and trajectory Track; a technical trajectory Track binds that same exact realization. Audio/video rates equal sample/frame Timebase rates without an implicit tolerance; exact video rates may use the lowest-terms rational form.
- Every Track references one exact realization and one declared Timebase. Its modality is compatible with the realization technical kind, and any technical timebase/frame agrees with the Track.
- Track modality and continuity describe how values are interpreted, not just the filename/media type. Continuity is exactly `continuous`, `segmented`, or `sparse`.
- Spatial tracks identify a coordinate frame when spatial interpretation is claimed.
- A synchronization mapping uses distinct source/target clocks and one or more ordered non-overlapping piecewise-affine segments.
- Every segment is half-open and non-empty, has scalar residual uncertainty in the target Timebase coordinate unit, and explicitly records its following boundary as `none`, dropout, reset, pause, or unknown. A `none` boundary is source-contiguous and has exactly equal mapped target values under exact rational interpretation of its binary64/integer operands; a gap or jump requires an explicit discontinuity. Mapping jitter uses the same target-unit convention.
- The mapping cites a method-compatible Activity that lists it as an output.
- Annotations resolve their Track, creating Agent, creation instant, and provenance Activity; their Activity includes the creator/output and encloses the timestamp. Temporal selector bounds occur together and are non-empty half-open intervals in Track coordinates.

The conversion in a segment is `target = source × scale + offset`. Source bounds use the source coordinate unit, `scale` is target units per source unit, and `offset` uses the target coordinate unit. Processors do not interpolate across a declared discontinuity. Clock wrap, epoch, time scale, leap behaviour, drift, pause, reset, and dropout information must not be reduced to an undocumented global offset.

IIIF Presentation 3, Web Annotation, and MEI are projection/binding targets. They do not replace VAO fixity, provenance, or clock evidence.

## Capability IRI

Full profile records and processors include `https://w3id.org/modavis/vao/vocab/capability/multimodal-synchronization`.
