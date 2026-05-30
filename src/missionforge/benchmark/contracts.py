"""Refs-first benchmark contracts for MissionForge value validation."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Mapping, Self

from ..contracts import (
    ContractValidationError,
    assert_refs_only_payload,
    ensure_json_value,
    require_enum,
    require_int_at_least,
    require_mapping,
    require_non_empty_str,
    require_str_list,
    validate_ref,
)
from ..metrics import safe_metric_values


BENCHMARK_BUDGET_SCHEMA_VERSION = "missionforge.benchmark_budget.v1"
BENCHMARK_TASK_SCHEMA_VERSION = "missionforge.benchmark_task.v1"
BENCHMARK_TRIAL_SCHEMA_VERSION = "missionforge.benchmark_trial.v1"
BENCHMARK_SUMMARY_SCHEMA_VERSION = "missionforge.benchmark_summary.v1"
BENCHMARK_AGGREGATE_SCHEMA_VERSION = "missionforge.benchmark_aggregate.v1"
OFFLINE_TRIAL_OUTCOME_SCHEMA_VERSION = "missionforge.offline_trial_outcome.v1"
BENCHMARK_COST_SOURCES = {"unavailable", "provider_reported", "pricing_table"}


class BenchmarkMode(StrEnum):
    """Comparable benchmark execution modes."""

    DIRECT_PIWORKER_CHAT = "direct_piworker_chat"
    MISSIONFORGE_RUNTIME_ONLY = "missionforge_runtime_only"
    MISSIONFORGE_FULL_PRODUCT_FLOW = "missionforge_full_product_flow"
    OFFLINE_HARNESS = "offline_harness"


class BenchmarkStatus(StrEnum):
    """Canonical trial status."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    ACCEPTED = "accepted"
    FAILED = "failed"
    NON_COMPARABLE = "non_comparable"


@dataclass(frozen=True)
class BenchmarkBudget:
    """Bounded resources for a benchmark task."""

    max_wall_minutes: int
    max_total_tokens: int
    max_cost_usd: float
    max_user_turns: int
    schema_version: str = BENCHMARK_BUDGET_SCHEMA_VERSION

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Self:
        data = _strict_mapping(
            payload,
            "benchmark_budget",
            {"schema_version", "max_wall_minutes", "max_total_tokens", "max_cost_usd", "max_user_turns"},
        )
        item = cls(
            max_wall_minutes=require_int_at_least(data.get("max_wall_minutes"), "benchmark_budget.max_wall_minutes", 1),
            max_total_tokens=require_int_at_least(data.get("max_total_tokens"), "benchmark_budget.max_total_tokens", 1),
            max_cost_usd=_require_number_at_least(data.get("max_cost_usd"), "benchmark_budget.max_cost_usd", 0.0),
            max_user_turns=require_int_at_least(data.get("max_user_turns"), "benchmark_budget.max_user_turns", 0),
            schema_version=require_non_empty_str(
                data.get("schema_version", BENCHMARK_BUDGET_SCHEMA_VERSION),
                "benchmark_budget.schema_version",
            ),
        )
        item.validate()
        return item

    def validate(self) -> None:
        if self.schema_version != BENCHMARK_BUDGET_SCHEMA_VERSION:
            raise ContractValidationError("benchmark_budget.schema_version is unsupported")
        require_int_at_least(self.max_wall_minutes, "benchmark_budget.max_wall_minutes", 1)
        require_int_at_least(self.max_total_tokens, "benchmark_budget.max_total_tokens", 1)
        _require_number_at_least(self.max_cost_usd, "benchmark_budget.max_cost_usd", 0.0)
        require_int_at_least(self.max_user_turns, "benchmark_budget.max_user_turns", 0)
        assert_refs_only_payload(self.to_dict_without_validation(), "benchmark_budget")

    def to_dict_without_validation(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "max_wall_minutes": self.max_wall_minutes,
            "max_total_tokens": self.max_total_tokens,
            "max_cost_usd": self.max_cost_usd,
            "max_user_turns": self.max_user_turns,
        }

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return self.to_dict_without_validation()


