# MissionForge DeepResearch v2

DeepResearch is a product integration built on MissionForge Kernel v2. It is
not part of core.

If the research request is already clear, run the active kernel-v2 command
directly:

```bash
PYTHONPATH=src:integrations/deepresearch/src \
python3 -m missionforge_deepresearch.cli academic kernel-v2-run \
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
PYTHONPATH=src:integrations/deepresearch/src \
python3 -m missionforge_deepresearch.cli academic frontdesk-tui \
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
PYTHONPATH=src:integrations/deepresearch/src \
python3 -m missionforge_deepresearch.cli academic frontdesk-step \
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
PYTHONPATH=src:integrations/deepresearch/src \
python3 -m missionforge_deepresearch.cli academic frontdesk-step \
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
PYTHONPATH=src:integrations/deepresearch/src \
python3 -m missionforge_deepresearch.cli academic frontdesk-run \
  --request-id research-001 \
  --workspace /tmp/mf-dr \
  --live-extension-mode \
  --kernel-v2-adapter-mode piworker \
  --piworker-provider-config-source codex_current \
  --stream-progress
```

## Product Shape

```text
academic request
  -> optional FrontDesk requirements document approved by user
  -> frozen contract, role briefs, rubrics, permissions, extension lock
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
- `source_packet`
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

The product-level token summary lives at:

```text
runs/{request_id}/metrics/usage_summary.json
```

## Fixture Smoke

Use fixture mode only to test wiring without a live PiWorker:

```bash
PYTHONPATH=src:integrations/deepresearch/src \
python3 -m missionforge_deepresearch.cli academic kernel-v2-run \
  --topic "compiler autotuning survey" \
  --request-id demo-kernel-v2-fixture \
  --workspace /tmp/mf-dr-kernel-v2-fixture \
  --kernel-v2-adapter-mode fixture
```

## Validate

```bash
PYTHONPATH=src:integrations/deepresearch/src python3 -m unittest \
  integrations.deepresearch.tests.test_frontdesk \
  integrations.deepresearch.tests.test_tui \
  integrations.deepresearch.tests.test_kernel_v2 \
  integrations.deepresearch.tests.test_cli \
  integrations.deepresearch.tests.test_deepresearch_import_boundaries
```
