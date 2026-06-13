# Module: Workspace Permission

## Goal

Provide the hard workspace and permission boundary for the simplified
PiWorker-centered runtime.

## Scope

- safe relative ref resolution;
- readable and writable root checks;
- denied ref overrides;
- command and network policy declarations;
- unsupported hard-policy reporting;
- permission-aware JSON/text artifact access.

## Non-Goals

- no semantic task judgment;
- no product-specific policy branches;
- no prompt-only security claims;
- no shell sandbox implementation in this module.

## Invariants

- all refs must pass `validate_ref`;
- denied refs override readable and writable refs;
- workspace policy denied refs are merged into the effective permission deny
  set;
- `RunWorkspace.root` is the outer filesystem workspace and
  `WorkspacePolicy.workspace_root_ref` is the run-local root under it;
- writes outside `PermissionManifest.writable_refs` fail closed;
- reads outside `PermissionManifest.readable_refs` fail closed;
- unsupported hard policies must be reported explicitly;
- workspace path resolution must stay under the declared filesystem root.

## Current Status

S2 adds `PermissionEnforcer` in `src/missionforge/permissions.py` and
`RunWorkspace` in `src/missionforge/workspace_runtime.py`.

S7 pushes the same boundary into `workers/pi-agent-runtime`:

- `permission_manifest` is required in the Pi runtime input envelope;
- `capability_grant` and `sandbox_profile` are now required in the Pi runtime
  input envelope and are validated together with the permission manifest;
- read, write, edit, and bash requests pass through the worker-side
  `ToolGateway` decision layer before touching local operations;
- read, write, and edit tools translate absolute tool paths back to workspace
  refs and reject paths outside readable/writable roots;
- denied refs override readable/writable refs at tool execution time;
- symlink components under tool paths are rejected before filesystem access;
- runtime-owned writes for output, session, event, metric, savepoint, and direct
  benchmark artifacts reject symlink components before writing;
- direct benchmark workspace and source refs use the same symlink-aware read and
  write path preparation as the main Pi runtime path;
- bash rejects commands that are not exact `allowed_commands` entries;
- when bash is explicitly enabled, the command executes through the
  `bubblewrap`-backed sandbox view rather than host-local shell execution;
- sandboxed bash receives only readable refs as readonly mounts, writable refs
  as writable mounts, and denied refs as masked readonly paths;
- sandboxed bash receives only `env_allowlist` variables plus a minimal
  runtime PATH/HOME/TMPDIR;
- `network_policy: disabled` runs bash in an unshared network namespace,
  `network_policy: enabled` shares the host network, and `restricted` still
  fails closed as an unsupported hard policy;
- gateway decisions are appended to runtime event logs as refs-first audit
  evidence using refs, command hashes, cwd refs, environment variable names,
  status, and safe reason codes;
- unsupported hard policies are reported as runtime failures before worker tool
  execution.

The Pi runtime evidence plane also records structure summaries for messages,
tool args, and tool results instead of raw transcript or tool-output bodies by
default. This keeps permissioned reads and write bodies from being copied into
session or event artifacts.

ToolGateway evidence intentionally does not store artifact bodies, raw command
strings, raw stdout/stderr, host paths, environment values, provider payloads,
or secrets.

Runtime `worker_claims` are not durable free text. Node runtime output stores
final assistant text as a length summary, and the Python adapter re-summarizes
any non-whitelisted claim strings at ingestion before writing execution reports
or operator-facing state. This prevents old runtimes, hand-written output, or
malicious output from smuggling raw final text or secrets through claim fields.

The current S7 hardening does not yet expose permission-aware grep/find/ls
tools. They should stay disabled until they can enforce denied roots without
leaking file names or contents through underlying search binaries.
