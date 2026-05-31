# Module: Agent Packets

## Goal

Define role-separated packet and report contracts for the simplified
PiWorker-centered execution path.

## Scope

- executor packet;
- executor report;
- judge packet;
- judge report;
- hard-check gate status;
- role vocabulary;
- judge decision vocabulary;
- refs-only packet/report validation.

## Non-Goals

- no PiWorker process invocation;
- no semantic judging in code;
- no product-specific behavior;
- no replacement for the legacy `WorkUnitContract` path yet.

## Invariants

- executor packets use `AgentRole.EXECUTOR`;
- judge packets use `AgentRole.JUDGE`;
- executor reports cannot contain acceptance or judge decision fields;
- judge reports use only `accepted`, `repair`, `revision_required`, or
  `rejected`;
- repair decisions require `repair_brief_ref`;
- revision decisions require `revision_request_ref`;
- accepted decisions require passed hard checks;
- judge report hard-check status must match the judge packet;
- judge packet artifact refs must come from the executor report;
- accepted decisions cannot include repair or revision refs;
- packet/report payloads are refs-only and reject raw prompts, transcripts,
  secrets, stdout/stderr bodies, and artifact bodies.

## Current Status

S3 adds `src/missionforge/agent_packets.py` and focused tests. It is a contract
layer only. Runtime invocation, PiWorker process integration, and tool-layer
enforcement remain later phases.
