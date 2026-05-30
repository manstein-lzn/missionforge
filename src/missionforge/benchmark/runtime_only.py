"""Benchmark-only MissionForge runtime-only trial runner."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import time
from typing import Any, Mapping

from ..contracts import (
    ContractValidationError,
    ensure_json_value,
    require_int_at_least,
    require_mapping,
    require_non_empty_str,
    validate_ref,
)
from ..ir import MissionIR
from ..json_store import JsonWorkspaceStore
from ..metric_store import MetricStore
from ..metrics import MetricEvent, MetricTrustLevel
from ..runner import MissionResult, MissionRuntime
from ..runtime import RuntimeEngine
from ..state import mission_run_id_for
from .contracts import (
    BenchmarkMode,
    BenchmarkStatus,
    BenchmarkSummary,
    BenchmarkTask,
    BenchmarkTrial,
)


RUNTIME_ONLY_RESULT_SCHEMA_VERSION = "missionforge.benchmark_runtime_only_result.v1"


@dataclass(frozen=True)
class RuntimeOnlyConfig:
    """Configuration for the benchmark-only MissionForge runtime arm."""

    max_attempts: int = 1
    pi_agent_config: Any | None = None
    product_gate_status: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        require_int_at_least(self.max_attempts, "runtime_only_config.max_attempts", 1)
        ensure_json_value(require_mapping(self.metadata, "runtime_only_config.metadata"), "runtime_only_config.metadata")
        if self.product_gate_status:
            require_non_empty_str(self.product_gate_status, "runtime_only_config.product_gate_status")


@dataclass(frozen=True)
class RuntimeOnlyTrialRecord:
    """Refs written by one MissionForge runtime-only benchmark trial."""

    trial: BenchmarkTrial
    summary: BenchmarkSummary
    metric_event: MetricEvent
    mission_result: MissionResult
    trial_ref: str
    summary_ref: str
    metric_events_ref: str
    review_packet_ref: str
    runtime_result_ref: str
    mission_ir_ref: str


class MissionForgeRuntimeOnlyBenchmarkRunner:
    """Run a prepared MissionIR fixture through MissionForge runtime only."""

    def __init__(
        self,
        config: RuntimeOnlyConfig | None = None,
        *,
        worker: Any | None = None,
    ) -> None:
        self.config = config or RuntimeOnlyConfig()
        self.worker = worker

    def run_trial(
        self,
        *,
        benchmark_run_id: str,
        task: BenchmarkTask,
        mission_ir_ref: str,
        seed: int,
        workspace: str | Path = ".",
        started_at: str = "1970-01-01T00:00:00Z",
        completed_at: str = "1970-01-01T00:00:00Z",
    ) -> RuntimeOnlyTrialRecord:
        run_id = _require_id(benchmark_run_id, "runtime_only.benchmark_run_id")
        mission_ref = validate_ref(mission_ir_ref, "runtime_only.mission_ir_ref")
        require_int_at_least(seed, "runtime_only.seed", 0)
        task.validate()
        root = Path(workspace).resolve()
        root.mkdir(parents=True, exist_ok=True)
        store = JsonWorkspaceStore(root)
        refs = _runtime_only_refs(run_id=run_id, task_id=task.task_id, seed=seed)
        runtime_workspace = _resolve_workspace_ref(root, refs["workspace"])
        runtime_workspace.mkdir(parents=True, exist_ok=True)

        mission = MissionIR.from_dict(store.read_json(mission_ref))
        started = time.monotonic()
        try:
            mission_result = self._run_runtime(mission, runtime_workspace)
        except Exception as exc:
            mission_result = MissionResult(
                mission_id=mission.mission_id,
                status="failed",
                evidence_refs=[],
                artifact_refs=[],
                failed_constraint_ids=[],
                metrics={
                    "runtime_exception_count": 1,
                    "runtime_exception_type": type(exc).__name__,
                    "verification_status": "runtime_exception",
                    "attempt_count": 0,
                    "repair_attempted": False,
                },
            )
        duration_ms = _duration_ms(started)
        runtime_result_ref = store.write_json(
            refs["runtime_result"],
            {
                "schema_version": RUNTIME_ONLY_RESULT_SCHEMA_VERSION,
                "benchmark_run_id": run_id,
                "task_id": task.task_id,
                "seed": seed,
                "mission_ir_ref": mission_ref,
                "workspace_ref": refs["workspace"],
                "duration_ms": duration_ms,
                "mission_result": mission_result.to_dict(),
            },
        )
        summary = _summary_from_runtime_result(
            task=task,
            seed=seed,
            result=mission_result,
            duration_ms=duration_ms,
            runtime_workspace=runtime_workspace,
            workspace_ref=refs["workspace"],
            metric_events_ref=refs["metric_events"],
            product_gate_status=self.config.product_gate_status,
        )
        metric_event = MetricEvent(
            metric_id=f"BM-{task.task_id}-{BenchmarkMode.MISSIONFORGE_RUNTIME_ONLY.value}-seed-{seed:04d}",
            mission_run_id=run_id,
            namespace="missionforge.harness",
            source_ref=refs["summary"],
            run_ref=refs["trial"],
            metric_kind="summary",
            values=summary.metric_values(),
            trust_level=MetricTrustLevel.OPERATOR_DIAGNOSTIC.value,
            tags=["benchmark", BenchmarkMode.MISSIONFORGE_RUNTIME_ONLY.value],
        )
        metric_event.validate()
        trial = BenchmarkTrial(
            benchmark_run_id=run_id,
            task_id=task.task_id,
            mode=BenchmarkMode.MISSIONFORGE_RUNTIME_ONLY,
            seed=seed,
            workspace_ref=refs["workspace"],
            started_at=started_at,
            completed_at=completed_at,
            status=BenchmarkStatus.ACCEPTED if summary.accepted else summary.status,
            artifact_refs=list(summary.artifact_refs),
            metric_events_ref=refs["metric_events"],
            summary_ref=refs["summary"],
            review_packet_ref=refs["review_packet"],
        )
        trial.validate()
        store.write_json(refs["trial"], trial.to_dict())
        store.write_json(refs["summary"], summary.to_dict())
        store.write_jsonl(refs["metric_events"], [metric_event.to_dict()])
        store.write_json(
            refs["review_packet"],
            {
                "schema_version": "missionforge.benchmark_review_packet.v1",
                "task_id": task.task_id,
                "seed": seed,
                "artifact_refs": list(summary.artifact_refs),
                "summary_ref": refs["summary"],
                "metric_events_ref": refs["metric_events"],
                "mission_ir_ref": mission_ref,
                "runtime_result_ref": runtime_result_ref,
                "runtime_workspace_ref": refs["workspace"],
                "runtime_status": mission_result.status,
                "verification_status": str(mission_result.metrics.get("verification_status", mission_result.status)),
                "repair_count": summary.repair_count,
                "generic_verifier_passed": summary.generic_verifier_passed,
                "runtime_metric_events_ref": _prefixed_runtime_ref(
                    refs["workspace"],
                    mission_result.metrics.get("metric_events_ref"),
                ),
                "runtime_metric_projection_ref": _prefixed_runtime_ref(
                    refs["workspace"],
                    mission_result.metrics.get("metric_projection_ref"),
                ),
            },
        )
        return RuntimeOnlyTrialRecord(
            trial=trial,
            summary=summary,
            metric_event=metric_event,
            mission_result=mission_result,
            trial_ref=refs["trial"],
            summary_ref=refs["summary"],
            metric_events_ref=refs["metric_events"],
            review_packet_ref=refs["review_packet"],
            runtime_result_ref=runtime_result_ref,
            mission_ir_ref=mission_ref,
        )

    def _run_runtime(self, mission: MissionIR, runtime_workspace: Path) -> MissionResult:
        if self.worker is not None:
            return RuntimeEngine(
                workspace=runtime_workspace,
                max_attempts=self.config.max_attempts,
                worker=self.worker,
            ).run(mission)
        return MissionRuntime(
            workspace=runtime_workspace,
            max_attempts=self.config.max_attempts,
            pi_agent_config=self.config.pi_agent_config,
        ).run(mission)


def _summary_from_runtime_result(
    *,
    task: BenchmarkTask,
    seed: int,
    result: MissionResult,
    duration_ms: int,
    runtime_workspace: Path,
    workspace_ref: str,
    metric_events_ref: str,
    product_gate_status: str,
) -> BenchmarkSummary:
    worker_metrics = _runtime_worker_metrics(runtime_workspace, result.mission_id)
    accepted = result.status == "completed_verified"
    verification_status = str(result.metrics.get("verification_status", result.status))
    repair_count = _repair_count(result.metrics)
    failure_taxonomy: list[str] = []
    if not accepted:
        failure_taxonomy.append(f"runtime_{verification_status}")
        if repair_count:
            failure_taxonomy.append("runtime_repair_incomplete")
    return BenchmarkSummary(
        task_id=task.task_id,
        mode=BenchmarkMode.MISSIONFORGE_RUNTIME_ONLY,
        seed=seed,
        accepted=accepted,
        status=BenchmarkStatus.ACCEPTED if accepted else BenchmarkStatus.FAILED,
        comparable=True,
        generic_verifier_passed=accepted,
        product_gate_status=product_gate_status,
        time_to_first_artifact_ms=_non_negative_metric(worker_metrics, "time_to_first_artifact_ms"),
        time_to_generic_verifier_pass_ms=duration_ms if accepted else 0,
        time_to_accepted_deliverable_ms=duration_ms if accepted else 0,
        wall_duration_ms=duration_ms,
        estimated_cost_usd=_non_negative_number_metric(worker_metrics, "provider_reported_cost_usd"),
        provider_reported_cost_usd=_non_negative_number_metric(worker_metrics, "provider_reported_cost_usd"),
        total_tokens=_non_negative_metric(worker_metrics, "total_tokens", "token_count"),
        input_tokens=_non_negative_metric(worker_metrics, "input_tokens"),
        output_tokens=_non_negative_metric(worker_metrics, "output_tokens"),
        cache_read_tokens=_non_negative_metric(worker_metrics, "cache_read_tokens"),
        cache_write_tokens=_non_negative_metric(worker_metrics, "cache_write_tokens"),
        tool_call_count=_non_negative_metric(worker_metrics, "tool_call_count"),
        repair_count=repair_count,
        user_turn_count=0,
        clarification_turn_count=0,
        privacy_violation_count=0,
        boundary_violation_count=0,
        defect_leakage_count=0,
        failure_taxonomy=failure_taxonomy,
        artifact_refs=[_join_ref(workspace_ref, ref) for ref in result.artifact_refs],
        metric_events_ref=metric_events_ref,
    )


def _runtime_worker_metrics(runtime_workspace: Path, mission_id: str) -> dict[str, Any]:
    try:
        projection = MetricStore(runtime_workspace).load_projection(mission_run_id_for(mission_id))
    except (FileNotFoundError, ContractValidationError):
        return {}
    values = projection.namespaces.get("missionforge.worker.pi_agent", {})
    return dict(values)


def _repair_count(metrics: Mapping[str, Any]) -> int:
    attempt_count = _non_negative_metric(metrics, "attempt_count")
    repair_attempted = metrics.get("repair_attempted")
    if repair_attempted is True and attempt_count > 1:
        return attempt_count - 1
    return 0


def _runtime_only_refs(*, run_id: str, task_id: str, seed: int) -> dict[str, str]:
    if seed < 0:
        raise ContractValidationError("runtime_only.seed must be >= 0")
    root = f"benchmarks/runs/{run_id}/trials/{task_id}/{BenchmarkMode.MISSIONFORGE_RUNTIME_ONLY.value}/seed-{seed}"
    return {
        "root": root,
        "workspace": f"{root}/workspace",
        "runtime_result": f"{root}/runtime_result.json",
        "trial": f"{root}/trial.json",
        "summary": f"{root}/summary.json",
        "metric_events": f"{root}/metric_events.jsonl",
        "review_packet": f"{root}/review_packet.json",
    }


def _prefixed_runtime_ref(workspace_ref: str, value: Any) -> str:
    if not isinstance(value, str) or not value:
        return ""
    return _join_ref(workspace_ref, value)


def _join_ref(prefix: str, ref: str) -> str:
    safe_prefix = validate_ref(prefix, "ref_prefix")
    safe_ref = validate_ref(ref, "ref")
    return f"{safe_prefix.rstrip('/')}/{safe_ref.lstrip('/')}" if safe_prefix else safe_ref


def _require_id(value: Any, field_name: str) -> str:
    text = require_non_empty_str(value, field_name)
    if "/" in text or "\\" in text or text in {".", ".."}:
        raise ContractValidationError(f"{field_name} must be a safe id, not a path")
    validate_ref(text, field_name)
    return text


def _resolve_workspace_ref(root: Path, ref: str) -> Path:
    safe_ref = validate_ref(ref, "runtime_only.ref")
    path = (root / safe_ref).resolve()
    if root not in path.parents and path != root:
        raise ContractValidationError("runtime-only benchmark ref escapes workspace")
    return path


def _non_negative_metric(metrics: Mapping[str, Any], *keys: str) -> int:
    for key in keys:
        value = metrics.get(key)
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
            return value
    return 0


def _non_negative_number_metric(metrics: Mapping[str, Any], *keys: str) -> float:
    for key in keys:
        value = metrics.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0:
            return float(value)
    return 0.0


def _duration_ms(started: float) -> int:
    return max(0, int((time.monotonic() - started) * 1000))
