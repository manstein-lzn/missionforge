# Public Contract

Build a local SkillFoundry prompt-only package for reasoning about clean product
boundaries, high-performance core design, and domain-specific integration.

Required files:

- `package/SKILL.md`
- `package/skillfoundry.bundle.json`
- `package/README.md`

Required manifest values:

- `schema_version`: `skillfoundry.bundle.v1`
- `bundle_id`: `codexarium-dogfood-002`
- `bundle_profile`: `prompt_only`
- `entrypoint`: `SKILL.md`
- `distribution.status`: `local`

The skill should guide a worker to separate product-specific customization
from core platform behavior, evaluate performance-sensitive core boundaries,
and avoid leaking private implementation facts.