@dataclass(frozen=True)
class BenchmarkTask:
    """One task fixture used by comparable benchmark modes."""

    task_id: str
    task_family: str
    difficulty: str
    initial_user_text_ref: str
    budget: BenchmarkBudget
    expected_output_refs: list[str] = field(default_factory=list)
    allowed_source_refs: list[str] = field(default_factory=list)
    acceptance_refs: list[str] = field(default_factory=list)
    schema_version: str = BENCHMARK_TASK_SCHEMA_VERSION

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Self:
        data = _strict_mapping(
            payload,
            "benchmark_task",
            {
                "schema_version",
                "task_id",
                "task_family",
                "difficulty",
                "initial_user_text_ref",
                "allowed_source_refs",
                "expected_output_refs",
                "budget",
                "acceptance_refs",
            },
        )
        task = cls(
            task_id=_require_id(data.get("task_id"), "benchmark_task.task_id"),
            task_family=require_non_empty_str(data.get("task_family"), "benchmark_task.task_family"),
            difficulty=require_non_empty_str(data.get("difficulty"), "benchmark_task.difficulty"),
            initial_user_text_ref=validate_ref(
                data.get("initial_user_text_ref"),
                "benchmark_task.initial_user_text_ref",
            ),
            allowed_source_refs=require_str_list(
                data.get("allowed_source_refs", []),
                "benchmark_task.allowed_source_refs",
            ),
            expected_output_refs=require_str_list(
                data.get("expected_output_refs", []),
                "benchmark_task.expected_output_refs",
            ),
            budget=BenchmarkBudget.from_dict(require_mapping(data.get("budget"), "benchmark_task.budget")),
            acceptance_refs=require_str_list(data.get("acceptance_refs", []), "benchmark_task.acceptance_refs"),
            schema_version=require_non_empty_str(
                data.get("schema_version", BENCHMARK_TASK_SCHEMA_VERSION),
                "benchmark_task.schema_version",
            ),
        )
        task.validate()
        return task

    def validate(self) -> None:
        if self.schema_version != BENCHMARK_TASK_SCHEMA_VERSION:
            raise ContractValidationError("benchmark_task.schema_version is unsupported")
        _require_id(self.task_id, "benchmark_task.task_id")
        require_non_empty_str(self.task_family, "benchmark_task.task_family")
        require_non_empty_str(self.difficulty, "benchmark_task.difficulty")
        validate_ref(self.initial_user_text_ref, "benchmark_task.initial_user_text_ref")
        _validate_ref_list(self.allowed_source_refs, "benchmark_task.allowed_source_refs")
        _validate_ref_list(self.expected_output_refs, "benchmark_task.expected_output_refs")
        _validate_ref_list(self.acceptance_refs, "benchmark_task.acceptance_refs")
        self.budget.validate()
        assert_refs_only_payload(self.to_dict_without_validation(), "benchmark_task")

    def to_dict_without_validation(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "task_id": self.task_id,
            "task_family": self.task_family,
            "difficulty": self.difficulty,
            "initial_user_text_ref": self.initial_user_text_ref,
            "allowed_source_refs": list(self.allowed_source_refs),
            "expected_output_refs": list(self.expected_output_refs),
            "budget": self.budget.to_dict(),
            "acceptance_refs": list(self.acceptance_refs),
        }

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return self.to_dict_without_validation()


