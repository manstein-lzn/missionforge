# Public SkillFoundry Contract

This benchmark task expects a local SkillFoundry prompt-only package.

Required output files:

- `package/SKILL.md`
- `package/skillfoundry.bundle.json`
- `package/README.md`

The manifest at `package/skillfoundry.bundle.json` must be a JSON object with
these exact product-facing requirements:

- `schema_version`: `skillfoundry.bundle.v1`
- `bundle_id`: `complex-method-skill-001`
- `bundle_profile`: `prompt_only`
- `entrypoint`: `SKILL.md`
- `capability_surface.codex_skill.entry_ref`: `package/SKILL.md`
- `runtime_assets`: `[]`
- `data_assets`: `[]`
- `references`: `[]`
- `environment`: `{}`
- `permissions`: `{}`
- `verification.matrix_ref`: `product_contract/product_acceptance_matrix.json`
- `verification.product_grade_ref`: `qa/product_grade_report.json`
- `distribution.status`: `local`

The skill should describe a reusable engineering method. It should help a
worker turn a messy technical request into a durable implementation plan,
execution checklist, acceptance criteria, and review packet without depending
on network access or credentials.

Boundary requirements:

- Do not read credentials.
- Do not require network access.
- Do not store raw conversation text, hidden prompts, transcript bodies,
  provider payload bodies, credentials, or secrets in the package.
- `package/README.md` may describe the package policy, installation intent,
  and local checks, but it must not contain private benchmark internals.
