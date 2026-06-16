"""Reviewer-guided research update loop for DeepResearch.

This module keeps the loop thin: MissionForge records bounded reviewer and
researcher calls, while PiWorker roles own the semantic critique and update.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from missionforge.adapters.pi_agent_runtime import PiAgentRuntimeAdapter, PiAgentRuntimeConfig
from missionforge.contracts import (
    ContractValidationError,
    assert_refs_only_payload,
    require_int_at_least,
    require_mapping,
    require_non_empty_str,
    stable_json_hash,
    validate_ref,
)
from missionforge.piworker_call import PiWorkerCall, PiWorkerCallResult, PiWorkerCallResultStatus, PiWorkerCallRole
from missionforge.piworker_runtime import PiWorkerCallAdapter, run_piworker_call
from missionforge.runtime_results import ExecutionReport, WorkerAdapterResult, WorkerResult
from missionforge.task_contract import NetworkPolicy, PermissionManifest

from .compiler import (
    EXTENSION_LOCK_REF,
    EXPECTED_WORKER_OUTPUT_REFS,
    JUDGE_RUBRIC_REF,
    MANUAL_REF,
    OUTPUT_CONTRACT_REF,
    PERMISSION_MANIFEST_REF,
    PRODUCT_REQUEST_REF,
    SOURCE_COLLECTION_REPORT_REF,
    SOURCE_PACKET_REF,
    STRUCTURAL_CHECK_POLICY_REF,
    TASK_CONTRACT_REF,
    WORKER_BRIEF_REF,
    WORKSPACE_POLICY_REF,
    load_deepresearch_task_contract,
)
from .product_contract import (
    AcademicResearchRequest,
    DeepResearchReviewedRunResult,
    DeepResearchReviewedRunStatus,
    DeepResearchRunResult,
    DeepResearchRunStatus,
    research_intensity_profile,
)
from .runtime import (
    RESEARCHER_MODES,
    RESEARCHER_CALL_REF,
    RESEARCHER_CALL_RESULT_REF,
    RUN_RESULT_REF,
    STRUCTURAL_CHECK_REPORT_REF,
    FixtureAcademicResearcherAdapter,
    _researcher_adapter,
    load_deepresearch_run_result,
    run_deepresearch_academic_single_agent,
    run_structural_checks,
)
from .source_collector import AcademicSourceCollectionConfig
from .workspace import read_json_ref, ref_is_non_empty_file, write_json_ref, write_text_ref


REVIEWER_MODES = {"fixture", "piworker"}
PEER_REVIEW_MANUAL_REF = "manuals/deepresearch_peer_reviewer.md"
REVIEWER_PERMISSION_MANIFEST_REF = "policy/reviewer_permission_manifest.json"
REVIEWED_RUN_RESULT_REF = "packages/deepresearch_reviewed_run_result.json"


def run_deepresearch_academic_reviewed(
    request: AcademicResearchRequest,
    *,
    workspace: str | Path = ".",
    researcher_adapter: PiWorkerCallAdapter | None = None,
    reviewer_adapter: PiWorkerCallAdapter | None = None,
    source_mode: str = "fixture",
    researcher_mode: str = "fixture",
    reviewer_mode: str = "fixture",
    search_intent_mode: str = "none",
    search_queries: list[str] | None = None,
    search_intent_ref: str | None = None,
    source_config: AcademicSourceCollectionConfig | None = None,
    piworker_config: PiAgentRuntimeConfig | None = None,
    piworker_environ: Mapping[str, str] | None = None,
    live_extension_mode: bool = False,
    extension_installer: Any | None = None,
    review_rounds: int | None = None,
) -> DeepResearchReviewedRunResult:
    """Run a draft through bounded paper-review-style update rounds."""

    request.validate()
    if reviewer_mode not in REVIEWER_MODES:
        raise ContractValidationError(f"deepresearch reviewer_mode must be one of {sorted(REVIEWER_MODES)}")
    if researcher_mode not in RESEARCHER_MODES:
        raise ContractValidationError(f"deepresearch researcher_mode must be one of {sorted(RESEARCHER_MODES)}")
    intensity_profile = research_intensity_profile(request.research_intensity)
    effective_review_rounds = (
        intensity_profile.default_review_rounds if review_rounds is None else require_int_at_least(review_rounds, "review_rounds", 0)
    )
    if effective_review_rounds > intensity_profile.max_review_rounds:
        raise ContractValidationError(
            f"deepresearch review_rounds exceeds {request.research_intensity.value} max_review_rounds"
        )
    root = Path(workspace).resolve()
    initial_result = run_deepresearch_academic_single_agent(
        request,
        workspace=root,
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
    if initial_result.status is not DeepResearchRunStatus.DRAFT_READY or effective_review_rounds == 0:
        status = (
            DeepResearchReviewedRunStatus.DRAFT_READY
            if initial_result.status is DeepResearchRunStatus.DRAFT_READY
            else DeepResearchReviewedRunStatus.FAILED
        )
        return _write_reviewed_result(
            root,
            run_result=initial_result,
            status=status,
            review_round_count=0,
            reviewer_report_refs=[],
            research_state_refs=[],
            reviewer_call_refs=[],
            reviewer_call_result_refs=[],
            revision_call_refs=[],
            revision_call_result_refs=[],
            extra_evidence_refs=[],
            extra_metric_refs=[],
        )

    compile_result = _compile_result_from_run(initial_result)
    task_contract, _workspace_policy, permission_manifest = load_deepresearch_task_contract(root, compile_result)
    run_root = root / initial_result.run_workspace_ref
    worker_extension_lock_ref = EXTENSION_LOCK_REF if ref_is_non_empty_file(run_root, EXTENSION_LOCK_REF) else None
    write_text_ref(run_root, PEER_REVIEW_MANUAL_REF, _peer_review_manual_text(request))
    write_json_ref(run_root, REVIEWER_PERMISSION_MANIFEST_REF, _reviewer_permission_manifest(request).to_dict())

    current_result = initial_result
    reviewer_report_refs: list[str] = []
    research_state_refs: list[str] = []
    reviewer_call_refs: list[str] = []
    reviewer_call_result_refs: list[str] = []
    revision_call_refs: list[str] = []
    revision_call_result_refs: list[str] = []
    extra_evidence_refs: list[str] = [
        _outer_ref(initial_result.run_workspace_ref, PEER_REVIEW_MANUAL_REF),
        _outer_ref(initial_result.run_workspace_ref, REVIEWER_PERMISSION_MANIFEST_REF),
    ]
    extra_metric_refs: list[str] = []

    for round_index in range(1, effective_review_rounds + 1):
        review_result = _run_peer_review_round(
            request,
            workspace=run_root,
            run_result=current_result,
            round_index=round_index,
            adapter=reviewer_adapter,
            reviewer_mode=reviewer_mode,
            piworker_config=piworker_config,
            piworker_environ=piworker_environ,
        )
        reviewer_report_ref = _reviewer_report_ref(round_index)
        directive_ref = _next_directive_ref(round_index)
        reviewer_call_ref = _reviewer_call_ref(round_index)
        reviewer_call_result_ref = _reviewer_call_result_ref(round_index)
        reviewer_report_refs.append(_outer_ref(current_result.run_workspace_ref, reviewer_report_ref))
        reviewer_call_refs.append(_outer_ref(current_result.run_workspace_ref, reviewer_call_ref))
        reviewer_call_result_refs.append(_outer_ref(current_result.run_workspace_ref, reviewer_call_result_ref))
        extra_evidence_refs.extend(
            [
                _outer_ref(current_result.run_workspace_ref, _review_spec_ref(round_index)),
                _outer_ref(current_result.run_workspace_ref, reviewer_report_ref),
                _outer_ref(current_result.run_workspace_ref, directive_ref),
                _outer_ref(current_result.run_workspace_ref, reviewer_call_ref),
                _outer_ref(current_result.run_workspace_ref, reviewer_call_result_ref),
            ]
        )
        extra_metric_refs.extend([_outer_ref(current_result.run_workspace_ref, ref) for ref in review_result.metric_refs])
        if review_result.status is not PiWorkerCallResultStatus.COMPLETED:
            return _write_reviewed_result(
                root,
                run_result=current_result,
                status=DeepResearchReviewedRunStatus.FAILED,
                review_round_count=round_index,
                reviewer_report_refs=reviewer_report_refs,
                research_state_refs=research_state_refs,
                reviewer_call_refs=reviewer_call_refs,
                reviewer_call_result_refs=reviewer_call_result_refs,
                revision_call_refs=revision_call_refs,
                revision_call_result_refs=revision_call_result_refs,
                extra_evidence_refs=extra_evidence_refs,
                extra_metric_refs=extra_metric_refs,
            )

        revision_result = _run_research_revision_round(
            request,
            workspace=run_root,
            task_contract_id=task_contract.contract_id,
            contract_hash=current_result.contract_hash,
            permission_manifest=permission_manifest,
            round_index=round_index,
            directive_ref=directive_ref,
            reviewer_report_ref=reviewer_report_ref,
            previous_research_state_refs=[_inner_ref(current_result.run_workspace_ref, ref) for ref in research_state_refs],
            extension_lock_ref=worker_extension_lock_ref,
            adapter=researcher_adapter,
            researcher_mode=researcher_mode,
            piworker_config=piworker_config,
            piworker_environ=piworker_environ,
        )
        revision_call_ref = _revision_call_ref(round_index)
        revision_call_result_ref = _revision_call_result_ref(round_index)
        research_state_ref = _research_state_ref(round_index)
        revision_call_refs.append(_outer_ref(current_result.run_workspace_ref, revision_call_ref))
        revision_call_result_refs.append(_outer_ref(current_result.run_workspace_ref, revision_call_result_ref))
        research_state_refs.append(_outer_ref(current_result.run_workspace_ref, research_state_ref))
        extra_evidence_refs.extend(
            [
                _outer_ref(current_result.run_workspace_ref, revision_call_ref),
                _outer_ref(current_result.run_workspace_ref, revision_call_result_ref),
                _outer_ref(current_result.run_workspace_ref, research_state_ref),
                _outer_ref(current_result.run_workspace_ref, revision_result.execution_report_ref),
            ]
        )
        extra_metric_refs.extend([_outer_ref(current_result.run_workspace_ref, ref) for ref in revision_result.metric_refs])
        structural = run_structural_checks(
            workspace=run_root,
            expected_refs=EXPECTED_WORKER_OUTPUT_REFS,
            call_result=revision_result,
        )
        current_result = _write_final_run_result(
            root,
            source_result=current_result,
            researcher_call_ref=_outer_ref(current_result.run_workspace_ref, revision_call_ref),
            researcher_call_result_ref=_outer_ref(current_result.run_workspace_ref, revision_call_result_ref),
            structural_status=str(structural.get("status", "failed")),
            extra_evidence_refs=extra_evidence_refs,
            extra_metric_refs=extra_metric_refs,
        )
        if current_result.status is not DeepResearchRunStatus.DRAFT_READY:
            return _write_reviewed_result(
                root,
                run_result=current_result,
                status=DeepResearchReviewedRunStatus.FAILED,
                review_round_count=round_index,
                reviewer_report_refs=reviewer_report_refs,
                research_state_refs=research_state_refs,
                reviewer_call_refs=reviewer_call_refs,
                reviewer_call_result_refs=reviewer_call_result_refs,
                revision_call_refs=revision_call_refs,
                revision_call_result_refs=revision_call_result_refs,
                extra_evidence_refs=extra_evidence_refs,
                extra_metric_refs=extra_metric_refs,
            )

    return _write_reviewed_result(
        root,
        run_result=current_result,
        status=DeepResearchReviewedRunStatus.DRAFT_READY,
        review_round_count=effective_review_rounds,
        reviewer_report_refs=reviewer_report_refs,
        research_state_refs=research_state_refs,
        reviewer_call_refs=reviewer_call_refs,
        reviewer_call_result_refs=reviewer_call_result_refs,
        revision_call_refs=revision_call_refs,
        revision_call_result_refs=revision_call_result_refs,
        extra_evidence_refs=extra_evidence_refs,
        extra_metric_refs=extra_metric_refs,
    )


def load_deepresearch_reviewed_run_result(workspace: str | Path, ref: str) -> DeepResearchReviewedRunResult:
    """Load a refs-first reviewer-guided DeepResearch result."""

    return DeepResearchReviewedRunResult.from_dict(read_json_ref(workspace, ref, "deepresearch_reviewed_run_result"))


def run_deepresearch_academic_reviewed_judged(
    request: AcademicResearchRequest,
    *,
    workspace: str | Path = ".",
    researcher_adapter: PiWorkerCallAdapter | None = None,
    reviewer_adapter: PiWorkerCallAdapter | None = None,
    judge_adapter: PiWorkerCallAdapter | None = None,
    source_mode: str = "fixture",
    researcher_mode: str = "fixture",
    reviewer_mode: str = "fixture",
    search_intent_mode: str = "none",
    search_queries: list[str] | None = None,
    search_intent_ref: str | None = None,
    source_config: AcademicSourceCollectionConfig | None = None,
    piworker_config: PiAgentRuntimeConfig | None = None,
    piworker_environ: Mapping[str, str] | None = None,
    live_extension_mode: bool = False,
    extension_installer: Any | None = None,
    review_rounds: int | None = None,
) -> Any:
    """Run reviewer-guided updates, then submit the revised draft to the independent judge."""

    from .judging import judge_deepresearch_run

    reviewed = run_deepresearch_academic_reviewed(
        request,
        workspace=workspace,
        researcher_adapter=researcher_adapter,
        reviewer_adapter=reviewer_adapter,
        source_mode=source_mode,
        researcher_mode=researcher_mode,
        reviewer_mode=reviewer_mode,
        search_intent_mode=search_intent_mode,
        search_queries=search_queries,
        search_intent_ref=search_intent_ref,
        source_config=source_config,
        piworker_config=piworker_config,
        piworker_environ=piworker_environ,
        live_extension_mode=live_extension_mode,
        extension_installer=extension_installer,
        review_rounds=review_rounds,
    )
    revised_run = load_deepresearch_run_result(workspace, reviewed.final_run_result_ref)
    return judge_deepresearch_run(
        request,
        workspace=workspace,
        run_result=revised_run,
        adapter=judge_adapter,
        piworker_config=piworker_config,
        piworker_environ=piworker_environ,
    )


def _run_peer_review_round(
    request: AcademicResearchRequest,
    *,
    workspace: Path,
    run_result: DeepResearchRunResult,
    round_index: int,
    adapter: PiWorkerCallAdapter | None,
    reviewer_mode: str,
    piworker_config: PiAgentRuntimeConfig | None,
    piworker_environ: Mapping[str, str] | None,
) -> PiWorkerCallResult:
    intensity_profile = research_intensity_profile(request.research_intensity)
    artifact_refs = [_inner_ref(run_result.run_workspace_ref, ref) for ref in run_result.draft_artifact_refs]
    evidence_refs = _dedupe_refs(
        [_inner_ref(run_result.run_workspace_ref, ref) for ref in run_result.evidence_refs if _is_in_run(run_result.run_workspace_ref, ref)]
    )
    metric_refs = _dedupe_refs(
        [_inner_ref(run_result.run_workspace_ref, ref) for ref in run_result.metric_refs if _is_in_run(run_result.run_workspace_ref, ref)]
    )
    spec = {
        "schema_version": "missionforge_deepresearch.peer_review_spec.v1",
        "request_id": request.request_id,
        "round_index": round_index,
        "contract_ref": TASK_CONTRACT_REF,
        "contract_hash": run_result.contract_hash,
        "manual_ref": PEER_REVIEW_MANUAL_REF,
        "judge_rubric_ref": JUDGE_RUBRIC_REF,
        "output_contract_ref": OUTPUT_CONTRACT_REF,
        "structural_check_ref": _inner_ref(run_result.run_workspace_ref, run_result.structural_check_ref),
        "research_intensity": request.research_intensity.value,
        "research_intensity_profile": intensity_profile.to_dict(),
        "artifact_refs": artifact_refs,
        "evidence_refs": evidence_refs,
        "metric_refs": metric_refs,
        "required_reviewer_report_ref": _reviewer_report_ref(round_index),
        "required_next_directive_ref": _next_directive_ref(round_index),
        "reviewer_authority": "guide_research_only_no_acceptance",
        "review_focus": [
            "coverage of central papers and engineering evidence",
            "freshness and stale-information risk",
            "citation support for material claims",
            "missing counterevidence or competing schools",
            "taxonomy, definitions, and conceptual precision",
            "clear next research directive for the researcher",
        ],
    }
    _validate_review_spec(spec)
    write_json_ref(workspace, _review_spec_ref(round_index), spec)
    call = PiWorkerCall(
        call_id=f"deepresearch-{request.request_id}-peer-review-round-{round_index:02d}",
        role=PiWorkerCallRole.JUDGE,
        contract_id=_contract_id(workspace),
        contract_hash=run_result.contract_hash,
        contract_ref=TASK_CONTRACT_REF,
        objective=(
            "Act as a strict academic paper reviewer for this intermediate DeepResearch draft. "
            "Do not accept the work. Identify flaws, missing evidence, stale claims, and write "
            "the next research directive that should steer the following update round."
        ),
        visible_refs=_dedupe_refs(
            [
                _review_spec_ref(round_index),
                PEER_REVIEW_MANUAL_REF,
                TASK_CONTRACT_REF,
                JUDGE_RUBRIC_REF,
                OUTPUT_CONTRACT_REF,
                STRUCTURAL_CHECK_POLICY_REF,
                REVIEWER_PERMISSION_MANIFEST_REF,
                *artifact_refs,
                *evidence_refs,
                *metric_refs,
            ]
        ),
        writable_refs=["reviews", "attempts"],
        expected_output_refs=[_reviewer_report_ref(round_index), _next_directive_ref(round_index)],
        permission_manifest_ref=REVIEWER_PERMISSION_MANIFEST_REF,
        source_packet_ref=_review_spec_ref(round_index),
        source_packet_hash=stable_json_hash(spec),
        evidence_refs=_dedupe_refs([_review_spec_ref(round_index), *artifact_refs, *evidence_refs]),
        output_schema_ref=_review_spec_ref(round_index),
        validation_policy_ref=_review_spec_ref(round_index),
        runtime_budget={
            "max_turns": intensity_profile.reviewer_max_turns,
            "timeout_seconds": intensity_profile.piworker_timeout_seconds,
        },
        metadata={
            "phase": "reviewer_guided_research",
            "round_index": round_index,
            "research_intensity": request.research_intensity.value,
            "authority": "guidance_only",
        },
    )
    write_json_ref(workspace, _reviewer_call_ref(round_index), call.to_dict())
    worker = adapter or _reviewer_adapter(reviewer_mode, piworker_config, piworker_environ)
    call_result = run_piworker_call(
        call,
        workspace=workspace,
        adapter=worker,
        result_id=f"{call.call_id}-result",
        metadata={"phase": "reviewer_guided_research", "round_index": round_index},
    )
    write_json_ref(workspace, _reviewer_call_result_ref(round_index), call_result.to_dict())
    if call_result.status is PiWorkerCallResultStatus.COMPLETED:
        for ref in call.expected_output_refs:
            if not ref_is_non_empty_file(workspace, ref):
                raise ContractValidationError(f"deepresearch peer reviewer did not produce required ref: {ref}")
    return call_result


def _run_research_revision_round(
    request: AcademicResearchRequest,
    *,
    workspace: Path,
    task_contract_id: str,
    contract_hash: str,
    permission_manifest: PermissionManifest,
    round_index: int,
    directive_ref: str,
    reviewer_report_ref: str,
    previous_research_state_refs: list[str],
    extension_lock_ref: str | None,
    adapter: PiWorkerCallAdapter | None,
    researcher_mode: str,
    piworker_config: PiAgentRuntimeConfig | None,
    piworker_environ: Mapping[str, str] | None,
) -> PiWorkerCallResult:
    intensity_profile = research_intensity_profile(request.research_intensity)
    source_packet = read_json_ref(workspace, SOURCE_PACKET_REF, "source_packet")
    expected_refs = [*EXPECTED_WORKER_OUTPUT_REFS, _research_state_ref(round_index)]
    visible_refs = _dedupe_refs(
        [
            TASK_CONTRACT_REF,
            WORKSPACE_POLICY_REF,
            PERMISSION_MANIFEST_REF,
            WORKER_BRIEF_REF,
            PRODUCT_REQUEST_REF,
            MANUAL_REF,
            PEER_REVIEW_MANUAL_REF,
            SOURCE_PACKET_REF,
            SOURCE_COLLECTION_REPORT_REF,
            OUTPUT_CONTRACT_REF,
            STRUCTURAL_CHECK_POLICY_REF,
            *([extension_lock_ref] if extension_lock_ref else []),
            _review_spec_ref(round_index),
            reviewer_report_ref,
            directive_ref,
            *previous_research_state_refs,
        ]
    )
    evidence_refs = _dedupe_refs(
        [
            SOURCE_PACKET_REF,
            SOURCE_COLLECTION_REPORT_REF,
            reviewer_report_ref,
            directive_ref,
            *([extension_lock_ref] if extension_lock_ref else []),
        ]
    )
    call = PiWorkerCall(
        call_id=f"deepresearch-{request.request_id}-revision-round-{round_index:02d}",
        role=PiWorkerCallRole.EXECUTOR,
        contract_id=task_contract_id,
        contract_hash=contract_hash,
        contract_ref=TASK_CONTRACT_REF,
        objective=(
            "Update the DeepResearch evidence packet and report artifacts using the peer review report, "
            "next research directive, frozen contract, and available tools. First update "
            "sources/source_packet.json with any added or corrected source_records; then update report artifacts "
            "so material claims cite those source ids. Write research_state.json to record the belief update, "
            "open questions, and remaining gaps."
        ),
        visible_refs=visible_refs,
        writable_refs=list(permission_manifest.writable_refs) + ["reviews"],
        expected_output_refs=expected_refs,
        permission_manifest_ref=PERMISSION_MANIFEST_REF,
        source_packet_ref=SOURCE_PACKET_REF,
        source_packet_hash=stable_json_hash(source_packet),
        evidence_refs=evidence_refs,
        output_schema_ref=OUTPUT_CONTRACT_REF,
        validation_policy_ref=STRUCTURAL_CHECK_POLICY_REF,
        runtime_budget={
            "max_turns": intensity_profile.researcher_max_turns,
            "timeout_seconds": intensity_profile.piworker_timeout_seconds,
        },
        metadata={
            "phase": "reviewer_guided_research_revision",
            "request_id": request.request_id,
            "round_index": round_index,
            "research_intensity": request.research_intensity.value,
        },
    )
    write_json_ref(workspace, _revision_call_ref(round_index), call.to_dict())
    worker = adapter or _revision_researcher_adapter(researcher_mode, piworker_config, piworker_environ)
    call_result = run_piworker_call(
        call,
        workspace=workspace,
        adapter=worker,
        extension_lock_ref=extension_lock_ref,
        result_id=f"{call.call_id}-result",
        metadata={"phase": "reviewer_guided_research_revision", "round_index": round_index},
    )
    write_json_ref(workspace, _revision_call_result_ref(round_index), call_result.to_dict())
    if call_result.status is PiWorkerCallResultStatus.COMPLETED:
        if not ref_is_non_empty_file(workspace, _research_state_ref(round_index)):
            raise ContractValidationError("deepresearch revision did not produce research_state.json")
    return call_result


class FixturePeerReviewerAdapter:
    """Offline peer reviewer adapter for reviewer-guided loop tests."""

    adapter_family = "fixture_deepresearch_peer_reviewer"

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
            raise ContractValidationError("fixture DeepResearch peer reviewer only supports judge-role calls")
        round_index = int(call.metadata.get("round_index", 1))
        reviewer_report_ref = _reviewer_report_ref(round_index)
        directive_ref = _next_directive_ref(round_index)
        write_text_ref(
            workspace,
            reviewer_report_ref,
            (
                "# Peer Review Report\n\n"
                "- Verdict: continue revision; this is not final acceptance.\n"
                "- Blocking concern: strengthen source coverage and cite material claims.\n"
                "- Check freshness, competing evidence, and taxonomy precision before final synthesis.\n"
            ),
        )
        write_text_ref(
            workspace,
            directive_ref,
            (
                "# Next Research Directive\n\n"
                "Revise the report using the reviewer findings. Update citations, source gaps, "
                "research delta, and research_state.json. Do not weaken the frozen contract.\n"
            ),
        )
        metrics_ref = _reviewer_metrics_ref(round_index)
        execution_report_ref = _reviewer_execution_report_ref(round_index)
        write_json_ref(workspace, metrics_ref, {"metric_ref": metrics_ref, "fixture": True, "round_index": round_index})
        report = ExecutionReport(
            report_id=f"deepresearch-fixture-peer-review-round-{round_index:02d}",
            call_id=call.call_id,
            status="completed",
            produced_artifacts=[reviewer_report_ref, directive_ref],
            changed_refs=[reviewer_report_ref, directive_ref, execution_report_ref, metrics_ref],
            evidence_refs=[_review_spec_ref(round_index), *call.evidence_refs],
            worker_claims=["fixture peer review guidance produced"],
            metrics={"metric_ref": metrics_ref},
        )
        write_json_ref(workspace, execution_report_ref, report.to_dict())
        return WorkerAdapterResult(
            execution_report=report,
            worker_result=WorkerResult(status="completed", execution_report_ref=execution_report_ref),
            event_evidence_refs=[],
            metrics={"metric_ref": metrics_ref},
        )


class FixtureReviewedResearcherAdapter(FixtureAcademicResearcherAdapter):
    """Fixture researcher that also writes per-round research state."""

    adapter_family = "fixture_deepresearch_reviewed_researcher"

    def run_call(self, call: PiWorkerCall, **kwargs: Any) -> WorkerAdapterResult:
        result = super().run_call(call, **kwargs)
        workspace = kwargs.get("workspace", ".")
        round_index = int(call.metadata.get("round_index", 1))
        state_ref = _research_state_ref(round_index)
        if state_ref in call.expected_output_refs:
            write_json_ref(
                workspace,
                state_ref,
                {
                    "schema_version": "missionforge_deepresearch.research_state.v1",
                    "request_id": call.metadata.get("request_id", "fixture"),
                    "round_index": round_index,
                    "contract_ref": call.contract_ref,
                    "contract_hash": call.contract_hash,
                    "source_packet_ref": SOURCE_PACKET_REF,
                    "updated_artifact_refs": list(EXPECTED_WORKER_OUTPUT_REFS),
                    "open_question_refs": ["reports/source_gaps.md"],
                    "reviewer_guidance_refs": [
                        _reviewer_report_ref(round_index),
                        _next_directive_ref(round_index),
                    ],
                },
            )
        return result


def _write_final_run_result(
    root: Path,
    *,
    source_result: DeepResearchRunResult,
    researcher_call_ref: str,
    researcher_call_result_ref: str,
    structural_status: str,
    extra_evidence_refs: list[str],
    extra_metric_refs: list[str],
) -> DeepResearchRunResult:
    status = DeepResearchRunStatus.DRAFT_READY if structural_status == "passed" else DeepResearchRunStatus.FAILED
    result = DeepResearchRunResult(
        request_id=source_result.request_id,
        status=status,
        run_workspace_ref=source_result.run_workspace_ref,
        run_result_ref=_outer_ref(source_result.run_workspace_ref, RUN_RESULT_REF),
        task_contract_ref=source_result.task_contract_ref,
        manual_ref=source_result.manual_ref,
        source_packet_ref=source_result.source_packet_ref,
        output_contract_ref=source_result.output_contract_ref,
        researcher_call_ref=researcher_call_ref,
        researcher_call_result_ref=researcher_call_result_ref,
        structural_check_ref=_outer_ref(source_result.run_workspace_ref, STRUCTURAL_CHECK_REPORT_REF),
        draft_artifact_refs=list(source_result.draft_artifact_refs),
        evidence_refs=_dedupe_refs([*source_result.evidence_refs, *extra_evidence_refs]),
        metric_refs=_dedupe_refs([*source_result.metric_refs, *extra_metric_refs]),
        contract_hash=source_result.contract_hash,
    )
    write_json_ref(root, result.run_result_ref, result.to_dict())
    return result


def _write_reviewed_result(
    root: Path,
    *,
    run_result: DeepResearchRunResult,
    status: DeepResearchReviewedRunStatus,
    review_round_count: int,
    reviewer_report_refs: list[str],
    research_state_refs: list[str],
    reviewer_call_refs: list[str],
    reviewer_call_result_refs: list[str],
    revision_call_refs: list[str],
    revision_call_result_refs: list[str],
    extra_evidence_refs: list[str],
    extra_metric_refs: list[str],
) -> DeepResearchReviewedRunResult:
    result = DeepResearchReviewedRunResult(
        request_id=run_result.request_id,
        status=status,
        run_workspace_ref=run_result.run_workspace_ref,
        reviewed_run_result_ref=_outer_ref(run_result.run_workspace_ref, REVIEWED_RUN_RESULT_REF),
        final_run_result_ref=run_result.run_result_ref,
        review_round_count=review_round_count,
        reviewer_report_refs=_dedupe_refs(reviewer_report_refs),
        research_state_refs=_dedupe_refs(research_state_refs),
        reviewer_call_refs=_dedupe_refs(reviewer_call_refs),
        reviewer_call_result_refs=_dedupe_refs(reviewer_call_result_refs),
        revision_call_refs=_dedupe_refs(revision_call_refs),
        revision_call_result_refs=_dedupe_refs(revision_call_result_refs),
        evidence_refs=_dedupe_refs([run_result.run_result_ref, *run_result.evidence_refs, *extra_evidence_refs]),
        metric_refs=_dedupe_refs([*run_result.metric_refs, *extra_metric_refs]),
        contract_hash=run_result.contract_hash,
    )
    write_json_ref(root, result.reviewed_run_result_ref, result.to_dict())
    return result


def _compile_result_from_run(run_result: DeepResearchRunResult) -> Any:
    from .compiler import DeepResearchTaskContractCompileResult

    return DeepResearchTaskContractCompileResult(
        request_id=run_result.request_id,
        run_workspace_ref=run_result.run_workspace_ref,
        task_contract_ref=run_result.task_contract_ref,
        workspace_policy_ref=_outer_ref(run_result.run_workspace_ref, WORKSPACE_POLICY_REF),
        permission_manifest_ref=_outer_ref(run_result.run_workspace_ref, PERMISSION_MANIFEST_REF),
        extension_lock_ref=None,
        worker_brief_ref=_outer_ref(run_result.run_workspace_ref, WORKER_BRIEF_REF),
        judge_rubric_ref=_outer_ref(run_result.run_workspace_ref, JUDGE_RUBRIC_REF),
        product_request_ref=_outer_ref(run_result.run_workspace_ref, PRODUCT_REQUEST_REF),
        manual_ref=run_result.manual_ref,
        source_packet_ref=run_result.source_packet_ref,
        source_collection_report_ref=_outer_ref(run_result.run_workspace_ref, SOURCE_COLLECTION_REPORT_REF),
        output_contract_ref=run_result.output_contract_ref,
        structural_check_policy_ref=_outer_ref(run_result.run_workspace_ref, STRUCTURAL_CHECK_POLICY_REF),
        compile_report_ref=_outer_ref(run_result.run_workspace_ref, "product_contract/compile_report.json"),
        expected_draft_refs=[ref.removeprefix(f"{run_result.run_workspace_ref}/") for ref in run_result.draft_artifact_refs],
        contract_hash=run_result.contract_hash,
    )


def _reviewer_permission_manifest(request: AcademicResearchRequest) -> PermissionManifest:
    return PermissionManifest(
        manifest_id=f"deepresearch-{request.request_id}-peer-reviewer-permissions",
        workspace_policy_ref=WORKSPACE_POLICY_REF,
        readable_refs=[
            "attempts",
            "contract",
            "compiled",
            "manuals",
            "policy",
            "product_contract",
            "projections",
            "reports",
            "sources",
            "reviews",
        ],
        writable_refs=["reviews", "attempts"],
        denied_refs=["secrets"],
        network_policy=NetworkPolicy.DISABLED,
    )


def _reviewer_adapter(
    reviewer_mode: str,
    piworker_config: PiAgentRuntimeConfig | None,
    piworker_environ: Mapping[str, str] | None,
) -> PiWorkerCallAdapter:
    if reviewer_mode == "fixture":
        return FixturePeerReviewerAdapter()
    if reviewer_mode == "piworker":
        return PiAgentRuntimeAdapter(
            piworker_config or PiAgentRuntimeConfig(provider_mode="live"),
            environ=piworker_environ,
        )
    raise ContractValidationError(f"deepresearch reviewer_mode must be one of {sorted(REVIEWER_MODES)}")


def _revision_researcher_adapter(
    researcher_mode: str,
    piworker_config: PiAgentRuntimeConfig | None,
    piworker_environ: Mapping[str, str] | None,
) -> PiWorkerCallAdapter:
    if researcher_mode == "fixture":
        return FixtureReviewedResearcherAdapter()
    return _researcher_adapter(researcher_mode, piworker_config, piworker_environ)


def _validate_review_spec(spec: Mapping[str, Any]) -> None:
    data = require_mapping(spec, "deepresearch_peer_review_spec")
    if require_non_empty_str(data.get("schema_version"), "deepresearch_peer_review_spec.schema_version") != "missionforge_deepresearch.peer_review_spec.v1":
        raise ContractValidationError("deepresearch_peer_review_spec.schema_version is unsupported")
    require_non_empty_str(data.get("request_id"), "deepresearch_peer_review_spec.request_id")
    require_int_at_least(data.get("round_index"), "deepresearch_peer_review_spec.round_index", 1)
    for field_name in (
        "contract_ref",
        "manual_ref",
        "judge_rubric_ref",
        "output_contract_ref",
        "structural_check_ref",
        "required_reviewer_report_ref",
        "required_next_directive_ref",
    ):
        validate_ref(data.get(field_name), f"deepresearch_peer_review_spec.{field_name}")
    require_non_empty_str(data.get("contract_hash"), "deepresearch_peer_review_spec.contract_hash")
    assert_refs_only_payload(data, "deepresearch_peer_review_spec")


def _peer_review_manual_text(request: AcademicResearchRequest) -> str:
    return f"""# DeepResearch Peer Reviewer Manual

