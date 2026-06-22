# Live Runtime Guide

Live mode is opt-in. Default development uses faux execution.

## Codex Current Provider

```python
from missionforge.adapters.pi_agent_runtime import PiAgentRuntimeConfig

config = PiAgentRuntimeConfig(
    provider_mode="live",
    provider_config_source="codex_current",
)
```

This reads the current Codex config/auth files and maps them into the child
process environment. Provider credentials are not serialized into MissionForge
artifacts.

Use `provider_config_source="env"` only when you intentionally want explicit
`MISSIONFORGE_PI_AGENT_*` environment variables.

## Runtime Artifacts

Live calls write:

- `attempts/<call_id>/pi_agent_input.json`
- `attempts/<call_id>/pi_agent_output.json`
- `attempts/<call_id>/pi_agent_session.jsonl`
- `attempts/<call_id>/pi_agent_events.jsonl`
- `attempts/<call_id>/pi_agent_metrics.json`
- `attempts/<call_id>/pi_agent_savepoints.jsonl`

## Progress

When a caller supplies a progress sink, MissionForge tails the PiWorker runtime
event stream and emits safe status summaries. It may report the current role,
safe tool names, workspace refs, streamed write length, artifact sizes, and the
age of the latest runtime event.

It must not emit raw prompts, model output bodies, stdout/stderr bodies,
provider payloads, tool result bodies, or secrets.

## Safety Rules

- Worker completion is not acceptance.
- Missing expected outputs are runtime failures.
- Secret material is redacted from durable evidence.
- Raw provider payloads do not become task truth.
- Recovered artifact packages still require reviewer/judge handling.

## Smoke Test

```bash
MISSIONFORGE_PI_AGENT_LIVE_SMOKE=1 \
PYTHONPATH=src \
python3 -m unittest tests.test_pi_agent_runtime_live_smoke
```
