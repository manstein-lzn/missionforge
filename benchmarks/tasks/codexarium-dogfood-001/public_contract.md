# Public Contract

Build a local SkillFoundry prompt-only package for turning vague product pain
into an executable local AI workflow plan.

Required files:

- `package/SKILL.md`
- `package/skillfoundry.bundle.json`
- `package/README.md`

Required manifest values:

- `schema_version`: `skillfoundry.bundle.v1`
- `bundle_id`: `codexarium-dogfood-001`
- `bundle_profile`: `prompt_only`
- `entrypoint`: `SKILL.md`
- `distribution.status`: `local`

The skill must not assume any private project internals. It should teach the
worker to extract real need, separate assumptions from confirmed requirements,
define a build plan, and preserve boundaries.
