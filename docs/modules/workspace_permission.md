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

This is a Python-side contract and filesystem boundary. Future phases still
need to push equivalent enforcement into `workers/pi-agent-runtime`, especially
for shell command policy.