@dataclass(frozen=True)
class BenchmarkSummary:
    """Safe comparable metrics for one trial."""

    task_id: str
    mode: BenchmarkMode
    seed: int
    accepted: bool
    status: BenchmarkStatus = BenchmarkStatus.COMPLETED
    comparable: bool = True
    generic_verifier_passed: bool = False
    hidden_acceptance_passed: bool = False
    product_gate_status: str = ""
    frontdesk_node_count: int = 0
    frontdesk_worker_call_count: int = 0
    frontdesk_missing_slot_count: int = 0
    frontdesk_slot_conflict_count: int = 0
    intent_bundle_ready: bool = False
    product_compile_status: str = ""
    product_clarification_count: int = 0
    product_acceptance_coverage_passed: bool = False
    product_gate_blocking_finding_count: int = 0
    review_score: float = 0.0
    time_to_first_artifact_ms: int = 0
    time_to_generic_verifier_pass_ms: int = 0
    time_to_product_gate_pass_ms: int = 0
    time_to_accepted_deliverable_ms: int = 0
    wall_duration_ms: int = 0
    estimated_cost_usd: float = 0.0
    provider_reported_cost_usd: float = 0.0
    cost_source: str = "unavailable"
    pricing_table_id: str = ""
    total_tokens: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    tool_call_count: int = 0
    repair_count: int = 0
    user_turn_count: int = 0
    clarification_turn_count: int = 0
    privacy_violation_count: int = 0
    boundary_violation_count: int = 0
    defect_leakage_count: int = 0
    failure_taxonomy: list[str] = field(default_factory=list)
    artifact_refs: list[str] = field(default_factory=list)
    metric_events_ref: str = ""
    schema_version: str = BENCHMARK_SUMMARY_SCHEMA_VERSION

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Self:
        data = _strict_mapping(payload, "benchmark_summary", _SUMMARY_FIELDS)
        summary = cls(
            task_id=_require_id(data.get("task_id"), "benchmark_summary.task_id"),
            mode=require_enum(data.get("mode"), BenchmarkMode, "benchmark_summary.mode"),
            seed=require_int_at_least(data.get("seed"), "benchmark_summary.seed", 0),
            accepted=_require_bool(data.get("accepted"), "benchmark_summary.accepted"),
            status=require_enum(data.get("status", BenchmarkStatus.COMPLETED.value), BenchmarkStatus, "benchmark_summary.status"),
            comparable=_require_bool(data.get("comparable", True), "benchmark_summary.comparable"),
            generic_verifier_passed=_require_bool(
                data.get("generic_verifier_passed", False),
                "benchmark_summary.generic_verifier_passed",
            ),
            hidden_acceptance_passed=_require_bool(
                data.get("hidden_acceptance_passed", False),
                "benchmark_summary.hidden_acceptance_passed",
            ),
            product_gate_status=str(data.get("product_gate_status", "")),
            frontdesk_node_count=require_int_at_least(
                data.get("frontdesk_node_count", 0),
                "benchmark_summary.frontdesk_node_count",
                0,
            ),
            frontdesk_worker_call_count=require_int_at_least(
                data.get("frontdesk_worker_call_count", 0),
                "benchmark_summary.frontdesk_worker_call_count",
                0,
            ),
            frontdesk_missing_slot_count=require_int_at_least(
                data.get("frontdesk_missing_slot_count", 0),
                "benchmark_summary.frontdesk_missing_slot_count",
                0,
            ),
            frontdesk_slot_conflict_count=require_int_at_least(
                data.get("frontdesk_slot_conflict_count", 0),
                "benchmark_summary.frontdesk_slot_conflict_count",
                0,
            ),
            intent_bundle_ready=_require_bool(data.get("intent_bundle_ready", False), "benchmark_summary.intent_bundle_ready"),
            product_compile_status=str(data.get("product_compile_status", "")),
            product_clarification_count=require_int_at_least(
                data.get("product_clarification_count", 0),
                "benchmark_summary.product_clarification_count",
                0,
            ),
            product_acceptance_coverage_passed=_require_bool(
                data.get("product_acceptance_coverage_passed", False),
                "benchmark_summary.product_acceptance_coverage_passed",
            ),
            product_gate_blocking_finding_count=require_int_at_least(
                data.get("product_gate_blocking_finding_count", 0),
                "benchmark_summary.product_gate_blocking_finding_count",
                0,
            ),
            review_score=_require_number_at_least(data.get("review_score", 0.0), "benchmark_summary.review_score", 0.0),
            time_to_first_artifact_ms=require_int_at_least(
                data.get("time_to_first_artifact_ms", 0),
                "benchmark_summary.time_to_first_artifact_ms",
                0,
            ),
            time_to_generic_verifier_pass_ms=require_int_at_least(
                data.get("time_to_generic_verifier_pass_ms", 0),
                "benchmark_summary.time_to_generic_verifier_pass_ms",
                0,
            ),
            time_to_product_gate_pass_ms=require_int_at_least(
                data.get("time_to_product_gate_pass_ms", 0),
                "benchmark_summary.time_to_product_gate_pass_ms",
                0,
            ),
            time_to_accepted_deliverable_ms=require_int_at_least(
                data.get("time_to_accepted_deliverable_ms", 0),
                "benchmark_summary.time_to_accepted_deliverable_ms",
                0,
            ),
            wall_duration_ms=require_int_at_least(data.get("wall_duration_ms", 0), "benchmark_summary.wall_duration_ms", 0),
            estimated_cost_usd=_require_number_at_least(
                data.get("estimated_cost_usd", 0.0),
                "benchmark_summary.estimated_cost_usd",
                0.0,
            ),
            provider_reported_cost_usd=_require_number_at_least(
                data.get("provider_reported_cost_usd", 0.0),
                "benchmark_summary.provider_reported_cost_usd",
                0.0,
            ),
            cost_source=_require_cost_source(data.get("cost_source", "unavailable"), "benchmark_summary.cost_source"),
            pricing_table_id=_optional_id(data.get("pricing_table_id", ""), "benchmark_summary.pricing_table_id"),
            total_tokens=require_int_at_least(data.get("total_tokens", 0), "benchmark_summary.total_tokens", 0),
            input_tokens=require_int_at_least(data.get("input_tokens", 0), "benchmark_summary.input_tokens", 0),
            output_tokens=require_int_at_least(data.get("output_tokens", 0), "benchmark_summary.output_tokens", 0),
            cache_read_tokens=require_int_at_least(
                data.get("cache_read_tokens", 0),
                "benchmark_summary.cache_read_tokens",
                0,
            ),
            cache_write_tokens=require_int_at_least(
                data.get("cache_write_tokens", 0),
                "benchmark_summary.cache_write_tokens",
                0,
            ),
            tool_call_count=require_int_at_least(data.get("tool_call_count", 0), "benchmark_summary.tool_call_count", 0),
            repair_count=require_int_at_least(data.get("repair_count", 0), "benchmark_summary.repair_count", 0),
            user_turn_count=require_int_at_least(data.get("user_turn_count", 0), "benchmark_summary.user_turn_count", 0),
            clarification_turn_count=require_int_at_least(
                data.get("clarification_turn_count", 0),
                "benchmark_summary.clarification_turn_count",
                0,
            ),
            privacy_violation_count=require_int_at_least(
                data.get("privacy_violation_count", 0),
                "benchmark_summary.privacy_violation_count",
                0,
            ),
            boundary_violation_count=require_int_at_least(
                data.get("boundary_violation_count", 0),
                "benchmark_summary.boundary_violation_count",
                0,
            ),
            defect_leakage_count=require_int_at_least(
                data.get("defect_leakage_count", 0),
                "benchmark_summary.defect_leakage_count",
                0,
            ),
            failure_taxonomy=require_str_list(data.get("failure_taxonomy", []), "benchmark_summary.failure_taxonomy"),
            artifact_refs=require_str_list(data.get("artifact_refs", []), "benchmark_summary.artifact_refs"),
            metric_events_ref=str(data.get("metric_events_ref", "")),
            schema_version=require_non_empty_str(
                data.get("schema_version", BENCHMARK_SUMMARY_SCHEMA_VERSION),
                "benchmark_summary.schema_version",
            ),
        )
        summary.validate()
        return summary

    def validate(self) -> None:
        if self.schema_version != BENCHMARK_SUMMARY_SCHEMA_VERSION:
            raise ContractValidationError("benchmark_summary.schema_version is unsupported")
        _require_id(self.task_id, "benchmark_summary.task_id")
        require_enum(self.mode, BenchmarkMode, "benchmark_summary.mode")
        require_enum(self.status, BenchmarkStatus, "benchmark_summary.status")
        require_int_at_least(self.seed, "benchmark_summary.seed", 0)
        _require_bool(self.accepted, "benchmark_summary.accepted")
        _require_bool(self.comparable, "benchmark_summary.comparable")
        _require_bool(self.intent_bundle_ready, "benchmark_summary.intent_bundle_ready")
        _require_bool(
            self.product_acceptance_coverage_passed,
            "benchmark_summary.product_acceptance_coverage_passed",
        )
        _validate_ref_list(self.artifact_refs, "benchmark_summary.artifact_refs")
        if self.metric_events_ref:
            validate_ref(self.metric_events_ref, "benchmark_summary.metric_events_ref")
        for name in _NON_NEGATIVE_INT_SUMMARY_FIELDS:
            require_int_at_least(getattr(self, name), f"benchmark_summary.{name}", 0)
        for name in _NON_NEGATIVE_FLOAT_SUMMARY_FIELDS:
            _require_number_at_least(getattr(self, name), f"benchmark_summary.{name}", 0.0)
        _require_cost_source(self.cost_source, "benchmark_summary.cost_source")
        if self.pricing_table_id:
            _require_id(self.pricing_table_id, "benchmark_summary.pricing_table_id")
        if self.cost_source == "pricing_table" and not self.pricing_table_id:
            raise ContractValidationError("benchmark_summary.pricing_table_id is required when cost_source is pricing_table")
        if self.cost_source != "pricing_table" and self.pricing_table_id:
            raise ContractValidationError("benchmark_summary.pricing_table_id is only allowed when cost_source is pricing_table")
        require_str_list(self.failure_taxonomy, "benchmark_summary.failure_taxonomy")
        assert_refs_only_payload(self.to_dict_without_validation(), "benchmark_summary")

    def metric_values(self) -> dict[str, Any]:
        """Return shallow scalar values suitable for MetricEvent."""

        return safe_metric_values(
            {
                "accepted": self.accepted,
                "comparable": self.comparable,
                "generic_verifier_passed": self.generic_verifier_passed,
                "hidden_acceptance_passed": self.hidden_acceptance_passed,
                "frontdesk_node_count": self.frontdesk_node_count,
                "frontdesk_worker_call_count": self.frontdesk_worker_call_count,
                "frontdesk_missing_slot_count": self.frontdesk_missing_slot_count,
                "frontdesk_slot_conflict_count": self.frontdesk_slot_conflict_count,
                "intent_bundle_ready": self.intent_bundle_ready,
                "product_compile_status": self.product_compile_status,
                "product_clarification_count": self.product_clarification_count,
                "product_acceptance_coverage_passed": self.product_acceptance_coverage_passed,
                "product_gate_blocking_finding_count": self.product_gate_blocking_finding_count,
                "review_score": self.review_score,
                "time_to_first_artifact_ms": self.time_to_first_artifact_ms,
                "time_to_generic_verifier_pass_ms": self.time_to_generic_verifier_pass_ms,
                "time_to_product_gate_pass_ms": self.time_to_product_gate_pass_ms,
                "time_to_accepted_deliverable_ms": self.time_to_accepted_deliverable_ms,
                "wall_duration_ms": self.wall_duration_ms,
                "estimated_cost_usd": self.estimated_cost_usd,
                "provider_reported_cost_usd": self.provider_reported_cost_usd,
                "cost_source": self.cost_source,
                "pricing_table_id": self.pricing_table_id,
                "total_tokens": self.total_tokens,
                "input_tokens": self.input_tokens,
                "output_tokens": self.output_tokens,
                "cache_read_tokens": self.cache_read_tokens,
                "cache_write_tokens": self.cache_write_tokens,
                "tool_call_count": self.tool_call_count,
                "repair_count": self.repair_count,
                "user_turn_count": self.user_turn_count,
                "clarification_turn_count": self.clarification_turn_count,
                "privacy_violation_count": self.privacy_violation_count,
                "boundary_violation_count": self.boundary_violation_count,
                "defect_leakage_count": self.defect_leakage_count,
                "failure_taxonomy_count": len(self.failure_taxonomy),
            }
        )

    def to_dict_without_validation(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "task_id": self.task_id,
            "mode": self.mode.value,
            "seed": self.seed,
            "accepted": self.accepted,
            "status": self.status.value,
            "comparable": self.comparable,
            "generic_verifier_passed": self.generic_verifier_passed,
            "hidden_acceptance_passed": self.hidden_acceptance_passed,
            "product_gate_status": self.product_gate_status,
            "frontdesk_node_count": self.frontdesk_node_count,
            "frontdesk_worker_call_count": self.frontdesk_worker_call_count,
            "frontdesk_missing_slot_count": self.frontdesk_missing_slot_count,
            "frontdesk_slot_conflict_count": self.frontdesk_slot_conflict_count,
            "intent_bundle_ready": self.intent_bundle_ready,
            "product_compile_status": self.product_compile_status,
            "product_clarification_count": self.product_clarification_count,
            "product_acceptance_coverage_passed": self.product_acceptance_coverage_passed,
            "product_gate_blocking_finding_count": self.product_gate_blocking_finding_count,
            "review_score": self.review_score,
            "time_to_first_artifact_ms": self.time_to_first_artifact_ms,
            "time_to_generic_verifier_pass_ms": self.time_to_generic_verifier_pass_ms,
            "time_to_product_gate_pass_ms": self.time_to_product_gate_pass_ms,
            "time_to_accepted_deliverable_ms": self.time_to_accepted_deliverable_ms,
            "wall_duration_ms": self.wall_duration_ms,
            "estimated_cost_usd": self.estimated_cost_usd,
            "provider_reported_cost_usd": self.provider_reported_cost_usd,
            "cost_source": self.cost_source,
            "pricing_table_id": self.pricing_table_id,
            "total_tokens": self.total_tokens,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cache_read_tokens": self.cache_read_tokens,
            "cache_write_tokens": self.cache_write_tokens,
            "tool_call_count": self.tool_call_count,
            "repair_count": self.repair_count,
            "user_turn_count": self.user_turn_count,
            "clarification_turn_count": self.clarification_turn_count,
            "privacy_violation_count": self.privacy_violation_count,
            "boundary_violation_count": self.boundary_violation_count,
            "defect_leakage_count": self.defect_leakage_count,
            "failure_taxonomy": list(self.failure_taxonomy),
            "artifact_refs": list(self.artifact_refs),
            "metric_events_ref": self.metric_events_ref,
        }

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return self.to_dict_without_validation()


