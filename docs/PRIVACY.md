# Privacy and local data

VAO Blender operates offline and requests only file access. It contains no
telemetry, analytics, account integration, update checker, or network client.
Opening a VAO does not contact identifiers, context URLs, DOI services, or remote
asset URLs found in metadata.

The extension processes:

- the source path selected by the user;
- package metadata and verified embedded payload bytes;
- deterministic validation diagnostics;
- a content-addressed media cache under Blender's user data directory or the
  custom directory configured in add-on preferences;
- trace properties attached to imported Blender collections and objects.

Source VAOs are opened read-only. Cache entries are derivatives addressed by
verified hashes and guarded by an ownership marker; clearing the cache does not
delete source packages. Imported geometry becomes part of the user's `.blend`
file when saved and must be removed separately if no longer wanted.

Diagnostic exports should redact absolute paths by default. A package may still
contain creator names, locations, identifiers, rights statements, or other
personal data supplied by its author. Review that data before sharing a report,
VAO, screenshot, or `.blend` file.
