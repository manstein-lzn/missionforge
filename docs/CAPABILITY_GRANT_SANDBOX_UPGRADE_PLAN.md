# Capability Grant And Sandbox Upgrade Plan

Last updated: 2026-06-13

Status: phase 1 complete; phase 2 wired through the Pi runtime tool boundary.

## Goal

Add fine-grained, revocable, sandbox-backed runtime autonomy without expanding
MissionForge into a large orchestration framework.

The target is simple:

```text
CapabilityGrant -> ToolGateway -> SandboxRunner -> isolated agent process
```

MissionForge should let different agents operate with different visibility,
write scope, command scope, network scope, and resource budgets inside one
outer run. The boundary must be enforced by the runtime, not by prompt text.

## Design Principle

Maximum freedom comes from a hard world boundary, not from soft instruction.

MissionForge should therefore:

- keep the existing contract, workspace, and permission primitives;
- add a short-lived capability grant layer for runtime authority;
- execute tools inside a sandboxed process with an isolated filesystem view;
- exchange state between agents only through refs, ledgers, or promoted
  artifacts;
- avoid in-place privilege escalation of a live sandbox;
- keep the runtime control plane orthogonal to product semantics.

## What This Upgrade Is

This is a runtime control-plane upgrade, not a product rewrite.

Keep stable:

- `TaskContract`
- `WorkspacePolicy`
- `PermissionManifest`
- `PiWorkerCall`
- `WorkerBrief`
- `JudgeRubric`
- decision ledgers
- repair and revision authority

Add or sharpen:

- `CapabilityGrant`
- `SandboxProfile`
- `ToolGateway`
- `SandboxRunner`
- per-agent sandbox lifecycle
- grant revocation and expiry
- explicit agent handoff rules

## Core Primitives

### CapabilityGrant

A short-lived runtime authority token.

It should identify:

- the role;
- the contract hash;
- the workspace policy ref;
- the permission manifest ref;
- the sandbox profile ref;
- the workspace view ref;
- the issue time;
- the expiry time;
- the issuer;
- the parent grant, if any;
- the revocation state.

The grant is not the sandbox. It only authorizes the sandbox.

### SandboxProfile

A declarative execution profile that maps authority into an OS boundary.

It should describe:

- filesystem mounts and visibility;
- writable roots;
- readonly roots;
- denied roots;
- network state;
- cwd rules;
- environment allowlist;
- resource budget;
- process isolation strategy;
- syscall or capability restrictions where available.

### ToolGateway

The single front door for tool requests.

It should:

- validate the grant;
- validate the tool request against the manifest;
- select the sandbox profile;
- route to the sandbox runner;
- record refs-first audit evidence;
- fail closed on unsupported policy.

### SandboxRunner

The execution boundary for one agent instance.

It should run the agent in an isolated process or namespace-backed sandbox.
Prefer an existing Linux mechanism such as `bubblewrap` or `nsjail` before
inventing a new sandbox implementation.

## Runtime Topology

The system should support:

```text
outer run
  -> agent A sandbox
  -> agent B sandbox
  -> judge sandbox
  -> repair sandbox
```

Each sandbox may have a different view of the same project tree.

Rules:

- no shared writable process memory as the coordination mechanism;
- no soft permission checks as the primary defense;
- no in-place permission escalation of a live sandbox;
- cross-agent transfer happens through refs or promoted artifacts only.

## Implementation Order

### Phase 1: Freeze The Runtime Boundary

- Add schema definitions for `CapabilityGrant` and `SandboxProfile`.
- Add a `ToolGateway` interface in the runtime layer.
- Keep core product-neutral.
- Do not change product integrations.

Exit condition: the runtime has an explicit grant object and an explicit
sandbox profile object, even if the first implementation is thin.

### Phase 2: Introduce Sandboxed Tool Execution

- Route tool execution through `ToolGateway`.
- Create a sandbox per agent role or per task phase.
- Back the sandbox with `bubblewrap`, `nsjail`, or a comparable Linux
  isolation mechanism.
- Keep bash available only inside the sandbox, not on the host.

Exit condition: read, write, command, and network differences can be enforced
between two agents running on the same outer job.

Current implementation note:

- the Pi runtime `read`, `write`, `edit`, and `bash` tools now route through a
  worker-side `ToolGateway` decision layer before touching local operations;
- the Python Pi runtime adapter emits `capability_grant` and `sandbox_profile`
  into the TypeScript runtime input envelope;
- the TypeScript runtime validates the grant, profile, permission manifest, and
  PiWorker call as one authority envelope before tools run;
- worker-side tools use the sandbox profile as the effective execution view, so
  profile refs, commands, network state, and environment allowlist can narrow
  the manifest at the tool boundary;
- gateway decisions are recorded as refs-first runtime events and do not store
  artifact bodies, raw command strings, stdout/stderr, environment values, host
  paths, provider payloads, or secrets;
- the Pi runtime bash tool executes explicit `allowed_commands` through a
  `bubblewrap` sandbox view;
- readable refs are mounted readonly, writable refs are mounted writable, and
  denied refs are masked;
- disabled network policy uses an unshared network namespace, while enabled
  policy shares the host network;
- `restricted` network policy still fails closed until domain-level network
  enforcement exists;
- the remaining phase 2 gap is the full per-agent process sandbox lifecycle.

### Phase 3: Add Grant Lifecycle

- Mint grants with expiry and revocation.
- Support refresh by minting a new grant rather than mutating the old one.
- Record grant issuance and revocation in refs-first evidence.

Exit condition: a revoked or expired grant cannot execute any new tool call.

### Phase 4: Add Multi-Agent Handoff Rules

- Define refs-only handoff between sandboxes.
- Define when a promoted artifact is required.
- Define when a new sandbox is required for privilege changes.

Exit condition: multi-agent collaboration no longer relies on shared mutable
process state.

### Phase 5: Harden and Verify

- Add tests for host escape prevention.
- Add tests for per-agent visibility differences.
- Add tests for network restrictions.
- Add tests for grant expiry and revocation.
- Add tests for permission transitions that require new sandboxes.

Exit condition: sandbox boundaries are exercised by tests, not just by docs.

## Non-Goals

This upgrade should not:

- add product semantics to `src/missionforge`;
- create a public worker marketplace;
- replace `TaskContract` with a new authority layer;
- turn `PermissionManifest` into a giant policy language;
- add soft prompt-only safety claims;
- require a single sandbox for all roles;
- make tool permissions depend on hidden model reasoning.

## Success Criteria

The upgrade is successful if MissionForge can:

- give different agents different file views in the same outer run;
- give different agents different command and network authority;
- revoke or expire authority cleanly;
- keep the root API small;
- keep product semantics outside core;
- preserve refs-first evidence and independent judgment;
- let models keep broad autonomy inside a small, hard world.