@dataclass(frozen=True)
class BenchmarkTrial:
    """One recorded execution attempt for a task/mode/seed."""

    benchmark_run_id: str
    task_id: str
    mode: BenchmarkMode
    seed: int
    workspace_ref: str
    started_at: str
    completed_at: str
    status: BenchmarkStatus
    artifact_refs: list[str] = field(default_factory=list)
    metric_events_ref: str = ""
    summary_ref: str = ""
    review_packet_ref: str = ""
    schema_version: str = BENCHMARK_TRIAL_SCHEMA_VERSION

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Self:
        data = _strict_mapping(
            payload,
            "benchmark_trial",
            {
                "schema_version",
                "benchmark_run_id",
                "task_id",
                "mode",
                "seed",
                "workspace_ref",
                "started_at",
                "completed_at",
                "status",
                "artifact_refs",
                "metric_events_ref",
                "summary_ref",
                "review_packet_ref",
            },
        )
        trial = cls(
            benchmark_run_id=_require_id(data.get("benchmark_run_id"), "benchmark_trial.benchmark_run_id"),
            task_id=_require_id(data.get("task_id"), "benchmark_trial.task_id"),
            mode=require_enum(data.get("mode"), BenchmarkMode, "benchmark_trial.mode"),
            seed=require_int_at_least(data.get("seed"), "benchmark_trial.seed", 0),
            workspace_ref=validate_ref(data.get("workspace_ref"), "benchmark_trial.workspace_ref"),
            started_at=require_non_empty_str(data.get("started_at"), "benchmark_trial.started_at"),
            completed_at=require_non_empty_str(data.get("completed_at"), "benchmark_trial.completed_at"),
            status=require_enum(data.get("status"), BenchmarkStatus, "benchmark_trial.status"),
            artifact_refs=require_str_list(data.get("artifact_refs", []), "benchmark_trial.artifact_refs"),
            metric_events_ref=str(data.get("metric_events_ref", "")),
            summary_ref=str(data.get("summary_ref", "")),
            review_packet_ref=str(data.get("review_packet_ref", "")),
            schema_version=require_non_empty_str(
                data.get("schema_version", BENCHMARK_TRIAL_SCHEMA_VERSION),
                "benchmark_trial.schema_version",
            ),
        )
        trial.validate()
        return trial

    def validate(self) -> None:
        if self.schema_version != BENCHMARK_TRIAL_SCHEMA_VERSION:
            raise ContractValidationError("benchmark_trial.schema_version is unsupported")
        _require_id(self.benchmark_run_id, "benchmark_trial.benchmark_run_id")
        _require_id(self.task_id, "benchmark_trial.task_id")
        require_enum(self.mode, BenchmarkMode, "benchmark_trial.mode")
        require_enum(self.status, BenchmarkStatus, "benchmark_trial.status")
        require_int_at_least(self.seed, "benchmark_trial.seed", 0)
        validate_ref(self.workspace_ref, "benchmark_trial.workspace_ref")
        require_non_empty_str(self.started_at, "benchmark_trial.started_at")
        require_non_empty_str(self.completed_at, "benchmark_trial.completed_at")
        _validate_ref_list(self.artifact_refs, "benchmark_trial.artifact_refs")
        for name in ("metric_events_ref", "summary_ref", "review_packet_ref"):
            ref = getattr(self, name)
            if ref:
                validate_ref(ref, f"benchmark_trial.{name}")
        assert_refs_only_payload(self.to_dict_without_validation(), "benchmark_trial")

    def to_dict_without_validation(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "benchmark_run_id": self.benchmark_run_id,
            "task_id": self.task_id,
            "mode": self.mode.value,
            "seed": self.seed,
            "workspace_ref": self.workspace_ref,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "status": self.status.value,
            "artifact_refs": list(self.artifact_refs),
            "metric_events_ref": self.metric_events_ref,
            "summary_ref": self.summary_ref,
            "review_packet_ref": self.review_packet_ref,
        }

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return self.to_dict_without_validation()


