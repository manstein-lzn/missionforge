# SkillFoundry Product Shell Validation Plan

Last updated: 2026-05-29

Status: architecture validation plan; Product Slice 1 prompt-only dogfood has
product-grade live evidence, and Product Slice 2 `code_runtime` is implemented
for deterministic validation.

## Purpose

This document defines where and how to start rebuilding SkillFoundry as a thin
product shell on the fixed MissionForge substrate.

The validation hypothesis is:

```text
MissionForge is strong enough to be the generic agent-work substrate, and
SkillFoundry can be rebuilt mostly as product contracts, bundle validators,
ProductGradeGate policy, registry semantics, reports, and small glue code.
```

The point of this validation is not to port the old SkillFoundry runtime. The
point is to prove that a real Capability Bundle product can be assembled by
composing MissionForge primitives instead of re-creating them.

## Architectural Decision

Start inside the existing integration directory:

```text
integrations/skillfoundry/
```

Do not start in a sibling repository yet. Do not add SkillFoundry branches to
MissionForge core. Do not add another production worker.

This is the correct first worksite because it preserves the dependency
direction:

```text
missionforge_skillfoundry -> missionforge
missionforge -> does not import missionforge_skillfoundry
```

Extraction into a separate SkillFoundry repository can happen later, after the
product shell has a stable API and has survived at least one real dogfood loop.

## Source Context

The sibling `../skillfoundry` project established the product target:

```text
User intent
  -> frozen product contract
  -> bounded strong-worker build
  -> independent verification
  -> ProductGradeGate
  -> registry
```

The enduring product semantics to preserve are:

- Capability Bundle, not prompt generation.
- FrontDesk-style translation from vague user needs into frozen product
  contracts.
- Bundle profiles and risk domains that inject implementation-grade checks.
- Independent verifier plus ProductGradeGate before product-grade promotion.
- Registry states that distinguish candidate assets from product-grade assets.
- Refs-only reports that do not expose raw conversation, prompts, transcripts,
  provider payloads, package bodies, or secrets.

The old implementation also included responsibilities that now belong to
MissionForge and should not be ported into the product shell:

- generic worker runtime;
- generic context ledger;
- generic adaptive loop state;
- generic evidence ledger;
- generic verifier and repair runtime;
- generic steering substrate;
- generic run inspection and operator history;
- LangGraph, ContextForge, and ForgeUnit-specific runtime infrastructure.

## Fixed Base

MissionForge is the fixed base for this validation:

- `MissionIR` carries task facts.
- `FrozenMissionContract` locks mission truth.
- `WorkUnitContract` bounds worker attempts.
- `pi-agent-runtime` is the only production worker.
- Evidence, artifacts, metrics, and verifier outputs are refs.
- The verifier closes MissionForge missions; worker self-report does not.
- Controlled steering proposes repairs or revisions without owning durable
  truth.
- Revision authority changes frozen contracts explicitly.

SkillFoundry may consume MissionForge public contracts and existing integration
bridges. MissionForge core must not import SkillFoundry.

## Responsibility Split

SkillFoundry owns product semantics:

- `SkillFoundryRequest`;
- `SkillProductContract`;
- bundle profiles;
- risk domains;
- capability surface;
- package manifest semantics;
- product acceptance matrix;
- bundle validators;
- ProductGradeGate;
- registry policy;
- product report shape;
- product-facing CLI/API glue.

MissionForge owns substrate mechanics:

- mission freezing;
- profile expansion mechanics;
- work-unit dispatch;
- PI Agent runtime integration;
- evidence and artifact refs;
- verifier closure;
- repair and controlled steering primitives;
- mission revision authority;
- operator inspection and controls.

The validation fails if SkillFoundry needs to replace any MissionForge substrate
mechanic to complete the first product slice.

## Current Baseline

The current branch contains the deterministic prompt-only MVP path from the
broader SkillFoundry-on-MissionForge roadmap:

- product contracts and bundle profiles;
- prompt-only contract compilation into MissionForge;
- prompt-only package validators;
- ProductGradeGate;
- local registry;
- thin runtime facade over `MissionRuntime`;
- opt-in live PI Agent dogfood harness;
- deterministic/faux PI Agent execution for expected output files.

Product Slice 2 now adds the `code_runtime` profile without changing
MissionForge core:

