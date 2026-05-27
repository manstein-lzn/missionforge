# MissionForge

MissionForge is a runtime for executing structured Mission IR with observable
LLM workers, evidence gates, adaptive repair, and verified closure.

It is intentionally not a SkillFoundry rewrite. SkillFoundry should become one
application on top of MissionForge. MissionForge owns the generic substrate:

```text
MissionIR + Workspace + WorkerProvider + ToolRegistry
  -> MissionResult + EvidenceLedger + Artifacts + Metrics
```

## Design Stance

- Mission semantics live in Mission IR and profile data, not task-name branches.
- The runtime core does not depend on LangGraph. LangGraph is an optional host.
- The only first-class worker target is PiWorker. Other workers are out of
  scope until the PiWorker path is complete.
- The PiWorker design is inspired by the MIT-licensed PI GitHub project. The
  initial skeleton does not vendor PI code; any future copied or adapted PI
  code must retain required attribution.
- Context and evidence are first-class runtime objects, not chat memory.
- Worker self-report is never acceptance evidence.
- Verifier failures must become structured repair inputs.
- Core code must not contain benchmark or product names such as Codexarium.
- Documentation starts and ends every module: each module has a module design
  document before implementation, and that document is updated when behavior
  changes.

## Design Program

MissionForge starts with formal architecture design, not code migration and not
a narrow MVP. The first repository state should clarify:

- the stable Mission IR contract
- the runtime state model
- the context/evidence ledger boundary
- the work-unit harness protocol
- the verifier and repair protocol
- the worker adapter boundary
- the optional host adapter boundary

Implementation starts only after these boundaries are explicit enough to keep
task-specific semantics out of runtime code.

## Package Layout

```text
src/missionforge/
  ir.py          Mission IR dataclasses and validation
  runner.py      Minimal runtime/result boundary
docs/
  ARCHITECTURE.md
  MISSION_IR.md
  DESIGN_PROGRAM.md
  DEVELOPMENT_PROTOCOL.md
  modules/
```

## Development

```bash
python3 -m unittest discover -s tests
```
