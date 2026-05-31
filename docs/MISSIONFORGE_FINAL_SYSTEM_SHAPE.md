# MissionForge Final System Shape

Last updated: 2026-05-31

Status: target architecture for the simplified PiWorker-centered MissionForge.

## Goal

Define the system shape MissionForge should converge toward after the value
benchmark and architecture rethink.

The target is not a large deterministic workflow engine. The target is a small
runtime substrate that lets PiWorker do high-intelligence work inside explicit
contracts, hard permissions, inspectable workspaces, and independent judgment.

## End-To-End Flow

```text
User conversation
  -> FrontDesk PiWorker session
  -> FrontDeskIntentBundle
  -> Product Integration
  -> TaskContract
  -> WorkerBrief + JudgeRubric + WorkspacePolicy + PermissionManifest
  -> Executor PiWorker
  -> artifacts + ExecutionReport
  -> Judge PiWorker
  -> JudgeReport
  -> accepted | repair | revision_required | rejected
  -> FinalPackage or RepairBrief or RevisionRequest
  -> DecisionLedger
```

This flow separates four things that were previously too easy to blend:

- user conversation;
- durable task obligation;
- worker-facing execution context;
- judge-facing acceptance criteria.

## Major Components

### 1. FrontDesk

FrontDesk is the user's conversational entry point.

Responsibilities:

- understand messy, incomplete, casual user intent;
- ask limited but high-value clarification questions;
- infer likely hidden pain and confirm it;
- collect goals, users, constraints, non-goals, risks, and expected outcomes;
- fill ProductInquiryProfile slots when provided;
- produce FrontDeskIntentBundle.

Non-responsibilities:

- no final domain contract authority;
- no runtime execution;
- no product-specific branches in MissionForge core;
- no deterministic fallback that pretends to understand user needs.

### 2. Product Integration

Product Integration is the only product-specific compilation layer.

Responsibilities:

- provide ProductInquiryProfile;
- consume FrontDeskIntentBundle;
- compile TaskContract;
- provide product-specific judge rubric fragments;
- provide product-specific hard check declarations;
- define final package expectations.

Examples:

- SkillFoundry integration compiles an intent bundle into a skill-development
  TaskContract and product packaging expectations.
- A future financial research integration compiles an intent bundle into a
  research contract, data-source boundaries, and risk disclaimers.

MissionForge core should not know either product's semantics.

### 3. Contract Kernel

The Contract Kernel owns durable task authority.

Primary object:

```text
TaskContract
```

Expected fields:

- `contract_id`
- `schema_version`
- `product_id`
- `objective`
- `background`
- `users_or_audience`
- `non_goals`
- `assumptions`
- `required_outputs`
- `hard_constraints`
- `semantic_acceptance`
- `risk_notes`
- `workspace_policy_ref`
- `permission_manifest_ref`
- `judge_rubric_ref`
- `revision_policy`
- `source_refs`
- `created_by`
- `created_at`
- `contract_hash`

TaskContract is not automatically the worker prompt. It is the authority from
which worker and judge views are derived.

### 4. Projection Layer

The Projection Layer turns the contract into role-specific packets.

```text
TaskContract
  -> WorkerBrief
  -> JudgeRubric
  -> RepairBrief
```

`WorkerBrief` is optimized for execution:

- what to build or produce;
- relevant context;
- allowed workspace;
- required artifacts;
- constraints;
- completion reporting format.

`JudgeRubric` is optimized for acceptance:

- what must be true;
- what evidence to inspect;
- what hard checks are mandatory;
- what semantic qualities matter;
- when to ask for repair;
- when to request revision instead of repair.

This split is one of the main lessons from the benchmark: contract truth and
worker prompt should not be forced to be the same artifact.

### 5. Workspace Runtime

The Workspace Runtime owns physical work boundaries.

Responsibilities:

- create the run workspace;
- write contract and projection artifacts;
- create allowed input/output directories;
- enforce path containment for file tools;
- pass permission manifests to PiWorker;
- record execution and judge packets;
- preserve artifact refs;
- maintain checkpoint and decision ledgers.

The workspace is the artifact plane. It remains filesystem-based for now
because PiWorker and many useful outputs are file-oriented.

### 6. Permission System

The Permission System is a hard boundary, not a prompt convention.

Primary object:

```text
PermissionManifest
```

Expected fields:

- readable roots;
- writable roots;
- executable command policy;
- network policy;
- environment variable allowlist;
- secret handling policy;
- max turns or runtime budget;
- max file size or artifact count where useful;
- denied paths;
- product-specific declared capabilities by ref, not code branch.

Near-term implementation may enforce a subset. The final shape should enforce
file and command boundaries at the PiWorker runtime/tool layer.

Known risk:

- file tools can be guarded by path containment;
- shell tools require stronger command, cwd, subprocess, and path policy than
  prompt-only instruction.

### 7. Executor PiWorker Node

The Executor receives an ExecutionPacket derived from WorkerBrief and
PermissionManifest.

Responsibilities:

- inspect allowed refs;
- produce required artifacts;
- run allowed tools;
- report what changed;
- cite artifact refs and evidence refs;
- propose repair or revision only as a request.

Non-responsibilities:

- no self-acceptance;
- no contract mutation;
- no permission expansion;
- no final product gate authority.

### 8. Judge PiWorker Node

The Judge receives a JudgePacket derived from TaskContract, JudgeRubric,
ExecutionReport, artifacts, and hard-check results.

Responsibilities:

- evaluate semantic fit against the rubric;
- identify missing or weak evidence;
- distinguish repairable implementation gaps from contract problems;
- return one of:
  - `accepted`
  - `repair`
  - `revision_required`
  - `rejected`

The Judge is allowed to perform semantic judgment. Code still validates the
JudgeReport schema, role separation, refs, and hard-check preconditions.

### 9. Repair And Revision

Repair and revision are different.

Repair:

- contract remains correct;
- artifact does not satisfy it yet;
- produce a RepairBrief and re-run Executor.

Revision:

- contract is wrong, incomplete, unsafe, or impossible;
- create a RevisionRequest;
- require Product Integration, policy, operator, or user authority depending
  on revision policy;
- freeze a new TaskContract revision before continuing.

No repair path may silently weaken acceptance.

### 10. Decision Ledger

The DecisionLedger is the system memory.

It records append-only events such as:

- contract frozen;
- worker packet issued;
- execution completed;
- hard check failed;
- judge accepted;
- judge requested repair;
- revision requested;
- revision approved;
- final package emitted;
- cost and metrics projection written.

Ledger entries should cite refs and compact summaries, not raw bodies.

## Target Workspace Layout

One possible run layout:

```text
runs/{run_id}/
  contract/
    task_contract.json
    task_contract.hash
    revisions.jsonl
  frontdesk/
    intent_bundle.json
    semantic_lock.json
    source_refs.json
  projections/
    worker_brief.md
    judge_rubric.md
    repair_brief.md
  policy/
    workspace_policy.json
    permission_manifest.json
  packets/
    execution_packet.json
    judge_packet.json
  artifacts/
    ...
  reports/
    execution_report.json
    judge_report.json
    final_package.json
  ledgers/
    decision_ledger.jsonl
    metrics.jsonl
  checkpoints/
    latest.json
```

The exact filenames can evolve. The separation should not.

## Relationship To Existing MissionIR

Existing MissionIR work contains useful principles:

- structured task truth;
- profile-independent constraints;
- freeze and hash;
- evidence requirements;
- explicit repair/revision;
- no worker self-acceptance.

The final system should preserve those principles while making the primary
contract smaller and easier for product integrations and PiWorker roles to use.

MissionIR can remain as:

- compatibility input;
- high-detail export;
- legacy runtime contract;
- optional product contract representation.

New implementation should prefer TaskContract plus role projections.

## Relationship To Existing Runtime

The existing runtime proves many boundaries, but the final shape should be
smaller.

Keep:

- refs-only state;
- no product branches;
- PiWorker-only direction;
- metrics as diagnostics;
- revision discipline;
- workspace artifacts;
- safe-point resume.

Reduce:

- deterministic semantic routing;
- complex proposal machinery;
- large verifier registry ambitions;
- runtime decomposition for its own sake;
- adapter abstractions that imply many workers.

## Final Acceptance Criteria

MissionForge reaches the target shape when a product can integrate without
changing core code and run this loop:

1. Product provides ProductInquiryProfile and contract compiler.
2. FrontDesk PiWorker turns casual user conversation into FrontDeskIntentBundle.
3. Product Integration compiles and freezes TaskContract.
4. MissionForge projects WorkerBrief, JudgeRubric, WorkspacePolicy, and
   PermissionManifest.
5. Executor PiWorker produces artifacts inside the allowed workspace.
6. Hard checks reject path, schema, permission, secret, and missing-artifact
   violations.
7. Judge PiWorker performs semantic acceptance using rubric and evidence.
8. Repair reuses the same contract; revision creates an explicit new contract.
9. DecisionLedger and metrics allow reproduction, audit, and benchmark
   comparison.
10. No product-specific logic is required in `src/missionforge`.

## Non-Goals For The Target Shape

- no general multi-worker marketplace;
- no prompt-only security model;
- no code-based fake understanding of user needs;
- no in-memory artifact plane before the workspace model is stable;
- no product-specific runtime branches;
- no automatic contract weakening;
- no treating token efficiency as the main reason for MissionForge to exist.