- profile-specific product contract defaults;
- code-runtime acceptance matrix;
- code-runtime manifest validation;
- MissionIR compiler dispatch for code-runtime package artifacts;
- generic `file_exists`, `json_field_exists`, and `command` validators;
- code-runtime bundle validators for runtime assets, scripts, schemas, raw
  context markers, and package self-grade claims;
- ProductGradeGate target package ref consistency checks;
- runtime facade coverage through the existing `MissionRuntime` path;
- FrontDesk mapping coverage for selecting `code_runtime`.

That baseline is enough to start Codexarium-style architecture validation. The
next work should use a realistic product request and package fixture rather
than another substrate abstraction pass.

Implementation guidance for adding the second and later bundle profiles lives
in `docs/bundle_profile_development_guide.md`. The same guide now serves as
the template for the third and later bundle profiles.

## Validation Question

The main question is:

```text
When SkillFoundry builds a real product-facing bundle, can almost all work be
expressed as product contracts, validators, registry policy, reports, and thin
glue around MissionForge?
```

The answer is "yes" only if:

- no SkillFoundry-specific branch is added to MissionForge core;
- no second production worker path is added;
- no product-owned evidence ledger is introduced;
- package quality is enforced by ProductGradeGate, not by worker claims;
- repair loops reuse MissionForge verifier, repair, steering, and revision
  surfaces;
- new bundle profiles add validators and contract expansion, not runtime forks.

## Product Slice 1

The first product slice is deliberately small:

```text
Profile: prompt_only
Package:
  package/SKILL.md
  package/skillfoundry.bundle.json
  package/README.md
```

This slice validates the essential shell:

- user intent becomes a frozen SkillFoundry product contract;
- the contract compiles to MissionForge mission truth;
- PI Agent creates candidate package artifacts;
- deterministic validators inspect the package;
- ProductGradeGate decides product-grade vs candidate;
- registry records the result without overstating quality;
- product report exposes refs only.

This is the correct first slice because it tests the product lifecycle without
mixing in runtime helpers, MCP, services, data ingestion, or UI complexity.

## First Real Scenario

The first real dogfood scenario should be small, useful, and verifiable without
private data or external services:

```text
Build a Codex skill that helps an agent turn a small product-planning markdown
brief into a refs-only implementation checklist and verification checklist.
```

Expected bundle behavior:

- explain when the skill should trigger;
- define what project docs the agent should inspect first;
- transform a short planning brief into implementation and verification
  checklists;
- keep outputs refs-only where product state is durable;
- forbid raw prompt, transcript, provider payload, API key, or secret leakage;
- require verification evidence before claiming completion.

Expected package files:

```text
package/SKILL.md
package/skillfoundry.bundle.json
package/README.md
```

Expected product artifacts:

```text
product_contract/skill_product_contract.json
product_contract/product_acceptance_matrix.json
product_contract/compiler_report.json
qa/skill_bundle_validation_report.json
qa/product_grade_report.json
registry/skillfoundry_registry.json
reports/skillfoundry_product_report.json
```

If ProductGradeGate fails, also produce:

```text
qa/product_repair_packet.json
```

## Execution Roadmap

### V0: Documentation And Boundary Lock

Status: this document.

Deliverables:

- architecture validation plan;
- linked SkillFoundry integration README;
- explicit start location;
- explicit non-goals and escalation gates.

Acceptance:

- the start location is `integrations/skillfoundry/`;
- product-shell vs substrate responsibilities are explicit;
- validation evidence is defined before product coding continues.

### V1: Live Dogfood Harness

Deliverables:

- opt-in live PI Agent dogfood entrypoint;
- dogfood report written as refs-only product evidence;
- failure classification:
  - product contract failure;
  - worker execution failure;
  - verifier failure;
  - product-grade failure;
  - registry failure;
  - completed product-grade registration.

Acceptance:

- live execution is disabled by default;
- current Codex provider configuration is used only when explicitly enabled;
- API keys, provider payloads, and raw model messages are absent from artifacts;
- a prompt-only request produces either a product report or a classified
  failure report.

### V2: Product Slice 1 Dogfood

Deliverables:

- the first real scenario represented as `SkillFoundryRequest`;
- generated prompt-only bundle package;
- validator report;
- ProductGradeGate report;
- registry decision;
- refs-only product report.

Acceptance:

