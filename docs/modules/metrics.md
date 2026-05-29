# Module: Metrics

Status: planned/implemented in Phase 12.

MissionForge metrics are diagnostic events. They are not evidence, verifier
inputs, authority grants, or runtime routing truth.

## Boundary

Metrics exist to make modules independently inspectable:

```text
module diagnostic values -> MetricEvent JSONL -> MetricProjection -> operator view
```

Runtime completion still comes from:

```text
FrozenMissionContract -> EvidenceLedger -> Verifier -> VerificationResult
```

## Contracts

`MetricEvent` is a refs-first diagnostic record:

- `missionforge.metric_event.v1`
- lower-case dotted namespace
- source, evidence, or run ref
- shallow scalar values only
- explicit diagnostic trust level
- no raw prompt, transcript, provider payload, stdout/stderr body, artifact
  body, or secret-shaped field

`MetricProjection` is a deterministic operator summary rebuilt from event
JSONL:

- `missionforge.metric_projection.v1`
- namespace-keyed summary values
- diagnostic flags used by operator diagnose
- event refs instead of embedded metric source bodies

## Namespaces

Reserved MissionForge namespaces include:

- `missionforge.runtime`
- `missionforge.verifier`
- `missionforge.harness`
- `missionforge.worker.pi_agent`
- `missionforge.steering`
- `missionforge.operator.cli`
- `missionforge.operator.rpc`
- `missionforge.store.json`

External products use `integration.<product>`.

Product names must not appear under `missionforge.*`.

## Runtime Rules

- Runtime writes metric event refs and projection refs.
- `MissionResult.metrics` remains a compatibility summary and cites
  `metric_events_ref` and `metric_projection_ref`.
- Operator inspect surfaces metric refs and the projection.
- Operator diagnose reads projection diagnostic flags, not arbitrary runtime
  metric dict keys.
- Runtime routing must not read `MetricEvent.values`.
- Verifier success must not depend on metrics.
