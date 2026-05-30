"""Benchmark-only MissionForge full FrontDesk/ProductIntegration trial runner."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re
import time
from typing import Any, Callable, Mapping, Protocol

from ..contracts import (
    ContractValidationError,
    VerificationStatus,
    assert_refs_only_payload,
    ensure_json_value,
    require_int_at_least,
    require_mapping,
    require_non_empty_str,
    validate_ref,
)
from ..frontdesk import FrontDesk, FrontDeskIntentBundle, IntentBundleReadiness
from ..frontdesk.pi_node_runner import FrontDeskPiNodeExecutionRecord, frontdesk_pi_node_execution_ref
from ..ir import MissionIR
from ..json_store import JsonWorkspaceStore
from ..metric_store import MetricStore
from ..metrics import MetricEvent, MetricTrustLevel, safe_metric_values
from ..product_integration import ProductCompileResult, ProductCompileStatus, ProductIntegration
from ..runner import MissionResult, MissionRuntime
from ..runtime import RuntimeEngine
from ..state import mission_run_id_for
from .contracts import BenchmarkMode, BenchmarkStatus, BenchmarkSummary, BenchmarkTask, BenchmarkTrial


FULL_PRODUCT_FLOW_RESULT_SCHEMA_VERSION = "missionforge.benchmark_full_product_flow_result.v1"
PRODUCT_GATE_OUTCOME_SCHEMA_VERSION = "missionforge.benchmark_product_gate_outcome.v1"
PRODUCT_GATE_PASS_STATUSES = {"passed", "product_grade"}


@dataclass(frozen=True)
class ProductGateOutcome:
    """Safe ProductGate benchmark read model returned by product integrations."""

    product_id: str
    status: str
    result_ref: str = ""
    evidence_refs: list[str] = field(default_factory=list)
    artifact_refs: list[str] = field(default_factory=list)
    diagnostic_refs: list[str] = field(default_factory=list)
    product_acceptance_coverage_passed: bool = False
    blocking_finding_count: int = 0
    outcome_category: str = ""
    schema_version: str = PRODUCT_GATE_OUTCOME_SCHEMA_VERSION

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ProductGateOutcome":
        data = require_mapping(payload, "product_gate_outcome")
        outcome = cls(
            product_id=require_non_empty_str(data.get("product_id"), "product_gate_outcome.product_id"),
            status=require_non_empty_str(data.get("status"), "product_gate_outcome.status"),
            result_ref=str(data.get("result_ref", "")),
            evidence_refs=_require_ref_list(data.get("evidence_refs", []), "product_gate_outcome.evidence_refs"),
            artifact_refs=_require_ref_list(data.get("artifact_refs", []), "product_gate_outcome.artifact_refs"),
            diagnostic_refs=_require_ref_list(data.get("diagnostic_refs", []), "product_gate_outcome.diagnostic_refs"),
            product_acceptance_coverage_passed=_require_bool(
                data.get("product_acceptance_coverage_passed", False),
                "product_gate_outcome.product_acceptance_coverage_passed",
            ),
            blocking_finding_count=require_int_at_least(
                data.get("blocking_finding_count", 0),
                "product_gate_outcome.blocking_finding_count",
                0,
            ),
            outcome_category=str(data.get("outcome_category", "")),
            schema_version=require_non_empty_str(
                data.get("schema_version", PRODUCT_GATE_OUTCOME_SCHEMA_VERSION),
                "product_gate_outcome.schema_version",
            ),
        )
        outcome.validate()
        return outcome

    @property
    def passed(self) -> bool:
        return (
            self.status in PRODUCT_GATE_PASS_STATUSES
            and self.blocking_finding_count == 0
            and self.product_acceptance_coverage_passed
        )

    def validate(self) -> None:
        if self.schema_version != PRODUCT_GATE_OUTCOME_SCHEMA_VERSION:
            raise ContractValidationError("product_gate_outcome.schema_version is unsupported")
        require_non_empty_str(self.product_id, "product_gate_outcome.product_id")
        require_non_empty_str(self.status, "product_gate_outcome.status")
        if self.result_ref:
            validate_ref(self.result_ref, "product_gate_outcome.result_ref")
        _require_ref_list(self.evidence_refs, "product_gate_outcome.evidence_refs")
        _require_ref_list(self.artifact_refs, "product_gate_outcome.artifact_refs")
        _require_ref_list(self.diagnostic_refs, "product_gate_outcome.diagnostic_refs")
        _require_bool(
            self.product_acceptance_coverage_passed,
            "product_gate_outcome.product_acceptance_coverage_passed",
        )
        require_int_at_least(self.blocking_finding_count, "product_gate_outcome.blocking_finding_count", 0)
        assert_refs_only_payload(self.to_dict_without_validation(), "product_gate_outcome")

    def to_dict_without_validation(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "product_id": self.product_id,
            "status": self.status,
            "result_ref": self.result_ref,
            "evidence_refs": list(self.evidence_refs),
            "artifact_refs": list(self.artifact_refs),
            "diagnostic_refs": list(self.diagnostic_refs),
            "product_acceptance_coverage_passed": self.product_acceptance_coverage_passed,
            "blocking_finding_count": self.blocking_finding_count,
            "outcome_category": self.outcome_category,
        }

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return self.to_dict_without_validation()


class ProductGateRunner(Protocol):
    """Product-specific ProductGate callable owned outside MissionForge core."""

    def run_product_gate(
        self,
        *,
        workspace: str | Path,
        task: BenchmarkTask,
        compile_result: ProductCompileResult,
        mission_result: MissionResult,
    ) -> ProductGateOutcome | Mapping[str, Any]:
        """Evaluate product acceptance and return a refs-only gate outcome."""


ProductGateCallable = Callable[..., ProductGateOutcome | Mapping[str, Any]]


@dataclass(frozen=True)
class FullProductFlowConfig:
    """Configuration for the benchmark-only full FrontDesk/ProductIntegration arm."""

    max_attempts: int = 1
    pi_agent_config: Any | None = None
    frontdesk_no_user_loop: bool = True
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        require_int_at_least(self.max_attempts, "full_product_flow_config.max_attempts", 1)
        if not isinstance(self.frontdesk_no_user_loop, bool):
            raise ContractValidationError("full_product_flow_config.frontdesk_no_user_loop must be boolean")
        ensure_json_value(require_mapping(self.metadata, "full_product_flow_config.metadata"), "full_product_flow_config.metadata")


@dataclass(frozen=True)
class FullProductFlowTrialRecord:
    """Refs written by one MissionForge full product-flow benchmark trial."""

    trial: BenchmarkTrial
    summary: BenchmarkSummary
    metric_events: list[MetricEvent]
    product_compile_result: ProductCompileResult
    product_gate_outcome: ProductGateOutcome
    mission_result: MissionResult
    trial_ref: str
    summary_ref: str
    metric_events_ref: str
    review_packet_ref: str
    full_result_ref: str
    product_compile_result_ref: str
    product_gate_outcome_ref: str


class MissionForgeFullProductFlowBenchmarkRunner:
    """Run colloquial user text through FrontDesk, ProductIntegration, runtime, and ProductGate."""

    def __init__(
        self,
        config: FullProductFlowConfig | None = None,
        *,
        product_integration: ProductIntegration | None = None,
        product_gate: ProductGateRunner | ProductGateCallable | None = None,
        frontdesk_worker: Any | None = None,
        runtime: MissionRuntime | None = None,
        runtime_worker: Any | None = None,
    ) -> None:
        self.config = config or FullProductFlowConfig()
        self.product_integration = product_integration
        self.product_gate = product_gate
        self.frontdesk_worker = frontdesk_worker
        self.runtime = runtime
        self.runtime_worker = runtime_worker

    def run_trial(
        self,
        *,
        benchmark_run_id: str,
        task: BenchmarkTask,
        seed: int,
        workspace: str | Path = ".",
        started_at: str = "1970-01-01T00:00:00Z",
        completed_at: str = "1970-01-01T00:00:00Z",
    ) -> FullProductFlowTrialRecord:
        run_id = _require_id(benchmark_run_id, "full_product_flow.benchmark_run_id")
        require_int_at_least(seed, "full_product_flow.seed", 0)
        task.validate()
        integration = self._product_integration_or_fail()
        product_id = _product_id_for(integration)
        root = Path(workspace).resolve()
        root.mkdir(parents=True, exist_ok=True)
        store = JsonWorkspaceStore(root)
        refs = _full_product_flow_refs(run_id=run_id, task_id=task.task_id, seed=seed)
        flow_workspace = _resolve_workspace_ref(root, refs["workspace"])
        flow_workspace.mkdir(parents=True, exist_ok=True)

        session_id = f"fd-{task.task_id}-seed-{seed}"
        session_ref = ""
        frontdesk_status = ""
        frontdesk_next_action = ""
        product_compile_result: ProductCompileResult | None = None
        product_gate_outcome: ProductGateOutcome | None = None
        mission_result: MissionResult | None = None
        mission_ref = ""
        failure_stage = ""
        failure_error_type = ""
        stage = "read_user_text"
        started = time.monotonic()
        try:
            user_text = store.read_text(task.initial_user_text_ref)
            frontdesk = FrontDesk(workspace=flow_workspace, worker=self.frontdesk_worker)
            stage = "frontdesk_start"
            session = frontdesk.start(user_text, session_id=session_id)
            session_ref = session.session_ref
            stage = "frontdesk_grill"
            frontdesk.grill(session.session_ref, require_core_need=self.config.frontdesk_no_user_loop)
            stage = "frontdesk_cover_semantics"
            frontdesk.cover_semantics(session.session_ref)
            stage = "frontdesk_plan_solution"
            frontdesk.plan_solution(session.session_ref)
            stage = "product_compile"
            product_compile_result = frontdesk.compile_product(session.session_ref, integration)
            stage = "runtime"
            if product_compile_result.status == ProductCompileStatus.COMPILED:
                mission_ref = product_compile_result.mission_ir_ref
                mission = MissionIR.from_dict(JsonWorkspaceStore(flow_workspace).read_json(mission_ref))
                mission_result = self._run_runtime(mission, flow_workspace)
                stage = "product_gate"
                product_gate_outcome = self._run_product_gate(
                    workspace=flow_workspace,
                    task=task,
                    compile_result=product_compile_result,
                    mission_result=mission_result,
                )
            else:
                mission_result = _synthetic_mission_result(
                    mission_id=f"full-product-flow-{task.task_id}",
                    status="failed",
                    failure_metric="product_compile_not_compiled",
                )
                product_gate_outcome = _default_product_gate_outcome(
                    product_id=product_id,
                    status="unsupported",
                    outcome_category="product_compile_not_compiled",
                )
            try:
                inspect = frontdesk.inspect(session_ref or session.session_ref)
                frontdesk_status = inspect.status
                frontdesk_next_action = inspect.next_action
            except Exception:
                frontdesk_status = ""
                frontdesk_next_action = ""
        except Exception as exc:
            failure_stage = stage
            failure_error_type = type(exc).__name__
            if product_compile_result is None:
                product_compile_result = _failed_compile_result(product_id=product_id, stage=stage)
            if mission_result is None:
                mission_result = _synthetic_mission_result(
                    mission_id=f"full-product-flow-{task.task_id}",
                    status="failed",
                    failure_metric=stage,
                )
            if product_gate_outcome is None:
                product_gate_outcome = _default_product_gate_outcome(
                    product_id=product_id,
                    status="failed" if stage == "product_gate" else "unsupported",
                    outcome_category=stage,
                )
        duration_ms = _duration_ms(started)

        assert product_compile_result is not None
        assert product_gate_outcome is not None
        assert mission_result is not None
        product_compile_result.validate()
        product_gate_outcome.validate()
        store.write_json(refs["product_compile_result"], product_compile_result.to_dict())
        store.write_json(refs["product_gate_outcome"], product_gate_outcome.to_dict())

        frontdesk_metrics = _frontdesk_metrics(flow_workspace=flow_workspace, session_id=session_id)
        intent_bundle_metrics = _intent_bundle_metrics(flow_workspace)
        runtime_worker_metrics = _runtime_worker_metrics(flow_workspace, mission_result.mission_id)
        failure_taxonomy = _failure_taxonomy(
            product_compile_result=product_compile_result,
            mission_result=mission_result,
            product_gate_outcome=product_gate_outcome,
            failure_stage=failure_stage,
            failure_error_type=failure_error_type,
        )
        summary = _summary_from_full_product_flow(
            task=task,
            seed=seed,
            duration_ms=duration_ms,
            workspace_ref=refs["workspace"],
            metric_events_ref=refs["metric_events"],
            product_compile_result=product_compile_result,
            product_gate_outcome=product_gate_outcome,
            mission_result=mission_result,
            frontdesk_metrics=frontdesk_metrics,
            intent_bundle_metrics=intent_bundle_metrics,
            runtime_worker_metrics=runtime_worker_metrics,
            failure_taxonomy=failure_taxonomy,
        )
        metric_events = _metric_events(
            run_id=run_id,
            task=task,
            seed=seed,
            refs=refs,
            summary=summary,
            product_id=product_id,
        )
        for event in metric_events:
            event.validate()
        trial = BenchmarkTrial(
            benchmark_run_id=run_id,
            task_id=task.task_id,
            mode=BenchmarkMode.MISSIONFORGE_FULL_PRODUCT_FLOW,
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
        full_result_ref = store.write_json(
            refs["full_result"],
            _full_result_payload(
                run_id=run_id,
                task=task,
                seed=seed,
                workspace_ref=refs["workspace"],
                duration_ms=duration_ms,
                session_ref=_prefixed_workspace_ref(refs["workspace"], session_ref),
                frontdesk_status=frontdesk_status,
                frontdesk_next_action=frontdesk_next_action,
                product_compile_result=product_compile_result,
                product_gate_outcome=product_gate_outcome,
                mission_result=mission_result,
                mission_ref=_prefixed_workspace_ref(refs["workspace"], mission_ref),
                failure_stage=failure_stage,
                failure_error_type=failure_error_type,
                failure_taxonomy=failure_taxonomy,
                product_compile_result_ref=refs["product_compile_result"],
                product_gate_outcome_ref=refs["product_gate_outcome"],
            ),
        )
        store.write_json(refs["trial"], trial.to_dict())
        store.write_json(refs["summary"], summary.to_dict())
        store.write_jsonl(refs["metric_events"], [event.to_dict() for event in metric_events])
        store.write_json(
            refs["review_packet"],
            _review_packet_payload(
                task=task,
                seed=seed,
                refs=refs,
                summary=summary,
                session_ref=_prefixed_workspace_ref(refs["workspace"], session_ref),
                mission_ref=_prefixed_workspace_ref(refs["workspace"], mission_ref),
                full_result_ref=full_result_ref,
                product_compile_result=product_compile_result,
                product_gate_outcome=product_gate_outcome,
                frontdesk_metrics=frontdesk_metrics,
            ),
        )
        return FullProductFlowTrialRecord(
            trial=trial,
            summary=summary,
            metric_events=metric_events,
            product_compile_result=product_compile_result,
            product_gate_outcome=product_gate_outcome,
            mission_result=mission_result,
            trial_ref=refs["trial"],
            summary_ref=refs["summary"],
            metric_events_ref=refs["metric_events"],
            review_packet_ref=refs["review_packet"],
            full_result_ref=full_result_ref,
            product_compile_result_ref=refs["product_compile_result"],
            product_gate_outcome_ref=refs["product_gate_outcome"],
        )

    def _product_integration_or_fail(self) -> ProductIntegration:
        if self.product_integration is None:
            raise ContractValidationError("full product flow benchmark requires a ProductIntegration")
        return self.product_integration

    def _run_runtime(self, mission: MissionIR, flow_workspace: Path) -> MissionResult:
        if self.runtime is not None:
            return self.runtime.run(mission)
        if self.runtime_worker is not None:
            return RuntimeEngine(
                workspace=flow_workspace,
                max_attempts=self.config.max_attempts,
                worker=self.runtime_worker,
            ).run(mission)
        return MissionRuntime(
            workspace=flow_workspace,
            max_attempts=self.config.max_attempts,
            pi_agent_config=self.config.pi_agent_config,
        ).run(mission)

    def _run_product_gate(
        self,
        *,
        workspace: Path,
        task: BenchmarkTask,
        compile_result: ProductCompileResult,
        mission_result: MissionResult,
    ) -> ProductGateOutcome:
        if self.product_gate is None:
            return _default_product_gate_outcome(
                product_id=compile_result.product_id,
                status="unsupported",
                outcome_category="product_gate_missing",
            )
        gate = self.product_gate
        if hasattr(gate, "run_product_gate"):
            payload = gate.run_product_gate(
                workspace=workspace,
                task=task,
                compile_result=compile_result,
                mission_result=mission_result,
            )
        else:
            payload = gate(
                workspace=workspace,
                task=task,
                compile_result=compile_result,
                mission_result=mission_result,
            )
        outcome = payload if isinstance(payload, ProductGateOutcome) else ProductGateOutcome.from_dict(payload)
        outcome.validate()
        return outcome


def _summary_from_full_product_flow(
    *,
    task: BenchmarkTask,
    seed: int,
    duration_ms: int,
    workspace_ref: str,
    metric_events_ref: str,
    product_compile_result: ProductCompileResult,
    product_gate_outcome: ProductGateOutcome,
    mission_result: MissionResult,
    frontdesk_metrics: Mapping[str, int],
    intent_bundle_metrics: Mapping[str, Any],
    runtime_worker_metrics: Mapping[str, Any],
    failure_taxonomy: list[str],
) -> BenchmarkSummary:
    generic_verifier_passed = mission_result.status == VerificationStatus.COMPLETED_VERIFIED.value
    accepted = (
        product_compile_result.status == ProductCompileStatus.COMPILED
        and generic_verifier_passed
        and product_gate_outcome.passed
    )
    artifact_refs = _dedupe_refs(
        [
            *[_join_ref(workspace_ref, ref) for ref in mission_result.artifact_refs],
            *[_join_ref(workspace_ref, ref) for ref in product_gate_outcome.artifact_refs],
        ]
    )
    return BenchmarkSummary(
        task_id=task.task_id,
        mode=BenchmarkMode.MISSIONFORGE_FULL_PRODUCT_FLOW,
        seed=seed,
        accepted=accepted,
        status=BenchmarkStatus.ACCEPTED if accepted else BenchmarkStatus.FAILED,
        comparable=True,
        generic_verifier_passed=generic_verifier_passed,
        hidden_acceptance_passed=False,
        product_gate_status=product_gate_outcome.status,
        frontdesk_node_count=_non_negative_metric(frontdesk_metrics, "frontdesk_node_count"),
        frontdesk_worker_call_count=_non_negative_metric(frontdesk_metrics, "frontdesk_worker_call_count"),
        frontdesk_missing_slot_count=_non_negative_metric(intent_bundle_metrics, "frontdesk_missing_slot_count"),
        frontdesk_slot_conflict_count=_non_negative_metric(intent_bundle_metrics, "frontdesk_slot_conflict_count"),
        intent_bundle_ready=bool(intent_bundle_metrics.get("intent_bundle_ready", False)),
        product_compile_status=product_compile_result.status.value,
        product_clarification_count=len(product_compile_result.clarification_questions),
        product_acceptance_coverage_passed=product_gate_outcome.product_acceptance_coverage_passed,
        product_gate_blocking_finding_count=product_gate_outcome.blocking_finding_count,
        time_to_first_artifact_ms=_non_negative_metric(runtime_worker_metrics, "time_to_first_artifact_ms"),
        time_to_generic_verifier_pass_ms=duration_ms if generic_verifier_passed else 0,
        time_to_product_gate_pass_ms=duration_ms if product_gate_outcome.passed else 0,
        time_to_accepted_deliverable_ms=duration_ms if accepted else 0,
        wall_duration_ms=duration_ms,
        estimated_cost_usd=_non_negative_number_metric(runtime_worker_metrics, "provider_reported_cost_usd"),
        provider_reported_cost_usd=_non_negative_number_metric(runtime_worker_metrics, "provider_reported_cost_usd"),
        total_tokens=_non_negative_metric(runtime_worker_metrics, "total_tokens", "token_count"),
        input_tokens=_non_negative_metric(runtime_worker_metrics, "input_tokens"),
        output_tokens=_non_negative_metric(runtime_worker_metrics, "output_tokens"),
        cache_read_tokens=_non_negative_metric(runtime_worker_metrics, "cache_read_tokens"),
        cache_write_tokens=_non_negative_metric(runtime_worker_metrics, "cache_write_tokens"),
        tool_call_count=_non_negative_metric(runtime_worker_metrics, "tool_call_count"),
        repair_count=_repair_count(mission_result.metrics),
        user_turn_count=1,
        clarification_turn_count=len(product_compile_result.clarification_questions),
        privacy_violation_count=0,
        boundary_violation_count=0,
        defect_leakage_count=0,
        failure_taxonomy=failure_taxonomy,
        artifact_refs=artifact_refs,
        metric_events_ref=metric_events_ref,
    )


def _metric_events(
    *,
    run_id: str,
    task: BenchmarkTask,
    seed: int,
    refs: Mapping[str, str],
    summary: BenchmarkSummary,
    product_id: str,
) -> list[MetricEvent]:
    harness_event = MetricEvent(
        metric_id=f"BM-{task.task_id}-{BenchmarkMode.MISSIONFORGE_FULL_PRODUCT_FLOW.value}-seed-{seed:04d}",
        mission_run_id=run_id,
        namespace="missionforge.harness",
        source_ref=refs["summary"],
        run_ref=refs["trial"],
        metric_kind="summary",
        values=summary.metric_values(),
        trust_level=MetricTrustLevel.OPERATOR_DIAGNOSTIC.value,
        tags=["benchmark", BenchmarkMode.MISSIONFORGE_FULL_PRODUCT_FLOW.value],
    )
    integration_event = MetricEvent(
        metric_id=f"BM-{task.task_id}-{_safe_metric_fragment(product_id)}-product-seed-{seed:04d}",
        mission_run_id=run_id,
        namespace=f"integration.{_safe_metric_fragment(product_id)}",
        source_ref=refs["product_gate_outcome"],
        run_ref=refs["trial"],
        metric_kind="summary",
        values=safe_metric_values(
            {
                "product_compile_status": summary.product_compile_status,
                "product_compile_compiled": summary.product_compile_status == ProductCompileStatus.COMPILED.value,
                "product_clarification_count": summary.product_clarification_count,
                "product_gate_status": summary.product_gate_status,
                "product_gate_passed": (
                    summary.product_gate_status in PRODUCT_GATE_PASS_STATUSES
                    and summary.product_gate_blocking_finding_count == 0
                    and summary.product_acceptance_coverage_passed
                ),
                "product_acceptance_coverage_passed": summary.product_acceptance_coverage_passed,
                "product_gate_blocking_finding_count": summary.product_gate_blocking_finding_count,
            }
        ),
        trust_level=MetricTrustLevel.INTEGRATION_DIAGNOSTIC.value,
        tags=["benchmark", BenchmarkMode.MISSIONFORGE_FULL_PRODUCT_FLOW.value, product_id],
    )
    return [harness_event, integration_event]


def _full_result_payload(
    *,
    run_id: str,
    task: BenchmarkTask,
    seed: int,
    workspace_ref: str,
    duration_ms: int,
    session_ref: str,
    frontdesk_status: str,
    frontdesk_next_action: str,
    product_compile_result: ProductCompileResult,
    product_gate_outcome: ProductGateOutcome,
    mission_result: MissionResult,
    mission_ref: str,
    failure_stage: str,
    failure_error_type: str,
    failure_taxonomy: list[str],
    product_compile_result_ref: str,
    product_gate_outcome_ref: str,
) -> dict[str, Any]:
    payload = {
        "schema_version": FULL_PRODUCT_FLOW_RESULT_SCHEMA_VERSION,
        "benchmark_run_id": run_id,
        "task_id": task.task_id,
        "seed": seed,
        "workspace_ref": workspace_ref,
        "duration_ms": duration_ms,
        "frontdesk": {
            "session_ref": session_ref,
            "status": frontdesk_status,
            "next_action": frontdesk_next_action,
        },
        "product_compile_result_ref": product_compile_result_ref,
        "product_compile_status": product_compile_result.status.value,
        "product_request_ref": _prefixed_workspace_ref(workspace_ref, product_compile_result.product_request_ref),
        "product_contract_ref": _prefixed_workspace_ref(workspace_ref, product_compile_result.product_contract_ref),
        "mission_ir_ref": mission_ref,
        "product_gate_spec_ref": _prefixed_workspace_ref(workspace_ref, product_compile_result.product_gate_spec_ref),
        "product_gate_outcome_ref": product_gate_outcome_ref,
        "product_gate_status": product_gate_outcome.status,
        "product_gate_result_ref": _prefixed_workspace_ref(workspace_ref, product_gate_outcome.result_ref),
        "mission_result": mission_result.to_dict(),
        "failure_stage": failure_stage,
        "failure_error_type": failure_error_type,
        "failure_taxonomy": list(failure_taxonomy),
    }
    assert_refs_only_payload(payload, "full_product_flow_result")
    return payload


def _review_packet_payload(
    *,
    task: BenchmarkTask,
    seed: int,
    refs: Mapping[str, str],
    summary: BenchmarkSummary,
    session_ref: str,
    mission_ref: str,
    full_result_ref: str,
    product_compile_result: ProductCompileResult,
    product_gate_outcome: ProductGateOutcome,
    frontdesk_metrics: Mapping[str, Any],
) -> dict[str, Any]:
    payload = {
        "schema_version": "missionforge.benchmark_review_packet.v1",
        "task_id": task.task_id,
        "seed": seed,
        "mode": BenchmarkMode.MISSIONFORGE_FULL_PRODUCT_FLOW.value,
        "artifact_refs": list(summary.artifact_refs),
        "summary_ref": refs["summary"],
        "metric_events_ref": refs["metric_events"],
        "full_product_flow_result_ref": full_result_ref,
        "frontdesk_session_ref": session_ref,
        "frontdesk_node_execution_refs": [
            _prefixed_workspace_ref(refs["workspace"], ref)
            for ref in frontdesk_metrics.get("frontdesk_node_execution_refs", [])
        ],
        "product_compile_result_ref": refs["product_compile_result"],
        "product_request_ref": _prefixed_workspace_ref(refs["workspace"], product_compile_result.product_request_ref),
        "product_contract_ref": _prefixed_workspace_ref(refs["workspace"], product_compile_result.product_contract_ref),
        "mission_ir_ref": mission_ref,
        "product_gate_spec_ref": _prefixed_workspace_ref(refs["workspace"], product_compile_result.product_gate_spec_ref),
        "product_gate_outcome_ref": refs["product_gate_outcome"],
        "product_gate_result_ref": _prefixed_workspace_ref(refs["workspace"], product_gate_outcome.result_ref),
        "product_gate_evidence_refs": [
            _prefixed_workspace_ref(refs["workspace"], ref) for ref in product_gate_outcome.evidence_refs
        ],
        "accepted": summary.accepted,
        "generic_verifier_passed": summary.generic_verifier_passed,
        "product_gate_status": summary.product_gate_status,
        "product_acceptance_coverage_passed": summary.product_acceptance_coverage_passed,
        "failure_taxonomy": list(summary.failure_taxonomy),
    }
    assert_refs_only_payload(payload, "full_product_flow_review_packet")
    return payload


def _frontdesk_metrics(*, flow_workspace: Path, session_id: str) -> dict[str, Any]:
    store = JsonWorkspaceStore(flow_workspace)
    execution_refs: list[str] = []
    completed = 0
    for node_name in ("need_griller", "solution_architect", "intent_bundle_author", "mission_ir_mapper"):
        ref = frontdesk_pi_node_execution_ref(session_id=session_id, node_name=node_name)
        if not store.exists(ref):
            continue
        record = FrontDeskPiNodeExecutionRecord.from_dict(store.read_json(ref))
        execution_refs.append(ref)
        if record.status in {"completed", "success", "succeeded"}:
            completed += 1
    return {
        "frontdesk_node_count": len(execution_refs),
        "frontdesk_worker_call_count": len(execution_refs),
        "frontdesk_completed_node_count": completed,
        "frontdesk_node_execution_refs": execution_refs,
    }


def _intent_bundle_metrics(flow_workspace: Path) -> dict[str, Any]:
    store = JsonWorkspaceStore(flow_workspace)
    if not store.exists("frontdesk/intent_bundle.json"):
        return {
            "frontdesk_missing_slot_count": 0,
            "frontdesk_slot_conflict_count": 0,
            "intent_bundle_ready": False,
        }
    bundle = FrontDeskIntentBundle.from_dict(store.read_json("frontdesk/intent_bundle.json"))
    return {
        "frontdesk_missing_slot_count": len(bundle.missing_blocking_slots),
        "frontdesk_slot_conflict_count": sum(1 for risk in bundle.risk_flags if "conflict" in risk.risk_id.lower()),
        "intent_bundle_ready": bundle.readiness == IntentBundleReadiness.READY_FOR_PRODUCT_COMPILE,
    }


def _failure_taxonomy(
    *,
    product_compile_result: ProductCompileResult,
    mission_result: MissionResult,
    product_gate_outcome: ProductGateOutcome,
    failure_stage: str,
    failure_error_type: str,
) -> list[str]:
    failures: list[str] = []
    if failure_stage:
        if failure_stage.startswith("frontdesk"):
            failures.append("frontdesk_missing_llm_artifact" if failure_error_type == "ContractValidationError" else "frontdesk_semantic_gap")
        elif failure_stage == "product_compile":
            failures.append("product_compile_failed_closed")
        elif failure_stage == "runtime":
            failures.append("runtime_worker_failed")
        elif failure_stage == "product_gate":
            failures.append("product_gate_failed")
        else:
            failures.append("task_fixture_invalid")
    if product_compile_result.status == ProductCompileStatus.NEEDS_CLARIFICATION:
        failures.append("product_compile_needs_clarification")
    elif product_compile_result.status == ProductCompileStatus.FAILED_CLOSED:
        failures.append("product_compile_failed_closed")
    elif product_compile_result.status not in {ProductCompileStatus.COMPILED}:
        failures.append(f"product_compile_{product_compile_result.status.value}")
    if product_compile_result.status == ProductCompileStatus.COMPILED and mission_result.status != VerificationStatus.COMPLETED_VERIFIED.value:
        failures.append("runtime_verifier_failed")
    if product_compile_result.status == ProductCompileStatus.COMPILED and not product_gate_outcome.passed:
        failures.append("product_gate_failed" if product_gate_outcome.status != "unsupported" else "product_gate_unsupported")
    if product_gate_outcome.outcome_category == "coverage_miss" or not product_gate_outcome.product_acceptance_coverage_passed:
        if product_compile_result.status == ProductCompileStatus.COMPILED and product_gate_outcome.status != "unsupported":
            failures.append("product_acceptance_coverage_miss")
    return sorted(set(failures))


def _failed_compile_result(*, product_id: str, stage: str) -> ProductCompileResult:
    return ProductCompileResult(
        product_id=product_id,
        status=ProductCompileStatus.FAILED_CLOSED,
        intent_bundle_ref="frontdesk/intent_bundle.json",
        reason=f"full product flow stopped during {stage}",
    )


def _default_product_gate_outcome(*, product_id: str, status: str, outcome_category: str) -> ProductGateOutcome:
    return ProductGateOutcome(
        product_id=product_id,
        status=status,
        product_acceptance_coverage_passed=False,
        blocking_finding_count=0,
        outcome_category=outcome_category,
    )


def _synthetic_mission_result(*, mission_id: str, status: str, failure_metric: str) -> MissionResult:
    return MissionResult(
        mission_id=mission_id,
        status=status,
        evidence_refs=[],
        artifact_refs=[],
        failed_constraint_ids=[],
        metrics={"failure_stage": failure_metric},
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


def _product_id_for(integration: ProductIntegration) -> str:
    product_id = getattr(integration, "product_id", "")
    if isinstance(product_id, str) and product_id.strip():
        return product_id.strip()
    return "product"


def _full_product_flow_refs(*, run_id: str, task_id: str, seed: int) -> dict[str, str]:
    if seed < 0:
        raise ContractValidationError("full_product_flow.seed must be >= 0")
    root = f"benchmarks/runs/{run_id}/trials/{task_id}/{BenchmarkMode.MISSIONFORGE_FULL_PRODUCT_FLOW.value}/seed-{seed}"
    return {
        "root": root,
        "workspace": f"{root}/workspace",
        "full_result": f"{root}/full_product_flow_result.json",
        "product_compile_result": f"{root}/product_compile_result.json",
        "product_gate_outcome": f"{root}/product_gate_outcome.json",
        "trial": f"{root}/trial.json",
        "summary": f"{root}/summary.json",
        "metric_events": f"{root}/metric_events.jsonl",
        "review_packet": f"{root}/review_packet.json",
    }


def _prefixed_workspace_ref(workspace_ref: str, ref: str) -> str:
    if not ref:
        return ""
    return _join_ref(workspace_ref, ref)


def _join_ref(prefix: str, ref: str) -> str:
    safe_prefix = validate_ref(prefix, "ref_prefix")
    safe_ref = validate_ref(ref, "ref")
    return f"{safe_prefix.rstrip('/')}/{safe_ref.lstrip('/')}" if safe_prefix else safe_ref


def _resolve_workspace_ref(root: Path, ref: str) -> Path:
    safe_ref = validate_ref(ref, "full_product_flow.ref")
    path = (root / safe_ref).resolve()
    if root not in path.parents and path != root:
        raise ContractValidationError("full product flow benchmark ref escapes workspace")
    return path


def _require_id(value: Any, field_name: str) -> str:
    text = require_non_empty_str(value, field_name)
    if "/" in text or "\\" in text or text in {".", ".."}:
        raise ContractValidationError(f"{field_name} must be a safe id, not a path")
    validate_ref(text, field_name)
    return text


def _require_bool(value: Any, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise ContractValidationError(f"{field_name} must be a boolean")
    return value


def _require_ref_list(value: Any, field_name: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
        raise ContractValidationError(f"{field_name} must be a list of non-empty strings")
    result = [item.strip() for item in value]
    for ref in result:
        validate_ref(ref, f"{field_name}[]")
    return result


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


def _dedupe_refs(refs: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for ref in refs:
        safe = validate_ref(ref, "full_product_flow.refs[]")
        if safe not in seen:
            result.append(safe)
            seen.add(safe)
    return result


def _safe_metric_fragment(value: str) -> str:
    fragment = re.sub(r"[^a-z0-9_]+", "_", value.lower()).strip("_")
    return fragment or "product"


__all__ = [
    "FULL_PRODUCT_FLOW_RESULT_SCHEMA_VERSION",
    "PRODUCT_GATE_OUTCOME_SCHEMA_VERSION",
    "FullProductFlowConfig",
    "FullProductFlowTrialRecord",
    "MissionForgeFullProductFlowBenchmarkRunner",
    "ProductGateOutcome",
    "ProductGateRunner",
]