@dataclass(frozen=True)
class OfflineTrialOutcome:
    """Deterministic offline outcome supplied to the VB1 harness."""

    accepted: bool
    status: BenchmarkStatus = BenchmarkStatus.COMPLETED
    comparable: bool = True
    artifact_refs: list[str] = field(default_factory=list)
    metric_values: dict[str, Any] = field(default_factory=dict)
    failure_taxonomy: list[str] = field(default_factory=list)
    product_gate_status: str = ""
    review_score: float = 0.0
    schema_version: str = OFFLINE_TRIAL_OUTCOME_SCHEMA_VERSION

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Self:
        data = _strict_mapping(
            payload,
            "offline_trial_outcome",
            {
                "schema_version",
                "accepted",
                "status",
                "comparable",
                "artifact_refs",
                "metric_values",
                "failure_taxonomy",
                "product_gate_status",
                "review_score",
            },
        )
        outcome = cls(
            accepted=_require_bool(data.get("accepted"), "offline_trial_outcome.accepted"),
            status=require_enum(data.get("status", BenchmarkStatus.COMPLETED.value), BenchmarkStatus, "offline_trial_outcome.status"),
            comparable=_require_bool(data.get("comparable", True), "offline_trial_outcome.comparable"),
            artifact_refs=require_str_list(data.get("artifact_refs", []), "offline_trial_outcome.artifact_refs"),
            metric_values=_strict_metric_values(data.get("metric_values", {}), "offline_trial_outcome.metric_values"),
            failure_taxonomy=require_str_list(data.get("failure_taxonomy", []), "offline_trial_outcome.failure_taxonomy"),
            product_gate_status=str(data.get("product_gate_status", "")),
            review_score=_require_number_at_least(data.get("review_score", 0.0), "offline_trial_outcome.review_score", 0.0),
            schema_version=require_non_empty_str(
                data.get("schema_version", OFFLINE_TRIAL_OUTCOME_SCHEMA_VERSION),
                "offline_trial_outcome.schema_version",
            ),
        )
        outcome.validate()
        return outcome

    def validate(self) -> None:
        if self.schema_version != OFFLINE_TRIAL_OUTCOME_SCHEMA_VERSION:
            raise ContractValidationError("offline_trial_outcome.schema_version is unsupported")
        _require_bool(self.accepted, "offline_trial_outcome.accepted")
        require_enum(self.status, BenchmarkStatus, "offline_trial_outcome.status")
        _require_bool(self.comparable, "offline_trial_outcome.comparable")
        _validate_ref_list(self.artifact_refs, "offline_trial_outcome.artifact_refs")
        _strict_metric_values(self.metric_values, "offline_trial_outcome.metric_values")
        require_str_list(self.failure_taxonomy, "offline_trial_outcome.failure_taxonomy")
        _require_number_at_least(self.review_score, "offline_trial_outcome.review_score", 0.0)
        assert_refs_only_payload(self.to_dict_without_validation(), "offline_trial_outcome")

    def to_dict_without_validation(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "accepted": self.accepted,
            "status": self.status.value,
            "comparable": self.comparable,
            "artifact_refs": list(self.artifact_refs),
            "metric_values": dict(self.metric_values),
            "failure_taxonomy": list(self.failure_taxonomy),
            "product_gate_status": self.product_gate_status,
            "review_score": self.review_score,
        }

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return self.to_dict_without_validation()


