# Design Program

MissionForge is a formal architecture effort, not an MVP extraction. The goal
is to define a durable mission execution substrate before implementation grows.

The project should proceed by design gates. Each gate must tighten the contract
between Mission IR, context evidence, work-unit execution, verification, repair,
and host integration.

## Gate 1: Mission Kernel

Define the canonical Mission IR and runtime state model.

Outputs:

- Mission IR schema
- Mission state schema
- Mission result schema
- stable ID rules
- source/provenance rules
- versioning policy

Design questions:

- What belongs in Mission IR versus profile data?
- What is the minimal mission truth required by every runtime?
- How are raw user inputs excluded from worker context while preserving
  provenance?

Acceptance:

- mission semantics are expressible without product-name branches
- a mission can be frozen and hashed
- invalid mission contracts fail closed

## Gate 2: Context and Evidence Kernel

Define the context plane inspired by ContextForge.

Outputs:

- evidence ref model
- contract manifest model
- ledger event model
- checkpoint model
- verification gate model
- raw input boundary model

Design questions:

- Which records are immutable?
- Which refs are worker-visible?
- Which artifacts are provenance-only?
- How is evidence freshness verified?

Acceptance:

- every worker-visible input has a frozen ref
- every verifier decision cites evidence refs
- raw conversation or raw private material is never operational context

## Gate 3: Work-Unit Harness

Define the execution plane inspired by ForgeUnit.

Outputs:

- work-unit contract schema
- attempt input manifest
- worker invocation record
- execution report
- artifact write scope model
- metrics model

Design questions:

- What is the minimum contract every worker consumes?
- How are tool calls, command calls, and model calls recorded?
- How does cancellation or steering appear in evidence?

Acceptance:

- worker self-report is not acceptance
- every attempt has independent execution evidence
- worker adapters can be swapped without changing Mission IR

## Gate 4: Verification and Repair Protocol

Define how MissionForge reaches closure.

Outputs:

- validator result schema
- failed constraint schema
- repair contract schema
- repair routing policy
- review and authority gates

Design questions:

- How do validators map failures back to Mission IR constraints?
- What repair hints are declarative data versus runtime logic?
- How are generated tests treated as evidence?

Acceptance:

- repair does not depend on string-matching logs
- failure records include constraint IDs and missing evidence
- adaptive routing is mission-generic

## Gate 5: Profile System

Define reusable capability profiles.

Initial candidate profiles:

- `capability_bundle`
- `explicit_output_root`
- `user_provided_evidence_only`
- `no_raw_log_or_secret_ingestion`
- `local_file_path_safety`
- `no_overwrite_conflict_policy`
- `rust_helper_runtime`
- `synthetic_fixture_pack`
- `reference_documentation_pack`
- `markdown_output_contract`

Design questions:

- Are profiles data-only, code-backed, or both?
- How are profiles versioned?
- How does FrontDesk select profiles without task-name detection?

Acceptance:

- profile composition can represent a concrete product mission without a
  product-specific branch
- another unrelated mission can reuse at least half of the same profiles

## Gate 6: Runtime Engine

Define and implement the fixed runtime loop.

Loop:

```text
validate mission
freeze context
compile work unit
execute worker
collect observation
verify evidence
route repair/review/closure
emit result
```

Design questions:

- Which state is durable?
- Which state is derived?
- How is resume represented without depending on a specific host framework?

Acceptance:

- the core runtime has no LangGraph dependency
- the same runtime can be called from CLI, tests, services, or host adapters

## Gate 7: Worker Adapters

Define the PiWorker adapter contract. Other workers are explicitly out of scope
for this design cycle.

MissionForge is informed by the PI GitHub project and the current SkillFoundry
PiWorker integration. The design should initially mirror the proven PiWorker
shape: bounded work-unit input, observable event stream, tool-mediated
workspace writes, provider metrics, and refs-only output evidence.

Acceptance:

- PiWorker consumes the canonical work-unit contract
- PiWorker metrics normalize provider usage, cache reads, tool calls, and model
  calls
- provider-specific telemetry is preserved as evidence, not control logic
- PI attribution requirements are recorded before any PI-derived source is
  copied or adapted

## Gate 8: Host Adapters

Define optional adapters after the core runtime is stable.

Candidate adapters:

- LangGraph node
- CLI command
- Python API
- HTTP service

Acceptance:

- host adapters do not own mission semantics
- host state can consume MissionResult without inspecting runtime internals

## Gate 9: SkillFoundry Adapter

Rebuild SkillFoundry as an application shell on top of MissionForge.

Acceptance:

- FrontDesk compiles user needs into Mission IR
- Skill package generation uses MissionRuntime
- SkillFoundry code contains no mission-name verifier branches
