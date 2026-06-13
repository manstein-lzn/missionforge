# Module: Host Adapters

## Goal

Expose MissionForge to external orchestrators without making those hosts part
of core runtime semantics.

## Current Status

Status: active operator shell, no legacy run facade.

Host adapters do not execute MissionForge contracts through an internal runtime
facade. The CLI/Python shell is an operator surface for refs-only inspection,
diagnosis, explicit control intent, independent review records, repository
validation, and FrontDesk authoring commands.

## Public Contracts

- `MissionCLI`
- `MissionCommandResult`
- `MissionCommandError`
- command exit code mapping helpers
- refs-only command output validator
- `MissionRunView`
- `ControlRequestWriter`
- `ControlRequestWriteResult`
- `MissionJSONLRPC`

## Commands

Implemented operator commands:

- `inspect`
- `diagnose`
- `control halt`
- `review record`
- `validate`
- `frontdesk ...`

There is no top-level `run` or `resume` command. Product execution should
compile into `TaskContract`, `WorkspacePolicy`, and `PermissionManifest`, then
use the TaskContract/PiWorker flow.

## Adapter Shapes

Observation surfaces are read-only:

```text
MissionResult + EvidenceLedger snapshot -> MissionRunView
```

Control surfaces write explicit intent:

```text
user or host control -> ControlRequest
```

FrontDesk commands author refs and fail closed when required PiWorker authoring
nodes are unavailable. Product-specific execution belongs in product
integrations, not in the host adapter.

## Invariants

- Host adapters do not infer product semantics.
- Host adapters do not own verifier, repair, or acceptance semantics.
- Observation adapters are read-only.
- Control adapters write explicit intent requests.
- Command results contain refs and compact metadata, not raw prompts,
  transcripts, provider payloads, stdout/stderr bodies, artifact bodies, or
  secrets.
- Core modules and package root do not import or re-export host adapters.