- package contains no raw request, provider payload, or transcript material;
- manifest has stable bundle identity and safe refs;
- README explains install and use boundaries without claiming product-grade
  status;
- ProductGradeGate makes a clear product-grade or candidate decision.

### V3: Repair Loop Exercise

Deliverables:

- one intentionally imperfect candidate package;
- repair packet from ProductGradeGate;
- second build attempt using MissionForge repair or controlled steering;
- final report comparing attempt 1 and attempt 2.

Acceptance:

- repair guidance is product-level guidance, not a new runtime protocol;
- MissionForge remains the authority for attempt boundaries and verifier
  closure;
- the second attempt improves at least one blocking finding.

### V4: Second Profile Selection

Deliverables:

- profile-selection memo based on V1 to V3 evidence;
- selected next profile contract additions;
- validator additions;
- at least one realistic package that fails before hardening and passes after
  repair.

Acceptance:

- the selected profile is justified by dogfood evidence;
- profile support lives under `integrations/skillfoundry`;
- no MissionForge core branch is needed.

### V5: Product Surface Decision

Deliverables:

- decision whether the next interface should be CLI, local API, or minimal UI;
- product report shape for the chosen surface;
- smoke path that runs without live LLM by default.

Recommended default:

```text
Start with CLI/API, not UI.
```

Reason:

The validation is about substrate fitness and product-grade delivery. UI should
come after the run/report/registry loop is stable enough to show real state.

### V6: Extraction Decision

Deliverables:

- decision memo on whether SkillFoundry remains an in-repo integration or
  becomes a separate product repository;
- public API boundary for `missionforge_skillfoundry`;
- migration checklist if extraction is approved.

Acceptance:

- extraction is based on stable product API evidence, not directory preference;
- MissionForge remains usable without installing SkillFoundry;
- deterministic validation still runs offline.

## Directory Shape

Keep the product shell compact:

```text
integrations/skillfoundry/
  docs/
    skillfoundry_integration.md
    skillfoundry_on_missionforge_plan.md
    skillfoundry_product_shell_validation_plan.md
  src/missionforge_skillfoundry/
    product_contract.py
    compiler.py
    validators.py
    product_grade_gate.py
    registry.py
    reports.py
    runtime.py
    dogfood.py
  tests/
```

Do not create:

```text
src/missionforge/adapters/skillfoundry.py
src/missionforge/.../skillfoundry_*.py
workers/skillfoundry-worker/
```

## Artifact Policy

Product state should stay refs-only wherever it is public or durable.

Allowed durable refs:

- product contract refs;
- mission refs;
- run refs;
- package file refs;
- validator report refs;
- product-grade report refs;
- repair packet refs;
- registry decision refs;
- product report refs.

Forbidden durable payloads:

- raw prompt;
- raw transcript;
- raw conversation;
- raw provider payload;
- API keys or provider secrets;
- package bodies embedded inside reports;
- worker self-report treated as product-grade proof.

The integration may inspect package files for validation. It should not inline
their bodies into product reports or registry decisions.

## Live Provider Policy

Live provider execution is allowed only for explicit dogfood runs.

Rules:

- default tests stay deterministic and offline;
- the live dogfood path may read the current environment's Codex-compatible
  provider key and base URL;
- provider configuration must not be copied into reports;
- raw provider payloads must not become public product state;
- live dogfood artifacts should stay under `.metaloop/` or another ignored
  operational workspace unless the user explicitly asks to preserve them.

## Failure Classification

Every dogfood failure should be classified before deciding the next action.

| Failure class | Meaning | Next action |
| --- | --- | --- |
| `product_contract_failure` | SkillFoundry compiled an invalid or ambiguous product contract | repair integration contract/compiler |
| `worker_execution_failure` | PI Agent did not produce required artifacts or failed before useful output | repair work-unit shaping, provider replay, turn budget, or worker runtime |
| `verifier_failure` | MissionForge verifier rejected the run | inspect verifier evidence and repair mission/work output |
| `product_grade_failure` | MissionForge run completed, but bundle quality gates failed | use ProductGradeGate repair packet and retry |
| `registry_failure` | Product-grade/candidate decision could not be recorded correctly | repair registry/report glue |
| `substrate_gap` | A generic MissionForge primitive is missing for product shells | escalate to MissionForge core design |
| `completed_product_grade` | Product-grade package registered with refs-only evidence | proceed to second profile selection |

