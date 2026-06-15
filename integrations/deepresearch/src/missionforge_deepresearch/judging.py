"""Phase 4 independent judge for the DeepResearch integration."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from missionforge.adapters.pi_agent_runtime import PiAgentRuntimeAdapter, PiAgentRuntimeConfig
from missionforge.agent_packets import HardCheckStatus, JudgeReportDecision
from missionforge.contracts import (
    ContractValidationError,
    assert_refs_only_payload,
    require_enum,
    require_mapping,
    require_non_empty_str,
    require_str_list,
    stable_json_hash,
    validate_ref,
)
from missionforge.piworker_call import PiWorkerCall, PiWorkerCallResultStatus, PiWorkerCallRole
from missionforge.piworker_runtime import PiWorkerCallAdapter, run_piworker_call
from missionforge.runtime_results import ExecutionReport, WorkerAdapterResult, WorkerResult
from missionforge.task_contract import NetworkPolicy, PermissionManifest

from .compiler import (
    JUDGE_RUBRIC_REF,
    OUTPUT_CONTRACT_REF,
    PERMISSION_MANIFEST_REF,
    STRUCTURAL_CHECK_POLICY_REF,
    TASK_CONTRACT_REF,
    WORKSPACE_POLICY_REF,
)
from .product_contract import AcademicResearchRequest, DeepResearchRunResult, DeepResearchRunStatus
from .runtime import run_deepresearch_academic_single_agent
from .source_collector import AcademicSourceCollectionConfig
from .workspace import read_json_ref, ref_is_non_empty_file, write_json_ref, write_text_ref


JUDGE_SPEC_SCHEMA_VERSION = "missionforge_deepresearch.judge_spec.v1"
JUDGE_REPORT_SCHEMA_VERSION = "missionforge_deepresearch.judge_report.v1"
JUDGED_RUN_RESULT_SCHEMA_VERSION = "missionforge_deepresearch.judged_run_result.v1"
FINAL_PACKAGE_SCHEMA_VERSION = "missionforge_deepresearch.final_package.v1"
JUDGED_RUN_STATUSES = {"accepted", "repair", "revision_required", "rejected", "judge_failed"}

JUDGE_SPEC_REF = "judge/judge_spec.json"
JUDGE_MANUAL_REF = "manuals/deepresearch_judge.md"
JUDGE_PERMISSION_MANIFEST_REF = "policy/judge_permission_manifest.json"
JUDGE_CALL_REF = "attempts/judge/piworker_call.json"
JUDGE_CALL_RESULT_REF = "attempts/judge/piworker_call_result.json"
JUDGE_EXECUTION_REPORT_REF = "attempts/judge/execution_report.json"
JUDGE_METRICS_REF = "attempts/judge/metrics.json"
JUDGE_REPORT_REF = "reports/judge_report.json"
JUDGE_RATIONALE_REF = "reports/judge_rationale.md"
JUDGE_REPAIR_BRIEF_REF = "reports/judge_repair_brief.md"
JUDGE_REVISION_REQUEST_REF = "reports/judge_revision_request.md"
JUDGED_RUN_RESULT_REF = "packages/deepresearch_judged_run_result.json"
FINAL_PACKAGE_REF = "packages/deepresearch_final_package.json"
_JUDGE_REPORT_REQUIRED_FIELDS = [
    "schema_version",
    "report_id",
    "request_id",
    "decision",
    "hard_check_status",
    "judge_spec_ref",
    "contract_ref",
    "contract_hash",
    "judge_rubric_ref",
    "rationale_ref",
    "artifact_refs",
    "accepted_artifact_refs",
    "evidence_refs",
    "repair_brief_ref",
    "revision_request_ref",
]


@dataclass(frozen=True)
class DeepResearchJudgeReport:
    """Refs-first product judge report written by an independent Judge PiWorker."""

    report_id: str
    request_id: str
    decision: JudgeReportDecision
    hard_check_status: HardCheckStatus
    judge_spec_ref: str
    contract_ref: str
    contract_hash: str
    judge_rubric_ref: str
    rationale_ref: str
    artifact_refs: list[str] = field(default_factory=list)
    accepted_artifact_refs: list[str] = field(default_factory=list)
    evidence_refs: list[str] = field(default_factory=list)
    repair_brief_ref: str = ""
    revision_request_ref: str = ""
    schema_version: str = JUDGE_REPORT_SCHEMA_VERSION

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "DeepResearchJudgeReport":
        data = require_mapping(payload, "deepresearch_judge_report")
        report = cls(
            schema_version=require_non_empty_str(
                data.get("schema_version", JUDGE_REPORT_SCHEMA_VERSION),
                "deepresearch_judge_report.schema_version",
            ),
            report_id=require_non_empty_str(data.get("report_id"), "deepresearch_judge_report.report_id"),
            request_id=require_non_empty_str(data.get("request_id"), "deepresearch_judge_report.request_id"),
            decision=require_enum(data.get("decision"), JudgeReportDecision, "deepresearch_judge_report.decision"),
            hard_check_status=require_enum(
                data.get("hard_check_status"),
                HardCheckStatus,
                "deepresearch_judge_report.hard_check_status",
            ),
            judge_spec_ref=validate_ref(data.get("judge_spec_ref"), "deepresearch_judge_report.judge_spec_ref"),
            contract_ref=validate_ref(data.get("contract_ref"), "deepresearch_judge_report.contract_ref"),
            contract_hash=require_non_empty_str(data.get("contract_hash"), "deepresearch_judge_report.contract_hash"),
            judge_rubric_ref=validate_ref(data.get("judge_rubric_ref"), "deepresearch_judge_report.judge_rubric_ref"),
            rationale_ref=validate_ref(data.get("rationale_ref"), "deepresearch_judge_report.rationale_ref"),
            artifact_refs=_ref_list(data.get("artifact_refs", []), "deepresearch_judge_report.artifact_refs"),
            accepted_artifact_refs=_ref_list(
                data.get("accepted_artifact_refs", []),
                "deepresearch_judge_report.accepted_artifact_refs",
            ),
            evidence_refs=_ref_list(data.get("evidence_refs", []), "deepresearch_judge_report.evidence_refs"),
            repair_brief_ref=_optional_ref(data.get("repair_brief_ref", ""), "deepresearch_judge_report.repair_brief_ref"),
            revision_request_ref=_optional_ref(
                data.get("revision_request_ref", ""),
                "deepresearch_judge_report.revision_request_ref",
            ),
        )
        report.validate()
        return report

    def validate(self) -> None:
        if self.schema_version != JUDGE_REPORT_SCHEMA_VERSION:
            raise ContractValidationError("deepresearch_judge_report.schema_version is unsupported")
        require_non_empty_str(self.report_id, "deepresearch_judge_report.report_id")
        require_non_empty_str(self.request_id, "deepresearch_judge_report.request_id")
        require_enum(self.decision, JudgeReportDecision, "deepresearch_judge_report.decision")
        require_enum(self.hard_check_status, HardCheckStatus, "deepresearch_judge_report.hard_check_status")
        for field_name in ("judge_spec_ref", "contract_ref", "judge_rubric_ref", "rationale_ref"):
            validate_ref(getattr(self, field_name), f"deepresearch_judge_report.{field_name}")
        require_non_empty_str(self.contract_hash, "deepresearch_judge_report.contract_hash")
        _validate_unique_refs(self.artifact_refs, "deepresearch_judge_report.artifact_refs")
        _validate_unique_refs(self.accepted_artifact_refs, "deepresearch_judge_report.accepted_artifact_refs")
        _validate_unique_refs(self.evidence_refs, "deepresearch_judge_report.evidence_refs")
        _optional_ref(self.repair_brief_ref, "deepresearch_judge_report.repair_brief_ref")
        _optional_ref(self.revision_request_ref, "deepresearch_judge_report.revision_request_ref")
        if self.decision is JudgeReportDecision.ACCEPTED:
            if self.hard_check_status is not HardCheckStatus.PASSED:
                raise ContractValidationError("deepresearch_judge_report.accepted requires passed hard checks")
            if set(self.accepted_artifact_refs) != set(self.artifact_refs):
                raise ContractValidationError("deepresearch_judge_report.accepted must accept all artifact refs")
            if self.repair_brief_ref or self.revision_request_ref:
                raise ContractValidationError("deepresearch_judge_report.accepted cannot include repair or revision refs")
        else:
            if self.accepted_artifact_refs:
                raise ContractValidationError("deepresearch_judge_report non-accepted decision cannot accept artifacts")
        if self.decision is JudgeReportDecision.REPAIR and not self.repair_brief_ref:
            raise ContractValidationError("deepresearch_judge_report.repair requires repair_brief_ref")
        if self.decision is JudgeReportDecision.REVISION_REQUIRED and not self.revision_request_ref:
            raise ContractValidationError("deepresearch_judge_report.revision_required requires revision_request_ref")
        assert_refs_only_payload(self.to_dict_without_validation(), "deepresearch_judge_report")

    def to_dict_without_validation(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "report_id": self.report_id,
            "request_id": self.request_id,
            "decision": self.decision.value,
            "hard_check_status": self.hard_check_status.value,
            "judge_spec_ref": self.judge_spec_ref,
            "contract_ref": self.contract_ref,
            "contract_hash": self.contract_hash,
            "judge_rubric_ref": self.judge_rubric_ref,
            "rationale_ref": self.rationale_ref,
            "artifact_refs": list(self.artifact_refs),
            "accepted_artifact_refs": list(self.accepted_artifact_refs),
            "evidence_refs": list(self.evidence_refs),
            "repair_brief_ref": self.repair_brief_ref,
            "revision_request_ref": self.revision_request_ref,
        }

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return self.to_dict_without_validation()


@dataclass(frozen=True)
class DeepResearchJudgedRunResult:
    """Refs-first Phase 4 result for one independent judge decision."""

    request_id: str
    status: str
    run_workspace_ref: str
    source_run_result_ref: str
    judged_run_result_ref: str
    judge_spec_ref: str
    judge_call_ref: str
    judge_call_result_ref: str
    judge_report_ref: str
    judge_rationale_ref: str
    final_package_ref: str = ""
    repair_brief_ref: str = ""
    revision_request_ref: str = ""
    evidence_refs: list[str] = field(default_factory=list)
    metric_refs: list[str] = field(default_factory=list)
    schema_version: str = JUDGED_RUN_RESULT_SCHEMA_VERSION

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "DeepResearchJudgedRunResult":
        data = require_mapping(payload, "deepresearch_judged_run_result")
        result = cls(
            schema_version=require_non_empty_str(
                data.get("schema_version", JUDGED_RUN_RESULT_SCHEMA_VERSION),
                "deepresearch_judged_run_result.schema_version",
            ),
            request_id=require_non_empty_str(data.get("request_id"), "deepresearch_judged_run_result.request_id"),
            status=require_enum_like(data.get("status"), JUDGED_RUN_STATUSES, "deepresearch_judged_run_result.status"),
            run_workspace_ref=validate_ref(data.get("run_workspace_ref"), "deepresearch_judged_run_result.run_workspace_ref"),
            source_run_result_ref=validate_ref(
                data.get("source_run_result_ref"),
                "deepresearch_judged_run_result.source_run_result_ref",
            ),
            judged_run_result_ref=validate_ref(
                data.get("judged_run_result_ref"),
                "deepresearch_judged_run_result.judged_run_result_ref",
            ),
            judge_spec_ref=validate_ref(data.get("judge_spec_ref"), "deepresearch_judged_run_result.judge_spec_ref"),
            judge_call_ref=validate_ref(data.get("judge_call_ref"), "deepresearch_judged_run_result.judge_call_ref"),
            judge_call_result_ref=validate_ref(
                data.get("judge_call_result_ref"),
                "deepresearch_judged_run_result.judge_call_result_ref",
            ),
            judge_report_ref=validate_ref(data.get("judge_report_ref"), "deepresearch_judged_run_result.judge_report_ref"),
            judge_rationale_ref=validate_ref(
                data.get("judge_rationale_ref"),
                "deepresearch_judged_run_result.judge_rationale_ref",
            ),
            final_package_ref=_optional_ref(
                data.get("final_package_ref", ""),
                "deepresearch_judged_run_result.final_package_ref",
            ),
            repair_brief_ref=_optional_ref(
                data.get("repair_brief_ref", ""),
                "deepresearch_judged_run_result.repair_brief_ref",
            ),
            revision_request_ref=_optional_ref(
                data.get("revision_request_ref", ""),
                "deepresearch_judged_run_result.revision_request_ref",
            ),
            evidence_refs=_ref_list(data.get("evidence_refs", []), "deepresearch_judged_run_result.evidence_refs"),
            metric_refs=_ref_list(data.get("metric_refs", []), "deepresearch_judged_run_result.metric_refs"),
        )
        result.validate()
        return result

    def validate(self) -> None:
        if self.schema_version != JUDGED_RUN_RESULT_SCHEMA_VERSION:
            raise ContractValidationError("deepresearch_judged_run_result.schema_version is unsupported")
        require_non_empty_str(self.request_id, "deepresearch_judged_run_result.request_id")
        require_enum_like(self.status, JUDGED_RUN_STATUSES, "deepresearch_judged_run_result.status")
        for field_name in (
            "run_workspace_ref",
            "source_run_result_ref",
            "judged_run_result_ref",
            "judge_spec_ref",
            "judge_call_ref",
            "judge_call_result_ref",
            "judge_report_ref",
            "judge_rationale_ref",
        ):
            validate_ref(getattr(self, field_name), f"deepresearch_judged_run_result.{field_name}")
        _optional_ref(self.final_package_ref, "deepresearch_judged_run_result.final_package_ref")
        _optional_ref(self.repair_brief_ref, "deepresearch_judged_run_result.repair_brief_ref")
        _optional_ref(self.revision_request_ref, "deepresearch_judged_run_result.revision_request_ref")
        if self.status == "accepted" and not self.final_package_ref:
            raise ContractValidationError("deepresearch_judged_run_result.accepted requires final_package_ref")
        if self.status != "accepted" and self.final_package_ref:
            raise ContractValidationError("deepresearch_judged_run_result final_package_ref requires accepted status")
        _validate_unique_refs(self.evidence_refs, "deepresearch_judged_run_result.evidence_refs")
        _validate_unique_refs(self.metric_refs, "deepresearch_judged_run_result.metric_refs")
        assert_refs_only_payload(self.to_dict_without_validation(), "deepresearch_judged_run_result")

    def to_dict_without_validation(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "request_id": self.request_id,
            "status": self.status,
            "run_workspace_ref": self.run_workspace_ref,
            "source_run_result_ref": self.source_run_result_ref,
            "judged_run_result_ref": self.judged_run_result_ref,
            "judge_spec_ref": self.judge_spec_ref,
            "judge_call_ref": self.judge_call_ref,
            "judge_call_result_ref": self.judge_call_result_ref,
            "judge_report_ref": self.judge_report_ref,
            "judge_rationale_ref": self.judge_rationale_ref,
            "final_package_ref": self.final_package_ref,
            "repair_brief_ref": self.repair_brief_ref,
            "revision_request_ref": self.revision_request_ref,
            "evidence_refs": list(self.evidence_refs),
            "metric_refs": list(self.metric_refs),
        }

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return self.to_dict_without_validation()


@dataclass(frozen=True)
class DeepResearchFinalPackage:
    """Final user-visible package refs emitted only after judge acceptance."""

    request_id: str
    run_workspace_ref: str
    final_package_ref: str
    source_run_result_ref: str
    judge_report_ref: str
    accepted_artifact_refs: list[str]
    evidence_refs: list[str]
    metric_refs: list[str]
    contract_hash: str
    status: str = "accepted"
    schema_version: str = FINAL_PACKAGE_SCHEMA_VERSION

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "DeepResearchFinalPackage":
        data = require_mapping(payload, "deepresearch_final_package")
        package = cls(
            schema_version=require_non_empty_str(
                data.get("schema_version", FINAL_PACKAGE_SCHEMA_VERSION),
                "deepresearch_final_package.schema_version",
            ),
            request_id=require_non_empty_str(data.get("request_id"), "deepresearch_final_package.request_id"),
            status=require_enum_like(data.get("status", "accepted"), {"accepted"}, "deepresearch_final_package.status"),
            run_workspace_ref=validate_ref(data.get("run_workspace_ref"), "deepresearch_final_package.run_workspace_ref"),
            final_package_ref=validate_ref(data.get("final_package_ref"), "deepresearch_final_package.final_package_ref"),
            source_run_result_ref=validate_ref(
                data.get("source_run_result_ref"),
                "deepresearch_final_package.source_run_result_ref",
            ),
            judge_report_ref=validate_ref(data.get("judge_report_ref"), "deepresearch_final_package.judge_report_ref"),
            accepted_artifact_refs=_ref_list(
                data.get("accepted_artifact_refs", []),
                "deepresearch_final_package.accepted_artifact_refs",
            ),
            evidence_refs=_ref_list(data.get("evidence_refs", []), "deepresearch_final_package.evidence_refs"),
            metric_refs=_ref_list(data.get("metric_refs", []), "deepresearch_final_package.metric_refs"),
            contract_hash=require_non_empty_str(data.get("contract_hash"), "deepresearch_final_package.contract_hash"),
        )
        package.validate()
        return package

    def validate(self) -> None:
        if self.schema_version != FINAL_PACKAGE_SCHEMA_VERSION:
            raise ContractValidationError("deepresearch_final_package.schema_version is unsupported")
        if self.status != "accepted":
            raise ContractValidationError("deepresearch_final_package.status must be accepted")
        for field_name in ("run_workspace_ref", "final_package_ref", "source_run_result_ref", "judge_report_ref"):
            validate_ref(getattr(self, field_name), f"deepresearch_final_package.{field_name}")
        _validate_unique_refs(self.accepted_artifact_refs, "deepresearch_final_package.accepted_artifact_refs")
        if not self.accepted_artifact_refs:
            raise ContractValidationError("deepresearch_final_package.accepted_artifact_refs must not be empty")
        _validate_unique_refs(self.evidence_refs, "deepresearch_final_package.evidence_refs")
        _validate_unique_refs(self.metric_refs, "deepresearch_final_package.metric_refs")
        require_non_empty_str(self.contract_hash, "deepresearch_final_package.contract_hash")
        assert_refs_only_payload(self.to_dict_without_validation(), "deepresearch_final_package")

    def to_dict_without_validation(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "request_id": self.request_id,
            "status": self.status,
            "run_workspace_ref": self.run_workspace_ref,
            "final_package_ref": self.final_package_ref,
            "source_run_result_ref": self.source_run_result_ref,
            "judge_report_ref": self.judge_report_ref,
            "accepted_artifact_refs": list(self.accepted_artifact_refs),
            "evidence_refs": list(self.evidence_refs),
            "metric_refs": list(self.metric_refs),
            "contract_hash": self.contract_hash,
        }

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return self.to_dict_without_validation()


def run_deepresearch_academic_judged(
    request: AcademicResearchRequest,
    *,
    workspace: str | Path = ".",
    researcher_adapter: PiWorkerCallAdapter | None = None,
    judge_adapter: PiWorkerCallAdapter | None = None,
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
) -> DeepResearchJudgedRunResult:
    """Run the DeepResearch draft path and submit it to an independent judge."""

    run_result = run_deepresearch_academic_single_agent(
        request,
        workspace=workspace,
        adapter=researcher_adapter,
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
    return judge_deepresearch_run(
        request,
        workspace=workspace,
        run_result=run_result,
        adapter=judge_adapter,
        piworker_config=piworker_config,
        piworker_environ=piworker_environ,
    )


def judge_deepresearch_run(
    request: AcademicResearchRequest,
    *,
    workspace: str | Path,
    run_result: DeepResearchRunResult,
    adapter: PiWorkerCallAdapter | None = None,
    piworker_config: PiAgentRuntimeConfig | None = None,
    piworker_environ: Mapping[str, str] | None = None,
) -> DeepResearchJudgedRunResult:
    """Run only the independent judge over an existing draft-ready result."""

    request.validate()
    run_result.validate()
    if run_result.status is not DeepResearchRunStatus.DRAFT_READY:
        raise ContractValidationError("deepresearch judge requires a draft_ready run result")
    root = Path(workspace).resolve()
    run_root = root / run_result.run_workspace_ref
    hard_check_status = _hard_check_status(run_root, _inner_ref(run_result.run_workspace_ref, run_result.structural_check_ref))
    task_contract = read_json_ref(run_root, TASK_CONTRACT_REF, "task_contract")
    permission_manifest = PermissionManifest(
        manifest_id=f"deepresearch-{request.request_id}-judge-permissions",
        workspace_policy_ref=WORKSPACE_POLICY_REF,
        readable_refs=[
            "contract",
            "compiled",
            "judge",
            "manuals",
            "packages",
            "policy",
            "product_contract",
            "projections",
            "reports",
            "sources",
            "attempts",
        ],
        writable_refs=["reports", "attempts"],
        denied_refs=["secrets"],
        network_policy=NetworkPolicy.DISABLED,
    )
    write_json_ref(run_root, JUDGE_PERMISSION_MANIFEST_REF, permission_manifest.to_dict())
    write_text_ref(run_root, JUDGE_MANUAL_REF, _judge_manual_text())
    artifact_refs = [_inner_ref(run_result.run_workspace_ref, ref) for ref in run_result.draft_artifact_refs]
    evidence_refs = _dedupe_refs(
        [_inner_ref(run_result.run_workspace_ref, ref) for ref in run_result.evidence_refs if _is_in_run(run_result.run_workspace_ref, ref)]
    )
    metric_refs = _dedupe_refs(
        [_inner_ref(run_result.run_workspace_ref, ref) for ref in run_result.metric_refs if _is_in_run(run_result.run_workspace_ref, ref)]
    )
    source_run_result_ref = _inner_ref(run_result.run_workspace_ref, run_result.run_result_ref)
    spec = {
        "schema_version": JUDGE_SPEC_SCHEMA_VERSION,
        "request_id": request.request_id,
        "source_run_result_ref": source_run_result_ref,
        "contract_ref": TASK_CONTRACT_REF,
        "contract_hash": run_result.contract_hash,
        "judge_rubric_ref": JUDGE_RUBRIC_REF,
        "manual_ref": JUDGE_MANUAL_REF,
        "output_contract_ref": OUTPUT_CONTRACT_REF,
        "structural_check_ref": _inner_ref(run_result.run_workspace_ref, run_result.structural_check_ref),
        "structural_check_policy_ref": STRUCTURAL_CHECK_POLICY_REF,
        "hard_check_status": hard_check_status.value,
        "artifact_refs": artifact_refs,
        "evidence_refs": evidence_refs,
        "metric_refs": metric_refs,
        "required_report_ref": JUDGE_REPORT_REF,
        "required_rationale_ref": JUDGE_RATIONALE_REF,
        "optional_repair_brief_ref": JUDGE_REPAIR_BRIEF_REF,
        "optional_revision_request_ref": JUDGE_REVISION_REQUEST_REF,
        "allowed_decisions": [item.value for item in JudgeReportDecision],
        "required_report_shape": _required_judge_report_shape(),
    }
    _validate_judge_spec(spec)
    write_json_ref(run_root, JUDGE_SPEC_REF, spec)
    call = PiWorkerCall(
        call_id=f"deepresearch-{request.request_id}-judge",
        role=PiWorkerCallRole.JUDGE,
        contract_id=require_non_empty_str(task_contract.get("contract_id"), "task_contract.contract_id"),
        contract_hash=run_result.contract_hash,
        contract_ref=TASK_CONTRACT_REF,
        objective=(
            "Independently judge the DeepResearch draft against the frozen contract, "
            "judge rubric, hard checks, artifact refs, and evidence refs. "
            "Write the required judge report JSON and rationale ref only."
        ),
        visible_refs=_dedupe_refs(
            [
                JUDGE_SPEC_REF,
                JUDGE_MANUAL_REF,
                TASK_CONTRACT_REF,
                JUDGE_RUBRIC_REF,
                OUTPUT_CONTRACT_REF,
                STRUCTURAL_CHECK_POLICY_REF,
                _inner_ref(run_result.run_workspace_ref, run_result.structural_check_ref),
                source_run_result_ref,
                JUDGE_PERMISSION_MANIFEST_REF,
                *artifact_refs,
                *evidence_refs,
                *metric_refs,
            ]
        ),
        writable_refs=list(permission_manifest.writable_refs),
        expected_output_refs=[JUDGE_REPORT_REF, JUDGE_RATIONALE_REF],
        permission_manifest_ref=JUDGE_PERMISSION_MANIFEST_REF,
        source_packet_ref=JUDGE_SPEC_REF,
        source_packet_hash=stable_json_hash(spec),
        evidence_refs=_dedupe_refs([JUDGE_SPEC_REF, source_run_result_ref, *artifact_refs, *evidence_refs]),
        output_schema_ref=JUDGE_SPEC_REF,
        validation_policy_ref=JUDGE_SPEC_REF,
        runtime_budget={"max_turns": 6},
        metadata={"phase": "phase4_independent_judge"},
    )
    write_json_ref(run_root, JUDGE_CALL_REF, call.to_dict())
    worker = adapter or _piworker_adapter(piworker_config, piworker_environ)
    call_result = run_piworker_call(
        call,
        workspace=run_root,
        adapter=worker,
        result_id=f"{call.call_id}-result",
        metadata={"phase": "phase4_independent_judge"},
    )
    write_json_ref(run_root, JUDGE_CALL_RESULT_REF, call_result.to_dict())
    if call_result.status is not PiWorkerCallResultStatus.COMPLETED:
        return _write_judged_result(
            root,
            run_result=run_result,
            status="judge_failed",
            call_result_metric_refs=call_result.metric_refs,
        )
    if not ref_is_non_empty_file(run_root, JUDGE_REPORT_REF) or not ref_is_non_empty_file(run_root, JUDGE_RATIONALE_REF):
        raise ContractValidationError("deepresearch judge did not produce required report refs")
    raw_judge_report = read_json_ref(run_root, JUDGE_REPORT_REF, "deepresearch_judge_report")
    normalized_judge_report = _normalize_judge_report_payload(raw_judge_report, spec=spec, call_id=call.call_id)
    judge_report = DeepResearchJudgeReport.from_dict(normalized_judge_report)
    _validate_judge_report_against_spec(judge_report, spec)
    if normalized_judge_report != raw_judge_report:
        write_json_ref(run_root, JUDGE_REPORT_REF, judge_report.to_dict())
    final_package_ref = ""
    if judge_report.decision is JudgeReportDecision.ACCEPTED:
        final_package = DeepResearchFinalPackage(
            request_id=request.request_id,
            run_workspace_ref=run_result.run_workspace_ref,
            final_package_ref=_outer_ref(run_result.run_workspace_ref, FINAL_PACKAGE_REF),
            source_run_result_ref=run_result.run_result_ref,
            judge_report_ref=_outer_ref(run_result.run_workspace_ref, JUDGE_REPORT_REF),
            accepted_artifact_refs=[_outer_ref(run_result.run_workspace_ref, ref) for ref in judge_report.accepted_artifact_refs],
            evidence_refs=_dedupe_refs(
                [
                    run_result.run_result_ref,
                    _outer_ref(run_result.run_workspace_ref, JUDGE_REPORT_REF),
                    _outer_ref(run_result.run_workspace_ref, JUDGE_RATIONALE_REF),
                    *run_result.evidence_refs,
                    *[_outer_ref(run_result.run_workspace_ref, ref) for ref in judge_report.evidence_refs],
                ]
            ),
            metric_refs=_dedupe_refs([*run_result.metric_refs, *[_outer_ref(run_result.run_workspace_ref, ref) for ref in call_result.metric_refs]]),
            contract_hash=run_result.contract_hash,
        )
        write_json_ref(root, final_package.final_package_ref, final_package.to_dict())
        final_package_ref = final_package.final_package_ref
    return _write_judged_result(
        root,
        run_result=run_result,
        status=judge_report.decision.value,
        final_package_ref=final_package_ref,
        repair_brief_ref=_outer_ref(run_result.run_workspace_ref, judge_report.repair_brief_ref) if judge_report.repair_brief_ref else "",
        revision_request_ref=_outer_ref(run_result.run_workspace_ref, judge_report.revision_request_ref)
        if judge_report.revision_request_ref
        else "",
        call_result_metric_refs=call_result.metric_refs,
    )


class FixtureDeepResearchJudgeAdapter:
    """Offline independent judge adapter for Phase 4 contract tests."""

    adapter_family = "fixture_deepresearch_judge"

    def __init__(self, decision: str = "accepted") -> None:
        self.decision = require_enum(decision, JudgeReportDecision, "fixture_judge.decision")

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
            raise ContractValidationError("fixture DeepResearch judge only supports judge calls")
        root = Path(workspace).resolve()
        spec = read_json_ref(root, JUDGE_SPEC_REF, "deepresearch_judge_spec")
        write_text_ref(root, JUDGE_RATIONALE_REF, "# Judge Rationale\n\nFixture judge rationale.\n")
        repair_brief_ref = ""
        revision_request_ref = ""
        if self.decision is JudgeReportDecision.REPAIR:
            repair_brief_ref = JUDGE_REPAIR_BRIEF_REF
            write_text_ref(root, repair_brief_ref, "# Repair Brief\n\nFixture repair request.\n")
        if self.decision is JudgeReportDecision.REVISION_REQUIRED:
            revision_request_ref = JUDGE_REVISION_REQUEST_REF
            write_text_ref(root, revision_request_ref, "# Revision Request\n\nFixture revision request.\n")
        accepted_artifact_refs = list(spec["artifact_refs"]) if self.decision is JudgeReportDecision.ACCEPTED else []
        report = DeepResearchJudgeReport(
            report_id=f"{call.call_id}-report",
            request_id=require_non_empty_str(spec.get("request_id"), "deepresearch_judge_spec.request_id"),
            decision=self.decision,
            hard_check_status=require_enum(spec.get("hard_check_status"), HardCheckStatus, "deepresearch_judge_spec.hard_check_status"),
            judge_spec_ref=JUDGE_SPEC_REF,
            contract_ref=TASK_CONTRACT_REF,
            contract_hash=require_non_empty_str(spec.get("contract_hash"), "deepresearch_judge_spec.contract_hash"),
            judge_rubric_ref=JUDGE_RUBRIC_REF,
            rationale_ref=JUDGE_RATIONALE_REF,
            artifact_refs=list(spec["artifact_refs"]),
            accepted_artifact_refs=accepted_artifact_refs,
            evidence_refs=[JUDGE_SPEC_REF, *list(spec["artifact_refs"])],
            repair_brief_ref=repair_brief_ref,
            revision_request_ref=revision_request_ref,
        )
        write_json_ref(root, JUDGE_REPORT_REF, report.to_dict())
        metrics = {"metric_ref": JUDGE_METRICS_REF, "fixture": True}
        write_json_ref(root, JUDGE_METRICS_REF, metrics)
        produced = [JUDGE_REPORT_REF, JUDGE_RATIONALE_REF]
        changed = [JUDGE_REPORT_REF, JUDGE_RATIONALE_REF, JUDGE_EXECUTION_REPORT_REF, JUDGE_METRICS_REF]
        if repair_brief_ref:
            changed.append(repair_brief_ref)
        if revision_request_ref:
            changed.append(revision_request_ref)
        execution_report = ExecutionReport(
            report_id="deepresearch-fixture-judge-execution-report",
            call_id=call.call_id,
            status="completed",
            produced_artifacts=produced,
            changed_refs=changed,
            evidence_refs=[JUDGE_SPEC_REF, JUDGE_REPORT_REF],
            worker_claims=["fixture judge produced independent decision"],
            metrics=metrics,
        )
        write_json_ref(root, JUDGE_EXECUTION_REPORT_REF, execution_report.to_dict())
        return WorkerAdapterResult(
            execution_report=execution_report,
            worker_result=WorkerResult(status="completed", execution_report_ref=JUDGE_EXECUTION_REPORT_REF),
            event_evidence_refs=[],
            metrics=metrics,
        )


def load_deepresearch_judged_run_result(workspace: str | Path, ref: str) -> DeepResearchJudgedRunResult:
    """Load a refs-first Phase 4 judged run result."""

    return DeepResearchJudgedRunResult.from_dict(read_json_ref(workspace, ref, "deepresearch_judged_run_result"))


def load_deepresearch_final_package(workspace: str | Path, ref: str) -> DeepResearchFinalPackage:
    """Load a final package emitted after judge acceptance."""

    return DeepResearchFinalPackage.from_dict(read_json_ref(workspace, ref, "deepresearch_final_package"))


def _write_judged_result(
    root: Path,
    *,
    run_result: DeepResearchRunResult,
    status: str,
    final_package_ref: str = "",
    repair_brief_ref: str = "",
    revision_request_ref: str = "",
    call_result_metric_refs: list[str],
) -> DeepResearchJudgedRunResult:
    result = DeepResearchJudgedRunResult(
        request_id=run_result.request_id,
        status=status,
        run_workspace_ref=run_result.run_workspace_ref,
        source_run_result_ref=run_result.run_result_ref,
        judged_run_result_ref=_outer_ref(run_result.run_workspace_ref, JUDGED_RUN_RESULT_REF),
        judge_spec_ref=_outer_ref(run_result.run_workspace_ref, JUDGE_SPEC_REF),
        judge_call_ref=_outer_ref(run_result.run_workspace_ref, JUDGE_CALL_REF),
        judge_call_result_ref=_outer_ref(run_result.run_workspace_ref, JUDGE_CALL_RESULT_REF),
        judge_report_ref=_outer_ref(run_result.run_workspace_ref, JUDGE_REPORT_REF),
        judge_rationale_ref=_outer_ref(run_result.run_workspace_ref, JUDGE_RATIONALE_REF),
        final_package_ref=final_package_ref,
        repair_brief_ref=repair_brief_ref,
        revision_request_ref=revision_request_ref,
        evidence_refs=_dedupe_refs(
            [
                run_result.run_result_ref,
                _outer_ref(run_result.run_workspace_ref, JUDGE_SPEC_REF),
                _outer_ref(run_result.run_workspace_ref, JUDGE_CALL_REF),
                _outer_ref(run_result.run_workspace_ref, JUDGE_CALL_RESULT_REF),
                _outer_ref(run_result.run_workspace_ref, JUDGE_REPORT_REF),
                _outer_ref(run_result.run_workspace_ref, JUDGE_RATIONALE_REF),
            ]
        ),
        metric_refs=_dedupe_refs([*run_result.metric_refs, *[_outer_ref(run_result.run_workspace_ref, ref) for ref in call_result_metric_refs]]),
    )
    write_json_ref(root, result.judged_run_result_ref, result.to_dict())
    return result


def _validate_judge_spec(spec: Mapping[str, Any]) -> None:
    data = require_mapping(spec, "deepresearch_judge_spec")
    if require_non_empty_str(data.get("schema_version"), "deepresearch_judge_spec.schema_version") != JUDGE_SPEC_SCHEMA_VERSION:
        raise ContractValidationError("deepresearch_judge_spec.schema_version is unsupported")
    require_non_empty_str(data.get("request_id"), "deepresearch_judge_spec.request_id")
    for field_name in (
        "source_run_result_ref",
        "contract_ref",
        "judge_rubric_ref",
        "manual_ref",
        "output_contract_ref",
        "structural_check_ref",
        "structural_check_policy_ref",
        "required_report_ref",
        "required_rationale_ref",
        "optional_repair_brief_ref",
        "optional_revision_request_ref",
    ):
        validate_ref(data.get(field_name), f"deepresearch_judge_spec.{field_name}")
    require_non_empty_str(data.get("contract_hash"), "deepresearch_judge_spec.contract_hash")
    require_enum(data.get("hard_check_status"), HardCheckStatus, "deepresearch_judge_spec.hard_check_status")
    _validate_unique_refs(_ref_list(data.get("artifact_refs", []), "deepresearch_judge_spec.artifact_refs"), "deepresearch_judge_spec.artifact_refs")
    if not data.get("artifact_refs"):
        raise ContractValidationError("deepresearch_judge_spec.artifact_refs must not be empty")
    _validate_unique_refs(_ref_list(data.get("evidence_refs", []), "deepresearch_judge_spec.evidence_refs"), "deepresearch_judge_spec.evidence_refs")
    _validate_unique_refs(_ref_list(data.get("metric_refs", []), "deepresearch_judge_spec.metric_refs"), "deepresearch_judge_spec.metric_refs")
    decisions = require_str_list(data.get("allowed_decisions", []), "deepresearch_judge_spec.allowed_decisions")
    if sorted(decisions) != sorted(item.value for item in JudgeReportDecision):
        raise ContractValidationError("deepresearch_judge_spec.allowed_decisions must match judge decision vocabulary")
    report_shape = require_mapping(data.get("required_report_shape", {}), "deepresearch_judge_spec.required_report_shape")
    if require_non_empty_str(
        report_shape.get("schema_version"),
        "deepresearch_judge_spec.required_report_shape.schema_version",
    ) != JUDGE_REPORT_SCHEMA_VERSION:
        raise ContractValidationError("deepresearch_judge_spec.required_report_shape.schema_version is unsupported")
    required_fields = require_str_list(
        report_shape.get("required_fields", []),
        "deepresearch_judge_spec.required_report_shape.required_fields",
    )
    if sorted(required_fields) != sorted(_JUDGE_REPORT_REQUIRED_FIELDS):
        raise ContractValidationError("deepresearch_judge_spec.required_report_shape.required_fields does not match")
    for field_name in (
        "report_ref",
        "rationale_ref",
        "repair_decision_requires_repair_brief_ref",
        "revision_required_decision_requires_revision_request_ref",
    ):
        validate_ref(report_shape.get(field_name), f"deepresearch_judge_spec.required_report_shape.{field_name}")
    assert_refs_only_payload(data, "deepresearch_judge_spec")


def _validate_judge_report_against_spec(report: DeepResearchJudgeReport, spec: Mapping[str, Any]) -> None:
    report.validate()
    if report.request_id != spec.get("request_id"):
        raise ContractValidationError("deepresearch judge report request_id does not match spec")
    if report.judge_spec_ref != JUDGE_SPEC_REF:
        raise ContractValidationError("deepresearch judge report judge_spec_ref does not match")
    if report.contract_ref != spec.get("contract_ref"):
        raise ContractValidationError("deepresearch judge report contract_ref does not match spec")
    if report.contract_hash != spec.get("contract_hash"):
        raise ContractValidationError("deepresearch judge report contract_hash does not match spec")
    if report.judge_rubric_ref != spec.get("judge_rubric_ref"):
        raise ContractValidationError("deepresearch judge report judge_rubric_ref does not match spec")
    if report.rationale_ref != spec.get("required_rationale_ref"):
        raise ContractValidationError("deepresearch judge report rationale_ref does not match spec")
    if set(report.artifact_refs) != set(spec.get("artifact_refs", [])):
        raise ContractValidationError("deepresearch judge report artifact refs do not match spec")
    if report.hard_check_status.value != spec.get("hard_check_status"):
        raise ContractValidationError("deepresearch judge report hard_check_status does not match spec")
    for ref in report.evidence_refs:
        if ref not in set([JUDGE_SPEC_REF, *spec.get("artifact_refs", []), *spec.get("evidence_refs", []), *spec.get("metric_refs", [])]):
            raise ContractValidationError("deepresearch judge report evidence ref was not visible to judge")


def _required_judge_report_shape() -> dict[str, Any]:
    return {
        "schema_version": JUDGE_REPORT_SCHEMA_VERSION,
        "required_fields": list(_JUDGE_REPORT_REQUIRED_FIELDS),
        "report_ref": JUDGE_REPORT_REF,
        "rationale_ref": JUDGE_RATIONALE_REF,
        "accepted_requires_all_artifacts": True,
        "non_accepted_requires_empty_accepted_artifacts": True,
        "repair_decision_requires_repair_brief_ref": JUDGE_REPAIR_BRIEF_REF,
        "revision_required_decision_requires_revision_request_ref": JUDGE_REVISION_REQUEST_REF,
    }


def _normalize_judge_report_payload(
    payload: Mapping[str, Any],
    *,
    spec: Mapping[str, Any],
    call_id: str,
) -> dict[str, Any]:
    """Apply mechanical schema aliases without changing the judge decision."""

    data = require_mapping(payload, "deepresearch_judge_report")
    normalized = {field_name: data[field_name] for field_name in _JUDGE_REPORT_REQUIRED_FIELDS if field_name in data}
    if "artifact_refs" not in normalized and "artifact_refs_reviewed" in data:
        normalized["artifact_refs"] = data["artifact_refs_reviewed"]
    if "evidence_refs" not in normalized and "evidence_refs_reviewed" in data:
        normalized["evidence_refs"] = data["evidence_refs_reviewed"]

    _set_if_missing(normalized, "schema_version", JUDGE_REPORT_SCHEMA_VERSION)
    _set_if_missing(normalized, "report_id", f"{call_id}-report")
    _set_if_missing(normalized, "request_id", spec.get("request_id"))
    _set_if_missing(normalized, "hard_check_status", spec.get("hard_check_status"))
    _set_if_missing(normalized, "judge_spec_ref", JUDGE_SPEC_REF)
    _set_if_missing(normalized, "contract_ref", spec.get("contract_ref"))
    _set_if_missing(normalized, "contract_hash", spec.get("contract_hash"))
    _set_if_missing(normalized, "judge_rubric_ref", spec.get("judge_rubric_ref"))
    _set_if_missing(normalized, "rationale_ref", spec.get("required_rationale_ref"))
    if "artifact_refs" not in normalized:
        normalized["artifact_refs"] = list(spec.get("artifact_refs", []))
    if "evidence_refs" not in normalized:
        normalized["evidence_refs"] = []

    decision = require_enum(normalized.get("decision"), JudgeReportDecision, "deepresearch_judge_report.decision")
    if "accepted_artifact_refs" not in normalized:
        normalized["accepted_artifact_refs"] = (
            list(normalized["artifact_refs"]) if decision is JudgeReportDecision.ACCEPTED else []
        )
    if "repair_brief_ref" not in normalized:
        normalized["repair_brief_ref"] = ""
    if "revision_request_ref" not in normalized:
        normalized["revision_request_ref"] = ""
    return normalized


def _set_if_missing(payload: dict[str, Any], field_name: str, value: Any) -> None:
    if payload.get(field_name) in (None, ""):
        payload[field_name] = value


def _judge_manual_text() -> str:
    return """# DeepResearch Judge Manual

