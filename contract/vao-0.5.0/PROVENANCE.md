# Vendored VAO 0.5.0 candidate provenance

This directory contains the VAO Standard 0.5.0 candidate artifacts used by VAO
Blender 0.4.0. They were copied from `modavis-project/vao-standard` commit
`d17b3f188fdf7fadd01ba025383e4feca8def935` on 2026-08-28.

The candidate adds explicit multi-carrier release bindings and carrier-member
delivery required by the Kinoorgel release. It is pinned by commit and file
digests because VAO 0.5.0 has not yet been declared a published standard.

`Schemas/vao-release-bundle-0.5.0.json` is the upstream normative artifact
inventory. The exact reference validator and its local dependencies are retained
under `Tools/`. `Schemas/vao-manifest-0.4.0.schema.json` is included only as the
unchanged source-checkout marker required by the upstream resource locator.

The upstream `NOTICE` and `LICENSE` govern this material. Documentation,
schemas, semantic artifacts, and fixtures are CC BY 4.0; reference software is
Apache-2.0.
