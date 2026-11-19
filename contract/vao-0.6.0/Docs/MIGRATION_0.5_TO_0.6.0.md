# Migrating VAO 0.5.0 to 0.6.0

The 0.5.0 specification, schemas, contexts, normative bundle, validator and fixtures
remain immutable. A strict 0.5 reader rejects a 0.6 envelope; compatibility means
continued 0.5 support and explicit migration, not silently accepting another contract.
The version dispatcher selects the appropriate retained reader.

## Complete workspace migration

Use a valid local 0.5 workspace whose preservation carrier contains the complete
realization closure. Partial or inconsistent inputs must be materialized and verified
before migration. Choose unused destination and receipt paths:

```sh
python Tools/migrate_vao05.py original-workspace new-0.6-workspace \
  --receipt migration-receipt.json
python Tools/vao.py validate new-0.6-workspace
```

The tool validates the complete source, preserves every declared asset's exact bytes
and realization identity, and creates new manifest, release and carrier identities.
It rewrites recognized core profile declarations for 0.6 and adds migration/code/
environment provenance. Continuing subject identities and opaque extensions remain
preserved. Original delivery locators are retained as source evidence; the new local
carrier provides a complete closure. The original workspace is not modified.

The receipt records source/output fixity, new and preserved identities, profile
mappings, declared losses/omissions and final validation. Existing paths, unsafe
paths or invalid inputs fail without replacing the source. Only outputs created by
that invocation are rolled back on failure.

## Adding an MMIC claim

0.5.0 had no accepted MMIC profile. Migration does not promote provisional annotations
or prototype extensions into a validated MMIC 1.0.0 claim. Preserve their original
meaning and evidence; review and construct the normalized domain model separately.

Declare the exact MMIC profile identifier and `specificationVersion: "1.0.0"`
inside a VAO `formatVersion: "0.6.0"` envelope. Select the appropriate physical carrier,
design or collection subjects, declare conformance levels and materializable groups,
and pin the local normative dependencies. Provide the state/geometry/evidence minima
for documentation and the complete models, fixed inputs and checked outputs required
by any decoding, comparison or generation claim. Designs and actual fabrication
records retain separate identities and evidence.

Read the [MMIC specification](VAO_MMIC_PROFILE_1.0.0.md) and
[conformance map](MMIC_CONFORMANCE_1.0.0.md). Unknown or unavailable data remains
qualified; unsupported operations must not be reported as valid execution. Neither
migration nor structural conformance certifies historical fidelity or physical
playability.
