# Component Acceptance Matrix

This matrix is the verification checklist for MissionForge component
development. It should be used by `/goal` runs before a phase is marked
`completed_verified`.

## Cross-Cutting Invariants

| Invariant | Required Evidence |
| --- | --- |
| No product-name runtime branches | code search and tests for generic route behavior |
| No LangGraph dependency in core runtime | import boundary review |
| No live LLM by default | tests with no provider configured |
| Worker self-report is not acceptance | verifier tests with worker-claim evidence |
| LLM proposal is not acceptance | controlled steering tests with proposal-only evidence |
| Frozen contracts are immutable except explicit revision | freeze/hash tests |
| Raw chat is not operational task truth | source/provenance tests |
| Evidence refs are durable and inspectable | evidence ledger tests |
| MissionResult is refs-only | runtime result tests |
| Provider metrics are not control logic | metrics evidence tests or review notes |

## Phase Gate Matrix

| Phase | Required Artifacts | Required Tests | Blocking Risks |
| --- | --- | --- | --- |
| 1 Contract Kernel | shared contracts, enums, refs, hash helpers | contract/ref/hash/schema tests | overloading one module, weak ref validation |
| 2 Profile and Freeze | profile registry, expansion, frozen contract hash | profile/freeze/provenance tests | profile-name runtime branching |
| 3 Evidence and Verification | ledger, validators, verification result, reviewer decision | validator/status/reviewer tests | trusting worker claims, weak manual gate semantics |
| 4 Harness and Steering | proposal validator, fake worker, work-unit commit, decision ledger | proposal/harness/control tests | allowing proposal to mutate contract or close mission |
| 5 Runtime Slice | deterministic MissionRuntime loop | vertical slice, route, refs-only tests | hidden host dependency, unbounded loop |
| 6.0 Adapter Boundary Preflight | adapter package boundary, shared adapter contracts | import-boundary tests | adapter code imported by core |
| 6A Faux PiWorker Adapter | faux PiWorker adapter, worker adapter contracts | faux adapter, event/evidence, metrics tests | worker output becoming acceptance |
| 6B SkillFoundry Compiler | SkillFoundry source compiler adapter | compiler fixture and import-boundary tests | product-specific code entering core |
| 6C Host Adapter Shell | optional host shell, observation/control surfaces | CLI/observation/control smoke tests | host-owned verifier or runtime semantics |

## Contract Kernel Acceptance

Must pass:

- invalid enum values are rejected
- invalid or unsafe refs are rejected
- required IDs are non-empty and stable
- duplicate constraint or validator IDs are rejected
- stable hash is deterministic
- all public contract objects round trip through JSON-compatible dicts

Should not include:

- worker execution
- profile expansion
- verifier execution
- runtime orchestration

## Profile And Freeze Acceptance

Must pass:

- profile expansion is deterministic
- expanded fragments cite source profile ID and version
- unknown profiles are rejected
- unknown validator types are rejected unless declared by a locked
  VerificationProfile
- frozen hash changes when contract-relevant content changes
- frozen hash remains stable across key ordering

Review required if:

- a profile needs imperative code
- a profile name resembles a product or benchmark name
- a verification profile grants broad manual acceptance

## Evidence And Verification Acceptance

Must pass:

- evidence ledger is append-only
- verifier decisions cite evidence refs
- blocking executable failures produce `failed`
- delegatable manual blockers produce `review_required`
- user-reserved manual blockers produce `human_acceptance_required`
- unsupported blocking validators produce `unsupported_verification_spec`
- advisory failures appear as warnings
- stale review decisions are rejected
- worker-authored review decisions are rejected

Review required if:

- command validators need network access
- validator output could leak raw logs, secrets, prompts, or transcripts
- a manual gate is being treated as automated proof

## Harness And Controlled Steering Acceptance

Must pass:

- valid proposals commit to WorkUnitContract
- malformed proposals fail closed
- unsafe paths are rejected
- missing refs are rejected
- expected outputs outside allowed scope are rejected
- proposal confidence grants no authority
- proposal cannot close a mission
- proposal cannot mutate a frozen contract
- rejected proposals are recorded
- halt control blocks dispatch at a safe point

Review required if:

- proposal provider behavior depends on live LLM output
- proposal validation requires mission-specific special cases
- control requests need hard interruption instead of safe-point handling

## Runtime Slice Acceptance

Must pass:

- runtime resolves profiles
- runtime freezes contract
- runtime validates and commits work unit
- runtime records execution report
- runtime verifies evidence
- runtime emits refs-only MissionResult
- runtime routes complete/fail/review/unsupported states
- runtime enforces an attempt limit
- runtime has no LangGraph, SkillFoundry, live LLM, or PiWorker dependency

Review required if:

- runtime needs a new adaptive decision not already documented
- runtime needs to revise frozen contract during execution
- runtime needs external state beyond the current workspace/store interfaces

## Adapter Acceptance

Adapter boundary preflight must prove:

- adapter modules live outside MissionForge core runtime imports
- shared adapter contracts are refs-only and JSON-compatible
- core modules do not import `missionforge.adapters`
- package root does not import or re-export adapter contracts
- raw payload, body, prompt, transcript, and secret-shaped fields are rejected
- optional dependencies are not required for default tests
- follow-on goals remain split by trust boundary

PiWorker adapter must prove:

- committed WorkUnitContract is the only worker input contract
- event stream maps to evidence and execution reports
- provider metrics are recorded without becoming route logic
- contract adjustment requests are evidence only
- MissionForge core has no PiWorker imports
- faux PiWorker tests pass before any live smoke

SkillFoundry adapter must prove:

- FrontDesk artifacts compile into MissionIR
- SkillFoundry product semantics stay outside core
- capability bundle generation uses profiles and validators, not runtime
  branches
- compile results are refs-only
- raw transcript input is rejected unless represented as an allowed sanitized
  source ref

Host adapters must prove:

- MissionIR in, MissionResult out remains the integration shape
- observation surfaces are read-only
- control surfaces write ControlRequest intent only
- host dependencies do not enter core imports

## Verification Commands

Every phase:

```bash
git diff --check
PYTHONPATH=src python3 -m unittest discover -s tests
```

Add focused commands when the phase introduces new tests. Record the command and
result in the final response and relevant module docs.