Do not treat worker self-report, generated prose, or generic verifier pass as
product-grade registration.

## Escalation Gates

Stop and redesign if validation appears to require any of the following:

- SkillFoundry import from `src/missionforge`;
- product-specific switches in MissionForge runtime;
- another production worker beside `pi-agent-runtime`;
- a product-owned replacement for MissionForge evidence, verifier, repair,
  steering, or revision authority;
- registry promotion based on worker self-report;
- raw user/provider material in public product state;
- second-profile support implemented as runtime branching instead of contract
  and validator expansion.

Escalate to MissionForge core only when the issue is substrate-generic and
would affect future product shells too.

## Second Profile Selection Rules

Do not choose the second profile by preference. Choose it from Product Slice 1
evidence.

Candidate profiles:

| Profile | Choose when dogfood shows |
| --- | --- |
| `script_tool` | users need local scripts, CLI helpers, fixtures, and smoke tests |
| `knowledge_runtime` | reference-heavy skills expose the most product value |
| `code_runtime` | executable helper logic dominates real acceptance criteria |
| `mcp_runtime` | tool-facing agent interfaces are the main reusable asset |
| `service_runtime` | long-running local service behavior is central to the capability |

The next profile is valid only if it adds SkillFoundry-owned contracts and
validators, not MissionForge runtime branches.

## Validation Commands

Default deterministic validation:

```bash
PYTHONPATH=src:integrations/skillfoundry/src \
  python3 -m unittest discover -s integrations/skillfoundry/tests
```

Integration boundary validation:

```bash
./scripts/validate_integrations.sh skillfoundry
```

Core regression:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests
```

PI Agent runtime regression:

```bash
npm test --prefix workers/pi-agent-runtime
```

Live dogfood is explicit opt-in:

```bash
MISSIONFORGE_SKILLFOUNDRY_LIVE_DOGFOOD=1 \
PYTHONPATH=src:integrations/skillfoundry/src \
  python3 -m unittest discover -s integrations/skillfoundry/tests \
    -p "test_skillfoundry_live_dogfood.py"
```

The exact live command may change as the dogfood scenario is refined. The
invariant does not change: default tests stay offline.

## Success Criteria

The architecture validation succeeds when:

- a realistic SkillFoundry request builds a prompt-only Capability Bundle
  through MissionForge;
- the result is validated, product-graded, and registered as either candidate or
  product-grade with no quality ambiguity;
- all SkillFoundry product semantics remain under `integrations/skillfoundry`;
- MissionForge core stays product-neutral;
- live PI Agent dogfood produces a concrete product report or classified
  failure report;
- repair guidance, if needed, flows through MissionForge work boundaries rather
  than a new SkillFoundry runtime;
- the next bundle profile is selected from evidence instead of speculation.

## Current Evidence

Product Slice 1 has an opt-in live PI Agent dogfood pass:

```text
Workspace: .metaloop/skillfoundry_live_dogfood_sf7_repair3/
Dogfood report: reports/skillfoundry_live_dogfood_report.json
Outcome category: completed
Run status: completed
Registry status: product_grade_registered
Report hash:
  sha256:97b2fb38d3b86af0484ec9a048bed53ffb3f208edbe23968604751be0790fd25
```

The run compiled a prompt-only SkillFoundry request, executed
`pi-agent-runtime` in live mode through MissionForge, produced
`package/SKILL.md`, `package/skillfoundry.bundle.json`, and
`package/README.md`, passed MissionForge verification, passed the
SkillFoundry bundle validators and ProductGradeGate, and registered the package
as `product_grade_registered`.

A common leak-marker scan over the repair3 workspace found no matches for API
key names, provider payload markers, raw prompt/transcript markers, or `sk-*`
token-shaped strings.

## Immediate Next Step

Use the Product Slice 1 evidence to plan the second bundle profile and first
real SkillFoundry product scenario. The recommended default is:

```text
Next profile: script_tool
Reason: it is the smallest profile that adds real runtime assets, fixtures, and
smoke tests without requiring MCP, services, data ingestion, or UI.
```

Do not implement `knowledge_runtime`, `code_runtime`, MCP, service bundles, or
UI until the second-profile memo explains why the selected profile is the right
next product pressure test.
