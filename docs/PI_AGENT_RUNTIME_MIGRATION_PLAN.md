# PI Agent Runtime Migration Plan

## Goal

Migrate MissionForge from the current limited command-sidecar PiWorker shape to
one production worker: a MissionForge-Owned PI Agent Worker Runtime based on
the sibling `/home/mansteinl/pi` project.

The intent is to let the LLM worker remain a complete coding agent inside a
MissionForge attempt boundary. MissionForge should govern the work contract,
workspace boundary, evidence, stop conditions, and verifier authority. It
should not micromanage the agent's internal plan, tool selection, or every file
read/write step.

The architecture goal is deliberately narrow: MissionForge should expose one
dedicated `pi-agent-runtime` worker path. Fake, faux, command, or sidecar
workers may exist only as temporary migration aids or test fixtures. They
should not become product-level runtime choices.

## Key Conclusion

The earlier MissionForge command PiWorker integration was useful, but it is not
the target runtime. It was a compatibility boundary inspired by SkillFoundry's
sidecar pattern:

```text
Python adapter -> JSON input -> Node sidecar -> JSON output -> verifier
```

The PI project is a better foundation for the worker the user wants:

- `packages/agent` provides the stateful agent loop.
- `packages/ai` provides provider/model/streaming abstractions, including
  OpenAI Responses handling.
- `packages/coding-agent` provides mature coding tools and session/runtime
  patterns.

The right next architecture is not "add more small tools to the SkillFoundry
sidecar". It is to create a MissionForge-owned PI Agent runtime module and
collapse production execution onto that single worker.

## SkillFoundry Relationship

MissionForge's earlier command PiWorker slice followed the SkillFoundry sidecar
contract style. It was not a direct extraction of PI's Agent runtime.

SkillFoundry's PiWorker is valuable as an adapter proof:

- deterministic faux mode
- live provider opt-in
- JSON input/output contract
- evidence-first mapping back into the host verifier

PI's runtime is a different and more complete layer. It already has the agent
loop, provider streaming, tool execution, steering queues, hooks, and coding
tool surface that MissionForge would otherwise have to rebuild.

Recommended framing:

- SkillFoundry sidecar remains only a compatibility prototype while migrating.
- PI Agent runtime becomes the only production worker runtime.
- MissionForge owns the integration shell, event schema, evidence policy, and
  verifier handoff.

If PI source is copied or vendored, keep the MIT license and copyright notice
from `/home/mansteinl/pi/LICENSE`.

## Runtime Completeness

PI is not "LLM Turing-complete" in the formal sense. The model itself is a
probabilistic process and every practical run is bounded by context, budget,
timeouts, and available tools.

Operationally, PI with:

- iterative agent loop
- bash execution
- filesystem read/write/edit tools
- provider streaming
- steering/follow-up queues

is a general-purpose coding agent runtime. With `bash` available, it can
delegate arbitrary computation to the environment, so the useful engineering
question is not "can it compute anything" but "what boundary does MissionForge
own around the attempt".

## PI Runtime Findings

### `packages/agent`

The core runtime is clean and reusable:

- `Agent` owns state, messages, tools, active run lifecycle, and queues.
- `runAgentLoop` handles assistant turns, tool calls, tool results, and
  continuation.
- Events cover `agent_start`, `turn_start`, `message_start`,
  `message_update`, `tool_execution_start`, `tool_execution_update`,
  `tool_execution_end`, `turn_end`, and `agent_end`.
- `steer`, `followUp`, `continue`, and `abort` are first-class APIs.
- `beforeToolCall`, `afterToolCall`, `prepareNextTurn`, and
  `shouldStopAfterTurn` are exactly the hooks MissionForge needs for evidence,
  budget, and framework-level policy.
- Tool execution can be `parallel` or `sequential`.

This is much closer to the desired worker than the current three-tool
sidecar.

### `packages/ai`

The provider layer already handles details that MissionForge should not
reimplement:

- OpenAI Responses conversion and streaming
- tool-call argument streaming and finalization
- reasoning/thinking blocks
- usage and cost shaping
- provider registry
- dynamic API key resolution through `getApiKey`

This should replace the hand-rolled OpenAI Responses parsing used in the
current SkillFoundry-style sidecar path.

### `packages/coding-agent` tools

The coding tools are the practical autonomy surface:

- `read`
- `bash`
- `edit`
- `write`
- `grep`
- `find`
- `ls`

The tools are already designed with pluggable operations, which lets
MissionForge wrap execution without removing worker freedom. Important details:

- `bash` supports streaming output, timeout, abort, env, and spawn hooks.
- `read` supports text and images, truncation, offsets, and custom operations.
- `edit` performs exact replacements, produces diffs/patches, and serializes
  mutations per file.
- `write` creates parent directories and serializes file mutations per file.

Security note: PI path resolution is cwd-oriented, but not by itself a full
MissionForge sandbox. MissionForge should add a workspace-root guard or run the
runtime inside an attempt workspace/container.

