"""Phase 3 quality evaluation for the DeepResearch integration."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Protocol

from missionforge.adapters.pi_agent_runtime import PiAgentRuntimeAdapter, PiAgentRuntimeConfig
from missionforge.contracts import (
    ContractValidationError,
    assert_refs_only_payload,
    require_mapping,
    require_non_empty_str,
    require_str,
    require_str_list,
    stable_json_hash,
    validate_ref,
)
from missionforge.piworker_call import PiWorkerCall, PiWorkerCallResult, PiWorkerCallResultStatus, PiWorkerCallRole
from missionforge.piworker_runtime import PiWorkerCallAdapter, run_piworker_call
from missionforge.runtime_results import ExecutionReport, WorkerAdapterResult, WorkerResult
from missionforge.task_contract import NetworkPolicy, PermissionManifest

from .compiler import (
    EXPECTED_DRAFT_REFS,
    EXTENSION_LOCK_REF,
    OUTPUT_CONTRACT_REF,
    PERMISSION_MANIFEST_REF,
    PRODUCT_REQUEST_REF,
    SOURCE_COLLECTION_REPORT_REF,
    SOURCE_PACKET_REF,
    STRUCTURAL_CHECK_POLICY_REF,
    TASK_CONTRACT_REF,
    WORKSPACE_POLICY_REF,
)
from .product_contract import AcademicResearchRequest, DeepResearchRunResult
from .product_contract import DeepResearchRunStatus
from .runtime import (
    run_deepresearch_academic_single_agent,
)
from .search_intent import SEARCH_INTENT_REF
from .source_collector import AcademicSourceCollectionConfig
from .workspace import read_json_ref, read_text_ref, ref_is_non_empty_file, write_json_ref, write_text_ref


QUALITY_EVALUATION_RESULT_SCHEMA_VERSION = "missionforge_deepresearch.quality_evaluation_result.v1"
QUALITY_EVALUATION_STATUS_VALUES = {"comparison_ready", "failed"}
BASELINE_MODES = {"direct_prompt"}
EVALUATOR_MODES = {"heuristic", "piworker"}
DIRECT_BASELINE_BRIEF_REF = "manuals/direct_skill_like_research_brief.md"
DIRECT_BASELINE_CALL_REF = "attempts/direct_baseline/piworker_call.json"
DIRECT_BASELINE_CALL_RESULT_REF = "attempts/direct_baseline/piworker_call_result.json"
DIRECT_BASELINE_EXECUTION_REPORT_REF = "attempts/direct_baseline/execution_report.json"
DIRECT_BASELINE_METRICS_REF = "attempts/direct_baseline/metrics.json"
DIRECT_BASELINE_STRUCTURAL_CHECK_REF = "reports/direct_baseline_structural_checks.json"
EVALUATION_SPEC_REF = "evaluation/quality_evaluation_spec.json"
EVALUATION_REPORT_REF = "evaluation/quality_comparison_report.md"
EVALUATION_SCORECARD_REF = "evaluation/quality_scorecard.json"
EVALUATOR_CALL_REF = "attempts/quality_evaluator/piworker_call.json"
EVALUATOR_CALL_RESULT_REF = "attempts/quality_evaluator/piworker_call_result.json"
EVALUATOR_EXECUTION_REPORT_REF = "attempts/quality_evaluator/execution_report.json"
EVALUATOR_METRICS_REF = "attempts/quality_evaluator/metrics.json"
EVALUATION_RESULT_REF = "packages/deepresearch_quality_evaluation_result.json"


@dataclass(frozen=True)
class DeepResearchQualityEvaluationResult:
    """Refs-first result for a Phase 3 MissionForge-vs-direct comparison."""

    request_id: str
    status: str
    missionforge_run_result_ref: str
    direct_run_result_ref: str
    evaluation_report_ref: str
    scorecard_ref: str
    evidence_refs: list[str] = field(default_factory=list)
    metric_refs: list[str] = field(default_factory=list)
    run_workspace_ref: str = ""
    evaluation_result_ref: str = ""
    schema_version: str = QUALITY_EVALUATION_RESULT_SCHEMA_VERSION

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "DeepResearchQualityEvaluationResult":
        data = require_mapping(payload, "deepresearch_quality_evaluation_result")
        result = cls(
            schema_version=require_non_empty_str(
                data.get("schema_version", QUALITY_EVALUATION_RESULT_SCHEMA_VERSION),
                "deepresearch_quality_evaluation_result.schema_version",
            ),
            request_id=require_non_empty_str(data.get("request_id"), "deepresearch_quality_evaluation_result.request_id"),
            status=require_enum_like(
                data.get("status"),
                QUALITY_EVALUATION_STATUS_VALUES,
                "deepresearch_quality_evaluation_result.status",
            ),
            run_workspace_ref=validate_ref(
                data.get("run_workspace_ref"),
                "deepresearch_quality_evaluation_result.run_workspace_ref",
            ),
            evaluation_result_ref=validate_ref(
                data.get("evaluation_result_ref"),
                "deepresearch_quality_evaluation_result.evaluation_result_ref",
            ),
            missionforge_run_result_ref=validate_ref(
                data.get("missionforge_run_result_ref"),
                "deepresearch_quality_evaluation_result.missionforge_run_result_ref",
            ),
            direct_run_result_ref=validate_ref(
                data.get("direct_run_result_ref"),
                "deepresearch_quality_evaluation_result.direct_run_result_ref",
            ),
            evaluation_report_ref=validate_ref(
                data.get("evaluation_report_ref"),
                "deepresearch_quality_evaluation_result.evaluation_report_ref",
            ),
            scorecard_ref=validate_ref(data.get("scorecard_ref"), "deepresearch_quality_evaluation_result.scorecard_ref"),
            evidence_refs=_ref_list(data.get("evidence_refs", []), "deepresearch_quality_evaluation_result.evidence_refs"),
            metric_refs=_ref_list(data.get("metric_refs", []), "deepresearch_quality_evaluation_result.metric_refs"),
        )
        result.validate()
        return result

    def validate(self) -> None:
        if self.schema_version != QUALITY_EVALUATION_RESULT_SCHEMA_VERSION:
            raise ContractValidationError("deepresearch_quality_evaluation_result.schema_version is unsupported")
        require_non_empty_str(self.request_id, "deepresearch_quality_evaluation_result.request_id")
        require_enum_like(self.status, QUALITY_EVALUATION_STATUS_VALUES, "deepresearch_quality_evaluation_result.status")
        for field_name in (
            "run_workspace_ref",
            "evaluation_result_ref",
            "missionforge_run_result_ref",
            "direct_run_result_ref",
            "evaluation_report_ref",
            "scorecard_ref",
        ):
            validate_ref(getattr(self, field_name), f"deepresearch_quality_evaluation_result.{field_name}")
        _validate_unique_refs(self.evidence_refs, "deepresearch_quality_evaluation_result.evidence_refs")
        _validate_unique_refs(self.metric_refs, "deepresearch_quality_evaluation_result.metric_refs")
        assert_refs_only_payload(self.to_dict_without_validation(), "deepresearch_quality_evaluation_result")

    def to_dict_without_validation(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "request_id": self.request_id,
            "status": self.status,
            "run_workspace_ref": self.run_workspace_ref,
            "evaluation_result_ref": self.evaluation_result_ref,
            "missionforge_run_result_ref": self.missionforge_run_result_ref,
            "direct_run_result_ref": self.direct_run_result_ref,
            "evaluation_report_ref": self.evaluation_report_ref,
            "scorecard_ref": self.scorecard_ref,
            "evidence_refs": list(self.evidence_refs),
            "metric_refs": list(self.metric_refs),
        }

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return self.to_dict_without_validation()


class QualityEvaluator(Protocol):
    """Minimal seam for Phase 3 comparison evaluation."""

    def evaluate(
        self,
        request: AcademicResearchRequest,
        *,
        workspace: str | Path,
        missionforge_result: DeepResearchRunResult,
        direct_result: DeepResearchRunResult,
    ) -> tuple[str, str]:
        """Write report and scorecard under workspace, returning their refs."""
        ...


def run_deepresearch_quality_evaluation(
    request: AcademicResearchRequest,
    *,
    workspace: str | Path = ".",
    missionforge_adapter: PiWorkerCallAdapter | None = None,
    direct_adapter: PiWorkerCallAdapter | None = None,
    evaluator_adapter: PiWorkerCallAdapter | None = None,
    source_mode: str = "fixture",
    researcher_mode: str = "fixture",
    search_intent_mode: str = "none",
    search_queries: list[str] | None = None,
    search_intent_ref: str | None = None,
    source_config: AcademicSourceCollectionConfig | None = None,
    piworker_config: PiAgentRuntimeConfig | None = None,
    piworker_environ: Mapping[str, str] | None = None,
    live_extension_mode: bool = False,
    extension_installer: Any | None = None,
    baseline_mode: str = "direct_prompt",
    evaluator_mode: str = "heuristic",
    evaluator: QualityEvaluator | None = None,
) -> DeepResearchQualityEvaluationResult:
    """Run Phase 3 A/B quality evaluation for one academic research request."""

    request.validate()
    if baseline_mode not in BASELINE_MODES:
        raise ContractValidationError(f"deepresearch baseline_mode must be one of {sorted(BASELINE_MODES)}")
    if evaluator_mode not in EVALUATOR_MODES:
        raise ContractValidationError(f"deepresearch evaluator_mode must be one of {sorted(EVALUATOR_MODES)}")
    root = Path(workspace).resolve()

    missionforge_result = run_deepresearch_academic_single_agent(
        request,
        workspace=root,
        adapter=missionforge_adapter,
        source_mode=source_mode,
        researcher_mode=researcher_mode,
        search_intent_mode=search_intent_mode,
        search_queries=search_queries,
        search_intent_ref=search_intent_ref,
        source_config=source_config,
        piworker_config=piworker_config,
        piworker_environ=piworker_environ,
        live_extension_mode=live_extension_mode,
        extension_installer=extension_installer,
    )
    direct_result = run_direct_prompt_baseline(
        request,
        workspace=root,
        missionforge_result=missionforge_result,
        adapter=direct_adapter,
        piworker_config=piworker_config,
        piworker_environ=piworker_environ,
    )
    active_evaluator = evaluator or _quality_evaluator(evaluator_mode, evaluator_adapter, piworker_config, piworker_environ)
    report_ref, scorecard_ref = active_evaluator.evaluate(
        request,
        workspace=root,
        missionforge_result=missionforge_result,
        direct_result=direct_result,
    )
    evaluator_evidence_refs = _existing_outer_refs(
        root,
        missionforge_result.run_workspace_ref,
        [EVALUATION_SPEC_REF, EVALUATOR_CALL_REF, EVALUATOR_CALL_RESULT_REF, EVALUATOR_EXECUTION_REPORT_REF],
    )
    evaluator_metric_refs = _existing_outer_refs(
        root,
        missionforge_result.run_workspace_ref,
        [EVALUATOR_METRICS_REF],
    )
    result = DeepResearchQualityEvaluationResult(
        request_id=request.request_id,
        status="comparison_ready",
        run_workspace_ref=missionforge_result.run_workspace_ref,
        evaluation_result_ref=_outer_ref(missionforge_result.run_workspace_ref, EVALUATION_RESULT_REF),
        missionforge_run_result_ref=missionforge_result.run_result_ref,
        direct_run_result_ref=direct_result.run_result_ref,
        evaluation_report_ref=_outer_ref(missionforge_result.run_workspace_ref, report_ref),
        scorecard_ref=_outer_ref(missionforge_result.run_workspace_ref, scorecard_ref),
        evidence_refs=_dedupe_refs(
            [
                missionforge_result.run_result_ref,
                direct_result.run_result_ref,
                _outer_ref(missionforge_result.run_workspace_ref, EVALUATION_SPEC_REF),
                _outer_ref(missionforge_result.run_workspace_ref, report_ref),
                _outer_ref(missionforge_result.run_workspace_ref, scorecard_ref),
                *evaluator_evidence_refs,
                *missionforge_result.evidence_refs,
                *direct_result.evidence_refs,
            ]
        ),
        metric_refs=_dedupe_refs([*missionforge_result.metric_refs, *direct_result.metric_refs, *evaluator_metric_refs]),
    )
    write_json_ref(root, result.evaluation_result_ref, result.to_dict())
    return result


def run_direct_prompt_baseline(
    request: AcademicResearchRequest,
    *,
    workspace: str | Path,
    missionforge_result: DeepResearchRunResult,
    adapter: PiWorkerCallAdapter | None = None,
    piworker_config: PiAgentRuntimeConfig | None = None,
    piworker_environ: Mapping[str, str] | None = None,
) -> DeepResearchRunResult:
    """Run a skill-like direct baseline against the same compiled workspace."""

    request.validate()
    missionforge_result.validate()
    root = Path(workspace).resolve()
    run_root = root / missionforge_result.run_workspace_ref
    contract_payload = read_json_ref(run_root, TASK_CONTRACT_REF, "task_contract")
    permission_payload = read_json_ref(run_root, PERMISSION_MANIFEST_REF, "permission_manifest")
    source_packet = read_json_ref(run_root, SOURCE_PACKET_REF, "source_packet")
    source_collection_report = read_json_ref(run_root, SOURCE_COLLECTION_REPORT_REF, "source_collection_report")
    baseline_refs = _direct_baseline_refs()
    baseline_brief = _direct_baseline_brief(request, source_packet, source_collection_report)
    write_text_ref(run_root, DIRECT_BASELINE_BRIEF_REF, baseline_brief)

    permission_manifest = PermissionManifest.from_dict(permission_payload)
    direct_permission_manifest = _direct_baseline_permission_manifest(permission_manifest, request.request_id)
    direct_permission_manifest_ref = "policy/direct_baseline_permission_manifest.json"
    write_json_ref(run_root, direct_permission_manifest_ref, direct_permission_manifest.to_dict())
    visible_refs = _dedupe_refs(
        [
            PRODUCT_REQUEST_REF,
            DIRECT_BASELINE_BRIEF_REF,
            SEARCH_INTENT_REF,
            SOURCE_PACKET_REF,
            SOURCE_COLLECTION_REPORT_REF,
            OUTPUT_CONTRACT_REF,
            STRUCTURAL_CHECK_POLICY_REF,
            direct_permission_manifest_ref,
            *([EXTENSION_LOCK_REF] if ref_is_non_empty_file(run_root, EXTENSION_LOCK_REF) else []),
        ]
    )
    call = PiWorkerCall(
        call_id=f"deepresearch-{request.request_id}-direct-baseline",
        role=PiWorkerCallRole.EXECUTOR,
        contract_id=f"deepresearch-{request.request_id}-direct-baseline",
        contract_hash=stable_json_hash(
            {
                "request": request.to_dict(),
                "baseline_brief_ref": DIRECT_BASELINE_BRIEF_REF,
                "source_packet_hash": stable_json_hash(source_packet),
                "source_collection_report_hash": stable_json_hash(source_collection_report),
            }
        ),
        contract_ref=DIRECT_BASELINE_BRIEF_REF,
        objective=(
            "Act like a direct skill-style academic deep research agent. Use the visible brief, "
            "source refs, and available tools to write the five requested report artifacts. "
            "Do not claim product acceptance."
        ),
        visible_refs=visible_refs,
        writable_refs=["direct_baseline/reports", "attempts", "packages"],
        expected_output_refs=list(baseline_refs),
        permission_manifest_ref=direct_permission_manifest_ref,
        source_packet_ref=SOURCE_PACKET_REF,
        source_packet_hash=stable_json_hash(source_packet),
        evidence_refs=[SEARCH_INTENT_REF, SOURCE_PACKET_REF, SOURCE_COLLECTION_REPORT_REF],
        output_schema_ref=OUTPUT_CONTRACT_REF,
        validation_policy_ref=STRUCTURAL_CHECK_POLICY_REF,
        runtime_budget={"max_turns": 8},
        metadata={"phase": "phase3_quality_evaluation", "baseline_mode": "direct_brief"},
    )
    write_json_ref(run_root, DIRECT_BASELINE_CALL_REF, call.to_dict())
    worker = adapter or _piworker_adapter(piworker_config, piworker_environ)
    extension_lock_ref = EXTENSION_LOCK_REF if ref_is_non_empty_file(run_root, EXTENSION_LOCK_REF) else None
    call_result = run_piworker_call(
        call,
        workspace=run_root,
        adapter=worker,
        result_id=f"{call.call_id}-result",
        extension_lock_ref=extension_lock_ref,
        metadata={"phase": "phase3_quality_evaluation", "baseline_mode": "direct_brief"},
    )
    write_json_ref(run_root, DIRECT_BASELINE_CALL_RESULT_REF, call_result.to_dict())
    structural = _run_direct_baseline_structural_checks(
        workspace=run_root,
        expected_refs=list(baseline_refs),
        call_result=call_result,
    )
    status = (
        DeepResearchRunStatus.DRAFT_READY
        if call_result.status is PiWorkerCallResultStatus.COMPLETED and structural["status"] == "passed"
        else DeepResearchRunStatus.FAILED
    )
    result = DeepResearchRunResult(
        request_id=f"{request.request_id}-direct-baseline",
        status=status,
        run_workspace_ref=missionforge_result.run_workspace_ref,
        run_result_ref=_outer_ref(missionforge_result.run_workspace_ref, "packages/direct_baseline_run_result.json"),
        task_contract_ref=missionforge_result.task_contract_ref,
        manual_ref=_outer_ref(missionforge_result.run_workspace_ref, DIRECT_BASELINE_BRIEF_REF),
        source_packet_ref=missionforge_result.source_packet_ref,
        output_contract_ref=missionforge_result.output_contract_ref,
        researcher_call_ref=_outer_ref(missionforge_result.run_workspace_ref, DIRECT_BASELINE_CALL_REF),
        researcher_call_result_ref=_outer_ref(missionforge_result.run_workspace_ref, DIRECT_BASELINE_CALL_RESULT_REF),
        structural_check_ref=_outer_ref(missionforge_result.run_workspace_ref, DIRECT_BASELINE_STRUCTURAL_CHECK_REF),
        draft_artifact_refs=[_outer_ref(missionforge_result.run_workspace_ref, ref) for ref in baseline_refs],
        evidence_refs=_dedupe_refs(
            [
                missionforge_result.source_packet_ref,
                missionforge_result.output_contract_ref,
                _outer_ref(missionforge_result.run_workspace_ref, DIRECT_BASELINE_BRIEF_REF),
                _outer_ref(missionforge_result.run_workspace_ref, call_result.execution_report_ref),
                _outer_ref(missionforge_result.run_workspace_ref, DIRECT_BASELINE_STRUCTURAL_CHECK_REF),
            ]
        ),
        metric_refs=[_outer_ref(missionforge_result.run_workspace_ref, ref) for ref in call_result.metric_refs],
        contract_hash=contract_payload.get("contract_hash", call.contract_hash),
    )
    write_json_ref(root, result.run_result_ref, result.to_dict())
    return result


class HeuristicQualityEvaluator:
    """Deterministic scorecard for Phase 3 triage, not semantic acceptance."""

    def evaluate(
        self,
        request: AcademicResearchRequest,
        *,
        workspace: str | Path,
        missionforge_result: DeepResearchRunResult,
        direct_result: DeepResearchRunResult,
    ) -> tuple[str, str]:
        root = Path(workspace).resolve()
        run_root = root / missionforge_result.run_workspace_ref
        missionforge_profile = _report_profile(
            run_root,
            [ref.removeprefix(f"{missionforge_result.run_workspace_ref}/") for ref in missionforge_result.draft_artifact_refs],
            source_packet_ref=SOURCE_PACKET_REF,
        )
        direct_profile = _report_profile(
            run_root,
            [ref.removeprefix(f"{direct_result.run_workspace_ref}/") for ref in direct_result.draft_artifact_refs],
            source_packet_ref=SOURCE_PACKET_REF,
        )
        scorecard = {
            "schema_version": "missionforge_deepresearch.quality_scorecard.v1",
            "request_id": request.request_id,
            "evaluator": "heuristic",
            "authority": "triage_only_not_acceptance",
            "criteria": {
                "coverage": "count distinct cited source markers and source ids present in reports",
                "freshness": "count recent year markers and source packet recent records",
                "citation_quality": "count citation markers and evidence index URLs",
                "delta_clarity": "check whether research_delta.md is non-empty and mentions baseline or previous refs",
                "gap_clarity": "check whether source_gaps.md is non-empty and explicit",
            },
            "missionforge": missionforge_profile,
            "direct_baseline": direct_profile,
            "comparison": _compare_profiles(missionforge_profile, direct_profile),
            "notes": [
                "This scorecard is a mechanical triage artifact.",
                "It does not judge semantic research quality or grant acceptance.",
                "Use a PiWorker evaluator or independent judge before product-grade decisions.",
            ],
        }
        write_json_ref(run_root, EVALUATION_SCORECARD_REF, scorecard)
        write_text_ref(run_root, EVALUATION_REPORT_REF, _quality_report_text(request, scorecard))
        write_json_ref(run_root, EVALUATION_SPEC_REF, _evaluation_spec_payload(request, missionforge_result, direct_result))
        return EVALUATION_REPORT_REF, EVALUATION_SCORECARD_REF


class PiWorkerQualityEvaluator:
    """LLM-authored Phase 3 comparison report, still not acceptance."""

    def __init__(
        self,
        *,
        adapter: PiWorkerCallAdapter | None = None,
        piworker_config: PiAgentRuntimeConfig | None = None,
        piworker_environ: Mapping[str, str] | None = None,
    ) -> None:
        self.adapter = adapter
        self.piworker_config = piworker_config
        self.piworker_environ = piworker_environ

    def evaluate(
        self,
        request: AcademicResearchRequest,
        *,
        workspace: str | Path,
        missionforge_result: DeepResearchRunResult,
        direct_result: DeepResearchRunResult,
    ) -> tuple[str, str]:
        root = Path(workspace).resolve()
        run_root = root / missionforge_result.run_workspace_ref
        spec = _evaluation_spec_payload(request, missionforge_result, direct_result)
        write_json_ref(run_root, EVALUATION_SPEC_REF, spec)
        permission_manifest = PermissionManifest(
            manifest_id=f"deepresearch-{request.request_id}-quality-evaluator-permissions",
            workspace_policy_ref=WORKSPACE_POLICY_REF,
            readable_refs=["reports", "direct_baseline/reports", "sources", "product_contract", "evaluation", "policy"],
            writable_refs=["evaluation", "attempts"],
            denied_refs=["secrets"],
            network_policy=NetworkPolicy.DISABLED,
        )
        permission_manifest_ref = "policy/quality_evaluator_permission_manifest.json"
        write_json_ref(run_root, permission_manifest_ref, permission_manifest.to_dict())
        call = PiWorkerCall(
            call_id=f"deepresearch-{request.request_id}-quality-evaluator",
            role=PiWorkerCallRole.JUDGE,
            contract_id=f"deepresearch-{request.request_id}-quality-evaluation",
            contract_hash=stable_json_hash(spec),
            contract_ref=EVALUATION_SPEC_REF,
            objective=(
                "Compare the MissionForge DeepResearch draft with the direct skill-like draft. "
                "Write a concise quality comparison report and a JSON scorecard. "
                "Do not grant final product acceptance."
            ),
            visible_refs=[
                EVALUATION_SPEC_REF,
                SOURCE_PACKET_REF,
                SOURCE_COLLECTION_REPORT_REF,
                "reports/final_report.md",
                "reports/evidence_index.md",
                "reports/research_delta.md",
                "reports/source_gaps.md",
                "direct_baseline/reports/final_report.md",
                "direct_baseline/reports/evidence_index.md",
                "direct_baseline/reports/research_delta.md",
                "direct_baseline/reports/source_gaps.md",
                permission_manifest_ref,
            ],
            writable_refs=["evaluation", "attempts"],
            expected_output_refs=[EVALUATION_REPORT_REF, EVALUATION_SCORECARD_REF],
            permission_manifest_ref=permission_manifest_ref,
            source_packet_ref=EVALUATION_SPEC_REF,
            source_packet_hash=stable_json_hash(spec),
            evidence_refs=[
                "reports/final_report.md",
                "reports/evidence_index.md",
                "reports/research_delta.md",
                "reports/source_gaps.md",
                "direct_baseline/reports/final_report.md",
                "direct_baseline/reports/evidence_index.md",
                "direct_baseline/reports/research_delta.md",
                "direct_baseline/reports/source_gaps.md",
            ],
            output_schema_ref=EVALUATION_SPEC_REF,
            validation_policy_ref=EVALUATION_SPEC_REF,
            runtime_budget={"max_turns": 4},
            metadata={"phase": "phase3_quality_evaluation", "evaluator": "piworker"},
        )
        write_json_ref(run_root, EVALUATOR_CALL_REF, call.to_dict())
        adapter = self.adapter or _piworker_adapter(self.piworker_config, self.piworker_environ)
        call_result = run_piworker_call(
            call,
            workspace=run_root,
            adapter=adapter,
            result_id=f"{call.call_id}-result",
            metadata={"phase": "phase3_quality_evaluation", "evaluator": "piworker"},
        )
        write_json_ref(run_root, EVALUATOR_CALL_RESULT_REF, call_result.to_dict())
        if call_result.status is not PiWorkerCallResultStatus.COMPLETED:
            raise ContractValidationError("quality evaluator PiWorker call did not complete")
        if not ref_is_non_empty_file(run_root, EVALUATION_REPORT_REF) or not ref_is_non_empty_file(run_root, EVALUATION_SCORECARD_REF):
            raise ContractValidationError("quality evaluator did not produce required evaluation artifacts")
        return EVALUATION_REPORT_REF, EVALUATION_SCORECARD_REF


class FixtureDirectBaselineAdapter:
    """Offline direct baseline adapter for tests and package shape checks."""

    adapter_family = "fixture_deepresearch_direct_baseline"

    def run_call(
        self,
        call: PiWorkerCall,
        *,
        workspace: str | Path = ".",
        evidence_store: Any | None = None,
        call_spec: Any | None = None,
        exit_criteria: list[str] | None = None,
        stop_conditions: list[str] | None = None,
        extension_lock_ref: str | None = None,
    ) -> WorkerAdapterResult:
        call.validate()
        if call.role is not PiWorkerCallRole.EXECUTOR:
            raise ContractValidationError("fixture direct baseline only supports executor calls")
        root = Path(workspace).resolve()
        for ref in call.expected_output_refs:
            title = ref.rsplit("/", 1)[-1].replace("_", " ").replace(".md", "").title()
            write_text_ref(
                root,
                ref,
                f"# Direct Baseline {title}\n\nFixture direct baseline artifact for {call.call_id}.\n",
            )
        metrics = {"metric_ref": DIRECT_BASELINE_METRICS_REF, "fixture": True}
        write_json_ref(root, DIRECT_BASELINE_METRICS_REF, metrics)
        report = ExecutionReport(
            report_id="deepresearch-fixture-direct-baseline-execution-report",
            call_id=call.call_id,
            status="completed",
            produced_artifacts=list(call.expected_output_refs),
            changed_refs=[*call.expected_output_refs, DIRECT_BASELINE_EXECUTION_REPORT_REF, DIRECT_BASELINE_METRICS_REF],
            evidence_refs=[SOURCE_PACKET_REF, DIRECT_BASELINE_BRIEF_REF],
            worker_claims=["fixture direct baseline produced"],
            metrics=metrics,
        )
        write_json_ref(root, DIRECT_BASELINE_EXECUTION_REPORT_REF, report.to_dict())
        return WorkerAdapterResult(
            execution_report=report,
            worker_result=WorkerResult(status="completed", execution_report_ref=DIRECT_BASELINE_EXECUTION_REPORT_REF),
            event_evidence_refs=[],
            metrics=metrics,
        )


class FixtureQualityEvaluatorAdapter:
    """Offline evaluator adapter for tests."""

    adapter_family = "fixture_deepresearch_quality_evaluator"

    def run_call(
        self,
        call: PiWorkerCall,
        *,
        workspace: str | Path = ".",
        evidence_store: Any | None = None,
        call_spec: Any | None = None,
        exit_criteria: list[str] | None = None,
        stop_conditions: list[str] | None = None,
        extension_lock_ref: str | None = None,
    ) -> WorkerAdapterResult:
        call.validate()
        if call.role is not PiWorkerCallRole.JUDGE:
            raise ContractValidationError("fixture quality evaluator only supports judge calls")
        root = Path(workspace).resolve()
        write_text_ref(root, EVALUATION_REPORT_REF, "# Quality Comparison\n\nFixture evaluator comparison.\n")
        write_json_ref(
            root,
            EVALUATION_SCORECARD_REF,
            {
                "schema_version": "missionforge_deepresearch.quality_scorecard.v1",
                "evaluator": "fixture",
                "authority": "triage_only_not_acceptance",
            },
        )
        metrics = {"metric_ref": EVALUATOR_METRICS_REF, "fixture": True}
        write_json_ref(root, EVALUATOR_METRICS_REF, metrics)
        report = ExecutionReport(
            report_id="deepresearch-fixture-quality-evaluator-execution-report",
            call_id=call.call_id,
            status="completed",
            produced_artifacts=[EVALUATION_REPORT_REF, EVALUATION_SCORECARD_REF],
            changed_refs=[EVALUATION_REPORT_REF, EVALUATION_SCORECARD_REF, EVALUATOR_EXECUTION_REPORT_REF, EVALUATOR_METRICS_REF],
            evidence_refs=[EVALUATION_SPEC_REF],
            worker_claims=["fixture quality comparison produced"],
            metrics=metrics,
        )
        write_json_ref(root, EVALUATOR_EXECUTION_REPORT_REF, report.to_dict())
        return WorkerAdapterResult(
            execution_report=report,
            worker_result=WorkerResult(status="completed", execution_report_ref=EVALUATOR_EXECUTION_REPORT_REF),
            event_evidence_refs=[],
            metrics=metrics,
        )


def load_deepresearch_quality_evaluation_result(
    workspace: str | Path,
    ref: str,
) -> DeepResearchQualityEvaluationResult:
    """Load a refs-first DeepResearch quality evaluation result."""

    return DeepResearchQualityEvaluationResult.from_dict(read_json_ref(workspace, ref, "deepresearch_quality_evaluation_result"))


def _quality_evaluator(
    evaluator_mode: str,
    evaluator_adapter: PiWorkerCallAdapter | None,
    piworker_config: PiAgentRuntimeConfig | None,
    piworker_environ: Mapping[str, str] | None,
) -> QualityEvaluator:
    if evaluator_mode == "heuristic":
        return HeuristicQualityEvaluator()
    if evaluator_mode == "piworker":
        return PiWorkerQualityEvaluator(
            adapter=evaluator_adapter,
            piworker_config=piworker_config,
            piworker_environ=piworker_environ,
        )
    raise ContractValidationError(f"deepresearch evaluator_mode must be one of {sorted(EVALUATOR_MODES)}")


def _piworker_adapter(
    piworker_config: PiAgentRuntimeConfig | None,
    piworker_environ: Mapping[str, str] | None,
) -> PiWorkerCallAdapter:
    return PiAgentRuntimeAdapter(
        piworker_config or PiAgentRuntimeConfig(provider_mode="live"),
        environ=piworker_environ,
    )


def _direct_baseline_refs() -> list[str]:
    return [f"direct_baseline/{ref}" for ref in EXPECTED_DRAFT_REFS]


def _direct_baseline_permission_manifest(
    source_permission_manifest: PermissionManifest,
    request_id: str,
) -> PermissionManifest:
    return PermissionManifest(
        manifest_id=f"deepresearch-{request_id}-direct-baseline-permissions",
        workspace_policy_ref=source_permission_manifest.workspace_policy_ref or WORKSPACE_POLICY_REF,
        readable_refs=[
            "manuals",
            "sources",
            "product_contract",
            "compiled",
            "policy",
            "direct_baseline/reports",
        ],
        writable_refs=["direct_baseline/reports", "attempts", "packages"],
        denied_refs=["secrets"],
        allowed_commands=[],
        network_policy=source_permission_manifest.network_policy,
        env_allowlist=list(source_permission_manifest.env_allowlist),
        extension_grants=list(source_permission_manifest.extension_grants),
    )


def _direct_baseline_brief(
    request: AcademicResearchRequest,
    source_packet: Mapping[str, Any],
    source_collection_report: Mapping[str, Any],
) -> str:
    source_count = len(source_packet.get("source_records", [])) if isinstance(source_packet.get("source_records"), list) else 0
    search_queries = source_packet.get("search_queries", [])
    query_lines = "\n".join(f"- {query}" for query in search_queries if isinstance(query, str)) or "- Use the topic directly."
    live_extension_note = (
        "Use the available web/code-search tools freely to gather evidence."
        if source_collection_report.get("mode") == "live"
        else "Use the visible source packet and report evidence gaps."
    )
    return f"""# Direct Skill-Like Academic Deep Research Brief

