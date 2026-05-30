# Public Contract

Build a local SkillFoundry prompt-only package for clarifying ambiguous user
requests before implementation.

Required files:

- `package/SKILL.md`
- `package/skillfoundry.bundle.json`
- `package/README.md`

Required manifest values:

- `schema_version`: `skillfoundry.bundle.v1`
- `bundle_id`: `sf-ambiguous-skill-001`
- `bundle_profile`: `prompt_only`
- `entrypoint`: `SKILL.md`
- `distribution.status`: `local`

The skill should help identify the real user pain, confirmed requirements,
open decisions, risks, and acceptance criteria. It must not store raw chat logs
or provider payloads.
