# Module: Runtime Engine

## Goal

Execute Mission IR through a fixed evidence-first adaptive loop.

## Scope

- mission validation
- profile resolution and mission expansion
- frozen contract creation
- work-unit compilation from FrozenMissionContract
- PiWorker execution
- observation collection
- verification
- adaptive routing
- mission result emission

## Non-Goals

- no LangGraph dependency in core
- no CodexWorker support in the first design cycle
- no task-name-specific control flow

## Current Status

Only a minimal `MissionRuntime.run()` facade exists. It validates Mission IR and
returns an accepted `MissionResult`.

## Public Contracts

- `MissionRuntime`
- `MissionResult`

## Invariants

- Runtime decisions must be based on structured mission state and verifier
  records.
- Worker self-report is never acceptance.
- Failed constraints must route repair through constraint IDs, not log strings.
- Repair, redesign, review, stop, and escalation are separate runtime
  decisions.
- PiWorker receives WorkUnitContract, not raw MissionIR or chat history.

## Dependencies

- Mission IR
- future context/evidence module
- future harness module
- future verifier module
- future PiWorker module

## Verification Strategy

- standalone runtime call without LangGraph
- deterministic fixture mission
- repair loop tests once verifier records exist
- MissionIR -> ExpandedMission -> FrozenMissionContract transition tests
- repair versus redesign routing tests

## Open Questions

- What state is durable versus derived?
- What is the exact resume boundary?
- How should user steering interrupt a running PiWorker attempt?
- Where should MissionRun live: JSONL ledger, SQLite, or pluggable store?
