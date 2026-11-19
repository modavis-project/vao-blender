# MMIC 1.0.0 conformance coverage

This is a reusable test and review map for MMIC 1.0.0. The executable
suite is [tests/test_mmic.py](../tests/test_mmic.py); run it through the full
[release gate](RELEASE_0.6.0.md). Historical accuracy, attribution,
performance and institutional approval require evidence beyond this suite.

## Requirements

| Requirement | Contract | Representative executable check |
| --- | --- | --- |
| CORE-01 | Independent profile specification version | `test_version_capability_and_group_contract_negatives` |
| CORE-02 | Open semantic subject classification | `test_06_core_semantic_projection_and_legacy_descriptor_regressions` |
| MMIC-01 | Identity and acyclic lifecycle | `test_gap_regressions_through_fixity_consistent_archives` |
| MMIC-02 | Physical and design documentary minima | `test_semantic_negative_matrix` |
| MMIC-03 | Canonical domain model and projection parity | `test_normative_json_rdf_json_and_jsonld_parity` |
| MMIC-04 | Complete model and execution identity | `test_reference_gaps_rejected_after_operational_repins` |
| MMIC-05 | Observation and qualified functional roles | `test_semantic_negative_matrix` |
| MMIC-06 | Native signals and exact export bindings | `test_C01_fixity_consistent_complete_carrier_rejected` |
| MMIC-07 | Geometry and full traversal coverage | `test_gap_regressions_through_fixity_consistent_archives` |
| MMIC-08 | Timing function and event/output consistency | `test_reference_gaps_rejected_after_operational_repins` |
| MMIC-09 | Evidence and reproducibility | `test_semantic_negative_matrix` |
| MMIC-10 | Playback comparison alignment and corrections | `test_corrections_retain_exact_prior_and_replacement_values` |
| MMIC-11 | Generation and actual fabrication lineage | `test_generation_constraints_and_byte_artifacts_are_operational` |
| MMIC-12 | Level-specific conformance | `test_complete_and_partial_carriers_and_deterministic_pack` |
| MMIC-13 | Profile registry and group materialization | `test_version_capability_and_group_contract_negatives` |
| MMIC-14 | Validation result and processor roles | `test_resource_limits_duplicates_and_unsupported_distinction` |
| MMIC-15 | Resource safety rights and dependencies | `test_access_redaction_and_preservation_of_unknown_extensions` |

The suite also tests the bounded trusted worker, installed resources, independent
JavaScript native/MIDI/layout/comparison traces, complete/partial deterministic
carriers and explicit 0.5 byte-preserving migration. Archive regressions rebuild
outer fixity and then isolate domain failures for C01, T01, M01, I01, I02, D01, G01
and H01. R01 exercises the axial point constraint directly in the RDF graph.

## Competency questions

“Reference” means an executable operation within the declared synthetic model.
“Documentary” means qualified representation, without historical or empirical
verification. These distinctions are part of the reference implementation boundary.

