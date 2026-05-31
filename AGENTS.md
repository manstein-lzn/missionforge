# MissionForge Agent Instructions

This file governs the whole repository.

MissionForge is being simplified into a PiWorker-centered agent runtime with
hard workspace, contract, evidence, and permission boundaries. The project is
not a deterministic Python system that tries to understand arbitrary user needs
through branching logic.

## Core Direction

- PiWorker is the only first-class intelligent worker direction.
- MissionForge core stays product-neutral. It must not contain SkillFoundry,
  Codexarium, benchmark, finance, customer, or other product-specific branches.
- Product-specific meaning belongs in external product integrations, inquiry
  profiles, task contracts, judge rubrics, artifacts, and product packages.
- FrontDesk is a high-intelligence requirements-discovery surface. If an
  LLM/PiWorker authoring node is required and unavailable, fail closed instead
  of fabricating understanding with code.
- MissionForge code owns hard boundaries: schemas, refs, workspace layout,
  permission manifests, contract freeze, revision records, secret exclusion,
  role separation, and ledgers.
- PiWorker nodes own semantic work: grilling requirements, designing solutions,
  executing tasks, judging artifacts, proposing repairs, and drafting revision
  requests.

## Non-Negotiable Laws

1. Raw chat is not operational task truth.
2. A frozen task contract, or an explicit revision of it, is the durable task
   authority.
3. MissionIR should be treated as a legacy/high-detail contract shape unless a
   change intentionally preserves it. New work should prefer a minimal
   TaskContract with WorkerBrief and JudgeRubric projections.
4. The execution worker may not self-accept its own work.
5. Semantic acceptance may be produced by a separate Judge PiWorker role, but
   that judge must use the frozen contract, judge rubric, artifact refs, and
   recorded evidence.
6. Code may reject invalid, unsafe, unauthorized, unreferenced, stale, or
   malformed outputs. Code should not pretend to perform product-level semantic
   judgment.
7. Repair must not silently weaken the frozen contract. Contract changes after
   execution starts require an explicit revision record.
8. Runtime state and operator output should cite refs instead of embedding raw
   prompts, transcripts, provider payloads, stdout/stderr bodies, artifact
   bodies, or secrets by default.
9. Metrics are diagnostics and cost evidence. Metrics are not semantic route or
   acceptance authority.
10. If a proposed change adds product semantics to `src/missionforge`, stop and
    move that behavior to an integration, profile, rubric, fixture, or test
    package.

## Preferred Architecture

Use this shape for new design and implementation work:

```text
FrontDesk
  -> FrontDeskIntentBundle
  -> ProductIntegration
  -> TaskContract
  -> WorkerBrief + JudgeRubric + WorkspacePolicy + PermissionManifest
  -> PiWorker execution node
  -> artifact refs + execution report
  -> independent Judge PiWorker node
  -> accepted | repair | revision_required | rejected
  -> decision ledger + final package
```

Keep these roles separate:

- FrontDesk discovers needs.
- ProductIntegration compiles domain-specific contracts.
- MissionForge core freezes contracts, prepares projections, invokes PiWorker,
  enforces workspace and permission boundaries, records evidence, and resumes
  state.
- PiWorker executes and judges through role-specific prompts and manifests.
- Product gates provide rubrics and hard checks; they do not become core
  product branches.

## Implementation Rules

- Prefer small data contracts over large orchestration classes.
- Prefer explicit artifacts and ledgers over hidden process memory.
- Prefer hard permission checks in the runtime/tool layer over prompt-only
  restrictions.
- Keep filesystem artifacts as the main artifact plane for now. Do not build an
  in-memory dataflow system until the workspace and permission model is stable.
- Do not introduce a public multi-worker registry. If a seam is needed, make it
  a PiWorker runtime boundary, not a provider zoo.
- Do not add deterministic regex/if-else logic to infer user needs, product
  intent, or semantic acceptance. Use LLM-authored artifacts plus schema and
  boundary validation.
- When changing behavior, update the relevant docs before considering the work
  complete.
- When adding tests, test contract shape, permission rejection, role separation,
  refs-only state, and revision behavior before broad semantic assertions.

## Legacy Code Guidance

The existing MissionIR, runtime, verifier, steering, metric, and revision
modules contain useful invariants and test evidence. Do not delete them
casually. When replacing them, preserve the underlying principles:

- product-neutral core
- frozen contract authority
- explicit revision
- refs-first evidence
- no worker self-acceptance
- hard permission and secret boundaries
- inspectable ledgers

At the same time, do not keep expanding legacy deterministic orchestration just
because the modules exist. New work should converge toward the simplified
agentic architecture documented under `docs/`.