You are the independent DeepResearch judge. Use only the frozen task contract,
judge rubric, hard checks, draft artifact refs, and evidence refs listed in
`judge/judge_spec.json`.

Write:

- `reports/judge_report.json`
- `reports/judge_rationale.md`

The JSON report must use schema `missionforge_deepresearch.judge_report.v1`.
Choose exactly one decision:

- `accepted`
- `repair`
- `revision_required`
- `rejected`

Only use `accepted` when all artifact refs satisfy the frozen contract and
hard checks passed. Use `repair` for same-contract fixes and write
`reports/judge_repair_brief.md`. Use `revision_required` only when the frozen
contract itself must change and write `reports/judge_revision_request.md`.
Do not modify draft artifacts.

`reports/judge_report.json` must be a single JSON object with exactly this
shape:

```json
{
  "schema_version": "missionforge_deepresearch.judge_report.v1",
  "report_id": "deepresearch-REQUEST_ID-judge-report",
  "request_id": "copy from judge/judge_spec.json",
  "decision": "accepted | repair | revision_required | rejected",
  "hard_check_status": "copy from judge/judge_spec.json",
  "judge_spec_ref": "judge/judge_spec.json",
  "contract_ref": "copy from judge/judge_spec.json",
  "contract_hash": "copy from judge/judge_spec.json",
  "judge_rubric_ref": "copy from judge/judge_spec.json",
  "rationale_ref": "copy required_rationale_ref from judge/judge_spec.json",
  "artifact_refs": ["copy every artifact_refs item from judge/judge_spec.json"],
  "accepted_artifact_refs": ["same as artifact_refs only when decision is accepted"],
  "evidence_refs": ["refs you relied on; each must be visible in judge/judge_spec.json"],
  "repair_brief_ref": "",
  "revision_request_ref": ""
}
```