## Exclusive Worker Architecture

MissionForge should have one production worker, not a worker-selection matrix.

```text
MissionForge production worker = pi-agent-runtime
```

This keeps the architecture clean:

- one worker contract
- one event vocabulary
- one evidence mapping
- one live provider path
- one debugging surface
- one place to tune autonomy, budget, sandboxing, and redaction

Test doubles are still allowed, but they are not architecture:

- `FakeWorker` can remain a Python unit-test fixture.
- Faux provider mode can remain inside `pi-agent-runtime` for deterministic
  offline tests.
- The command PiWorker adapter was only a migration bridge and is not a
  production runtime path.

No Worker Selection Matrix:

- no public `fake_worker` runtime choice
- no public `faux_piworker` runtime choice
- no public `command_piworker` runtime choice after cutover
- no long-term runtime registry until a real second production worker exists

The product-level path should be:

```text
MissionRuntime
  -> WorkUnitContract
  -> Python WorkerAdapter boundary
  -> PI Agent runtime command/module
  -> PI Agent
  -> PI AI provider layer
  -> PI coding tools
  -> artifacts/events/session/metrics
  -> ExecutionReport + EvidenceLedger
  -> Verifier
  -> MissionResult
```

Recommended module layout:

```text
workers/pi-agent-runtime/
  package.json
  src/main.ts
  src/missionforge-contract.ts
  src/provider-config.ts
  src/runtime.ts
  src/tools.ts
  src/evidence-recorder.ts
  tests/
  NOTICE
```

Python remains the host/orchestrator. TypeScript/Node owns the live agent run.
MissionForge Python core must still not import OpenAI SDKs, PI provider code,
or Node runtime internals.

## Worker Autonomy Boundary

The worker should be constrained at the right layer:

- Give the PI agent the full coding tool set by default.
- Keep `bash` available.
- Let the agent decide whether to read, grep, edit, write, test, or create
  scratch files.
- Use `beforeToolCall` and tool operation wrappers for hard framework
  boundaries only.
- Use `afterToolCall` and event subscriptions for evidence capture.
- Use MissionForge verifier output as the only completion authority.

Recommended hard boundaries:

- attempt workspace root or container root
- wall-clock timeout
- max turns or max provider calls
- secret redaction
- no provider credentials in serialized artifacts
- execution event log
- final output contract validation
- verifier-owned acceptance

Recommended soft boundaries:

- `allowed_scope` becomes an output and acceptance envelope, not a per-step
  micro-permission system.
- Worker scratch files are allowed under the attempt directory.
- Reads should be broad within the attempt workspace unless a mission contract
  explicitly says otherwise.
- Writes outside final expected outputs can be recorded as `changed_refs` and
  judged by the verifier or reviewer.

This preserves the user's goal: do not bind the LLM worker's hands, but make
the attempt observable and recoverable.

## Live Provider Policy

Live provider config should reuse the current Codex configuration resolver:

```text
model: current Codex model
base_url: current Codex provider base_url
wire_api: responses
api_key: current Codex auth/env key
```

The Node runtime should receive provider values through process environment or
an in-memory provider callback:

```text
MISSIONFORGE_PI_AGENT_PROVIDER=live
MISSIONFORGE_PI_AGENT_MODEL=<codex model>
MISSIONFORGE_PI_AGENT_BASE_URL=<codex base url>
MISSIONFORGE_PI_AGENT_API_KEY=<redacted in all artifacts>
```

Rules:

- API key is never written to `pi_agent_input.json`.
- API key is never written to session, events, metrics, evidence, or reports.
- Provider errors and tool output are redacted before persistence.
- Default tests use a faux provider and remain offline.
- Live smoke tests stay opt-in.
- Current Phase 6 live smoke passes through `provider_config_source =
  "codex_current"` and writes only a small expected artifact.

PI's `getApiKey` hook should be used when possible so long-running runs can
resolve credentials per provider call.

## Contract Shape

Use the dedicated PI Agent runtime JSON envelope.

Input:

- `schema_version`
- `work_unit_id`
- `mission_id`
- `iteration`
- `workspace_root`
- `attempt_dir_ref`
- `input_ref`
- `output_ref`
- `session_ref`
- `events_ref`
- `metrics_ref`
- `contract`
- `runtime`

Output:

- `schema_version`
- `work_unit_id`
- `status`
- `produced_artifacts`
- `changed_refs`
- `commands_run`
- `tests_run`
- `failures`
- `worker_claims`
- `verifier_evidence`
- `new_unknowns`
- `recommended_next_steps`
- `verification_status`
- `input_ref`
- `output_ref`
- `session_ref`
- `events_ref`
- `metrics_ref`
- `duration_ms`
- `metrics`

Add PI-specific details inside referenced artifacts, not directly inside the
top-level `ExecutionReport`.

Recommended referenced artifacts:

