# MissionForge DeepResearch v2

DeepResearch is a product integration built on MissionForge Kernel v2. It is
not part of core. It is also the reference example for external MissionForge
applications: its source imports MissionForge only through `import missionforge`
and uses the public package API.

Install it like a normal downstream package:

```bash
python3 -m pip install missionforge
python3 -m pip install missionforge-deepresearch
```

For source-tree development, use editable installs instead of `PYTHONPATH`:

```bash
python3 -m pip install -e .
python3 -m pip install -e integrations/deepresearch
```

If the research request is already clear, run the active kernel-v2 command
directly:

```bash
missionforge-deepresearch academic kernel-v2-run \
  --topic "调研主题" \
  --request-id research-001 \
  --workspace /tmp/mf-dr \
  --research-intensity standard \
  --live-extension-mode \
  --kernel-v2-adapter-mode piworker \
  --piworker-provider-config-source codex_current \
  --stream-progress
```

If the user only has a rough idea, use the chat-style FrontDesk TUI. It keeps
the request id, workspace, provider config, and live tools in one session. Type
natural-language replies; use `/show` to inspect the requirements document and
`/approve` to approve it and start DeepResearch.
FrontDesk is conversation-first: for vague input it should reply directly to
the user, challenge the scope, and ask focused follow-up questions before it
offers an approval-ready requirements document. The persisted requirements file
is a durable snapshot, not the primary interaction surface.
When a question has clear alternatives, FrontDesk may provide candidate choices
that the TUI can render as selectable options; the final option should allow
the user to supply a custom idea. Seed papers, uploaded PDFs, OpenAlex keys, and
other provider credentials are optional accelerators, not required inputs.
The FrontDesk workspace keeps three separate planes:

- `frontdesk/assistant_turn.json`: the next user-facing conversational turn.
- `frontdesk/session_state.json`: recoverable ambiguity and requirement state.
- `frontdesk/research_requirements.md`: approval snapshot for the eventual
  DeepResearch run.

`frontdesk/frontdesk_control.json` is only routing/control metadata and should
not grow into a mixed UI/state/document artifact.
During the research run, the TUI shows a project progress board derived from
the researcher-owned `state/research_state.json`, reviewer observation, judge
report, source packet, claim index, and usage summary. It is meant to answer
"how is the research project converging?" rather than merely listing runtime
tool calls. When `rich` is installed, the TUI renders panels, tables, colored
status labels, and Markdown requirements; source-tree runs without installed
dependencies fall back to plain text.

While the research run is active, the TUI also accepts user interventions:

- plain text: queued as a user message for the next kernel safe point;
- `/revise <text>`: queued as a contract revision request;
- `/pause`: requests a safe-point pause;
- `/cancel`: requests safe-point cancellation;
- `/resume`: records a resume request for the next safe point;
- `/checkpoint`: requests a checkpoint at the next safe point;
- `/stop`: requests stop after the current turn;
- `/status`: prints the current project board.
- `/help`: prints the runtime command list.

These events are stored under `interaction/user_events.jsonl` and projected to
the next worker through execution-scoped `interaction/safe_points/*.json`
snapshot refs. They are not frozen contract authority; scope or acceptance
changes still require explicit revision.

```bash
missionforge-deepresearch academic frontdesk-tui \
  --request-id research-001 \
  --workspace /tmp/mf-dr \
  --research-intensity intensive \
  --frontdesk-adapter-mode piworker \
  --kernel-v2-adapter-mode piworker \
  --piworker-provider-config-source codex_current \
  --stream-progress
```

The lower-level non-interactive FrontDesk commands remain available for scripts:

```bash
missionforge-deepresearch academic frontdesk-step \
  --initial-input "我想研究一个方向，但还没想清楚范围" \
  --request-id research-001 \
  --workspace /tmp/mf-dr \
  --research-intensity intensive \
  --live-extension-mode \
  --frontdesk-adapter-mode piworker \
  --piworker-provider-config-source codex_current
```

Continue scripted FrontDesk with another message:

```bash
missionforge-deepresearch academic frontdesk-step \
  --message "补充回答或修正需求" \
  --request-id research-001 \
  --workspace /tmp/mf-dr \
  --research-intensity intensive \
  --live-extension-mode \
  --frontdesk-adapter-mode piworker \
  --piworker-provider-config-source codex_current
```

When scripted FrontDesk returns `ready_for_approval` and the user agrees, launch
DeepResearch from the approved requirements document:

```bash
missionforge-deepresearch academic frontdesk-run \
  --request-id research-001 \
  --workspace /tmp/mf-dr \
  --live-extension-mode \
  --kernel-v2-adapter-mode piworker \
  --piworker-provider-config-source codex_current \
  --stream-progress
```

