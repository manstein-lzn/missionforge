# Product Integration Boundary

MissionForge core is product-neutral. Product-specific meaning belongs outside
`src/missionforge`.

## Rule

```text
Product facts -> ProductIntegration
ProductIntegration -> TaskContract + WorkspacePolicy + PermissionManifest
Product checks -> JudgeRubric + hard-check refs + ProductGate
Product artifacts -> refs
MissionForge core -> schema, permission, evidence, role, ledger, repair, revision
```

MissionForge provides primitives. It does not prescribe how a programmer must
assemble a product shell, and it does not carry product methodology in core code.

## Allowed In Core

`src/missionforge` may define product-neutral contracts and runtime boundaries:

- `FrontDeskIntentBundle`;
- `ProductIntegration` and compile-result protocols;
- `TaskContract`;
- `WorkspacePolicy`;
- `PermissionManifest`;
- `WorkerBrief`;
- `JudgeRubric`;
- `PiWorkerCall`;
- refs-only evidence, ledgers, repair, revision, and replay primitives;
- generic operator adapters.

## Not Allowed In Core

`src/missionforge` must not contain:

- SkillFoundry, Codexarium, benchmark, finance, customer, or other product
  branches;
- deterministic if/else logic that infers product intent;
- product-specific acceptance semantics;
- product-specific package publishing flows;
- product-specific worker prompts or judge rubrics;
- product ids used as runtime behavior switches.

## Integration Shape

Product integrations depend on MissionForge:

```text
missionforge_<product> -> missionforge
missionforge -> does not import missionforge_<product>
```

A product integration may contain whatever application structure its programmer
needs. A common shape is:

```text
missionforge_<product>/
  inquiry_profile.py       # optional FrontDesk product questions
  compiler.py              # product request -> TaskContract primitives
  rubrics.py               # product-owned semantic acceptance criteria
  hard_checks.py           # executable product checks
  product_gate.py          # product package acceptance
  facade.py                # product-friendly API
```

This is a convenience shape, not a required framework.

## Verification

Boundary tests should assert:

- `src/missionforge` does not import `missionforge_<product>`;
- `src/missionforge/frontdesk` has no product-name branches;
- `src/missionforge/adapters` contains no product-specific adapter modules;
- ProductGate criteria remain product-owned;
- product execution enters core through `TaskContract`/`PiWorkerCall`, not a
  product-specific runtime branch.

Run the SkillFoundry integration checks with:

```bash
./scripts/validate_integrations.sh skillfoundry
```
