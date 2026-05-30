# Public Contract

Build a local SkillFoundry prompt-only package.

Required files:

- `package/SKILL.md`
- `package/skillfoundry.bundle.json`
- `package/README.md`

Required manifest values:

- `schema_version`: `skillfoundry.bundle.v1`
- `bundle_id`: `sf-simple-skill-001`
- `bundle_profile`: `prompt_only`
- `entrypoint`: `SKILL.md`
- `capability_surface.codex_skill.entry_ref`: `package/SKILL.md`
- `verification.matrix_ref`: `product_contract/product_acceptance_matrix.json`
- `verification.product_grade_ref`: `qa/product_grade_report.json`
- `distribution.status`: `local`

The skill should be a reusable engineering planning checklist. It must not
require credentials, network access, or raw transcript storage.
