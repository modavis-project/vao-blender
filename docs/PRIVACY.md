# Privacy and local data

VAO Blender operates offline and requests only file access. It contains no
telemetry, analytics, account integration, update checker, or network client.
Opening a VAO does not contact identifiers, context URLs, DOI services, or remote
asset URLs found in metadata.

The extension processes:

- the source path selected by the user for the lifetime of the live session;
- package metadata and verified embedded payload bytes;
- deterministic validation diagnostics;
- a content-addressed media cache under Blender's user data directory or the
  custom directory configured in add-on preferences;
- trace properties attached to imported Blender collections and objects,
  including a random materialization identifier, the source basename as a
  display hint, and source fingerprints.

The selected absolute source path is live-session state and is not persisted in
a saved `.blend`. Durable trace properties retain only its basename as a display
hint plus the content fingerprints needed to explain a detached materialization,
not an automatically reusable path. Relinking therefore always requires the
user to choose a local VAO explicitly.

Source VAOs are opened read-only. Cache entries are derivatives addressed by
verified hashes and guarded by a cache-root ownership marker, atomic index,
cross-process lock, quota, and quarantine. Cleanup never follows a broad path and
skips files protected by a live session. Clearing the cache cannot delete source
packages. Imported geometry becomes part of the user's `.blend` file when saved;
use the VAO **Remove Materialization** action or ordinary Blender deletion when it
is no longer wanted.

Relinking a saved materialization reads and completely revalidates the VAO path
selected by the user. The extension compares durable package, manifest, asset,
and realization fingerprints before attaching a new live session; it does not
search the network or silently substitute a similarly named file.

Diagnostic exports should redact absolute paths by default. A package may still
contain creator names, locations, identifiers, rights statements, or other
personal data supplied by its author. Review that data before sharing a report,
VAO, screenshot, or `.blend` file.