Topic: {request.topic}
Audience: {request.audience}
Language: {request.language}

Act as a strong academic deep research agent. Produce the same five artifacts
as a Codex skill-like implementation would produce:

- direct_baseline/reports/final_report.md
- direct_baseline/reports/evidence_index.md
- direct_baseline/reports/research_delta.md
- direct_baseline/reports/reading_plan.md
- direct_baseline/reports/source_gaps.md

Quality bar:

- cover the major lines of work, important papers, code, benchmarks, and open gaps;
- prioritize recent evidence and clearly label historical background;
- cite source identifiers or URLs for material claims;
- compare with previous run refs when present, otherwise state this is a baseline;
- state source gaps instead of inventing support.

Search queries:

{query_lines}

Source packet currently contains {source_count} records.
{live_extension_note}

Do not claim final product acceptance. Stop after writing the required files.
"""


def _run_direct_baseline_structural_checks(
    *,
    workspace: str | Path,
    expected_refs: list[str],
    call_result: PiWorkerCallResult,
) -> dict[str, Any]:
    checked_refs = [validate_ref(ref, "deepresearch_direct_baseline_structural_check.expected_refs[]") for ref in expected_refs]
    missing_or_empty = [ref for ref in checked_refs if not ref_is_non_empty_file(workspace, ref)]
    missing_from_worker_result = sorted(set(checked_refs) - set(call_result.output_refs))
    status = "passed" if not missing_or_empty and not missing_from_worker_result else "failed"
    report = {
        "schema_version": "missionforge_deepresearch.direct_baseline_structural_check_report.v1",
        "status": status,
        "checked_refs": checked_refs,
        "missing_or_empty_refs": missing_or_empty,
        "missing_from_worker_result_refs": missing_from_worker_result,
        "baseline_mode": "direct_brief",
        "notes": [
            "Structural checks do not judge research quality.",
            "Passing structural checks only permits draft_ready for the direct baseline.",
        ],
    }
    write_json_ref(workspace, DIRECT_BASELINE_STRUCTURAL_CHECK_REF, report)
    return report


def _evaluation_spec_payload(
    request: AcademicResearchRequest,
    missionforge_result: DeepResearchRunResult,
    direct_result: DeepResearchRunResult,
) -> dict[str, Any]:
    return {
        "schema_version": "missionforge_deepresearch.quality_evaluation_spec.v1",
        "request_id": request.request_id,
        "topic": request.topic,
        "language": request.language,
        "authority": "triage_only_not_acceptance",
        "missionforge_artifact_refs": list(missionforge_result.draft_artifact_refs),
        "direct_artifact_refs": list(direct_result.draft_artifact_refs),
        "missionforge_result_ref": missionforge_result.run_result_ref,
        "direct_result_ref": direct_result.run_result_ref,
        "criteria": [
            "coverage",
            "freshness",
            "citation_quality",
            "delta_clarity",
            "gap_clarity",
            "readability",
        ],
        "required_outputs": [EVALUATION_REPORT_REF, EVALUATION_SCORECARD_REF],
        "notes": [
            "Compare visible output quality, not internal auditability.",
            "Do not grant final product acceptance.",
        ],
    }


def _report_profile(run_root: Path, artifact_refs: list[str], *, source_packet_ref: str) -> dict[str, Any]:
    combined = "\n".join(_safe_read_text(run_root, ref) for ref in artifact_refs)
    source_packet = read_json_ref(run_root, source_packet_ref, "source_packet")
    source_records = source_packet.get("source_records", [])
    source_count = len(source_records) if isinstance(source_records, list) else 0
    urls = combined.count("http://") + combined.count("https://")
    citation_markers = _count_citation_markers(combined)
    recent_years = _count_recent_years(combined)
    evidence_index = _safe_read_text(run_root, _first_matching_ref(artifact_refs, "evidence_index.md"))
    delta = _safe_read_text(run_root, _first_matching_ref(artifact_refs, "research_delta.md"))
    gaps = _safe_read_text(run_root, _first_matching_ref(artifact_refs, "source_gaps.md"))
    return {
        "artifact_count": sum(1 for ref in artifact_refs if ref_is_non_empty_file(run_root, ref)),
        "source_packet_record_count": source_count,
        "word_count": _word_count(combined),
        "citation_marker_count": citation_markers,
        "url_count": urls,
        "recent_year_marker_count": recent_years,
        "evidence_index_non_empty": bool(evidence_index.strip()),
        "evidence_index_url_count": evidence_index.count("http://") + evidence_index.count("https://"),
        "delta_non_empty": bool(delta.strip()),
        "delta_mentions_baseline_or_previous": _contains_any(delta.lower(), ["baseline", "previous", "上一轮", "基线"]),
        "source_gaps_non_empty": bool(gaps.strip()),
        "source_gaps_explicit": _contains_any(gaps.lower(), ["gap", "缺口", "missing", "不足", "受限"]),
    }


def _compare_profiles(missionforge: Mapping[str, Any], direct: Mapping[str, Any]) -> dict[str, Any]:
    fields = [
        "word_count",
        "citation_marker_count",
        "url_count",
        "recent_year_marker_count",
        "evidence_index_url_count",
    ]
    deltas: dict[str, Any] = {}
    for field_name in fields:
        left = int(missionforge.get(field_name, 0) or 0)
        right = int(direct.get(field_name, 0) or 0)
        deltas[field_name] = left - right
    return {
        "metric_deltas_missionforge_minus_direct": deltas,
        "missionforge_has_delta": bool(missionforge.get("delta_non_empty")),
        "direct_has_delta": bool(direct.get("delta_non_empty")),
        "missionforge_has_explicit_gaps": bool(missionforge.get("source_gaps_explicit")),
        "direct_has_explicit_gaps": bool(direct.get("source_gaps_explicit")),
        "interpretation": "mechanical_triage_only",
    }


def _quality_report_text(request: AcademicResearchRequest, scorecard: Mapping[str, Any]) -> str:
    comparison = require_mapping(scorecard.get("comparison", {}), "quality_scorecard.comparison")
    deltas = require_mapping(
        comparison.get("metric_deltas_missionforge_minus_direct", {}),
        "quality_scorecard.comparison.metric_deltas_missionforge_minus_direct",
    )
    return f"""# DeepResearch Phase 3 Quality Comparison