Open the project web console:

```bash
missionforge-deepresearch academic web-console \
  --request-id research-001 \
  --workspace /tmp/mf-dr \
  --host 127.0.0.1 \
  --port 8765
```

The web console reads the same persisted refs as CLI/TUI: project manifest,
lifecycle state, resume diagnostics, source packet, coverage report, citation
registry, claim-support review, acceptance gate, judge report, usage summary,
and final Markdown. It also lets the browser submit FrontDesk messages through
the same `run_deepresearch_frontdesk_turn` path as CLI/TUI. The browser does
not choose provider config or write product truth directly. Browser approval
uses the same `approve_frontdesk_requirements` boundary as CLI/TUI. Start
Research requires that approval to already exist, then runs Kernel v2 as a
server-owned background task and writes
`web/tasks/current_task.json`; `/api/task` returns the current task state. The
browser still cannot choose provider config or adapter mode. Pause, resume,
checkpoint, stop-after-current-turn, cancel, message, and revise controls append
events through the same MissionForge interaction ledger as TUI. Start Research
uses a workspace-local `web/locks/kernel_v2.lock` guard; if another process owns
the project run, the web API reports a sanitized `locked` task state instead of
starting a duplicate Kernel run. The web console also records explicit retry,
revision, and lock-recovery lifecycle requests as project refs. These requests
do not mutate the frozen contract or start a new Kernel attempt; attempt
generation and upload controls remain follow-up work.

## Product Shape

```text
academic request
  -> optional FrontDesk requirements document approved by user
  -> frozen contract, role briefs, rubrics, permissions, extension lock
  -> source_mapper PiWorker
  -> researcher PiWorker
  -> reviewer PiWorker
  -> judge PiWorker
  -> accepted | repair/research continuation | blocked | failed
```

Python owns hard boundaries: refs, schemas, permission manifests, extension
locks, route decisions, flow ledgers, progress projection, final path printing,
and token usage summaries.

PiWorker owns semantic research: search planning, source triage, repository and
documentation inspection, synthesis, gap tracking, reviewer critique response,
and final judgment.

The `source_mapper` is a first-pass evidence handoff phase, not the whole
research run. It should build `sources/source_packet.json`,
`reports/evidence_index.md`, `reports/source_gaps.md`, and
`state/research_state.json` from a representative source set, then hand off to
research synthesis. Broad follow-up targets belong in the gap/state artifacts
so later researcher/reviewer passes can request narrow expansion without losing
the first durable evidence base.

PiWorker also owns the user-facing project progress board by keeping
`state/research_state.json` current. MissionForge renders that board but does
not infer semantic research quality in Python.

## Intensities

- `standard`: web, paper, documentation, and repository-metadata survey.
- `intensive`: deeper repository/code-audit-backed survey when the topic
  involves software systems. The researcher may inspect README, docs, examples,
  tests, configs, source layout, entrypoints, and workflow/tool definitions. It
  must not require installing projects, executing repository code, running
  benchmarks, or experimental reproduction.

There is no active `experimental` intensity.

## Outputs

The CLI prints absolute paths for files that exist:

- `requirements`
- `frontdesk_control`
- `frontdesk_research_request`
- `final_report`
- `citation_projected_report`
- `source_packet`
- `source_graph`
- `canonical_sources`
- `citation_registry`
- `result_package`
- `judge_report`
- `usage_summary`

If an expected file is missing, it is printed under `缺失输出`.

The main package lives at:

```text
runs/{request_id}/packages/deepresearch_kernel_v2_result.json
```

The final markdown report normally lives at:

```text
runs/{request_id}/reports/final_report.md
```

The citation-projected markdown report normally lives at:

```text
runs/{request_id}/reports/final_report.citation_projected.md
```

The product-level token summary lives at:

```text
runs/{request_id}/metrics/usage_summary.json
```

## Fixture Smoke

Use fixture mode only to test wiring without a live PiWorker:

```bash
missionforge-deepresearch academic kernel-v2-run \
  --topic "compiler autotuning survey" \
  --request-id demo-kernel-v2-fixture \
  --workspace /tmp/mf-dr-kernel-v2-fixture \
  --kernel-v2-adapter-mode fixture
```

## Validate

```bash
python3 -m unittest \
  integrations.deepresearch.tests.test_frontdesk \
  integrations.deepresearch.tests.test_tui \
  integrations.deepresearch.tests.test_kernel_v2 \
  integrations.deepresearch.tests.test_cli \
  integrations.deepresearch.tests.test_deepresearch_import_boundaries
```
