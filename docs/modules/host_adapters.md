# Module: Host Adapters

## Goal

Expose MissionForge to external orchestrators without making those hosts part
of core runtime semantics.

## Current Status

Status: active operator shell, no legacy run facade.

Host adapters do not execute MissionForge contracts through an internal runtime
facade. The CLI/Python shell is an operator surface for refs-only inspection,
terminal observation, diagnosis, explicit control intent, independent review
records, repository validation, and FrontDesk authoring commands.

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
- `tui`
- `frontdesk ...`

There is no top-level `run` or `resume` command. Product execution should
compile into `TaskContract`, `WorkspacePolicy`, and `PermissionManifest`, then
use the TaskContract/PiWorker flow.

## Terminal Observer

`tui` is a read-only terminal observer for an existing workspace/run ref:

```bash
python -m missionforge.adapters.cli tui \
  --workspace . \
  --flow-result-ref kernel/example/runs/example/executions/001/flow_result.json \
  --watch

python -m missionforge.adapters.cli status \
  --workspace . \
  --flow-result-ref kernel/example/runs/example/executions/001/flow_result.json \
  --json
```

`--run-ref` is accepted as an alias for `--flow-result-ref` for host shells
that already use run-ref terminology.

The human terminal view renders compact metadata from event logs, execution
reports, boundary reports, extension load reports, metrics, and common artifact
directories. It does not mutate workspace state, drive orchestration, accept
work, or inspect product semantics.

The machine form returns the same observation through `MissionCommandResult`.
Both forms preserve the refs-first rule: operator output may include refs,
sizes, timestamps, statuses, counts, and safe event projections, but not raw
prompts, transcripts, provider payloads, stdout/stderr bodies, artifact bodies,
or secrets.

## User Progress Streams

Products can declare a user-visible progress stream in `PermissionManifest`:

```json
{
  "progress_streams": [
    {
      "stream_id": "user-progress",
      "stream_ref": "progress/progress.jsonl",
      "audience": "user",
      "renderer": "plain"
    }
  ]
}
```

This is a mountable MissionForge capability, not a product-specific UI. The
product or PiWorker writes short `ProgressEvent` records to the declared stream;
MissionForge validates, tails, and renders them. MissionForge does not infer
semantic progress from filenames, metrics, or product state.

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
