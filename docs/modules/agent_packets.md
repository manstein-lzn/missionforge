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
- no product-specific behavior.

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
- execution reports may carry `packet_hash`, and judge packets/reports may carry
  hashes for the packet/report artifacts they bind to;
  hash mismatches fail validation when hashes are supplied;
- accepted decisions cannot include repair or revision refs;
- packet/report payloads are refs-only and reject raw prompts, transcripts,
  secrets, stdout/stderr bodies, and artifact bodies.

## Current Status

`src/missionforge/agent_packets.py` is the role-separated packet layer for the
current TaskContract/PiWorker flow. PiWorker invocation is handled through
`PiWorkerCall` and `missionforge.adapters.pi_agent_runtime`; permission and
workspace enforcement stay in the runtime/tool boundary.
