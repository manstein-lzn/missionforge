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

## Thin Integration Rule

A product integration should be manual-first and code-thin. MissionForge exists
to give capable PiWorker agents hard boundaries, tools, evidence refs, and
independent judgment. It should not encourage programmers to rebuild product
intelligence as thousands of lines of deterministic Python.

Keep product semantics in artifacts that PiWorker can read and write:

- product manuals and operating instructions;
- inquiry profiles and task contracts;
- source policies and tool-use policies;
- judge rubrics and repair instructions;
- evidence indexes, deltas, research notes, and final packages.

Keep product code limited to mechanical responsibilities:

- compile requests into MissionForge primitives;
- wire role-specific PiWorker calls;
- expose bounded tools and execute LLM-authored plans;
- validate schemas, refs, permissions, output presence, and package shape;
- record ledgers, repair tickets, revision records, and replay metadata.

Do not add product code that pretends to be the expert:

- deterministic intent inference;
- domain-specific conclusion logic;
- hardcoded topic branches;
- semantic source importance rules for arbitrary domains;
- product-level acceptance hidden behind validators.

Code volume is a design signal. A product integration that needs a few hundred
lines of orchestration plus clear manuals and rubrics is usually aligned with
MissionForge. A product integration that grows into many thousands of lines of
semantic workflow logic should be reviewed and compressed back into PiWorker
instructions, tool boundaries, and artifacts. Tests, UI, and low-level
collectors are exceptions, but product reasoning should stay inspectable.

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

- Codexarium, benchmark, finance, customer, or other product
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

Run active integration checks with:

```bash
./scripts/validate_integrations.sh deepresearch
```