- `pi_events.jsonl`: normalized AgentEvent and tool events
- `pi_session.jsonl`: compact transcript or provider-visible messages
- `pi_metrics.json`: turns, tool calls, usage, token counts, cost estimates
- `pi_tool_results.jsonl`: optional structured details for large tool outputs

## Migration Phases

### Phase 0: Ownership and Packaging

Decide how to bring PI into MissionForge:

- preferred: vendor a small internal Node package under
  `workers/pi-agent-runtime/`
- acceptable during development: reference sibling `/home/mansteinl/pi` through
  local path dependencies
- avoid: importing the whole PI coding-agent product shell as the first step

Bring the runtime pieces in this order:

1. `@earendil-works/pi-ai`
2. `@earendil-works/pi-agent-core`
3. selected coding tools from `@earendil-works/pi-coding-agent`

Add `NOTICE`/license attribution if code is copied.

### Phase 1: Faux PI Agent Runtime

Build a Node runtime CLI that consumes MissionForge's existing
`pi_worker_input.json` and emits `pi_worker_output.json`.

Use PI Agent with a faux provider first:

- no network
- deterministic assistant messages
- deterministic tool calls
- real event/session/metrics artifact writing

Acceptance:

- Python adapter can invoke this runtime through the existing command boundary.
- Existing offline tests still pass.
- New tests prove the output contract and event artifacts.

### Phase 2: Full Coding Tools With MissionForge Wrappers

Expose PI tools:

- `read`
- `bash`
- `edit`
- `write`
- `grep`
- `find`
- `ls`

Wrap tool operations for:

- workspace-root enforcement
- event recording
- redaction
- command timeout defaults
- output truncation and artifact spillover

Do not remove `bash` by default. Avoid exposing multiple public tool profiles
until there is a concrete mission-level reason. The default worker should be
complete and autonomous.

### Phase 3: Live Provider

Connect `packages/ai` OpenAI Responses support to the Codex current provider
config already resolved by MissionForge.

Acceptance:

- live mode is opt-in
- no secrets are serialized
- live smoke can create a small expected artifact
- provider/tool-call SSE handling comes from PI, not custom sidecar parsing

### Phase 4: Cutover To The Single Worker

Replace production worker execution with `pi-agent-runtime`.

Cutover rules:

- `MissionRuntime` uses `pi-agent-runtime` as the only production worker.
- Existing fake/faux behavior is moved behind test helpers or the runtime's
  internal faux provider.
- The command PiWorker adapter is removed from the production path.
- Configuration should choose provider mode, model, timeout, and budget for
  the one worker; it should not choose between different worker runtimes.

### Phase 5: Session, Steering, and Repair

Adopt more of PI's harness ideas where they help MissionForge:

- save points after each assistant turn
- steering messages between turns
- follow-up messages for repair prompts
- abort semantics
- transcript compaction

MissionForge does not need to adopt PI's TUI or full CLI shell to get these
benefits.

## Verification Plan

Offline validators:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests
```

Node runtime validators once the package exists:

```bash
npm test --prefix workers/pi-agent-runtime
npm run build --prefix workers/pi-agent-runtime
```

Required test cases:

- faux provider run writes expected output
- tool event stream is recorded
- bash output is captured and truncated
- edit/write mutations are serialized per file
- workspace escape is blocked or isolated
- API key-like values are redacted from all artifacts
- missing output fails as worker failure, not verifier success
- worker claims remain low-trust evidence
- verifier still owns completion

Optional smoke:

```bash
MISSIONFORGE_PI_AGENT_LIVE_SMOKE=1 PYTHONPATH=src python3 -m unittest ...
```

## Risks

- PI requires Node `>=22.19.0`; MissionForge is currently Python-only.
- Copying PI source creates update drift unless the vendored boundary is kept
  small.
- `bash` is intentionally powerful; the hard boundary must be workspace or
  container isolation, not prompt-only instruction.
- Cwd-based path resolution needs a MissionForge root guard or sandbox.
- Provider config must not leak through events, stdout, stderr, metrics, or
  transcript artifacts.
- Large tool outputs need spillover artifacts to avoid oversized JSON reports.
- The first version should avoid adopting PI's entire TUI/session product shell
  until MissionForge's worker contract is stable.

## Recommendation

Proceed with the PI Agent runtime migration. The current sidecar is good proof
that MissionForge can host a worker behind JSON contracts, but it is too small
for the desired level of autonomy.

The detailed implementation plan is maintained in
`docs/PI_AGENT_RUNTIME_IMPLEMENTATION_PLAN.md`.

The next implementation goal should be:

1. add `workers/pi-agent-runtime/`
2. wire PI Agent + PI AI + full coding tools in faux mode
3. invoke it from MissionForge as the dedicated production worker
4. switch live provider to PI's OpenAI Responses implementation
5. keep the old command PiWorker retired from production use

This gives MissionForge a complete and independent LLM worker while preserving
the framework's real responsibilities: contracts, evidence, safe attempt
boundaries, and verified closure.
