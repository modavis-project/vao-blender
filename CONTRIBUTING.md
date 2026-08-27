# Contributing

Thanks for helping improve VAO Blender. Bug reports, test cases, documentation,
accessibility improvements, and narrowly scoped code changes are welcome.

## Before opening an issue

Search existing issues, then collect the Blender version, operating system,
extension version, VAO `formatVersion`, validation state, and diagnostic codes.
Do not upload a VAO or absolute local paths unless you are authorized to share
them. A minimal synthetic package is strongly preferred.

Use GitHub's security advisory flow instead of a public issue for suspected
vulnerabilities; see [SECURITY.md](SECURITY.md).

## Development workflow

1. Fork the repository and create a focused branch from `main`.
2. Use Python 3.11 or newer and Blender 5.1 or newer.
3. Keep the core package Blender-neutral. Blender imports belong under
   `vao_blender/blender/`.
4. Add regression tests for behavior changes. Contract changes require positive,
   negative, adversarial, and reference-parity evidence where applicable.
5. Run:

   ```console
   python -m unittest discover -s tests/unit -v
   ruff check vao_blender tests scripts
   ruff format --check vao_blender tests scripts
   python scripts/release_audit.py
   ```

6. Run the relevant Blender integration tests described in
   [docs/RELEASE.md](docs/RELEASE.md).
7. Open a pull request describing the user-visible result, compatibility impact,
   tests, and any security or rights implications.

## Compatibility rules

- Never accept an unreviewed VAO version through a range or prefix match.
- Never weaken a fixity, carrier-closure, path, or rights check for convenience.
- Never execute active content from a VAO package.
- Never infer scientific validity from machine conformance.
- Preserve source VAO bytes; derived files belong in the managed cache or the
  user's Blender project.
- Changes to vendored contracts or wheels must update provenance, checksums,
  third-party notices, tests, and release audit expectations together.

Contributions must be compatible with GPL-3.0-or-later and include the right to
submit the work. By participating, you agree to the
[Code of Conduct](CODE_OF_CONDUCT.md).
