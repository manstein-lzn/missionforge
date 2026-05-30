# Public Contract

Build a product-gate-oriented SkillFoundry prompt-only package.

Required files:

- `package/SKILL.md`
- `package/skillfoundry.bundle.json`
- `package/README.md`

Required manifest values:

- `schema_version`: `skillfoundry.bundle.v1`
- `bundle_id`: `sf-product-gate-001`
- `bundle_profile`: `prompt_only`
- `entrypoint`: `SKILL.md`
- `runtime_assets`: `[]`
- `data_assets`: `[]`
- `references`: `[]`
- `environment`: `{}`
- `permissions`: `{}`
- `distribution.status`: `local`

The skill should emphasize product-grade checks, artifact refs, boundary
safety, and local verification.
