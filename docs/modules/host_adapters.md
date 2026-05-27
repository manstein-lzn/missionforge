# Module: Host Adapters

## Goal

Expose MissionForge to external orchestrators without making them core
dependencies.

## Scope

- Python API
- CLI
- optional LangGraph node
- future HTTP service

## Non-Goals

- no LangGraph dependency in `missionforge` core
- no host-owned mission semantics

## Current Status

Design-only.

## Public Contracts

To be designed:

- `MissionNode`
- `MissionCLI`
- `MissionService`

## Invariants

- Hosts pass Mission IR in and receive MissionResult out.
- Host adapters do not inspect private runtime internals.
- Host adapters do not own verifier or repair semantics.

## Dependencies

- runtime engine

## Verification Strategy

- standalone Python API first
- CLI smoke
- optional LangGraph adapter after core runtime is stable

## Open Questions

- What is the smallest host state mapping?
- Should adapters support streaming observation events?