@dataclass(frozen=True)
class BenchmarkAggregate:
    """Deterministic aggregate over benchmark summaries."""

    benchmark_run_id: str
    summary_refs: list[str]
    mode_summaries: dict[str, dict[str, Any]]
    failure_taxonomy_counts: dict[str, int] = field(default_factory=dict)
    task_count: int = 0
    trial_count: int = 0
    accepted_count: int = 0
    comparable_trial_count: int = 0
    schema_version: str = BENCHMARK_AGGREGATE_SCHEMA_VERSION

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Self:
        data = _strict_mapping(
            payload,
            "benchmark_aggregate",
            {
                "schema_version",
                "benchmark_run_id",
                "summary_refs",
                "mode_summaries",
                "failure_taxonomy_counts",
                "task_count",
                "trial_count",
                "accepted_count",
                "comparable_trial_count",
            },
        )
        aggregate = cls(
            benchmark_run_id=_require_id(data.get("benchmark_run_id"), "benchmark_aggregate.benchmark_run_id"),
            summary_refs=require_str_list(data.get("summary_refs", []), "benchmark_aggregate.summary_refs"),
            mode_summaries={
                require_non_empty_str(key, "benchmark_aggregate.mode_summaries.key"): _strict_metric_values(
                    value,
                    f"benchmark_aggregate.mode_summaries.{key}",
                )
                for key, value in require_mapping(data.get("mode_summaries", {}), "benchmark_aggregate.mode_summaries").items()
            },
            failure_taxonomy_counts=_require_int_mapping(
                data.get("failure_taxonomy_counts", {}),
                "benchmark_aggregate.failure_taxonomy_counts",
            ),
            task_count=require_int_at_least(data.get("task_count", 0), "benchmark_aggregate.task_count", 0),
            trial_count=require_int_at_least(data.get("trial_count", 0), "benchmark_aggregate.trial_count", 0),
            accepted_count=require_int_at_least(data.get("accepted_count", 0), "benchmark_aggregate.accepted_count", 0),
            comparable_trial_count=require_int_at_least(
                data.get("comparable_trial_count", 0),
                "benchmark_aggregate.comparable_trial_count",
                0,
            ),
            schema_version=require_non_empty_str(
                data.get("schema_version", BENCHMARK_AGGREGATE_SCHEMA_VERSION),
                "benchmark_aggregate.schema_version",
            ),
        )
        aggregate.validate()
        return aggregate

    def validate(self) -> None:
        if self.schema_version != BENCHMARK_AGGREGATE_SCHEMA_VERSION:
            raise ContractValidationError("benchmark_aggregate.schema_version is unsupported")
        _require_id(self.benchmark_run_id, "benchmark_aggregate.benchmark_run_id")
        _validate_ref_list(self.summary_refs, "benchmark_aggregate.summary_refs")
        for mode, values in self.mode_summaries.items():
            require_non_empty_str(mode, "benchmark_aggregate.mode_summaries.key")
            _strict_metric_values(values, f"benchmark_aggregate.mode_summaries.{mode}")
        for key, count in self.failure_taxonomy_counts.items():
            require_non_empty_str(key, "benchmark_aggregate.failure_taxonomy_counts.key")
            require_int_at_least(count, f"benchmark_aggregate.failure_taxonomy_counts.{key}", 0)
        require_int_at_least(self.task_count, "benchmark_aggregate.task_count", 0)
        require_int_at_least(self.trial_count, "benchmark_aggregate.trial_count", 0)
        require_int_at_least(self.accepted_count, "benchmark_aggregate.accepted_count", 0)
        require_int_at_least(self.comparable_trial_count, "benchmark_aggregate.comparable_trial_count", 0)
        assert_refs_only_payload(self.to_dict_without_validation(), "benchmark_aggregate")

    def to_dict_without_validation(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "benchmark_run_id": self.benchmark_run_id,
            "summary_refs": list(self.summary_refs),
            "mode_summaries": {
                mode: dict(values)
                for mode, values in sorted(self.mode_summaries.items())
            },
            "failure_taxonomy_counts": dict(sorted(self.failure_taxonomy_counts.items())),
            "task_count": self.task_count,
            "trial_count": self.trial_count,
            "accepted_count": self.accepted_count,
            "comparable_trial_count": self.comparable_trial_count,
        }

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return self.to_dict_without_validation()


