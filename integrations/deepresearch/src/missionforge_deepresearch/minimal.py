"""Minimal skill-like DeepResearch orchestration.

This path intentionally keeps Python small: it freezes refs, writes a strong
manual, calls one PiWorker, and performs boundary validation. The model owns
research strategy, source triage, synthesis, and report writing.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

from missionforge.adapters.pi_agent_runtime import PiAgentRuntimeAdapter, PiAgentRuntimeConfig
from missionforge.contracts import ContractValidationError, stable_json_hash, validate_ref
from missionforge.extensions import compile_extension_lock, npm_install_extension, write_extension_lock
from missionforge.piworker_call import PiWorkerCall, PiWorkerCallResultStatus, PiWorkerCallRole
from missionforge.piworker_runtime import PiWorkerCallAdapter, run_piworker_call
from missionforge.runtime_results import ExecutionReport, WorkerAdapterResult, WorkerResult
from missionforge.task_contract import ExtensionGrant, NetworkPolicy, PermissionManifest, WorkspacePolicy

from .evidence import audit_report_citations, audit_source_packet
from .extension_grants import academic_deepresearch_extension_grants
from .product_contract import AcademicResearchRequest, research_intensity_profile, research_report_section_specs
from .workspace import read_json_ref, read_text_ref, ref_is_non_empty_file, write_json_ref, write_text_ref


MINIMAL_RESULT_REF = "packages/deepresearch_minimal_result.json"
MINIMAL_LOOP_RESULT_REF = "packages/deepresearch_minimal_loop_result.json"
MINIMAL_CONTRACT_REF = "contract/minimal_task_contract.json"
MINIMAL_MANUAL_REF = "manuals/deepresearch_minimal.md"
MINIMAL_WORKSPACE_POLICY_REF = "policy/minimal_workspace_policy.json"
MINIMAL_PERMISSION_REF = "policy/minimal_permission_manifest.json"
MINIMAL_OUTPUT_CONTRACT_REF = "product_contract/minimal_output_contract.json"
MINIMAL_EXTENSION_LOCK_REF = "compiled/extension_lock.json"
MINIMAL_CALL_REF = "attempts/researcher/piworker_call.json"
MINIMAL_CALL_RESULT_REF = "attempts/researcher/piworker_call_result.json"
MINIMAL_RESEARCH_CALL_REF_TEMPLATE = "attempts/researcher_round_{round_index}/piworker_call.json"
MINIMAL_RESEARCH_CALL_RESULT_REF_TEMPLATE = "attempts/researcher_round_{round_index}/piworker_call_result.json"
MINIMAL_REVIEW_CALL_REF_TEMPLATE = "attempts/reviewer_round_{round_index}/piworker_call.json"
MINIMAL_REVIEW_CALL_RESULT_REF_TEMPLATE = "attempts/reviewer_round_{round_index}/piworker_call_result.json"
MINIMAL_REVIEW_DECISION_REF_TEMPLATE = "reviews/review_round_{round_index}.json"
MINIMAL_REVIEW_BRIEF_REF_TEMPLATE = "reviews/review_round_{round_index}_brief.md"
MINIMAL_EXECUTION_REPORT_REF = "attempts/researcher/execution_report.json"
MINIMAL_METRICS_REF = "attempts/researcher/metrics.json"
MINIMAL_BOUNDARY_VALIDATION_REF = "reports/boundary_validation.json"
MINIMAL_SOURCE_PACKET_REF = "sources/source_packet.json"
MINIMAL_REPORT_REFS = [
    "reports/final_report.md",
    "reports/evidence_index.md",
    "reports/source_gaps.md",
]


@dataclass(frozen=True)
class MinimalDeepResearchResult:
    """Refs-first result for the minimal DeepResearch path."""

    request_id: str
    status: str
    worker_status: str
    boundary_status: str
    run_workspace_ref: str
    result_ref: str
    contract_ref: str
    manual_ref: str
    source_packet_ref: str
    final_report_ref: str
    boundary_validation_ref: str
    call_ref: str
    call_result_ref: str
    extension_lock_ref: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "missionforge_deepresearch.minimal_result.v1",
            "request_id": self.request_id,
            "status": self.status,
            "worker_status": self.worker_status,
            "boundary_status": self.boundary_status,
            "run_workspace_ref": self.run_workspace_ref,
            "result_ref": self.result_ref,
            "contract_ref": self.contract_ref,
            "manual_ref": self.manual_ref,
            "source_packet_ref": self.source_packet_ref,
            "final_report_ref": self.final_report_ref,
            "boundary_validation_ref": self.boundary_validation_ref,
            "check_ref": self.boundary_validation_ref,
            "call_ref": self.call_ref,
            "call_result_ref": self.call_result_ref,
            "extension_lock_ref": self.extension_lock_ref,
        }


@dataclass(frozen=True)
class MinimalDeepResearchLoopResult:
    """Refs-first result for the researcher-reviewer minimal loop."""

    request_id: str
    status: str
    review_decision: str
    review_round_count: int
    run_workspace_ref: str
    result_ref: str
    minimal_result_ref: str
    final_report_ref: str
    source_packet_ref: str
    boundary_validation_ref: str
    review_decision_refs: list[str]
    extension_lock_ref: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "missionforge_deepresearch.minimal_loop_result.v1",
            "request_id": self.request_id,
            "status": self.status,
            "review_decision": self.review_decision,
            "review_round_count": self.review_round_count,
            "run_workspace_ref": self.run_workspace_ref,
            "result_ref": self.result_ref,
            "minimal_result_ref": self.minimal_result_ref,
            "final_report_ref": self.final_report_ref,
            "source_packet_ref": self.source_packet_ref,
            "boundary_validation_ref": self.boundary_validation_ref,
            "review_decision_refs": list(self.review_decision_refs),
            "extension_lock_ref": self.extension_lock_ref,
        }


def run_deepresearch_minimal(
    request: AcademicResearchRequest,
    *,
    workspace: str | Path = ".",
    adapter: PiWorkerCallAdapter | None = None,
    researcher_mode: str = "fixture",
    piworker_config: PiAgentRuntimeConfig | None = None,
    piworker_environ: dict[str, str] | None = None,
    live_extension_mode: bool = False,
    extension_installer: Callable[[ExtensionGrant, Path], Mapping[str, Any]] | None = None,
) -> MinimalDeepResearchResult:
    """Run the small prompt-first DeepResearch orchestration."""

    request.validate()
    if researcher_mode not in {"fixture", "piworker"}:
        raise ContractValidationError("minimal DeepResearch researcher_mode must be fixture or piworker")
    root = Path(workspace).resolve()
    run_ref = f"runs/{request.request_id}"
    run_root = root / run_ref
    run_root.mkdir(parents=True, exist_ok=True)
    profile = research_intensity_profile(request.research_intensity)
    contract = _minimal_contract(request)
    output_contract = _minimal_output_contract(request)
    workspace_policy = _minimal_workspace_policy(run_ref)
    permission = _minimal_permission_manifest(request, live_extension_mode=live_extension_mode)
    write_json_ref(run_root, "product_contract/research_request.json", request.to_dict())
    write_json_ref(run_root, MINIMAL_CONTRACT_REF, contract)
    write_text_ref(run_root, MINIMAL_MANUAL_REF, _minimal_manual(request))
    write_json_ref(run_root, MINIMAL_WORKSPACE_POLICY_REF, workspace_policy)
    write_json_ref(run_root, MINIMAL_PERMISSION_REF, permission.to_dict())
    write_json_ref(run_root, MINIMAL_OUTPUT_CONTRACT_REF, output_contract)
    write_json_ref(run_root, MINIMAL_SOURCE_PACKET_REF, _empty_source_packet(request))
    extension_lock_ref = _compile_minimal_extension_lock(
        permission,
        run_root=run_root,
        live_extension_mode=live_extension_mode,
        extension_installer=extension_installer,
    )
    call = _minimal_researcher_call(
        request=request,
        contract=contract,
        profile=profile,
        researcher_mode=researcher_mode,
        round_index=0,
        extension_lock_ref=extension_lock_ref,
    )
    write_json_ref(run_root, MINIMAL_CALL_REF, call.to_dict())
    worker = adapter or _minimal_adapter(researcher_mode, piworker_config, piworker_environ)
    call_result = run_piworker_call(
        call,
        workspace=run_root,
        adapter=worker,
        result_id=f"{call.call_id}-result",
        extension_lock_ref=extension_lock_ref,
    )
    write_json_ref(run_root, MINIMAL_CALL_RESULT_REF, call_result.to_dict())
    boundary = _minimal_boundary_validation(run_root, call_result.output_refs)
    write_json_ref(run_root, MINIMAL_BOUNDARY_VALIDATION_REF, boundary)
    worker_status = call_result.status.value
    boundary_status = str(boundary["status"])
    status = "draft_ready" if call_result.status is PiWorkerCallResultStatus.COMPLETED and boundary_status != "blocked" else "failed"
    result = MinimalDeepResearchResult(
        request_id=request.request_id,
        status=status,
        worker_status=worker_status,
        boundary_status=boundary_status,
        run_workspace_ref=run_ref,
        result_ref=_outer_ref(run_ref, MINIMAL_RESULT_REF),
        contract_ref=_outer_ref(run_ref, MINIMAL_CONTRACT_REF),
        manual_ref=_outer_ref(run_ref, MINIMAL_MANUAL_REF),
        source_packet_ref=_outer_ref(run_ref, MINIMAL_SOURCE_PACKET_REF),
        final_report_ref=_outer_ref(run_ref, "reports/final_report.md"),
        boundary_validation_ref=_outer_ref(run_ref, MINIMAL_BOUNDARY_VALIDATION_REF),
        call_ref=_outer_ref(run_ref, MINIMAL_CALL_REF),
        call_result_ref=_outer_ref(run_ref, MINIMAL_CALL_RESULT_REF),
        extension_lock_ref=_outer_ref(run_ref, extension_lock_ref) if extension_lock_ref else None,
    )
    write_json_ref(root, result.result_ref, result.to_dict())
    return result


def run_deepresearch_minimal_loop(
    request: AcademicResearchRequest,
    *,
    workspace: str | Path = ".",
    researcher_adapter: PiWorkerCallAdapter | None = None,
    reviewer_adapter: PiWorkerCallAdapter | None = None,
    researcher_mode: str = "fixture",
    reviewer_mode: str = "fixture",
    piworker_config: PiAgentRuntimeConfig | None = None,
    piworker_environ: dict[str, str] | None = None,
    live_extension_mode: bool = False,
    extension_installer: Callable[[ExtensionGrant, Path], Mapping[str, Any]] | None = None,
    review_rounds: int | None = None,
) -> MinimalDeepResearchLoopResult:
    """Run a small researcher-reviewer loop without Python research strategy."""

    request.validate()
    profile = research_intensity_profile(request.research_intensity)
    max_rounds = profile.default_review_rounds if review_rounds is None else review_rounds
    if max_rounds < 0 or max_rounds > profile.max_review_rounds:
        raise ContractValidationError(
            f"minimal-loop review_rounds must be between 0 and {profile.max_review_rounds}"
        )
    root = Path(workspace).resolve()
    initial = run_deepresearch_minimal(
        request,
        workspace=root,
        adapter=researcher_adapter,
        researcher_mode=researcher_mode,
        piworker_config=piworker_config,
        piworker_environ=piworker_environ,
        live_extension_mode=live_extension_mode,
        extension_installer=extension_installer,
    )
    run_ref = initial.run_workspace_ref
    run_root = root / run_ref
    extension_lock_ref = MINIMAL_EXTENSION_LOCK_REF if ref_is_non_empty_file(run_root, MINIMAL_EXTENSION_LOCK_REF) else None
    contract = read_json_ref(run_root, MINIMAL_CONTRACT_REF, "minimal_contract")
    reviewer = reviewer_adapter or _minimal_reviewer_adapter(reviewer_mode, piworker_config, piworker_environ)
    researcher = researcher_adapter or _minimal_adapter(researcher_mode, piworker_config, piworker_environ)
    review_decision_refs: list[str] = []
    decision = "not_reviewed"
    completed_rounds = 0

    if initial.status != "draft_ready":
        return _write_minimal_loop_result(
            root=root,
            request=request,
            status="failed",
            review_decision=decision,
            review_round_count=0,
            review_decision_refs=review_decision_refs,
            extension_lock_ref=initial.extension_lock_ref,
        )

    for round_index in range(1, max_rounds + 1):
        completed_rounds = round_index
        review_ref = MINIMAL_REVIEW_DECISION_REF_TEMPLATE.format(round_index=round_index)
        review_brief_ref = MINIMAL_REVIEW_BRIEF_REF_TEMPLATE.format(round_index=round_index)
        write_text_ref(run_root, review_brief_ref, _minimal_review_brief(round_index))
        review_call = _minimal_review_call(
            request=request,
            contract=contract,
            profile=profile,
            round_index=round_index,
            review_ref=review_ref,
            review_brief_ref=review_brief_ref,
            extension_lock_ref=extension_lock_ref,
        )
        write_json_ref(run_root, MINIMAL_REVIEW_CALL_REF_TEMPLATE.format(round_index=round_index), review_call.to_dict())
        review_result = run_piworker_call(
            review_call,
            workspace=run_root,
            adapter=reviewer,
            result_id=f"{review_call.call_id}-result",
            extension_lock_ref=extension_lock_ref,
        )
        write_json_ref(
            run_root,
            MINIMAL_REVIEW_CALL_RESULT_REF_TEMPLATE.format(round_index=round_index),
            review_result.to_dict(),
        )
        if review_result.status is not PiWorkerCallResultStatus.COMPLETED or not ref_is_non_empty_file(run_root, review_ref):
            decision = "review_failed"
            return _write_minimal_loop_result(
                root=root,
                request=request,
                status="failed",
                review_decision=decision,
                review_round_count=completed_rounds,
                review_decision_refs=review_decision_refs,
                extension_lock_ref=initial.extension_lock_ref,
            )
        review_decision_refs.append(_outer_ref(run_ref, review_ref))
        review_payload = _normalize_review_decision(read_json_ref(run_root, review_ref, "minimal_review_decision"))
        write_json_ref(run_root, review_ref, review_payload)
        decision = review_payload["decision"]
        if decision == "accepted":
            return _write_minimal_loop_result(
                root=root,
                request=request,
                status="accepted",
                review_decision=decision,
                review_round_count=completed_rounds,
                review_decision_refs=review_decision_refs,
                extension_lock_ref=initial.extension_lock_ref,
            )
        if decision in {"tool_blocked", "rejected"}:
            return _write_minimal_loop_result(
                root=root,
                request=request,
                status=decision,
                review_decision=decision,
                review_round_count=completed_rounds,
                review_decision_refs=review_decision_refs,
                extension_lock_ref=initial.extension_lock_ref,
            )
        research_call = _minimal_researcher_call(
            request=request,
            contract=contract,
            profile=profile,
            researcher_mode=researcher_mode,
            round_index=round_index,
            extension_lock_ref=extension_lock_ref,
            objective=(
                f"Revise the DeepResearch artifacts using reviewer decision ref `{review_ref}`. "
                "Close blocking evidence gaps when tools allow it. Update source_packet, final_report, "
                "evidence_index, and source_gaps."
            ),
            extra_visible_refs=[review_ref],
        )
        write_json_ref(run_root, MINIMAL_RESEARCH_CALL_REF_TEMPLATE.format(round_index=round_index), research_call.to_dict())
        research_result = run_piworker_call(
            research_call,
            workspace=run_root,
            adapter=researcher,
            result_id=f"{research_call.call_id}-result",
            extension_lock_ref=extension_lock_ref,
        )
        write_json_ref(
            run_root,
            MINIMAL_RESEARCH_CALL_RESULT_REF_TEMPLATE.format(round_index=round_index),
            research_result.to_dict(),
        )
        boundary = _minimal_boundary_validation(run_root, research_result.output_refs)
        write_json_ref(run_root, MINIMAL_BOUNDARY_VALIDATION_REF, boundary)
        if research_result.status is not PiWorkerCallResultStatus.COMPLETED or boundary["status"] == "blocked":
            return _write_minimal_loop_result(
                root=root,
                request=request,
                status="failed",
                review_decision=decision,
                review_round_count=completed_rounds,
                review_decision_refs=review_decision_refs,
                extension_lock_ref=initial.extension_lock_ref,
            )

    return _write_minimal_loop_result(
        root=root,
        request=request,
        status="open_gaps",
        review_decision=decision,
        review_round_count=completed_rounds,
        review_decision_refs=review_decision_refs,
        extension_lock_ref=initial.extension_lock_ref,
    )


class MinimalFixtureResearcherAdapter:
    """Small fixture worker for validating the minimal path only."""

    adapter_family = "fixture_deepresearch_minimal_researcher"

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
        request = read_json_ref(workspace, "product_contract/research_request.json", "research_request")
        source_packet = _fixture_source_packet(request)
        write_json_ref(workspace, MINIMAL_SOURCE_PACKET_REF, source_packet)
        write_text_ref(workspace, "reports/final_report.md", _fixture_report(request, source_packet))
        write_text_ref(workspace, "reports/evidence_index.md", _reference_lines(source_packet))
        write_text_ref(workspace, "reports/source_gaps.md", "Fixture mode validates structure, not live coverage.\n")
        write_json_ref(workspace, MINIMAL_METRICS_REF, {"metric_ref": MINIMAL_METRICS_REF, "fixture": True})
        report = ExecutionReport(
            report_id="deepresearch-minimal-fixture-execution-report",
            call_id=call.call_id,
            status="completed",
            produced_artifacts=list(call.expected_output_refs),
            changed_refs=[*call.expected_output_refs, MINIMAL_EXECUTION_REPORT_REF, MINIMAL_METRICS_REF],
            evidence_refs=[MINIMAL_SOURCE_PACKET_REF, "reports/evidence_index.md"],
            metrics={"metric_ref": MINIMAL_METRICS_REF},
        )
        write_json_ref(workspace, MINIMAL_EXECUTION_REPORT_REF, report.to_dict())
        return WorkerAdapterResult(
            execution_report=report,
            worker_result=WorkerResult(status="completed", execution_report_ref=MINIMAL_EXECUTION_REPORT_REF),
            metrics={"metric_ref": MINIMAL_METRICS_REF},
        )


class MinimalFixtureReviewerAdapter:
    """Fixture reviewer for validating loop wiring only."""

    adapter_family = "fixture_deepresearch_minimal_reviewer"

    def __init__(self, decision: str = "accepted") -> None:
        self.decision = decision

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
        round_index = int(call.metadata.get("round_index", 1))
        review_ref = MINIMAL_REVIEW_DECISION_REF_TEMPLATE.format(round_index=round_index)
        decision = _normalize_review_decision(
            {
                "schema_version": "missionforge_deepresearch.minimal_review_decision.v1",
                "round_index": round_index,
                "decision": self.decision,
                "blocking_gaps": [],
                "next_research_instructions": [],
                "tool_gaps": [],
                "rationale": "Fixture reviewer validates loop wiring only.",
            }
        )
        write_json_ref(workspace, review_ref, decision)
        report_ref = f"attempts/reviewer_round_{round_index}/execution_report.json"
        metrics_ref = f"attempts/reviewer_round_{round_index}/metrics.json"
        write_json_ref(workspace, metrics_ref, {"fixture": True})
        report = ExecutionReport(
            report_id=f"deepresearch-minimal-fixture-reviewer-round-{round_index}",
            call_id=call.call_id,
            status="completed",
            produced_artifacts=[review_ref],
            changed_refs=[review_ref, report_ref, metrics_ref],
            evidence_refs=[review_ref],
            metrics={"metric_ref": metrics_ref},
        )
        write_json_ref(workspace, report_ref, report.to_dict())
        return WorkerAdapterResult(
            execution_report=report,
            worker_result=WorkerResult(status="completed", execution_report_ref=report_ref),
            metrics={"metric_ref": metrics_ref},
        )


def _minimal_adapter(
    researcher_mode: str,
    piworker_config: PiAgentRuntimeConfig | None,
    piworker_environ: dict[str, str] | None,
) -> PiWorkerCallAdapter:
    if researcher_mode == "fixture":
        return MinimalFixtureResearcherAdapter()
    return PiAgentRuntimeAdapter(piworker_config or PiAgentRuntimeConfig(provider_mode="live"), environ=piworker_environ)


def _minimal_reviewer_adapter(
    reviewer_mode: str,
    piworker_config: PiAgentRuntimeConfig | None,
    piworker_environ: dict[str, str] | None,
) -> PiWorkerCallAdapter:
    if reviewer_mode == "fixture":
        return MinimalFixtureReviewerAdapter()
    if reviewer_mode != "piworker":
        raise ContractValidationError("minimal-loop reviewer_mode must be fixture or piworker")
    return PiAgentRuntimeAdapter(piworker_config or PiAgentRuntimeConfig(provider_mode="live"), environ=piworker_environ)


def _minimal_researcher_call(
    *,
    request: AcademicResearchRequest,
    contract: dict[str, Any],
    profile: Any,
    researcher_mode: str,
    round_index: int,
    extension_lock_ref: str | None,
    objective: str | None = None,
    extra_visible_refs: list[str] | None = None,
) -> PiWorkerCall:
    call_suffix = "minimal-researcher" if round_index == 0 else f"minimal-researcher-round-{round_index}"
    return PiWorkerCall(
        call_id=f"deepresearch-{request.request_id}-{call_suffix}",
        role=PiWorkerCallRole.EXECUTOR,
        contract_id=contract["contract_id"],
        contract_hash=stable_json_hash(contract),
        contract_ref=MINIMAL_CONTRACT_REF,
        objective=objective or contract["objective"],
        visible_refs=_dedupe_refs(
            [
                "product_contract/research_request.json",
                MINIMAL_CONTRACT_REF,
                MINIMAL_MANUAL_REF,
                MINIMAL_WORKSPACE_POLICY_REF,
                MINIMAL_PERMISSION_REF,
                MINIMAL_OUTPUT_CONTRACT_REF,
                MINIMAL_SOURCE_PACKET_REF,
                *(MINIMAL_REPORT_REFS if round_index > 0 else []),
                *([extension_lock_ref] if extension_lock_ref else []),
                *(extra_visible_refs or []),
            ]
        ),
        writable_refs=["sources", "reports", "attempts", "packages", "reviews"],
        expected_output_refs=[MINIMAL_SOURCE_PACKET_REF, *MINIMAL_REPORT_REFS],
        permission_manifest_ref=MINIMAL_PERMISSION_REF,
        source_packet_ref=MINIMAL_SOURCE_PACKET_REF,
        source_packet_hash=stable_json_hash(_empty_source_packet(request)),
        output_schema_ref=MINIMAL_OUTPUT_CONTRACT_REF,
        validation_policy_ref=MINIMAL_OUTPUT_CONTRACT_REF,
        runtime_budget={
            "max_turns": profile.researcher_max_turns,
            "timeout_seconds": profile.piworker_timeout_seconds,
        },
        metadata={
            "path": "minimal",
            "researcher_mode": researcher_mode,
            "round_index": round_index,
            "live_extension_mode": bool(extension_lock_ref),
        },
    )


def _minimal_review_call(
    *,
    request: AcademicResearchRequest,
    contract: dict[str, Any],
    profile: Any,
    round_index: int,
    review_ref: str,
    review_brief_ref: str,
    extension_lock_ref: str | None,
) -> PiWorkerCall:
    return PiWorkerCall(
        call_id=f"deepresearch-{request.request_id}-minimal-reviewer-round-{round_index}",
        role=PiWorkerCallRole.JUDGE,
        contract_id=contract["contract_id"],
        contract_hash=stable_json_hash(contract),
        contract_ref=MINIMAL_CONTRACT_REF,
        objective=(
            "Act as a strict academic paper reviewer for the current DeepResearch artifacts. "
            f"Write one JSON decision to `{review_ref}`. If important evidence gaps can be closed "
            "with available tools, choose continue and give concrete next_research_instructions. "
            "If gaps are caused by missing tools, choose tool_blocked. If the report is sufficient, choose accepted."
        ),
        visible_refs=_dedupe_refs(
            [
                "product_contract/research_request.json",
                MINIMAL_CONTRACT_REF,
                MINIMAL_MANUAL_REF,
                MINIMAL_PERMISSION_REF,
                MINIMAL_OUTPUT_CONTRACT_REF,
                MINIMAL_BOUNDARY_VALIDATION_REF,
                MINIMAL_SOURCE_PACKET_REF,
                *MINIMAL_REPORT_REFS,
                review_brief_ref,
                *([extension_lock_ref] if extension_lock_ref else []),
            ]
        ),
        writable_refs=["reviews", "attempts"],
        expected_output_refs=[review_ref],
        permission_manifest_ref=MINIMAL_PERMISSION_REF,
        source_packet_ref=MINIMAL_SOURCE_PACKET_REF,
        source_packet_hash=stable_json_hash({"round_index": round_index, "review_ref": review_ref}),
        output_schema_ref=review_brief_ref,
        validation_policy_ref=review_brief_ref,
        runtime_budget={
            "max_turns": profile.reviewer_max_turns,
            "timeout_seconds": profile.piworker_timeout_seconds,
        },
        metadata={"path": "minimal_loop", "round_index": round_index},
    )


def _minimal_contract(request: AcademicResearchRequest) -> dict[str, Any]:
    return {
        "schema_version": "missionforge_deepresearch.minimal_task_contract.v1",
        "contract_id": f"deepresearch-{request.request_id}-minimal",
        "objective": f"Produce a citation-backed academic deep research report for: {request.topic}",
        "authority": "frozen_minimal_contract",
        "expected_outputs": [MINIMAL_SOURCE_PACKET_REF, *MINIMAL_REPORT_REFS],
        "rules": [
            "Use the manual as the research skill prompt.",
            "Write source_packet.json before report artifacts.",
            "Cite material claims with [S1] style source ids from source_packet.json.",
            "Record evidence gaps instead of inventing support.",
            "Do not claim final acceptance.",
        ],
    }


def _minimal_output_contract(request: AcademicResearchRequest) -> dict[str, Any]:
    return {
        "schema_version": "missionforge_deepresearch.minimal_output_contract.v1",
        "expected_outputs": [MINIMAL_SOURCE_PACKET_REF, *MINIMAL_REPORT_REFS],
        "report_sections": research_report_section_specs(request.language),
        "source_record_required_fields": ["source_id", "title", "source_type"],
        "citation_format": "[S1] or [S1, S2]",
    }


def _minimal_workspace_policy(run_ref: str) -> dict[str, Any]:
    return WorkspacePolicy(
        policy_id="deepresearch-minimal-workspace",
        workspace_root_ref=run_ref,
        input_refs=["product_contract", "contract", "manuals", "policy", "sources", "compiled", "reviews"],
        artifact_root_refs=["sources", "reports", "attempts", "packages", "compiled", "reviews"],
        scratch_root_refs=["attempts"],
        denied_refs=["secrets"],
    ).to_dict()


def _minimal_permission_manifest(
    request: AcademicResearchRequest,
    *,
    live_extension_mode: bool,
) -> PermissionManifest:
    return PermissionManifest(
        manifest_id="deepresearch-minimal-permissions",
        workspace_policy_ref=MINIMAL_WORKSPACE_POLICY_REF,
        readable_refs=["product_contract", "contract", "manuals", "policy", "sources", "compiled", "reviews"],
        writable_refs=["sources", "reports", "attempts", "packages", "compiled", "reviews"],
        denied_refs=["secrets"],
        network_policy=NetworkPolicy.ENABLED,
        env_allowlist=["PATH"],
        extension_grants=_minimal_live_extension_grants(request) if live_extension_mode else [],
    )


def _compile_minimal_extension_lock(
    permission: PermissionManifest,
    *,
    run_root: Path,
    live_extension_mode: bool,
    extension_installer: Callable[[ExtensionGrant, Path], Mapping[str, Any]] | None,
) -> str | None:
    if not live_extension_mode:
        return None
    extension_lock = compile_extension_lock(
        permission,
        source_permission_manifest_ref=MINIMAL_PERMISSION_REF,
        workspace_root=run_root,
        install_root_ref=".missionforge/extensions",
        mode="install",
        installer=extension_installer or npm_install_extension,
    )
    write_extension_lock(run_root / MINIMAL_EXTENSION_LOCK_REF, extension_lock)
    return MINIMAL_EXTENSION_LOCK_REF


def _minimal_live_extension_grants(request: AcademicResearchRequest) -> list[ExtensionGrant]:
    return academic_deepresearch_extension_grants(request)


def _minimal_manual(request: AcademicResearchRequest) -> str:
    sections = "\n".join(f"- `## {item['title']}`: {item['purpose']}" for item in research_report_section_specs(request.language))
    return f"""# Minimal Academic Deep Research Skill

