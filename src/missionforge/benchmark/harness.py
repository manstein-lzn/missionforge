"""Offline benchmark harness for deterministic VB1 validation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..contracts import ContractValidationError, require_non_empty_str, validate_ref
from ..json_store import JsonWorkspaceStore
from ..metrics import MetricEvent, MetricTrustLevel
from .contracts import (
    BenchmarkAggregate,
    BenchmarkMode,
    BenchmarkStatus,
    BenchmarkSummary,
    BenchmarkTask,
    BenchmarkTrial,
    OfflineTrialOutcome,
    build_aggregate,
)
from .report import build_aggregate_report


@dataclass(frozen=True)
class OfflineTrialRecord:
    """Refs written by one offline benchmark trial."""

    trial: BenchmarkTrial
    summary: BenchmarkSummary
    metric_event: MetricEvent
    trial_ref: str
    summary_ref: str
    metric_events_ref: str
    review_packet_ref: str


class OfflineBenchmarkHarness:
    """Record deterministic benchmark artifacts without invoking workers."""

    def __init__(self, workspace: str | Path = ".") -> None:
        self.workspace = Path(workspace)
        self.store = JsonWorkspaceStore(self.workspace)

    def task_ref(self, task: BenchmarkTask) -> str:
        task.validate()
        return f"benchmarks/tasks/{task.task_id}/task.json"

    def write_task(self, task: BenchmarkTask) -> str:
        task.validate()
        return self.store.write_json(self.task_ref(task), task.to_dict())

    def record_trial(
        self,
        *,
        benchmark_run_id: str,
        task: BenchmarkTask,
        mode: BenchmarkMode,
        seed: int,
        outcome: OfflineTrialOutcome,
        started_at: str = "1970-01-01T00:00:00Z",
        completed_at: str = "1970-01-01T00:00:00Z",
    ) -> OfflineTrialRecord:
        """Write a deterministic offline trial and safe harness metric event."""

        run_id = require_non_empty_str(benchmark_run_id, "offline_harness.benchmark_run_id")
        validate_ref(run_id, "offline_harness.benchmark_run_id")
        task.validate()
        outcome.validate()
        root = _trial_root(run_id=run_id, task_id=task.task_id, mode=mode, seed=seed)
        workspace_ref = f"{root}/workspace"
        trial_ref = f"{root}/trial.json"
        summary_ref = f"{root}/summary.json"
        metric_events_ref = f"{root}/metric_events.jsonl"
        review_packet_ref = f"{root}/review_packet.json"
        summary = _summary_from_outcome(
            task=task,
            mode=mode,
            seed=seed,
            outcome=outcome,
            metric_events_ref=metric_events_ref,
        )
        metric_event = MetricEvent(
            metric_id=f"BM-{task.task_id}-{mode.value}-seed-{seed:04d}",
            mission_run_id=run_id,
            namespace="missionforge.harness",
            source_ref=summary_ref,
            run_ref=trial_ref,
            metric_kind="summary",
            values=summary.metric_values(),
            trust_level=MetricTrustLevel.OPERATOR_DIAGNOSTIC.value,
            tags=["benchmark", mode.value],
        )
        metric_event.validate()
        trial = BenchmarkTrial(
            benchmark_run_id=run_id,
            task_id=task.task_id,
            mode=mode,
            seed=seed,
            workspace_ref=workspace_ref,
            started_at=started_at,
            completed_at=completed_at,
            status=BenchmarkStatus.ACCEPTED if summary.accepted else outcome.status,
            artifact_refs=list(outcome.artifact_refs),
            metric_events_ref=metric_events_ref,
            summary_ref=summary_ref,
            review_packet_ref=review_packet_ref,
        )
        trial.validate()
        self.store.write_json(trial_ref, trial.to_dict())
        self.store.write_json(summary_ref, summary.to_dict())
        self.store.write_jsonl(metric_events_ref, [metric_event.to_dict()])
        self.store.write_json(
            review_packet_ref,
            {
                "schema_version": "missionforge.benchmark_review_packet.v1",
                "task_id": task.task_id,
                "seed": seed,
                "artifact_refs": list(outcome.artifact_refs),
                "summary_ref": summary_ref,
                "metric_events_ref": metric_events_ref,
            },
        )
        return OfflineTrialRecord(
            trial=trial,
            summary=summary,
            metric_event=metric_event,
            trial_ref=trial_ref,
            summary_ref=summary_ref,
            metric_events_ref=metric_events_ref,
            review_packet_ref=review_packet_ref,
        )

    def write_aggregate(self, *, benchmark_run_id: str, records: list[OfflineTrialRecord]) -> tuple[str, str, BenchmarkAggregate]:
        """Write deterministic aggregate JSON and Markdown report."""

        run_id = require_non_empty_str(benchmark_run_id, "offline_harness.benchmark_run_id")
        validate_ref(run_id, "offline_harness.benchmark_run_id")
        sorted_records = sorted(
            records,
            key=lambda record: (record.summary.task_id, record.summary.mode.value, record.summary.seed),
        )
        aggregate = build_aggregate(
            benchmark_run_id=run_id,
            summaries=[record.summary for record in sorted_records],
            summary_refs=[record.summary_ref for record in sorted_records],
        )
        aggregate_ref = f"benchmarks/runs/{run_id}/aggregate.json"
        report_ref = f"benchmarks/runs/{run_id}/report.md"
        self.store.write_json(aggregate_ref, aggregate.to_dict())
        self.store.write_text(report_ref, build_aggregate_report(aggregate))
        return aggregate_ref, report_ref, aggregate


def _summary_from_outcome(
    *,
    task: BenchmarkTask,
    mode: BenchmarkMode,
    seed: int,
    outcome: OfflineTrialOutcome,
    metric_events_ref: str,
) -> BenchmarkSummary:
    values: dict[str, Any] = dict(outcome.metric_values)
    return BenchmarkSummary(
        task_id=task.task_id,
        mode=mode,
        seed=seed,
        accepted=outcome.accepted,
        status=BenchmarkStatus.ACCEPTED if outcome.accepted else outcome.status,
        comparable=outcome.comparable,
        product_gate_status=outcome.product_gate_status,
        review_score=outcome.review_score,
        time_to_first_artifact_ms=int(values.get("time_to_first_artifact_ms", 0)),
        time_to_generic_verifier_pass_ms=int(values.get("time_to_generic_verifier_pass_ms", 0)),
        time_to_product_gate_pass_ms=int(values.get("time_to_product_gate_pass_ms", 0)),
        time_to_accepted_deliverable_ms=int(values.get("time_to_accepted_deliverable_ms", 0)),
        wall_duration_ms=int(values.get("wall_duration_ms", 0)),
        estimated_cost_usd=float(values.get("estimated_cost_usd", 0.0)),
        provider_reported_cost_usd=float(values.get("provider_reported_cost_usd", 0.0)),
        total_tokens=int(values.get("total_tokens", 0)),
        input_tokens=int(values.get("input_tokens", 0)),
        output_tokens=int(values.get("output_tokens", 0)),
        cache_read_tokens=int(values.get("cache_read_tokens", 0)),
        cache_write_tokens=int(values.get("cache_write_tokens", 0)),
        tool_call_count=int(values.get("tool_call_count", 0)),
        repair_count=int(values.get("repair_count", 0)),
        user_turn_count=int(values.get("user_turn_count", 0)),
        clarification_turn_count=int(values.get("clarification_turn_count", 0)),
        privacy_violation_count=int(values.get("privacy_violation_count", 0)),
        boundary_violation_count=int(values.get("boundary_violation_count", 0)),
        defect_leakage_count=int(values.get("defect_leakage_count", 0)),
        failure_taxonomy=list(outcome.failure_taxonomy),
        artifact_refs=list(outcome.artifact_refs),
        metric_events_ref=metric_events_ref,
    )


def _trial_root(*, run_id: str, task_id: str, mode: BenchmarkMode, seed: int) -> str:
    if seed < 0:
        raise ContractValidationError("offline_harness.seed must be >= 0")
    return f"benchmarks/runs/{run_id}/trials/{task_id}/{mode.value}/seed-{seed}"