| Question | Supported scope | Contract |
| --- | --- | --- |
| CQ-01 Which individual material object is represented by this scan, recording and MIDI? | Reference processing and preservation within declared capabilities | MMIC-01, MMIC-03 |
| CQ-02 Does a manufacturer catalogue number identify one copy, an edition/program or a catalogue description? | Documentary claims and evidence; no empirical certification | MMIC-01 |
| CQ-03 Which historical state was scanned or played? | Documentary claims and evidence; no empirical certification | MMIC-01, MMIC-02 |
| CQ-04 Which claims about maker, pinner, editor, performer, operator and restorer are supported? | Documentary claims and evidence; no empirical certification | MMIC-09 |
| CQ-05 Can a virtual object and its immutable interpretation releases survive a host or file-path change? | Reference processing and preservation within declared capabilities | MMIC-01, MMIC-13 |
| CQ-06 Where in the original image or 3D acquisition did this detected feature come from? | Reference processing and preservation within declared capabilities | MMIC-05, MMIC-07 |
| CQ-07 Was this region observed blank, obscured, damaged or never scanned? | Documentary claims and evidence; no empirical certification | MMIC-02, MMIC-05 |
| CQ-08 Which measured dimension and unit support the track spacing or punch size? | Documentary claims and evidence; no empirical certification | MMIC-07, MMIC-08, MMIC-09 |
| CQ-09 Which candidate model versions fit this carrier, and why was one chosen? | Reference processing and preservation within declared capabilities | MMIC-04, MMIC-05 |
| CQ-10 Can an intact raised projection be distinguished from its punched opening or a missing tongue? | Documentary claims and evidence; no empirical certification | MMIC-05, MMIC-07 |
| CQ-11 Are several openings separate attacks or one webbed continuous command? | Documentary claims and evidence; no empirical certification | MMIC-05, MMIC-06 |
| CQ-12 Is this channel a note, pedal, expression, registration, transport or unknown signal? | Reference processing and preservation within declared capabilities | MMIC-05, MMIC-06 |
| CQ-13 Does a printed curve directly control a mechanism or guide an operator? | Documentary claims and evidence; no empirical certification | MMIC-05, MMIC-06 |
| CQ-14 Which aperture/follower geometry and offsets changed the timing of this actuation? | Reference processing and preservation within declared capabilities | MMIC-04, MMIC-08 |
| CQ-15 Which pedal/expression values are latched, continuous, coded, relative or unknown? | Reference processing and preservation within declared capabilities | MMIC-06 |
| CQ-16 Which mechanical target, pitch, tuning and registration underlie this MIDI key? | Documentary claims and evidence; no empirical certification | MMIC-04, MMIC-06 |
| CQ-17 Are repeated notes mechanically playable under the selected model/state? | Documentary claims and evidence; no empirical certification | MMIC-06, MMIC-11 |
| CQ-18 Which sounding duration is observed, modelled or chosen solely for MIDI export? | Reference processing and preservation within declared capabilities | MMIC-06 |
| CQ-19 Which performance features were absent from the carrier and supplied editorially? | Documentary claims and evidence; no empirical certification | MMIC-06, MMIC-09 |
| CQ-20 Which face, origin, direction and traversal pass explain this disk event? | Reference processing and preservation within declared capabilities | MMIC-07 |
| CQ-21 Is a seam-crossing feature continuous across zero angle? | Reference processing and preservation within declared capabilities | MMIC-07 |
| CQ-22 Which axial tune-selection position belongs to this barrel program? | Documentary claims and evidence; no empirical certification | MMIC-07 |
| CQ-23 Does this program advance axially through successive revolutions? | Reference processing and preservation within declared capabilities | MMIC-07, MMIC-08 |
| CQ-24 Which ordered physical parts or panels make the complete program? | Reference processing and preservation within declared capabilities | MMIC-01, MMIC-07, MMIC-13 |
| CQ-25 How do stops, reversals, rewind and repeated passes map to time? | Unsegmented forward/reverse reference clocks; segmented execution unsupported | MMIC-07, MMIC-08 |
| CQ-26 Can the interpretation be reproduced from fixed inputs? | Reference processing and preservation within declared capabilities | MMIC-04, MMIC-08, MMIC-09 |
| CQ-27 Is this recording actual playback, a synthesized rendering or an unknown kind? | Reference processing and preservation within declared capabilities | MMIC-10 |
| CQ-28 How was audio-derived MIDI aligned with image-derived output? | Reference processing and preservation within declared capabilities | MMIC-10 |
| CQ-29 Could disagreement be a conversion error, instrument fault, operator action or audio transcription error? | Documentary claims and evidence; no empirical certification | MMIC-10 |
| CQ-30 Which exact decision changed this MIDI, and can the previous result be recovered? | Reference processing and preservation within declared capabilities | MMIC-01, MMIC-10 |
| CQ-31 What does the stated accuracy measure mean and where does it apply? | Documentary claims and evidence; no empirical certification | MMIC-09 |
| CQ-32 Are carrier metadata, source images, audio, interpretations and annotations licensed independently? | Reference processing and preservation within declared capabilities | MMIC-15 |
| CQ-33 Which exact realizations are embedded in the carrier, remotely available or intentionally unavailable? | Reference processing and preservation within declared capabilities | MMIC-13 |
| CQ-34 Can one VAO package contain several carriers, programs or interpretations without merging their identities? | Reference processing and preservation within declared capabilities | MMIC-01, MMIC-13 |
| CQ-35 Does an EDM/CIDOC-CRM projection preserve the physical/digital distinction and uncertainty? | Lossless native RDF; informative CRM/EDM mappings without receiving-profile compliance claims | MMIC-03 |
| CQ-36 What can a consumer do when a specialized decoder is unsupported? | Preserve unknown data and report unsupported or unmaterialized capabilities | MMIC-12, MMIC-14 |