You are a strict academic paper reviewer guiding an intermediate DeepResearch
draft for `{request.topic}`. Your job is to improve the next research update,
not to grant final acceptance.

Write:

- `reviews/round_XX/reviewer_report.md`
- `reviews/round_XX/next_research_directive.md`

Review like a serious program committee reviewer:

- identify missing seminal or recent work;
- challenge unsupported claims and weak citations;
- flag stale information, shallow taxonomy, and vague definitions;
- demand counterevidence or competing approaches where appropriate;
- point to source gaps instead of inventing facts;
- give the researcher a concrete next-step directive.

Do not change the frozen contract. Do not accept the work. Final product
acceptance belongs only to the independent judge after the reviewed draft is
ready.
"""


def _contract_id(workspace: Path) -> str:
    task_contract = read_json_ref(workspace, TASK_CONTRACT_REF, "task_contract")
    return require_non_empty_str(task_contract.get("contract_id"), "task_contract.contract_id")


def _review_spec_ref(round_index: int) -> str:
    return f"reviews/round_{round_index:02d}/review_spec.json"


def _reviewer_report_ref(round_index: int) -> str:
    return f"reviews/round_{round_index:02d}/reviewer_report.md"


def _next_directive_ref(round_index: int) -> str:
    return f"reviews/round_{round_index:02d}/next_research_directive.md"


def _research_state_ref(round_index: int) -> str:
    return f"reviews/round_{round_index:02d}/research_state.json"


def _reviewer_call_ref(round_index: int) -> str:
    return f"attempts/reviewer/round_{round_index:02d}/piworker_call.json"


def _reviewer_call_result_ref(round_index: int) -> str:
    return f"attempts/reviewer/round_{round_index:02d}/piworker_call_result.json"


def _reviewer_execution_report_ref(round_index: int) -> str:
    return f"attempts/reviewer/round_{round_index:02d}/execution_report.json"


def _reviewer_metrics_ref(round_index: int) -> str:
    return f"attempts/reviewer/round_{round_index:02d}/metrics.json"


def _revision_call_ref(round_index: int) -> str:
    return f"attempts/researcher/round_{round_index:02d}/piworker_call.json"


def _revision_call_result_ref(round_index: int) -> str:
    return f"attempts/researcher/round_{round_index:02d}/piworker_call_result.json"


def _outer_ref(run_workspace_ref: str, ref: str) -> str:
    return f"{validate_ref(run_workspace_ref, 'run_workspace_ref')}/{validate_ref(ref, 'run_ref')}"


def _inner_ref(run_workspace_ref: str, ref: str) -> str:
    safe_run_ref = validate_ref(run_workspace_ref, "run_workspace_ref")
    safe_ref = validate_ref(ref, "run_ref")
    prefix = f"{safe_run_ref}/"
    if not safe_ref.startswith(prefix):
        raise ContractValidationError(f"ref is not under run workspace: {safe_ref}")
    return safe_ref[len(prefix):]


def _is_in_run(run_workspace_ref: str, ref: str) -> bool:
    return validate_ref(ref, "ref").startswith(f"{validate_ref(run_workspace_ref, 'run_workspace_ref')}/")


def _dedupe_refs(refs: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for ref in refs:
        safe_ref = validate_ref(ref, "ref")
        if safe_ref not in seen:
            result.append(safe_ref)
            seen.add(safe_ref)
    return result