Do not rename these keys. Put explanatory findings in
`reports/judge_rationale.md`, not in the JSON report.
"""


def _hard_check_status(workspace: Path, structural_check_ref: str) -> HardCheckStatus:
    if not ref_is_non_empty_file(workspace, structural_check_ref):
        return HardCheckStatus.MISSING
    structural = read_json_ref(workspace, structural_check_ref, "deepresearch_structural_check_report")
    return HardCheckStatus.PASSED if structural.get("status") == "passed" else HardCheckStatus.FAILED


def _piworker_adapter(
    piworker_config: PiAgentRuntimeConfig | None,
    piworker_environ: Mapping[str, str] | None,
) -> PiWorkerCallAdapter:
    return PiAgentRuntimeAdapter(
        piworker_config or PiAgentRuntimeConfig(provider_mode="live"),
        environ=piworker_environ,
    )


def _inner_ref(run_workspace_ref: str, ref: str) -> str:
    run_ref = validate_ref(run_workspace_ref, "run_workspace_ref")
    safe_ref = validate_ref(ref, "ref")
    prefix = f"{run_ref}/"
    if safe_ref.startswith(prefix):
        return safe_ref[len(prefix) :]
    return safe_ref


def _outer_ref(run_workspace_ref: str, ref: str) -> str:
    return f"{validate_ref(run_workspace_ref, 'run_workspace_ref')}/{validate_ref(ref, 'run_ref')}"


def _is_in_run(run_workspace_ref: str, ref: str) -> bool:
    safe_run = validate_ref(run_workspace_ref, "run_workspace_ref")
    safe_ref = validate_ref(ref, "ref")
    return safe_ref == safe_run or safe_ref.startswith(f"{safe_run}/")


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


def _optional_ref(value: Any, field_name: str) -> str:
    if value is None or value == "":
        return ""
    return validate_ref(value, field_name)


def _validate_unique_refs(values: list[str], field_name: str) -> None:
    refs = _ref_list(values, field_name)
    if len(refs) != len(set(refs)):
        raise ContractValidationError(f"{field_name} must not contain duplicate refs")


def require_enum_like(value: Any, allowed: set[str], field_name: str) -> str:
    text = require_non_empty_str(value, field_name)
    if text not in allowed:
        raise ContractValidationError(f"{field_name} must be one of {sorted(allowed)}")
    return text
