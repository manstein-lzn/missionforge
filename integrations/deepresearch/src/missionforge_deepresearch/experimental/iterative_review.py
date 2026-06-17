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
    require_str_list,
    stable_json_hash,
    validate_ref,
)
from missionforge.piworker_call import PiWorkerCall, PiWorkerCallResult, PiWorkerCallResultStatus, PiWorkerCallRole
from missionforge.piworker_runtime import PiWorkerCallAdapter, run_piworker_call
from missionforge.runtime_results import ExecutionReport, WorkerAdapterResult, WorkerResult
from missionforge.task_contract import NetworkPolicy, PermissionManifest

from ..compiler import (
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
from ..product_contract import (
    AcademicResearchRequest,
    DeepResearchReviewedRunResult,
    DeepResearchReviewedRunStatus,
    DeepResearchRunResult,
    DeepResearchRunStatus,
    research_intensity_profile,
)
from ..runtime import (
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
from ..source_collector import AcademicSourceCollectionConfig
from ..workspace import read_json_ref, ref_is_non_empty_file, write_json_ref, write_text_ref


REVIEWER_MODES = {"fixture", "piworker"}
REVIEW_OBSERVATION_SCHEMA_VERSION = "missionforge_deepresearch.reviewer_observation.v1"
REVIEW_OBSERVATION_SCHEMA_DOC_VERSION = "missionforge_deepresearch.reviewer_observation_schema.v1"
RESEARCH_STATE_SCHEMA_VERSION = "missionforge_deepresearch.research_state.v1"
RESEARCH_STATE_SCHEMA_DOC_VERSION = "missionforge_deepresearch.research_state_schema.v1"
REVIEW_OBSERVATION_DECISIONS = {"continue", "ready_for_judge", "tool_blocked", "revision_required", "rejected"}
REVIEW_OBSERVATION_NEXT_ACTIONS = {
    "researcher_revision",
    "judge",
    "stop_blocked",
    "contract_revision",
    "stop_failed",
}
REVIEW_OBSERVATION_REQUIRED_FIELDS = [
    "schema_version",
    "request_id",
    "round_index",
    "decision",
    "contract_ref",
    "contract_hash",
    "reviewer_report_ref",
    "next_directive_ref",
]
REVIEW_OBSERVATION_OPTIONAL_FIELDS = [
    "artifact_refs",
    "evidence_refs",
    "blocker_refs",
    "state_refs",
    "allowed_next_actions",
]
REVIEW_OBSERVATION_REF_FIELDS = [
    "contract_ref",
    "reviewer_report_ref",
    "next_directive_ref",
    "artifact_refs",
    "evidence_refs",
    "blocker_refs",
    "state_refs",
]
RESEARCH_STATE_REQUIRED_FIELDS = [
    "schema_version",
    "request_id",
    "round_index",
    "contract_ref",
    "contract_hash",
    "source_packet_ref",
    "reviewer_observation_ref",
    "reviewer_report_ref",
    "next_directive_ref",
    "prior_state_refs",
    "belief_updates",
    "current_hypotheses",
    "confidence_notes",
    "unresolved_gaps",
    "next_best_actions",
    "updated_artifact_refs",
    "evidence_refs",
]
RESEARCH_STATE_REF_FIELDS = [
    "contract_ref",
    "source_packet_ref",
    "reviewer_observation_ref",
    "reviewer_report_ref",
    "next_directive_ref",
    "prior_state_refs",
    "reviewer_guidance_refs",
    "updated_artifact_refs",
    "evidence_refs",
]
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
            reviewer_observation_refs=[],
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
    reviewer_observation_refs: list[str] = []
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
        reviewer_observation_schema_ref = _reviewer_observation_schema_ref(round_index)
        research_state_schema_ref = _research_state_schema_ref(round_index)
        write_json_ref(run_root, reviewer_observation_schema_ref, _reviewer_observation_schema_payload(round_index))
        write_json_ref(run_root, research_state_schema_ref, _research_state_schema_payload(round_index))
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
        observation_ref = _reviewer_observation_ref(round_index)
        reviewer_call_ref = _reviewer_call_ref(round_index)
        reviewer_call_result_ref = _reviewer_call_result_ref(round_index)
        reviewer_report_refs.append(_outer_ref(current_result.run_workspace_ref, reviewer_report_ref))
        reviewer_observation_refs.append(_outer_ref(current_result.run_workspace_ref, observation_ref))
        reviewer_call_refs.append(_outer_ref(current_result.run_workspace_ref, reviewer_call_ref))
        reviewer_call_result_refs.append(_outer_ref(current_result.run_workspace_ref, reviewer_call_result_ref))
        extra_evidence_refs.extend(
            [
                _outer_ref(current_result.run_workspace_ref, _review_spec_ref(round_index)),
                _outer_ref(current_result.run_workspace_ref, reviewer_observation_schema_ref),
                _outer_ref(current_result.run_workspace_ref, research_state_schema_ref),
                _outer_ref(current_result.run_workspace_ref, reviewer_report_ref),
                _outer_ref(current_result.run_workspace_ref, directive_ref),
                _outer_ref(current_result.run_workspace_ref, observation_ref),
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
                reviewer_observation_refs=reviewer_observation_refs,
                research_state_refs=research_state_refs,
                reviewer_call_refs=reviewer_call_refs,
                reviewer_call_result_refs=reviewer_call_result_refs,
                revision_call_refs=revision_call_refs,
                revision_call_result_refs=revision_call_result_refs,
                extra_evidence_refs=extra_evidence_refs,
                extra_metric_refs=extra_metric_refs,
            )

        observation = _normalize_reviewer_observation(
            read_json_ref(run_root, observation_ref, "deepresearch_reviewer_observation"),
            request=request,
            round_index=round_index,
            contract_hash=current_result.contract_hash,
            reviewer_report_ref=reviewer_report_ref,
            directive_ref=directive_ref,
        )
        write_json_ref(run_root, observation_ref, observation)
        decision = observation["decision"]
        if decision == "ready_for_judge":
            current_result = _write_run_result_with_extra_refs(
                root,
                source_result=current_result,
                extra_evidence_refs=extra_evidence_refs,
                extra_metric_refs=extra_metric_refs,
            )
            return _write_reviewed_result(
                root,
                run_result=current_result,
                status=DeepResearchReviewedRunStatus.DRAFT_READY,
                review_round_count=round_index,
                reviewer_report_refs=reviewer_report_refs,
                reviewer_observation_refs=reviewer_observation_refs,
                research_state_refs=research_state_refs,
                reviewer_call_refs=reviewer_call_refs,
                reviewer_call_result_refs=reviewer_call_result_refs,
                revision_call_refs=revision_call_refs,
                revision_call_result_refs=revision_call_result_refs,
                extra_evidence_refs=extra_evidence_refs,
                extra_metric_refs=extra_metric_refs,
            )
        if decision in {"tool_blocked", "revision_required"}:
            return _write_reviewed_result(
                root,
                run_result=current_result,
                status=DeepResearchReviewedRunStatus.BLOCKED,
                review_round_count=round_index,
                reviewer_report_refs=reviewer_report_refs,
                reviewer_observation_refs=reviewer_observation_refs,
                research_state_refs=research_state_refs,
                reviewer_call_refs=reviewer_call_refs,
                reviewer_call_result_refs=reviewer_call_result_refs,
                revision_call_refs=revision_call_refs,
                revision_call_result_refs=revision_call_result_refs,
                extra_evidence_refs=extra_evidence_refs,
                extra_metric_refs=extra_metric_refs,
            )
        if decision == "rejected":
            return _write_reviewed_result(
                root,
                run_result=current_result,
                status=DeepResearchReviewedRunStatus.FAILED,
                review_round_count=round_index,
                reviewer_report_refs=reviewer_report_refs,
                reviewer_observation_refs=reviewer_observation_refs,
                research_state_refs=research_state_refs,
                reviewer_call_refs=reviewer_call_refs,
                reviewer_call_result_refs=reviewer_call_result_refs,
                revision_call_refs=revision_call_refs,
                revision_call_result_refs=revision_call_result_refs,
                extra_evidence_refs=extra_evidence_refs,
                extra_metric_refs=extra_metric_refs,
            )

        revision_permission_manifest_ref = _revision_permission_manifest_ref(round_index)
        revision_permission_manifest = _revision_permission_manifest(permission_manifest)
        write_json_ref(run_root, revision_permission_manifest_ref, revision_permission_manifest.to_dict())
        extra_evidence_refs.append(_outer_ref(current_result.run_workspace_ref, revision_permission_manifest_ref))
        revision_result = _run_research_revision_round(
            request,
            workspace=run_root,
            task_contract_id=task_contract.contract_id,
            contract_hash=current_result.contract_hash,
            permission_manifest=permission_manifest,
            permission_manifest_ref=revision_permission_manifest_ref,
            round_index=round_index,
            directive_ref=directive_ref,
            reviewer_report_ref=reviewer_report_ref,
            reviewer_observation_ref=observation_ref,
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
                _outer_ref(current_result.run_workspace_ref, _research_state_schema_ref(round_index)),
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
                reviewer_observation_refs=reviewer_observation_refs,
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
        reviewer_observation_refs=reviewer_observation_refs,
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

    from ..judging import judge_deepresearch_run

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
    if reviewed.status is not DeepResearchReviewedRunStatus.DRAFT_READY:
        return reviewed
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
    prior_research_state_refs = _dedupe_refs([ref for ref in evidence_refs if ref.endswith("/research_state.json")])
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
        "prior_research_state_refs": prior_research_state_refs,
        "required_reviewer_report_ref": _reviewer_report_ref(round_index),
        "required_next_directive_ref": _next_directive_ref(round_index),
        "required_reviewer_observation_ref": _reviewer_observation_ref(round_index),
        "required_reviewer_observation_schema_ref": _reviewer_observation_schema_ref(round_index),
        "required_research_state_schema_ref": _research_state_schema_ref(round_index),
        "required_observation_shape": _required_reviewer_observation_shape(round_index),
        "required_research_state_shape": _required_research_state_shape(round_index),
        "reviewer_authority": "guide_research_only_no_acceptance",
        "allowed_observation_decisions": sorted(REVIEW_OBSERVATION_DECISIONS),
        "review_focus": [
            "complete one-pass critique rather than incremental drip feedback",
            "coverage of central papers and engineering evidence",
            "freshness and stale-information risk",
            "citation support for material claims",
            "missing counterevidence or competing schools",
            "taxonomy, definitions, and conceptual precision",
            "posterior coherence across prior research_state refs when present",
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
            "Do not accept the work. Give one complete, high-quality critique in this round: "
            "measure the current posterior from the visible draft, evidence refs, and any prior "
            "research_state refs; identify all material flaws, missing evidence, stale claims, "
            "and the next research directive that should let the researcher repair the draft when "
            "repair is the right next step. Write the structured reviewer observation exactly as "
            "specified in review_spec.required_observation_shape. The follow-up research_state.json "
            "must be written exactly as specified in review_spec.required_research_state_shape; "
            "Python will route only on those control artifacts."
        ),
        visible_refs=_dedupe_refs(
            [
                _review_spec_ref(round_index),
                _reviewer_observation_schema_ref(round_index),
                _research_state_schema_ref(round_index),
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
        expected_output_refs=[
            _reviewer_report_ref(round_index),
            _next_directive_ref(round_index),
            _reviewer_observation_ref(round_index),
        ],
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
            "request_id": request.request_id,
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
    permission_manifest_ref: str,
    round_index: int,
    directive_ref: str,
    reviewer_report_ref: str,
    reviewer_observation_ref: str,
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
            permission_manifest_ref,
            WORKER_BRIEF_REF,
            PRODUCT_REQUEST_REF,
            MANUAL_REF,
            PEER_REVIEW_MANUAL_REF,
            _reviewer_observation_schema_ref(round_index),
            _research_state_schema_ref(round_index),
            SOURCE_PACKET_REF,
            SOURCE_COLLECTION_REPORT_REF,
            OUTPUT_CONTRACT_REF,
            STRUCTURAL_CHECK_POLICY_REF,
            *([extension_lock_ref] if extension_lock_ref else []),
            _review_spec_ref(round_index),
            reviewer_report_ref,
            directive_ref,
            reviewer_observation_ref,
            *previous_research_state_refs,
        ]
    )
    evidence_refs = _dedupe_refs(
        [
            SOURCE_PACKET_REF,
            SOURCE_COLLECTION_REPORT_REF,
            reviewer_report_ref,
            directive_ref,
            reviewer_observation_ref,
            *previous_research_state_refs,
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
            "structured reviewer observation, next research directive, frozen contract, and available tools. First update "
            "sources/source_packet.json with any added or corrected source_records; then update report artifacts "
            "so material claims cite those source ids. Write research_state.json as the revised posterior for this "
            "round: include contract_ref, contract_hash, source_packet_ref, reviewer_observation_ref, "
            "reviewer_report_ref, next_directive_ref, prior_state_refs, belief_updates, current_hypotheses, "
            "confidence_notes, unresolved_gaps, next_best_actions, updated_artifact_refs, and evidence_refs. "
            "Do not claim final acceptance."
        ),
        visible_refs=visible_refs,
        writable_refs=_dedupe_refs([*permission_manifest.writable_refs, "reviews"]),
        expected_output_refs=expected_refs,
        permission_manifest_ref=permission_manifest_ref,
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
        state_ref = _research_state_ref(round_index)
        if not ref_is_non_empty_file(workspace, state_ref):
            raise ContractValidationError("deepresearch revision did not produce research_state.json")
        state = _normalize_research_state(
            read_json_ref(workspace, state_ref, "deepresearch_research_state"),
            request=request,
            round_index=round_index,
            contract_hash=contract_hash,
            reviewer_observation_ref=reviewer_observation_ref,
            reviewer_report_ref=reviewer_report_ref,
            directive_ref=directive_ref,
        )
        write_json_ref(workspace, state_ref, state)
    return call_result


class FixturePeerReviewerAdapter:
    """Offline peer reviewer adapter for reviewer-guided loop tests."""

    adapter_family = "fixture_deepresearch_peer_reviewer"

    def __init__(self, decision: str = "continue") -> None:
        if decision not in REVIEW_OBSERVATION_DECISIONS:
            raise ContractValidationError(
                f"fixture DeepResearch peer reviewer decision must be one of {sorted(REVIEW_OBSERVATION_DECISIONS)}"
            )
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
        call.validate()
        if call.role is not PiWorkerCallRole.JUDGE:
            raise ContractValidationError("fixture DeepResearch peer reviewer only supports judge-role calls")
        round_index = int(call.metadata.get("round_index", 1))
        request_id = str(call.metadata.get("request_id", "fixture"))
        reviewer_report_ref = _reviewer_report_ref(round_index)
        directive_ref = _next_directive_ref(round_index)
        observation_ref = _reviewer_observation_ref(round_index)
        write_text_ref(
            workspace,
            reviewer_report_ref,
            (
                "# Peer Review Report\n\n"
                f"- Verdict: {self.decision}; this is not final acceptance.\n"
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
        write_json_ref(
            workspace,
            observation_ref,
            {
                "schema_version": REVIEW_OBSERVATION_SCHEMA_VERSION,
                "request_id": request_id,
                "round_index": round_index,
                "decision": self.decision,
                "contract_ref": call.contract_ref,
                "contract_hash": call.contract_hash,
                "reviewer_report_ref": reviewer_report_ref,
                "next_directive_ref": directive_ref,
                "artifact_refs": [],
                "evidence_refs": [_review_spec_ref(round_index)],
                "blocker_refs": [reviewer_report_ref] if self.decision in {"tool_blocked", "revision_required", "rejected"} else [],
                "state_refs": [
                    ref for ref in call.visible_refs if ref.startswith("reviews/") and ref.endswith("/research_state.json")
                ],
                "allowed_next_actions": _next_actions_for_review_decision(self.decision),
            },
        )
        metrics_ref = _reviewer_metrics_ref(round_index)
        execution_report_ref = _reviewer_execution_report_ref(round_index)
        write_json_ref(workspace, metrics_ref, {"metric_ref": metrics_ref, "fixture": True, "round_index": round_index})
        report = ExecutionReport(
            report_id=f"deepresearch-fixture-peer-review-round-{round_index:02d}",
            call_id=call.call_id,
            status="completed",
            produced_artifacts=[reviewer_report_ref, directive_ref, observation_ref],
            changed_refs=[reviewer_report_ref, directive_ref, observation_ref, execution_report_ref, metrics_ref],
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
                    "schema_version": RESEARCH_STATE_SCHEMA_VERSION,
                    "request_id": call.metadata.get("request_id", "fixture"),
                    "round_index": round_index,
                    "posterior_kind": "review_guided_research_state",
                    "contract_ref": call.contract_ref,
                    "contract_hash": call.contract_hash,
                    "source_packet_ref": SOURCE_PACKET_REF,
                    "prior_state_refs": [
                        ref for ref in call.visible_refs if ref.startswith("reviews/") and ref.endswith("/research_state.json")
                    ],
                    "reviewer_observation_ref": _reviewer_observation_ref(round_index),
                    "reviewer_report_ref": _reviewer_report_ref(round_index),
                    "next_directive_ref": _next_directive_ref(round_index),
                    "belief_updates": [
                        {
                            "update": "Reviewer-guided revision strengthened source coverage and citation support.",
                            "supporting_refs": [SOURCE_PACKET_REF, "reports/evidence_index.md"],
                            "risk_refs": ["reports/source_gaps.md"],
                        }
                    ],
                    "current_hypotheses": [
                        {
                            "hypothesis": "The revised report is structurally ready for independent judging.",
                            "supporting_refs": ["reports/final_report.md", SOURCE_PACKET_REF],
                        }
                    ],
                    "confidence_notes": [
                        {
                            "topic": "Fixture confidence is limited to structural contract coverage.",
                            "evidence_refs": [SOURCE_PACKET_REF],
                            "risk_refs": ["reports/source_gaps.md"],
                        }
                    ],
                    "unresolved_gaps": [
                        {
                            "gap": "Fixture mode does not perform live semantic source triage.",
                            "gap_refs": ["reports/source_gaps.md"],
                            "next_action": "Use a live researcher and reviewer for semantic validation.",
                        }
                    ],
                    "next_best_actions": [
                        {
                            "action": "submit_to_independent_judge",
                            "depends_on_refs": ["reports/final_report.md", "reports/evidence_index.md"],
                        }
                    ],
                    "updated_artifact_refs": list(EXPECTED_WORKER_OUTPUT_REFS),
                    "evidence_refs": [SOURCE_PACKET_REF, "reports/evidence_index.md", "reports/source_gaps.md"],
                    "reviewer_guidance_refs": [
                        _reviewer_report_ref(round_index),
                        _next_directive_ref(round_index),
                        _reviewer_observation_ref(round_index),
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


def _write_run_result_with_extra_refs(
    root: Path,
    *,
    source_result: DeepResearchRunResult,
    extra_evidence_refs: list[str],
    extra_metric_refs: list[str],
) -> DeepResearchRunResult:
    result = DeepResearchRunResult(
        request_id=source_result.request_id,
        status=source_result.status,
        run_workspace_ref=source_result.run_workspace_ref,
        run_result_ref=source_result.run_result_ref,
        task_contract_ref=source_result.task_contract_ref,
        manual_ref=source_result.manual_ref,
        source_packet_ref=source_result.source_packet_ref,
        output_contract_ref=source_result.output_contract_ref,
        researcher_call_ref=source_result.researcher_call_ref,
        researcher_call_result_ref=source_result.researcher_call_result_ref,
        structural_check_ref=source_result.structural_check_ref,
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
    reviewer_observation_refs: list[str],
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
        reviewer_observation_refs=_dedupe_refs(reviewer_observation_refs),
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
    from ..compiler import DeepResearchTaskContractCompileResult

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


def _revision_permission_manifest(base_manifest: PermissionManifest) -> PermissionManifest:
    return PermissionManifest(
        manifest_id=f"{base_manifest.manifest_id}-review-revision",
        workspace_policy_ref=base_manifest.workspace_policy_ref,
        readable_refs=_dedupe_refs([*base_manifest.readable_refs, "reviews"]),
        writable_refs=_dedupe_refs([*base_manifest.writable_refs, "reviews"]),
        denied_refs=list(base_manifest.denied_refs),
        allowed_commands=list(base_manifest.allowed_commands),
        network_policy=base_manifest.network_policy,
        env_allowlist=list(base_manifest.env_allowlist),
        secret_ref=base_manifest.secret_ref,
        unsupported_hard_policies=list(base_manifest.unsupported_hard_policies),
        extension_grants=list(base_manifest.extension_grants),
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
        "required_reviewer_observation_ref",
        "required_reviewer_observation_schema_ref",
        "required_research_state_schema_ref",
    ):
        validate_ref(data.get(field_name), f"deepresearch_peer_review_spec.{field_name}")
    require_non_empty_str(data.get("contract_hash"), "deepresearch_peer_review_spec.contract_hash")
    decisions = set(require_str_list(data.get("allowed_observation_decisions", []), "deepresearch_peer_review_spec.allowed_observation_decisions"))
    if decisions != REVIEW_OBSERVATION_DECISIONS:
        raise ContractValidationError("deepresearch_peer_review_spec.allowed_observation_decisions does not match")
    shape = require_mapping(
        data.get("required_observation_shape"),
        "deepresearch_peer_review_spec.required_observation_shape",
    )
    if (
        require_non_empty_str(
            shape.get("schema_version"),
            "deepresearch_peer_review_spec.required_observation_shape.schema_version",
        )
        != REVIEW_OBSERVATION_SCHEMA_VERSION
    ):
        raise ContractValidationError("deepresearch_peer_review_spec.required_observation_shape.schema_version is unsupported")
    required_fields = set(
        require_str_list(
            shape.get("required_fields", []),
            "deepresearch_peer_review_spec.required_observation_shape.required_fields",
        )
    )
    for field_name in (
        "schema_version",
        "request_id",
        "round_index",
        "decision",
        "contract_ref",
        "contract_hash",
        "reviewer_report_ref",
        "next_directive_ref",
    ):
        if field_name not in required_fields:
            raise ContractValidationError(
                f"deepresearch_peer_review_spec.required_observation_shape.required_fields missing {field_name}"
            )
    shape_decisions = set(
        require_str_list(
            shape.get("allowed_decisions", []),
            "deepresearch_peer_review_spec.required_observation_shape.allowed_decisions",
        )
    )
    if shape_decisions != REVIEW_OBSERVATION_DECISIONS:
        raise ContractValidationError("deepresearch_peer_review_spec.required_observation_shape.allowed_decisions does not match")
    validate_ref(
        shape.get("reviewer_report_ref"),
        "deepresearch_peer_review_spec.required_observation_shape.reviewer_report_ref",
    )
    validate_ref(
        shape.get("next_directive_ref"),
        "deepresearch_peer_review_spec.required_observation_shape.next_directive_ref",
    )
    assert_refs_only_payload(data, "deepresearch_peer_review_spec")

    state_shape = require_mapping(
        data.get("required_research_state_shape"),
        "deepresearch_peer_review_spec.required_research_state_shape",
    )
    if (
        require_non_empty_str(
            state_shape.get("schema_version"),
            "deepresearch_peer_review_spec.required_research_state_shape.schema_version",
        )
        != RESEARCH_STATE_SCHEMA_VERSION
    ):
        raise ContractValidationError("deepresearch_peer_review_spec.required_research_state_shape.schema_version is unsupported")
    state_required_fields = set(
        require_str_list(
            state_shape.get("required_fields", []),
            "deepresearch_peer_review_spec.required_research_state_shape.required_fields",
        )
    )
    if state_required_fields != set(RESEARCH_STATE_REQUIRED_FIELDS):
        raise ContractValidationError("deepresearch_peer_review_spec.required_research_state_shape.required_fields does not match")
    state_optional_fields = set(
        require_str_list(
            state_shape.get("optional_fields", []),
            "deepresearch_peer_review_spec.required_research_state_shape.optional_fields",
        )
    )
    if state_optional_fields != {"posterior_kind", "reviewer_guidance_refs"}:
        raise ContractValidationError("deepresearch_peer_review_spec.required_research_state_shape.optional_fields does not match")
    state_refs_only_fields = set(
        require_str_list(
            state_shape.get("refs_only_fields", []),
            "deepresearch_peer_review_spec.required_research_state_shape.refs_only_fields",
        )
    )
    if state_refs_only_fields != set(RESEARCH_STATE_REF_FIELDS):
        raise ContractValidationError("deepresearch_peer_review_spec.required_research_state_shape.refs_only_fields does not match")
    validate_ref(
        state_shape.get("reviewer_observation_ref"),
        "deepresearch_peer_review_spec.required_research_state_shape.reviewer_observation_ref",
    )
    validate_ref(
        state_shape.get("reviewer_report_ref"),
        "deepresearch_peer_review_spec.required_research_state_shape.reviewer_report_ref",
    )
    validate_ref(
        state_shape.get("next_directive_ref"),
        "deepresearch_peer_review_spec.required_research_state_shape.next_directive_ref",
    )
    assert_refs_only_payload(state_shape, "deepresearch_peer_review_spec.required_research_state_shape")


def _reviewer_observation_schema_ref(round_index: int) -> str:
    return f"reviews/round_{round_index:02d}/reviewer_observation_schema.json"


def _research_state_schema_ref(round_index: int) -> str:
    return f"reviews/round_{round_index:02d}/research_state_schema.json"


def _reviewer_observation_schema_payload(round_index: int) -> dict[str, Any]:
    return {
        "schema_version": REVIEW_OBSERVATION_SCHEMA_DOC_VERSION,
        "artifact_ref": _reviewer_observation_ref(round_index),
        "required_fields": list(REVIEW_OBSERVATION_REQUIRED_FIELDS),
        "optional_fields": list(REVIEW_OBSERVATION_OPTIONAL_FIELDS),
        "refs_only_fields": list(REVIEW_OBSERVATION_REF_FIELDS),
        "allowed_decisions": sorted(REVIEW_OBSERVATION_DECISIONS),
        "decision_next_actions": {decision: _next_actions_for_review_decision(decision) for decision in sorted(REVIEW_OBSERVATION_DECISIONS)},
        "notes": [
            "This schema artifact is the canonical contract for reviewer_observation.json.",
            "The runtime routes only on the JSON control artifact, not on the schema artifact content.",
        ],
    }


def _research_state_schema_payload(round_index: int) -> dict[str, Any]:
    return {
        "schema_version": RESEARCH_STATE_SCHEMA_DOC_VERSION,
        "artifact_ref": _research_state_ref(round_index),
        "required_fields": list(RESEARCH_STATE_REQUIRED_FIELDS),
        "optional_fields": ["posterior_kind", "reviewer_guidance_refs"],
        "refs_only_fields": list(RESEARCH_STATE_REF_FIELDS),
        "notes": [
            "This schema artifact is the canonical contract for research_state.json.",
            "The runtime validates the produced state artifact against the frozen control fields.",
        ],
    }


def _research_state_ref(round_index: int) -> str:
    return f"reviews/round_{round_index:02d}/research_state.json"


def require_list_of_mappings(value: Any, field_name: str) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise ContractValidationError(f"{field_name} must be a list of mappings")
    result: list[dict[str, Any]] = []
    for index, item in enumerate(value):
        if not isinstance(item, Mapping):
            raise ContractValidationError(f"{field_name}[{index}] must be a mapping")
        result.append(dict(item))
    return result


def _normalize_reviewer_observation(
    payload: Mapping[str, Any],
    *,
    request: AcademicResearchRequest,
    round_index: int,
    contract_hash: str,
    reviewer_report_ref: str,
    directive_ref: str,
) -> dict[str, Any]:
    data = require_mapping(payload, "deepresearch_reviewer_observation")
    schema_version = require_non_empty_str(
        data.get("schema_version"),
        "deepresearch_reviewer_observation.schema_version",
    )
    if schema_version != REVIEW_OBSERVATION_SCHEMA_VERSION:
        raise ContractValidationError("deepresearch_reviewer_observation.schema_version is unsupported")
    request_id = require_non_empty_str(data.get("request_id"), "deepresearch_reviewer_observation.request_id")
    if request_id != request.request_id:
        raise ContractValidationError("deepresearch_reviewer_observation.request_id does not match request")
    observed_round = require_int_at_least(data.get("round_index"), "deepresearch_reviewer_observation.round_index", 1)
    if observed_round != round_index:
        raise ContractValidationError("deepresearch_reviewer_observation.round_index does not match review round")
    decision = require_non_empty_str(data.get("decision"), "deepresearch_reviewer_observation.decision")
    if decision not in REVIEW_OBSERVATION_DECISIONS:
        raise ContractValidationError(
            f"deepresearch_reviewer_observation.decision must be one of {sorted(REVIEW_OBSERVATION_DECISIONS)}"
        )
    observed_contract_ref = validate_ref(data.get("contract_ref"), "deepresearch_reviewer_observation.contract_ref")
    if observed_contract_ref != TASK_CONTRACT_REF:
        raise ContractValidationError("deepresearch_reviewer_observation.contract_ref does not match task contract")
    observed_contract_hash = require_non_empty_str(
        data.get("contract_hash"),
        "deepresearch_reviewer_observation.contract_hash",
    )
    if observed_contract_hash != contract_hash:
        raise ContractValidationError("deepresearch_reviewer_observation.contract_hash does not match current run")
    observed_report_ref = validate_ref(
        data.get("reviewer_report_ref"),
        "deepresearch_reviewer_observation.reviewer_report_ref",
    )
    if observed_report_ref != reviewer_report_ref:
        raise ContractValidationError("deepresearch_reviewer_observation.reviewer_report_ref does not match")
    observed_directive_ref = validate_ref(
        data.get("next_directive_ref"),
        "deepresearch_reviewer_observation.next_directive_ref",
    )
    if observed_directive_ref != directive_ref:
        raise ContractValidationError("deepresearch_reviewer_observation.next_directive_ref does not match")
    allowed_next_actions = require_str_list(
        data.get("allowed_next_actions", _next_actions_for_review_decision(decision)),
        "deepresearch_reviewer_observation.allowed_next_actions",
    )
    unknown_actions = sorted(set(allowed_next_actions) - REVIEW_OBSERVATION_NEXT_ACTIONS)
    if unknown_actions:
        raise ContractValidationError(f"deepresearch_reviewer_observation.allowed_next_actions contains unknown values: {unknown_actions}")
    expected_actions = _next_actions_for_review_decision(decision)
    if sorted(set(allowed_next_actions)) != expected_actions:
        raise ContractValidationError("deepresearch_reviewer_observation.allowed_next_actions does not match decision")
    normalized = {
        "schema_version": REVIEW_OBSERVATION_SCHEMA_VERSION,
        "request_id": request_id,
        "round_index": observed_round,
        "decision": decision,
        "contract_ref": observed_contract_ref,
        "contract_hash": observed_contract_hash,
        "reviewer_report_ref": observed_report_ref,
        "next_directive_ref": observed_directive_ref,
        "artifact_refs": _dedupe_refs(require_str_list(data.get("artifact_refs", []), "deepresearch_reviewer_observation.artifact_refs")),
        "evidence_refs": _dedupe_refs(require_str_list(data.get("evidence_refs", []), "deepresearch_reviewer_observation.evidence_refs")),
        "blocker_refs": _dedupe_refs(require_str_list(data.get("blocker_refs", []), "deepresearch_reviewer_observation.blocker_refs")),
        "state_refs": _dedupe_refs(require_str_list(data.get("state_refs", []), "deepresearch_reviewer_observation.state_refs")),
        "allowed_next_actions": sorted(set(allowed_next_actions)),
    }
    assert_refs_only_payload(normalized, "deepresearch_reviewer_observation")
    return normalized


def _normalize_research_state(
    payload: Mapping[str, Any],
    *,
    request: AcademicResearchRequest,
    round_index: int,
    contract_hash: str,
    reviewer_observation_ref: str,
    reviewer_report_ref: str,
    directive_ref: str,
) -> dict[str, Any]:
    data = require_mapping(payload, "deepresearch_research_state")
    if require_non_empty_str(data.get("schema_version"), "deepresearch_research_state.schema_version") != RESEARCH_STATE_SCHEMA_VERSION:
        raise ContractValidationError("deepresearch_research_state.schema_version is unsupported")
    request_id = require_non_empty_str(data.get("request_id"), "deepresearch_research_state.request_id")
    if request_id != request.request_id:
        raise ContractValidationError("deepresearch_research_state.request_id does not match request")
    observed_round = require_int_at_least(data.get("round_index"), "deepresearch_research_state.round_index", 1)
    if observed_round != round_index:
        raise ContractValidationError("deepresearch_research_state.round_index does not match review round")
    observed_contract_ref = validate_ref(data.get("contract_ref"), "deepresearch_research_state.contract_ref")
    if observed_contract_ref != TASK_CONTRACT_REF:
        raise ContractValidationError("deepresearch_research_state.contract_ref does not match task contract")
    observed_contract_hash = require_non_empty_str(data.get("contract_hash"), "deepresearch_research_state.contract_hash")
    if observed_contract_hash != contract_hash:
        raise ContractValidationError("deepresearch_research_state.contract_hash does not match current run")
    observed_source_packet_ref = validate_ref(data.get("source_packet_ref"), "deepresearch_research_state.source_packet_ref")
    if observed_source_packet_ref != SOURCE_PACKET_REF:
        raise ContractValidationError("deepresearch_research_state.source_packet_ref does not match source packet")
    observed_reviewer_observation_ref = validate_ref(
        data.get("reviewer_observation_ref"),
        "deepresearch_research_state.reviewer_observation_ref",
    )
    if observed_reviewer_observation_ref != reviewer_observation_ref:
        raise ContractValidationError("deepresearch_research_state.reviewer_observation_ref does not match review round")
    observed_reviewer_report_ref = validate_ref(
        data.get("reviewer_report_ref"),
        "deepresearch_research_state.reviewer_report_ref",
    )
    if observed_reviewer_report_ref != reviewer_report_ref:
        raise ContractValidationError("deepresearch_research_state.reviewer_report_ref does not match review round")
    observed_directive_ref = validate_ref(
        data.get("next_directive_ref"),
        "deepresearch_research_state.next_directive_ref",
    )
    if observed_directive_ref != directive_ref:
        raise ContractValidationError("deepresearch_research_state.next_directive_ref does not match review round")
    normalized = {
        "schema_version": RESEARCH_STATE_SCHEMA_VERSION,
        "request_id": request_id,
        "round_index": observed_round,
        "contract_ref": observed_contract_ref,
        "contract_hash": observed_contract_hash,
        "source_packet_ref": observed_source_packet_ref,
        "reviewer_observation_ref": observed_reviewer_observation_ref,
        "reviewer_report_ref": observed_reviewer_report_ref,
        "next_directive_ref": observed_directive_ref,
        "prior_state_refs": _dedupe_refs(require_str_list(data.get("prior_state_refs", []), "deepresearch_research_state.prior_state_refs")),
        "belief_updates": list(require_list_of_mappings(data.get("belief_updates", []), "deepresearch_research_state.belief_updates")),
        "current_hypotheses": list(require_list_of_mappings(data.get("current_hypotheses", []), "deepresearch_research_state.current_hypotheses")),
        "confidence_notes": list(require_list_of_mappings(data.get("confidence_notes", []), "deepresearch_research_state.confidence_notes")),
        "unresolved_gaps": list(require_list_of_mappings(data.get("unresolved_gaps", []), "deepresearch_research_state.unresolved_gaps")),
        "next_best_actions": list(require_list_of_mappings(data.get("next_best_actions", []), "deepresearch_research_state.next_best_actions")),
        "updated_artifact_refs": _dedupe_refs(require_str_list(data.get("updated_artifact_refs", []), "deepresearch_research_state.updated_artifact_refs")),
        "evidence_refs": _dedupe_refs(require_str_list(data.get("evidence_refs", []), "deepresearch_research_state.evidence_refs")),
    }
    posterior_kind = data.get("posterior_kind")
    if posterior_kind is not None:
        normalized["posterior_kind"] = require_non_empty_str(posterior_kind, "deepresearch_research_state.posterior_kind")
    reviewer_guidance_refs = data.get("reviewer_guidance_refs")
    if reviewer_guidance_refs is not None:
        normalized["reviewer_guidance_refs"] = _dedupe_refs(
            require_str_list(reviewer_guidance_refs, "deepresearch_research_state.reviewer_guidance_refs")
        )
    assert_refs_only_payload(normalized, "deepresearch_research_state")
    return normalized


def _next_actions_for_review_decision(decision: str) -> list[str]:
    if decision == "continue":
        return ["researcher_revision"]
    if decision == "ready_for_judge":
        return ["judge"]
    if decision == "tool_blocked":
        return ["stop_blocked"]
    if decision == "revision_required":
        return ["contract_revision"]
    if decision == "rejected":
        return ["stop_failed"]
    raise ContractValidationError(
        f"deepresearch reviewer observation decision must be one of {sorted(REVIEW_OBSERVATION_DECISIONS)}"
    )


def _peer_review_manual_text(request: AcademicResearchRequest) -> str:
    return f"""# DeepResearch Peer Reviewer Manual

You are a strict academic paper reviewer guiding an intermediate DeepResearch
draft for `{request.topic}`. Your job is to improve the next research update,
not to grant final acceptance.

Treat the loop as state refinement:

- the frozen contract, source packet, draft artifacts, and prior state refs are
  the prior/current posterior you can inspect;
- your report and directive are the expert measurement;
- `reviewer_observation.json` is the small control artifact;
- the researcher writes the next `research_state.json` posterior only after a
  `continue` decision;
- the independent judge remains the only final acceptance authority.

Write:

- `reviews/round_XX/reviewer_report.md`
- `reviews/round_XX/next_research_directive.md`
- `reviews/round_XX/reviewer_observation.json`

The JSON observation is the only control artifact the Python loop may route on.
Use exactly one decision:

- `continue`: another researcher revision is likely to improve the posterior;
- `ready_for_judge`: no further review-guided revision is needed before the
  independent judge;
- `tool_blocked`: missing tools or inaccessible evidence prevent progress;
- `revision_required`: the frozen contract must change before progress is
  legitimate;
- `rejected`: the draft should fail rather than continue this contract.

The observation must cite the report and directive refs, include the current
contract ref/hash, include any research-state refs you relied on in `state_refs`,
and keep all blockers or state pointers as refs. Do not put raw transcripts,
prompts, provider payloads, or secrets into the observation.

Use the exact reviewer observation shape declared in
`reviews/round_XX/review_spec.json.required_observation_shape`. The canonical
JSON fields are:

- `schema_version`: `missionforge_deepresearch.reviewer_observation.v1`
- `request_id`
- `round_index`
- `decision`
- `contract_ref`
- `contract_hash`
- `reviewer_report_ref`
- `next_directive_ref`
- `artifact_refs`
- `evidence_refs`
- `blocker_refs`
- `state_refs`
- `allowed_next_actions`

Do not rename `next_directive_ref`, `artifact_refs`, or `evidence_refs`.

The follow-up `research_state.json` must use the exact control fields declared
in `review_spec.json.required_research_state_shape`:

- `schema_version`: `missionforge_deepresearch.research_state.v1`
- `request_id`
- `round_index`
- `contract_ref`
- `contract_hash`
- `source_packet_ref`
- `reviewer_observation_ref`
- `reviewer_report_ref`
- `next_directive_ref`
- `prior_state_refs`
- `belief_updates`
- `current_hypotheses`
- `confidence_notes`
- `unresolved_gaps`
- `next_best_actions`
- `updated_artifact_refs`
- `evidence_refs`

`posterior_kind` and `reviewer_guidance_refs` may be included as optional
metadata, but do not rename the required control fields above.

Review like a serious program committee reviewer:

- identify missing seminal or recent work;
- challenge unsupported claims and weak citations;
- flag stale information, shallow taxonomy, and vague definitions;
- demand counterevidence or competing approaches where appropriate;
- point to source gaps instead of inventing facts;
- give the researcher a concrete next-step directive.

Your feedback should be complete in one pass. Do not hold back important
critique for later rounds, and do not limit yourself to the checklist above if
expert judgment reveals another material weakness. The checklist is a floor, not
a ceiling.

The directive should be repair-oriented and batching-friendly: group related
fixes, state the evidence or source strategy needed, and make clear which
changes are mandatory before judge submission versus residual risks that should
be disclosed but should not cause endless iteration.

Do not change the frozen contract. Do not accept the work. Final product
acceptance belongs only to the independent judge after the reviewed draft is
ready.
"""


def _required_reviewer_observation_shape(round_index: int) -> dict[str, Any]:
    return {
        "schema_version": REVIEW_OBSERVATION_SCHEMA_VERSION,
        "accepted_schema_versions": [REVIEW_OBSERVATION_SCHEMA_VERSION],
        "required_fields": list(REVIEW_OBSERVATION_REQUIRED_FIELDS),
        "optional_fields": [
            "artifact_refs",
            "evidence_refs",
            "blocker_refs",
            "state_refs",
            "allowed_next_actions",
        ],
        "reviewer_report_ref": _reviewer_report_ref(round_index),
        "next_directive_ref": _next_directive_ref(round_index),
        "allowed_decisions": sorted(REVIEW_OBSERVATION_DECISIONS),
        "decision_next_actions": {decision: _next_actions_for_review_decision(decision) for decision in sorted(REVIEW_OBSERVATION_DECISIONS)},
    }


def _required_research_state_shape(round_index: int) -> dict[str, Any]:
    return {
        "schema_version": RESEARCH_STATE_SCHEMA_VERSION,
        "accepted_schema_versions": [RESEARCH_STATE_SCHEMA_VERSION],
        "required_fields": list(RESEARCH_STATE_REQUIRED_FIELDS),
        "optional_fields": [
            "posterior_kind",
            "reviewer_guidance_refs",
        ],
        "reviewer_observation_ref": _reviewer_observation_ref(round_index),
        "reviewer_report_ref": _reviewer_report_ref(round_index),
        "next_directive_ref": _next_directive_ref(round_index),
        "refs_only_fields": list(RESEARCH_STATE_REF_FIELDS),
    }


def _contract_id(workspace: Path) -> str:
    task_contract = read_json_ref(workspace, TASK_CONTRACT_REF, "task_contract")
    return require_non_empty_str(task_contract.get("contract_id"), "task_contract.contract_id")


def _review_spec_ref(round_index: int) -> str:
    return f"reviews/round_{round_index:02d}/review_spec.json"


def _reviewer_report_ref(round_index: int) -> str:
    return f"reviews/round_{round_index:02d}/reviewer_report.md"


def _next_directive_ref(round_index: int) -> str:
    return f"reviews/round_{round_index:02d}/next_research_directive.md"


def _reviewer_observation_ref(round_index: int) -> str:
    return f"reviews/round_{round_index:02d}/reviewer_observation.json"


def _revision_permission_manifest_ref(round_index: int) -> str:
    return f"reviews/round_{round_index:02d}/revision_permission_manifest.json"


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