You are an expert academic deep researcher. MissionForge only provides the
workspace, refs, permissions, and output contract. You decide the research
strategy, search terms, source triage, synthesis, and final wording.

Topic: {request.topic}
Audience: {request.audience}
Language: {request.language}
Research intensity: {request.research_intensity.value}

Do the work:

- Use available tools freely within the runtime permission boundary.
- Build a high-quality evidence set before writing conclusions.
- Write `sources/source_packet.json` with `source_records` using `S1`, `S2`, ...
  source ids.
- For each source record, include `source_id`, `title`, `source_type`, and at
  least one locator: `url`, `doi`, `source_ref`, `arxiv_id`, `github_repo`, or a
  plain `locator` string.
- Write `reports/final_report.md` with material claims cited as `[S1]` or
  `[S1, S2]`.
- Write `reports/evidence_index.md` mapping every source id in
  `sources/source_packet.json` to evidence notes and limits.
- Write `reports/source_gaps.md` with missing evidence and follow-up searches.
- Separate current evidence from historical context.
- Include counterevidence, failure modes, and uncertainty.
- Compare with previous run refs if present: {request.previous_run_refs or "none"}.

Required final report sections:

{sections}
"""


def _minimal_review_brief(round_index: int) -> str:
    return f"""# Minimal DeepResearch Review Brief