_SUMMARY_FIELDS = {
    "schema_version",
    "task_id",
    "mode",
    "seed",
    "accepted",
    "status",
    "comparable",
    "generic_verifier_passed",
    "hidden_acceptance_passed",
    "product_gate_status",
    "frontdesk_node_count",
    "frontdesk_worker_call_count",
    "frontdesk_missing_slot_count",
    "frontdesk_slot_conflict_count",
    "intent_bundle_ready",
    "product_compile_status",
    "product_clarification_count",
    "product_acceptance_coverage_passed",
    "product_gate_blocking_finding_count",
    "review_score",
    "time_to_first_artifact_ms",
    "time_to_generic_verifier_pass_ms",
    "time_to_product_gate_pass_ms",
    "time_to_accepted_deliverable_ms",
    "wall_duration_ms",
    "estimated_cost_usd",
    "provider_reported_cost_usd",
    "cost_source",
    "pricing_table_id",
    "total_tokens",
    "input_tokens",
    "output_tokens",
    "cache_read_tokens",
    "cache_write_tokens",
    "tool_call_count",
    "repair_count",
    "user_turn_count",
    "clarification_turn_count",
    "frontdesk_node_count",
    "frontdesk_worker_call_count",
    "frontdesk_missing_slot_count",
    "frontdesk_slot_conflict_count",
    "product_clarification_count",
    "product_gate_blocking_finding_count",
    "privacy_violation_count",
    "boundary_violation_count",
    "defect_leakage_count",
    "failure_taxonomy",
    "artifact_refs",
    "metric_events_ref",
}

_NON_NEGATIVE_INT_SUMMARY_FIELDS = {
    "seed",
    "time_to_first_artifact_ms",
    "time_to_generic_verifier_pass_ms",
    "time_to_product_gate_pass_ms",
    "time_to_accepted_deliverable_ms",
    "wall_duration_ms",
    "total_tokens",
    "input_tokens",
    "output_tokens",
    "cache_read_tokens",
    "cache_write_tokens",
    "tool_call_count",
    "repair_count",
    "user_turn_count",
    "clarification_turn_count",
    "privacy_violation_count",
    "boundary_violation_count",
    "defect_leakage_count",
}

_NON_NEGATIVE_FLOAT_SUMMARY_FIELDS = {
    "review_score",
    "estimated_cost_usd",
    "provider_reported_cost_usd",
}


