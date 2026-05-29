# Module: Store Boundary

Status: implemented for the Phase 16 JSON backend slice and Phase 17 main
write-path wiring.

MissionForge storage is a small protocol boundary over the existing
workspace-relative JSON/JSONL layout. It is not a database framework.

## Public Contracts

- `RunStore`
- `ArtifactStore`
- `EventLogStore`
- `JsonWorkspaceStore`
- `JsonRunStore`
- `JsonArtifactStore`
- `JsonEventLogStore`

## Default Backend

The default backend remains JSON files under the workspace:

```text
runs/{mission_run_id}/mission_run.json
runs/{mission_run_id}/attempts.jsonl
runs/{mission_run_id}/artifact_hygiene.json
runs/{mission_run_id}/metrics/events.jsonl
runs/{mission_run_id}/metrics/projection.json
runs/{mission_run_id}/revisions/{revision_id}/...
```

## Rules

- refs must be workspace-relative safe refs
- JSON output is deterministic where contractually required
- JSONL append behavior is explicit
- stores return refs, contract objects, or backend-test payloads
- runtime, steering, revision, metric, and CLI durable writes should go through
  `JsonWorkspaceStore` or a facade built on it
- no SQLite, remote store, HTTP service, or migration tool is introduced in
  this slice

## Current Wiring

Phase 17 routes the main durable writes through `JsonWorkspaceStore` while
preserving the existing file layout. Legacy direct read helpers may remain where
they protect compatibility or avoid circular imports, but new durable writes
should not bypass the store boundary.

## Verification

```bash
PYTHONPATH=src python3 -m unittest tests/test_store_contracts.py tests/test_json_store_backend.py tests/test_runtime_store_integration.py tests/test_mission_revision_workflow.py
```