Round: {round_index}

You are an independent academic reviewer. Do not rewrite the report. Decide
whether the current artifacts are ready, need another research pass, are blocked
by missing tools, or should be rejected.

Read:

- `sources/source_packet.json`
- `reports/final_report.md`
- `reports/evidence_index.md`
- `reports/source_gaps.md`
- `reports/boundary_validation.json`
- `product_contract/minimal_output_contract.json`

Write exactly one JSON object to
`reviews/review_round_{round_index}.json`:

```json
{{
  "schema_version": "missionforge_deepresearch.minimal_review_decision.v1",
  "round_index": {round_index},
  "decision": "accepted | continue | tool_blocked | rejected",
  "blocking_gaps": ["specific gaps that must be closed before final use"],
  "next_research_instructions": ["concrete instructions for the researcher if decision is continue"],
  "tool_gaps": ["missing tools or access if decision is tool_blocked"],
  "rationale": "short reviewer rationale"
}}
```
"""


def _normalize_review_decision(payload: Mapping[str, Any]) -> dict[str, Any]:
    data = dict(payload)
    decision = str(data.get("decision", "")).strip()
    if decision not in {"accepted", "continue", "tool_blocked", "rejected"}:
        raise ContractValidationError("minimal review decision must be accepted, continue, tool_blocked, or rejected")
    round_index = data.get("round_index", 0)
    if not isinstance(round_index, int) or isinstance(round_index, bool) or round_index < 0:
        raise ContractValidationError("minimal review decision round_index must be a non-negative integer")
    return {
        "schema_version": "missionforge_deepresearch.minimal_review_decision.v1",
        "round_index": round_index,
        "decision": decision,
        "blocking_gaps": _string_list(data.get("blocking_gaps", [])),
        "next_research_instructions": _string_list(data.get("next_research_instructions", [])),
        "tool_gaps": _string_list(data.get("tool_gaps", [])),
        "rationale": str(data.get("rationale", "")).strip(),
    }


def _write_minimal_loop_result(
    *,
    root: Path,
    request: AcademicResearchRequest,
    status: str,
    review_decision: str,
    review_round_count: int,
    review_decision_refs: list[str],
    extension_lock_ref: str | None,
) -> MinimalDeepResearchLoopResult:
    run_ref = f"runs/{request.request_id}"
    result = MinimalDeepResearchLoopResult(
        request_id=request.request_id,
        status=status,
        review_decision=review_decision,
        review_round_count=review_round_count,
        run_workspace_ref=run_ref,
        result_ref=_outer_ref(run_ref, MINIMAL_LOOP_RESULT_REF),
        minimal_result_ref=_outer_ref(run_ref, MINIMAL_RESULT_REF),
        final_report_ref=_outer_ref(run_ref, "reports/final_report.md"),
        source_packet_ref=_outer_ref(run_ref, MINIMAL_SOURCE_PACKET_REF),
        boundary_validation_ref=_outer_ref(run_ref, MINIMAL_BOUNDARY_VALIDATION_REF),
        review_decision_refs=review_decision_refs,
        extension_lock_ref=extension_lock_ref,
    )
    write_json_ref(root, result.result_ref, result.to_dict())
    return result


def _empty_source_packet(request: AcademicResearchRequest) -> dict[str, Any]:
    return {
        "schema_version": "missionforge_deepresearch.source_packet.v1",
        "request_id": request.request_id,
        "source_records": [],
        "notes": ["Researcher must replace this with collected evidence."],
    }


def _minimal_boundary_validation(workspace: Path, output_refs: list[str]) -> dict[str, Any]:
    missing = [ref for ref in [MINIMAL_SOURCE_PACKET_REF, *MINIMAL_REPORT_REFS] if not ref_is_non_empty_file(workspace, ref)]
    source_packet = read_json_ref(workspace, MINIMAL_SOURCE_PACKET_REF, "source_packet")
    source_audit = audit_source_packet(source_packet)
    citation_audit = audit_report_citations(
        final_report_text=read_text_ref(workspace, "reports/final_report.md") if ref_is_non_empty_file(workspace, "reports/final_report.md") else "",
        evidence_index_text=read_text_ref(workspace, "reports/evidence_index.md") if ref_is_non_empty_file(workspace, "reports/evidence_index.md") else "",
        source_ids=source_audit.source_ids,
    )
    missing_from_worker = sorted(set([MINIMAL_SOURCE_PACKET_REF, *MINIMAL_REPORT_REFS]) - set(output_refs))
    blocking_errors = [
        *[f"missing_or_empty_ref:{ref}" for ref in missing],
        *[f"missing_from_worker_result_ref:{ref}" for ref in missing_from_worker],
        *_blocking_source_errors(source_audit.errors),
        *_blocking_citation_errors(citation_audit.errors),
    ]
    warnings = [
        *_nonblocking_source_errors(source_audit.errors),
        *_nonblocking_citation_errors(citation_audit.errors),
    ]
    status = "blocked" if blocking_errors else "passed_with_warnings" if warnings else "passed"
    return {
        "schema_version": "missionforge_deepresearch.boundary_validation.v1",
        "status": status,
        "blocking_errors": blocking_errors,
        "warnings": warnings,
        "missing_or_empty_refs": missing,
        "missing_from_worker_result_refs": missing_from_worker,
        "source_packet_audit": source_audit.to_dict(),
        "citation_audit": citation_audit.to_dict(),
    }


def _blocking_source_errors(errors: list[str]) -> list[str]:
    return [
        error
        for error in errors
        if error.startswith("source_packet_")
        or error.endswith("_not_mapping")
        or error.endswith("_source_id_invalid")
        or error.endswith("_duplicate")
        or error.endswith("_missing_title")
        or error.endswith("_missing_source_type")
        or error.endswith("_invalid_source_ref")
    ]


def _nonblocking_source_errors(errors: list[str]) -> list[str]:
    blocking = set(_blocking_source_errors(errors))
    return [error for error in errors if error not in blocking]


def _blocking_citation_errors(errors: list[str]) -> list[str]:
    return [
        error
        for error in errors
        if error.startswith("final_report_missing_source_citations")
        or error.startswith("final_report_unknown_source_ids")
        or error.startswith("references_unknown_source_ids")
    ]


def _nonblocking_citation_errors(errors: list[str]) -> list[str]:
    blocking = set(_blocking_citation_errors(errors))
    return [error for error in errors if error not in blocking]


def _fixture_source_packet(request: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "missionforge_deepresearch.source_packet.v1",
        "request_id": str(request["request_id"]),
        "source_records": [
            {
                "source_id": "S1",
                "title": "Minimal fixture source",
                "source_type": "fixture",
                "source_ref": MINIMAL_SOURCE_PACKET_REF,
            }
        ],
    }


def _fixture_report(request: dict[str, Any], source_packet: dict[str, Any]) -> str:
    headings = {item["section_id"]: item["title"] for item in research_report_section_specs(str(request.get("language", "zh")))}
    return (
        f"# {request['topic']}\n\n"
        f"## {headings['scope_and_method']}\n\n"
        "Minimal fixture run for orchestration validation [S1].\n\n"
        f"## {headings['evidence_base']}\n\n"
        "Fixture evidence only [S1].\n\n"
        f"## {headings['major_lines_of_work']}\n\n"
        "The real researcher must identify the field structure.\n\n"
        f"## {headings['comparison_matrix']}\n\n"
        "| Item | Evidence | Limit |\n|---|---|---|\n| fixture | [S1] | not live research |\n\n"
        f"## {headings['counterevidence_and_failure_modes']}\n\n"
        "Treating this fixture as a real research result is the main failure mode.\n\n"
        f"## {headings['research_delta']}\n\n"
        "Baseline fixture run.\n\n"
        f"## {headings['source_gaps']}\n\n"
        "Live source collection is required for real coverage.\n\n"
        f"## {headings['references']}\n\n"
        f"{_reference_lines(source_packet)}"
    )


def _reference_lines(source_packet: dict[str, Any]) -> str:
    lines = []
    for record in source_packet.get("source_records", []):
        if isinstance(record, dict):
            source_id = str(record.get("source_id", "")).strip()
            title = str(record.get("title", "")).strip()
            locator = str(record.get("url") or record.get("doi") or record.get("source_ref") or "").strip()
            if source_id and title:
                lines.append(f"- [{source_id}] {title}. {locator}".rstrip())
    return "\n".join(lines) + ("\n" if lines else "")


def _dedupe_refs(refs: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for ref in refs:
        safe_ref = validate_ref(ref, "minimal_ref")
        if safe_ref not in seen:
            result.append(safe_ref)
            seen.add(safe_ref)
    return result


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def _outer_ref(run_workspace_ref: str, ref: str) -> str:
    return f"{validate_ref(run_workspace_ref, 'run_workspace_ref')}/{validate_ref(ref, 'run_ref')}"