def build_aggregate(*, benchmark_run_id: str, summaries: list[BenchmarkSummary], summary_refs: list[str]) -> BenchmarkAggregate:
    """Build a deterministic aggregate from safe summary records."""

    run_id = _require_id(benchmark_run_id, "benchmark_aggregate.benchmark_run_id")
    for ref in summary_refs:
        validate_ref(ref, "benchmark_aggregate.summary_refs[]")
    sorted_summaries = sorted(summaries, key=lambda item: (item.task_id, item.mode.value, item.seed))
    mode_summaries: dict[str, dict[str, Any]] = {}
    failure_counts: dict[str, int] = {}
    for summary in sorted_summaries:
        summary.validate()
        bucket = mode_summaries.setdefault(
            summary.mode.value,
            {
                "trial_count": 0,
                "accepted_count": 0,
                "comparable_accepted_count": 0,
                "comparable_trial_count": 0,
                "estimated_cost_usd": 0.0,
                "total_estimated_cost_usd": 0.0,
                "provider_reported_cost_usd": 0.0,
                "total_provider_reported_cost_usd": 0.0,
                "estimated_cost_available_count": 0,
                "provider_reported_cost_available_count": 0,
                "cost_source": "unavailable",
                "pricing_table_id": "",
                "total_tokens": 0,
                "tool_call_count": 0,
                "repair_count": 0,
                "privacy_violation_count": 0,
                "boundary_violation_count": 0,
                "defect_leakage_count": 0,
                "wall_duration_ms": 0,
                "total_wall_duration_ms": 0,
                "time_to_accepted_deliverable_ms": 0,
                "avg_time_to_accepted_deliverable_ms": 0.0,
                "p50_time_to_accepted_deliverable_ms": 0.0,
                "p95_time_to_accepted_deliverable_ms": 0.0,
                "non_comparable_trial_count": 0,
            },
        )
        bucket["trial_count"] += 1
        bucket["accepted_count"] += 1 if summary.accepted else 0
        bucket["comparable_accepted_count"] += 1 if summary.accepted and summary.comparable else 0
        bucket["comparable_trial_count"] += 1 if summary.comparable else 0
        bucket["non_comparable_trial_count"] += 0 if summary.comparable else 1
        bucket["total_estimated_cost_usd"] += summary.estimated_cost_usd
        bucket["total_provider_reported_cost_usd"] += summary.provider_reported_cost_usd
        if summary.estimated_cost_usd > 0.0 and summary.cost_source in {"pricing_table", "provider_reported"}:
            bucket["estimated_cost_available_count"] += 1
        if summary.provider_reported_cost_usd > 0.0:
            bucket["provider_reported_cost_available_count"] += 1
        if summary.cost_source == "pricing_table":
            bucket["cost_source"] = "pricing_table"
            if summary.pricing_table_id:
                bucket["pricing_table_id"] = summary.pricing_table_id
        elif summary.cost_source == "provider_reported" and bucket["cost_source"] == "unavailable":
            bucket["cost_source"] = "provider_reported"
        bucket["total_wall_duration_ms"] += summary.wall_duration_ms
        if summary.comparable:
            bucket["estimated_cost_usd"] += summary.estimated_cost_usd
            bucket["provider_reported_cost_usd"] += summary.provider_reported_cost_usd
            bucket["total_tokens"] += summary.total_tokens
            bucket["tool_call_count"] += summary.tool_call_count
            bucket["repair_count"] += summary.repair_count
        bucket["privacy_violation_count"] += summary.privacy_violation_count
        bucket["boundary_violation_count"] += summary.boundary_violation_count
        bucket["defect_leakage_count"] += summary.defect_leakage_count
        if summary.comparable:
            bucket["wall_duration_ms"] += summary.wall_duration_ms
        if summary.comparable and summary.accepted and summary.time_to_accepted_deliverable_ms > 0:
            bucket["time_to_accepted_deliverable_ms"] += summary.time_to_accepted_deliverable_ms
        for failure in summary.failure_taxonomy:
            failure_counts[failure] = failure_counts.get(failure, 0) + 1
    for values in mode_summaries.values():
        comparable = values["comparable_trial_count"]
        values["success_rate_within_budget"] = (
            values["comparable_accepted_count"] / comparable if comparable else 0.0
        )
        values["cost_per_accepted_deliverable_usd"] = (
            values["estimated_cost_usd"] / values["comparable_accepted_count"]
            if values["comparable_accepted_count"]
            else 0.0
        )
        accepted_times = sorted(
            summary.time_to_accepted_deliverable_ms
            for summary in sorted_summaries
            if summary.mode.value in mode_summaries
            and values is mode_summaries[summary.mode.value]
            and summary.comparable
            and summary.accepted
            and summary.time_to_accepted_deliverable_ms > 0
        )
        values["avg_time_to_accepted_deliverable_ms"] = (
            values["time_to_accepted_deliverable_ms"] / len(accepted_times) if accepted_times else 0.0
        )
        values["p50_time_to_accepted_deliverable_ms"] = _percentile(accepted_times, 0.50)
        values["p95_time_to_accepted_deliverable_ms"] = _percentile(accepted_times, 0.95)
    aggregate = BenchmarkAggregate(
        benchmark_run_id=run_id,
        summary_refs=sorted(summary_refs),
        mode_summaries=mode_summaries,
        failure_taxonomy_counts=failure_counts,
        task_count=len({summary.task_id for summary in sorted_summaries}),
        trial_count=len(sorted_summaries),
        accepted_count=sum(1 for summary in sorted_summaries if summary.accepted),
        comparable_trial_count=sum(1 for summary in sorted_summaries if summary.comparable),
    )
    aggregate.validate()
    return aggregate


def _strict_mapping(value: Mapping[str, Any], field_name: str, allowed: set[str]) -> dict[str, Any]:
    data = require_mapping(value, field_name)
    extra = sorted(set(data) - allowed)
    if extra:
        raise ContractValidationError(f"{field_name} contains unknown field(s): {', '.join(extra)}")
    return data


def _validate_ref_list(values: list[str], field_name: str) -> None:
    require_str_list(values, field_name)
    for ref in values:
        validate_ref(ref, f"{field_name}[]")


def _require_id(value: Any, field_name: str) -> str:
    text = require_non_empty_str(value, field_name)
    if "/" in text or "\\" in text or text in {".", ".."}:
        raise ContractValidationError(f"{field_name} must be a safe id, not a path")
    validate_ref(text, field_name)
    return text


def _optional_id(value: Any, field_name: str) -> str:
    if value is None or value == "":
        return ""
    return _require_id(value, field_name)


def _require_bool(value: Any, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise ContractValidationError(f"{field_name} must be a boolean")
    return value


def _require_number_at_least(value: Any, field_name: str, minimum: float) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool) or value < minimum:
        raise ContractValidationError(f"{field_name} must be a number >= {minimum}")
    return float(value)


def _require_cost_source(value: Any, field_name: str) -> str:
    text = require_non_empty_str(value, field_name)
    if text not in BENCHMARK_COST_SOURCES:
        raise ContractValidationError(f"{field_name} must be one of {sorted(BENCHMARK_COST_SOURCES)}")
    return text


def _require_int_mapping(value: Any, field_name: str) -> dict[str, int]:
    data = require_mapping(value, field_name)
    result: dict[str, int] = {}
    for key, item in data.items():
        result[require_non_empty_str(key, f"{field_name}.key")] = require_int_at_least(
            item,
            f"{field_name}.{key}",
            0,
        )
    return result


def _strict_metric_values(value: Any, field_name: str) -> dict[str, Any]:
    data = require_mapping(value, field_name)
    result: dict[str, Any] = {}
    for key, item in data.items():
        if not isinstance(key, str) or not key:
            raise ContractValidationError(f"{field_name} keys must be non-empty strings")
        if item is None:
            continue
        if not _is_scalar_metric_value(item):
            raise ContractValidationError(f"{field_name}.{key} must be a scalar metric value")
        result[key] = ensure_json_value(item, f"{field_name}.{key}")
    return safe_metric_values(result)


def _is_scalar_metric_value(value: Any) -> bool:
    if isinstance(value, bool):
        return True
    return isinstance(value, (str, int, float))


def _percentile(values: list[int], percentile: float) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return float(values[0])
    index = int(round((len(values) - 1) * percentile))
    index = max(0, min(index, len(values) - 1))
    return float(values[index])