Topic: {request.topic}

This is a Phase 3 triage comparison between the MissionForge single-agent
product shell and a direct skill-like baseline. It is not semantic acceptance.

## Mechanical Delta

- word_count: {deltas.get("word_count", 0)}
- citation_marker_count: {deltas.get("citation_marker_count", 0)}
- url_count: {deltas.get("url_count", 0)}
- recent_year_marker_count: {deltas.get("recent_year_marker_count", 0)}
- evidence_index_url_count: {deltas.get("evidence_index_url_count", 0)}

## Notes

- Positive numbers mean the MissionForge draft has a higher mechanical count.
- Counts are not quality judgment; they only identify where a human or PiWorker
  evaluator should look next.
- The next product decision should depend on visible output quality:
  coverage, freshness, citations, delta clarity, and gap clarity.
"""


def _safe_read_text(run_root: Path, ref: str) -> str:
    if not ref:
        return ""
    try:
        return read_text_ref(run_root, ref)
    except ContractValidationError:
        return ""


def _first_matching_ref(refs: list[str], suffix: str) -> str:
    for ref in refs:
        if ref.endswith(suffix):
            return ref
    return ""


def _count_citation_markers(text: str) -> int:
    total = 0
    total += text.count("[E")
    total += text.count("[S")
    total += text.count("(http://")
    total += text.count("(https://")
    return total


def _count_recent_years(text: str) -> int:
    total = 0
    for year in range(2023, 2027):
        total += text.count(str(year))
    return total


def _word_count(text: str) -> int:
    return len([part for part in text.replace("\n", " ").split(" ") if part.strip()])


def _contains_any(text: str, needles: list[str]) -> bool:
    return any(needle in text for needle in needles)


def _outer_ref(run_workspace_ref: str, ref: str) -> str:
    return f"{validate_ref(run_workspace_ref, 'run_workspace_ref')}/{validate_ref(ref, 'run_ref')}"


def _existing_outer_refs(root: Path, run_workspace_ref: str, refs: list[str]) -> list[str]:
    run_root = root / validate_ref(run_workspace_ref, "run_workspace_ref")
    return [_outer_ref(run_workspace_ref, ref) for ref in refs if ref_is_non_empty_file(run_root, ref)]


def _dedupe_refs(refs: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for ref in refs:
        safe_ref = validate_ref(ref, "ref")
        if safe_ref not in seen:
            result.append(safe_ref)
            seen.add(safe_ref)
    return result


def _ref_list(value: Any, field_name: str) -> list[str]:
    return [validate_ref(item, f"{field_name}[]") for item in require_str_list(value, field_name)]


def _validate_unique_refs(values: list[str], field_name: str) -> None:
    refs = _ref_list(values, field_name)
    if len(refs) != len(set(refs)):
        raise ContractValidationError(f"{field_name} must not contain duplicate refs")


def require_enum_like(value: Any, allowed: set[str], field_name: str) -> str:
    text = require_str(value, field_name)
    if text not in allowed:
        raise ContractValidationError(f"{field_name} must be one of {sorted(allowed)}")
    return text
