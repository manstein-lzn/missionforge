"""Multi-task, multi-seed benchmark orchestration and reporting."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any, Mapping, Protocol

from ..contracts import (
    ContractValidationError,
    assert_refs_only_payload,
    ensure_json_value,
    require_int_at_least,
    require_mapping,
    require_non_empty_str,
    require_str_list,
    validate_ref,
)
from ..json_store import JsonWorkspaceStore
from .acceptance import (
    AcceptanceResult,
    AcceptanceVisibility,
    apply_hidden_acceptance,
    evaluate_acceptance_pack,
    load_acceptance_pack,
)
from .contracts import (
    BenchmarkAggregate,
    BenchmarkMode,
    BenchmarkStatus,
    BenchmarkSummary,
    BenchmarkTask,
    BenchmarkTrial,
    build_aggregate,
)
from .report import build_aggregate_report


MULTISEED_MANIFEST_SCHEMA_VERSION = "missionforge.benchmark_multiseed_manifest.v1"
MULTISEED_RESULT_SCHEMA_VERSION = "missionforge.benchmark_multiseed_result.v1"
MODE_COMPARISON_SCHEMA_VERSION = "missionforge.benchmark_mode_comparison.v1"
TABLE_DATA_SCHEMA_VERSION = "missionforge.benchmark_table_data.v1"


class BenchmarkTrialRunner(Protocol):
    """Shared runner surface for benchmark modes."""

    def run_trial(
        self,
        *,
        benchmark_run_id: str,
        task: BenchmarkTask,
        seed: int,
        workspace: str | Path = ".",
        started_at: str = "1970-01-01T00:00:00Z",
        completed_at: str = "1970-01-01T00:00:00Z",
    ) -> Any:
        """Run one benchmark trial and return an object with trial/summary refs."""


@dataclass(frozen=True)
class MultiSeedBenchmarkManifest:
    """Comparable multi-task/multi-seed benchmark run manifest."""

    benchmark_run_id: str
    task_refs: list[str]
    modes: list[BenchmarkMode]
    seeds: list[int]
    hidden_acceptance_joined: bool = True
    fairness_controls: dict[str, Any] = field(default_factory=dict)
    schema_version: str = MULTISEED_MANIFEST_SCHEMA_VERSION

    def validate(self) -> None:
        if self.schema_version != MULTISEED_MANIFEST_SCHEMA_VERSION:
            raise ContractValidationError("multiseed_manifest.schema_version is unsupported")
        _require_id(self.benchmark_run_id, "multiseed_manifest.benchmark_run_id")
        _require_ref_list(self.task_refs, "multiseed_manifest.task_refs")
        if not self.modes:
            raise ContractValidationError("multiseed_manifest.modes must not be empty")
        for mode in self.modes:
            if not isinstance(mode, BenchmarkMode):
                raise ContractValidationError("multiseed_manifest.modes[] must be BenchmarkMode")
        if not self.seeds:
            raise ContractValidationError("multiseed_manifest.seeds must not be empty")
        for seed in self.seeds:
            require_int_at_least(seed, "multiseed_manifest.seeds[]", 0)
        if not isinstance(self.hidden_acceptance_joined, bool):
            raise ContractValidationError("multiseed_manifest.hidden_acceptance_joined must be boolean")
        ensure_json_value(require_mapping(self.fairness_controls, "multiseed_manifest.fairness_controls"), "multiseed_manifest.fairness_controls")
        assert_refs_only_payload(self.to_dict_without_validation(), "multiseed_manifest")

    def to_dict_without_validation(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "benchmark_run_id": self.benchmark_run_id,
            "task_refs": list(self.task_refs),
            "modes": [mode.value for mode in self.modes],
            "seeds": list(self.seeds),
            "hidden_acceptance_joined": self.hidden_acceptance_joined,
            "fairness_controls": dict(self.fairness_controls),
        }

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return self.to_dict_without_validation()


@dataclass(frozen=True)
class MultiSeedBenchmarkResult:
    """Refs written by a multi-seed benchmark run."""

    manifest: MultiSeedBenchmarkManifest
    aggregate: BenchmarkAggregate
    summary_refs: list[str]
    hidden_acceptance_result_refs: list[str]
    non_comparable_trial_refs: list[str]
    manifest_ref: str
    aggregate_ref: str
    report_ref: str
    mode_comparison_ref: str
    table_data_ref: str
    schema_version: str = MULTISEED_RESULT_SCHEMA_VERSION

    def validate(self) -> None:
        if self.schema_version != MULTISEED_RESULT_SCHEMA_VERSION:
            raise ContractValidationError("multiseed_result.schema_version is unsupported")
        self.manifest.validate()
        self.aggregate.validate()
        _require_ref_list(self.summary_refs, "multiseed_result.summary_refs")
        _require_ref_list(self.hidden_acceptance_result_refs, "multiseed_result.hidden_acceptance_result_refs")
        _require_ref_list(self.non_comparable_trial_refs, "multiseed_result.non_comparable_trial_refs")
        for ref in (
            self.manifest_ref,
            self.aggregate_ref,
            self.report_ref,
            self.mode_comparison_ref,
            self.table_data_ref,
        ):
            validate_ref(ref, "multiseed_result.refs")
        assert_refs_only_payload(self.to_dict_without_validation(), "multiseed_result")

    def to_dict_without_validation(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "manifest_ref": self.manifest_ref,
            "aggregate_ref": self.aggregate_ref,
            "report_ref": self.report_ref,
            "mode_comparison_ref": self.mode_comparison_ref,
            "table_data_ref": self.table_data_ref,
            "summary_refs": list(self.summary_refs),
            "hidden_acceptance_result_refs": list(self.hidden_acceptance_result_refs),
            "non_comparable_trial_refs": list(self.non_comparable_trial_refs),
        }

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return self.to_dict_without_validation()


class MultiSeedBenchmarkRunner:
    """Run a benchmark matrix and join evaluator-only hidden acceptance."""

    def __init__(self, *, workspace: str | Path = ".", mode_runners: Mapping[BenchmarkMode, BenchmarkTrialRunner]) -> None:
        self.workspace = Path(workspace).resolve()
        self.store = JsonWorkspaceStore(self.workspace)
        self.mode_runners = dict(mode_runners)

    def run(
        self,
        *,
        benchmark_run_id: str,
        tasks: list[BenchmarkTask],
        modes: list[BenchmarkMode],
        seeds: list[int],
        started_at: str = "1970-01-01T00:00:00Z",
        completed_at: str = "1970-01-01T00:00:00Z",
    ) -> MultiSeedBenchmarkResult:
        run_id = _require_id(benchmark_run_id, "multiseed.benchmark_run_id")
        if not tasks:
            raise ContractValidationError("multiseed.tasks must not be empty")
        if not modes:
            raise ContractValidationError("multiseed.modes must not be empty")
        if not seeds:
            raise ContractValidationError("multiseed.seeds must not be empty")
        for task in tasks:
            task.validate()
        for seed in seeds:
            require_int_at_least(seed, "multiseed.seeds[]", 0)
        task_refs = [f"benchmarks/tasks/{task.task_id}/task.json" for task in tasks]
        manifest = MultiSeedBenchmarkManifest(
            benchmark_run_id=run_id,
            task_refs=task_refs,
            modes=list(modes),
            seeds=list(seeds),
            fairness_controls={
                "same_initial_user_text": True,
                "hidden_checks_worker_visible": False,
                "clean_workspace_per_trial": True,
                "same_post_run_evaluator": True,
            },
        )
        manifest.validate()
        manifest_ref = f"benchmarks/runs/{run_id}/manifest.json"
        self.store.write_json(manifest_ref, manifest.to_dict())

        summaries: list[BenchmarkSummary] = []
        summary_refs: list[str] = []
        hidden_result_refs: list[str] = []
        non_comparable_trial_refs: list[str] = []
        for task in tasks:
            for mode in modes:
                runner = self._runner_for(mode)
                for seed in seeds:
                    record = runner.run_trial(
                        benchmark_run_id=run_id,
                        task=_worker_visible_task(task),
                        seed=seed,
                        workspace=self.workspace,
                        started_at=started_at,
                        completed_at=completed_at,
                    )
                    trial = _record_trial(record)
                    summary = _record_summary(record)
                    summary_ref = _record_summary_ref(record)
                    trial_ref = _record_trial_ref(record)
                    hidden_results = self._join_hidden_acceptance(
                        task=task,
                        trial=trial,
                        summary_ref=summary_ref,
                        summary=summary,
                    )
                    for hidden_ref, hidden_summary in hidden_results:
                        hidden_result_refs.append(hidden_ref)
                        summary = hidden_summary
                    if not summary.comparable:
                        non_comparable_trial_refs.append(trial_ref)
                    trial = BenchmarkTrial(
                        benchmark_run_id=trial.benchmark_run_id,
                        task_id=trial.task_id,
                        mode=trial.mode,
                        seed=trial.seed,
                        workspace_ref=trial.workspace_ref,
                        started_at=trial.started_at,
                        completed_at=trial.completed_at,
                        status=BenchmarkStatus.ACCEPTED if summary.accepted else summary.status,
                        artifact_refs=list(summary.artifact_refs),
                        metric_events_ref=trial.metric_events_ref,
                        summary_ref=summary_ref,
                        review_packet_ref=trial.review_packet_ref,
                    )
                    trial.validate()
                    self.store.write_json(summary_ref, summary.to_dict())
                    self.store.write_json(trial_ref, trial.to_dict())
                    summaries.append(summary)
                    summary_refs.append(summary_ref)

        aggregate = build_aggregate(benchmark_run_id=run_id, summaries=summaries, summary_refs=summary_refs)
        aggregate_ref = f"benchmarks/runs/{run_id}/aggregate.json"
        report_ref = f"benchmarks/runs/{run_id}/report.md"
        comparison_ref = f"benchmarks/runs/{run_id}/mode_comparisons.json"
        table_ref = f"benchmarks/runs/{run_id}/table_data.json"
        comparisons = build_mode_comparisons(aggregate)
        table_data = build_table_data(aggregate=aggregate, comparisons=comparisons)
        self.store.write_json(aggregate_ref, aggregate.to_dict())
        self.store.write_json(comparison_ref, comparisons)
        self.store.write_json(table_ref, table_data)
        self.store.write_text(report_ref, build_aggregate_report(aggregate))
        result = MultiSeedBenchmarkResult(
            manifest=manifest,
            aggregate=aggregate,
            summary_refs=summary_refs,
            hidden_acceptance_result_refs=hidden_result_refs,
            non_comparable_trial_refs=non_comparable_trial_refs,
            manifest_ref=manifest_ref,
            aggregate_ref=aggregate_ref,
            report_ref=report_ref,
            mode_comparison_ref=comparison_ref,
            table_data_ref=table_ref,
        )
        result.validate()
        self.store.write_json(f"benchmarks/runs/{run_id}/multiseed_result.json", result.to_dict())
        return result

    def _runner_for(self, mode: BenchmarkMode) -> BenchmarkTrialRunner:
        runner = self.mode_runners.get(mode)
        if runner is None:
            raise ContractValidationError(f"multiseed runner missing mode: {mode.value}")
        return runner

    def _join_hidden_acceptance(
        self,
        *,
        task: BenchmarkTask,
        trial: BenchmarkTrial,
        summary_ref: str,
        summary: BenchmarkSummary,
    ) -> list[tuple[str, BenchmarkSummary]]:
        results: list[tuple[str, BenchmarkSummary]] = []
        current = summary
        for acceptance_ref in task.acceptance_refs:
            pack = load_acceptance_pack(self.workspace, acceptance_ref)
            if pack.visibility != AcceptanceVisibility.HIDDEN:
                continue
            result_ref = _hidden_result_ref(trial=trial, pack_id=pack.pack_id)
            acceptance = evaluate_acceptance_pack(
                workspace=self.workspace,
                trial_workspace_ref=trial.workspace_ref,
                pack=pack,
                result_ref=result_ref,
            )
            self.store.write_json(result_ref, acceptance.to_dict())
            current = apply_hidden_acceptance(current, acceptance)
            current = BenchmarkSummary(
                task_id=current.task_id,
                mode=current.mode,
                seed=current.seed,
                accepted=current.accepted,
                status=current.status,
                comparable=current.comparable,
                generic_verifier_passed=current.generic_verifier_passed,
                hidden_acceptance_passed=current.hidden_acceptance_passed,
                product_gate_status=current.product_gate_status,
                frontdesk_node_count=current.frontdesk_node_count,
                frontdesk_worker_call_count=current.frontdesk_worker_call_count,
                frontdesk_missing_slot_count=current.frontdesk_missing_slot_count,
                frontdesk_slot_conflict_count=current.frontdesk_slot_conflict_count,
                intent_bundle_ready=current.intent_bundle_ready,
                product_compile_status=current.product_compile_status,
                product_clarification_count=current.product_clarification_count,
                product_acceptance_coverage_passed=current.product_acceptance_coverage_passed,
                product_gate_blocking_finding_count=current.product_gate_blocking_finding_count,
                review_score=current.review_score,
                time_to_first_artifact_ms=current.time_to_first_artifact_ms,
                time_to_generic_verifier_pass_ms=current.time_to_generic_verifier_pass_ms,
                time_to_product_gate_pass_ms=current.time_to_product_gate_pass_ms,
                time_to_accepted_deliverable_ms=current.time_to_accepted_deliverable_ms,
                wall_duration_ms=current.wall_duration_ms,
                estimated_cost_usd=current.estimated_cost_usd,
                provider_reported_cost_usd=current.provider_reported_cost_usd,
                total_tokens=current.total_tokens,
                input_tokens=current.input_tokens,
                output_tokens=current.output_tokens,
                cache_read_tokens=current.cache_read_tokens,
                cache_write_tokens=current.cache_write_tokens,
                tool_call_count=current.tool_call_count,
                repair_count=current.repair_count,
                user_turn_count=current.user_turn_count,
                clarification_turn_count=current.clarification_turn_count,
                privacy_violation_count=current.privacy_violation_count,
                boundary_violation_count=current.boundary_violation_count,
                defect_leakage_count=current.defect_leakage_count,
                failure_taxonomy=current.failure_taxonomy,
                artifact_refs=current.artifact_refs,
                metric_events_ref=current.metric_events_ref or summary_ref.replace("summary.json", "metric_events.jsonl"),
            )
            results.append((result_ref, current))
        return results


def build_mode_comparisons(aggregate: BenchmarkAggregate) -> dict[str, Any]:
    """Build deterministic effect-size rows from aggregate mode summaries."""

    aggregate.validate()
    modes = aggregate.mode_summaries
    baseline_name = "direct_piworker_chat" if "direct_piworker_chat" in modes else sorted(modes)[0] if modes else ""
    baseline = modes.get(baseline_name, {})
    rows: list[dict[str, Any]] = []
    for mode, values in sorted(modes.items()):
        rows.append(
            {
                "mode": mode,
                "baseline_mode": baseline_name,
                "success_rate_delta": _number(values.get("success_rate_within_budget")) - _number(baseline.get("success_rate_within_budget")),
                "cost_per_acceptance_delta_usd": _number(values.get("cost_per_accepted_deliverable_usd"))
                - _number(baseline.get("cost_per_accepted_deliverable_usd")),
                "avg_time_to_acceptance_delta_ms": _number(values.get("avg_time_to_accepted_deliverable_ms"))
                - _number(baseline.get("avg_time_to_accepted_deliverable_ms")),
                "comparable_accepted_count_delta": int(values.get("comparable_accepted_count", 0))
                - int(baseline.get("comparable_accepted_count", 0)),
                "total_accepted_count_delta": int(values.get("accepted_count", 0)) - int(baseline.get("accepted_count", 0)),
                "non_comparable_trial_count": int(values.get("non_comparable_trial_count", 0)),
            }
        )
    payload = {
        "schema_version": MODE_COMPARISON_SCHEMA_VERSION,
        "benchmark_run_id": aggregate.benchmark_run_id,
        "baseline_mode": baseline_name,
        "winner_by_success_rate": _winner(modes, "success_rate_within_budget", higher=True),
        "winner_by_cost_per_acceptance": _winner(modes, "cost_per_accepted_deliverable_usd", higher=False),
        "winner_by_time_to_acceptance": _winner(modes, "avg_time_to_accepted_deliverable_ms", higher=False),
        "effect_size_rows": rows,
    }
    assert_refs_only_payload(payload, "mode_comparisons")
    return payload


def build_table_data(*, aggregate: BenchmarkAggregate, comparisons: Mapping[str, Any]) -> dict[str, Any]:
    """Build table-ready data for cost/time/stability charting."""

    aggregate.validate()
    rows: list[dict[str, Any]] = []
    for mode, values in sorted(aggregate.mode_summaries.items()):
        rows.append(
            {
                "mode": mode,
                "trial_count": int(values.get("trial_count", 0)),
                "comparable_trial_count": int(values.get("comparable_trial_count", 0)),
                "non_comparable_trial_count": int(values.get("non_comparable_trial_count", 0)),
                "comparable_accepted_count": int(values.get("comparable_accepted_count", 0)),
                "total_accepted_count": int(values.get("accepted_count", 0)),
                "success_rate_within_budget": _number(values.get("success_rate_within_budget")),
                "estimated_cost_usd": _number(values.get("estimated_cost_usd")),
                "total_estimated_cost_usd": _number(values.get("total_estimated_cost_usd")),
                "cost_per_accepted_deliverable_usd": _number(values.get("cost_per_accepted_deliverable_usd")),
                "avg_time_to_accepted_deliverable_ms": _number(values.get("avg_time_to_accepted_deliverable_ms")),
                "p50_time_to_accepted_deliverable_ms": _number(values.get("p50_time_to_accepted_deliverable_ms")),
                "p95_time_to_accepted_deliverable_ms": _number(values.get("p95_time_to_accepted_deliverable_ms")),
                "repair_count": int(values.get("repair_count", 0)),
                "defect_leakage_count": int(values.get("defect_leakage_count", 0)),
            }
        )
    payload = {
        "schema_version": TABLE_DATA_SCHEMA_VERSION,
        "benchmark_run_id": aggregate.benchmark_run_id,
        "mode_rows": rows,
        "effect_size_rows": list(comparisons.get("effect_size_rows", [])),
        "failure_taxonomy_counts": dict(aggregate.failure_taxonomy_counts),
    }
    assert_refs_only_payload(payload, "benchmark_table_data")
    return payload


def _worker_visible_task(task: BenchmarkTask) -> BenchmarkTask:
    return BenchmarkTask(
        task_id=task.task_id,
        task_family=task.task_family,
        difficulty=task.difficulty,
        initial_user_text_ref=task.initial_user_text_ref,
        allowed_source_refs=list(task.allowed_source_refs),
        expected_output_refs=list(task.expected_output_refs),
        budget=task.budget,
        acceptance_refs=[],
        schema_version=task.schema_version,
    )


def _record_trial(record: Any) -> BenchmarkTrial:
    trial = getattr(record, "trial", None)
    if not isinstance(trial, BenchmarkTrial):
        raise ContractValidationError("benchmark runner record must expose BenchmarkTrial trial")
    trial.validate()
    return trial


def _record_summary(record: Any) -> BenchmarkSummary:
    summary = getattr(record, "summary", None)
    if not isinstance(summary, BenchmarkSummary):
        raise ContractValidationError("benchmark runner record must expose BenchmarkSummary summary")
    summary.validate()
    return summary


def _record_summary_ref(record: Any) -> str:
    return validate_ref(getattr(record, "summary_ref", ""), "benchmark_runner_record.summary_ref")


def _record_trial_ref(record: Any) -> str:
    return validate_ref(getattr(record, "trial_ref", ""), "benchmark_runner_record.trial_ref")


def _hidden_result_ref(*, trial: BenchmarkTrial, pack_id: str) -> str:
    return (
        f"benchmarks/runs/{trial.benchmark_run_id}/trials/{trial.task_id}/"
        f"{trial.mode.value}/seed-{trial.seed}/hidden_acceptance_{_safe_id(pack_id)}.json"
    )


def _winner(modes: Mapping[str, Mapping[str, Any]], metric: str, *, higher: bool) -> str:
    candidates = [
        (mode, _number(values.get(metric)))
        for mode, values in modes.items()
        if _eligible_for_metric_winner(values, metric)
    ]
    if not candidates:
        return ""
    if not higher:
        non_zero = [(mode, value) for mode, value in candidates if value > 0]
        candidates = non_zero or candidates
    selected = max(candidates, key=lambda item: (item[1], item[0])) if higher else min(candidates, key=lambda item: (item[1], item[0]))
    return selected[0]


def _eligible_for_metric_winner(values: Mapping[str, Any], metric: str) -> bool:
    if metric in {
        "cost_per_accepted_deliverable_usd",
        "avg_time_to_accepted_deliverable_ms",
        "p50_time_to_accepted_deliverable_ms",
        "p95_time_to_accepted_deliverable_ms",
    }:
        return int(values.get("comparable_accepted_count", 0)) > 0
    return True


def _number(value: Any) -> float:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return 0.0


def _require_id(value: Any, field_name: str) -> str:
    text = require_non_empty_str(value, field_name)
    if "/" in text or "\\" in text or text in {".", ".."}:
        raise ContractValidationError(f"{field_name} must be a safe id, not a path")
    validate_ref(text, field_name)
    return text


def _safe_id(value: str) -> str:
    text = require_non_empty_str(value, "multiseed.safe_id").lower()
    safe = "".join(char if char.isalnum() or char in "._-" else "-" for char in text).strip("-._")
    if not safe:
        raise ContractValidationError("safe id is empty")
    return safe


def _require_ref_list(value: Any, field_name: str) -> list[str]:
    refs = require_str_list(value, field_name)
    for ref in refs:
        validate_ref(ref, f"{field_name}[]")
    return refs


__all__ = [
    "MODE_COMPARISON_SCHEMA_VERSION",
    "MULTISEED_MANIFEST_SCHEMA_VERSION",
    "MULTISEED_RESULT_SCHEMA_VERSION",
    "TABLE_DATA_SCHEMA_VERSION",
    "BenchmarkTrialRunner",
    "MultiSeedBenchmarkManifest",
    "MultiSeedBenchmarkResult",
    "MultiSeedBenchmarkRunner",
    "build_mode_comparisons",
    "build_table_data",
]
