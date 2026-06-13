"""Thin SkillFoundry product facade over MissionForge runtime."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from missionforge.agentic_flow import AgenticFlowResult, AgenticFlowRunner, AgenticFlowStatus
from missionforge.agent_packets import HardCheckStatus
from missionforge.contracts import ContractValidationError, VerificationStatus, validate_ref
from missionforge.piworker_runtime import create_default_task_contract_flow
from missionforge.runtime_results import MissionResult

from .product_contract import SkillFoundryRequest
from .product_grade_gate import PRODUCT_GRADE_REPORT_REF, evaluate_product_grade
from .registry import RegistryEntry, register_skill_bundle
from .reports import SkillFoundryProductReport, write_product_report
from .task_contract_compiler import (
    SKILLFOUNDRY_HARD_CHECK_RESULT_REF,
    compile_skillfoundry_task_contract,
    load_skillfoundry_task_contract,
)
from .validators import BUNDLE_VALIDATION_REPORT_REF, validate_skill_bundle
from .workspace import write_json_ref


def run_skillfoundry_task_contract_bundle_build(
    request: SkillFoundryRequest,
    *,
    workspace: str | Path = ".",
    executor: Any | None = None,
    judge: Any | None = None,
    max_attempts: int = 1,
    pi_agent_config: Any | None = None,
    piworker_runner: Any | None = None,
    allow_candidate_registration: bool = True,
) -> SkillFoundryProductReport:
    """TaskContract-native SkillFoundry product facade.

    Product semantics stay in this integration. MissionForge core receives only
    TaskContract, workspace policy, permission manifest, hard-check refs, and
    role-separated executor/judge nodes.
    """

    if max_attempts < 1:
        raise ContractValidationError("SkillFoundry TaskContract facade requires max_attempts >= 1")
    root = Path(workspace).resolve()
    compile_result = compile_skillfoundry_task_contract(request, workspace=root)
    task_contract, workspace_policy, permission_manifest = load_skillfoundry_task_contract(root, compile_result)
    run_root = root / compile_result.run_workspace_ref
    _write_task_contract_hard_check(run_root, request, compile_result.run_workspace_ref)

    if (executor is None) != (judge is None):
        raise ContractValidationError("SkillFoundry TaskContract facade requires both executor and judge, or neither")
    if executor is None or judge is None:
        preset = create_default_task_contract_flow(
            root,
            piworker_config=pi_agent_config,
            piworker_runner=piworker_runner,
        )
        flow_runner = preset.runner
        executor = preset.executor
        judge = preset.judge
    else:
        flow_runner = AgenticFlowRunner(root)

    flow_result = flow_runner.run(
        run_id=f"skillfoundry-{request.bundle_id}-taskcontract",
        contract=task_contract,
        workspace_policy=workspace_policy,
        permission_manifest=permission_manifest,
        executor=executor,
        judge=judge,
        hard_check_status=HardCheckStatus.PASSED,
        hard_check_refs=list(compile_result.hard_check_refs),
    )
    mission_result = _mission_result_from_task_contract_flow(task_contract.contract_id, flow_result)
    validate_skill_bundle(
        workspace=run_root,
        bundle_id=request.bundle_id,
        matrix_ref=_run_relative_ref(compile_result.run_workspace_ref, compile_result.acceptance_matrix_ref),
        report_ref=BUNDLE_VALIDATION_REPORT_REF,
    )
    product_grade = evaluate_product_grade(
        workspace=run_root,
        bundle_id=request.bundle_id,
        mission_result=mission_result,
        bundle_validation_report_ref=BUNDLE_VALIDATION_REPORT_REF,
        report_ref=PRODUCT_GRADE_REPORT_REF,
    )
    registry_entry = register_skill_bundle(
        workspace=run_root,
        product_grade_report_ref=PRODUCT_GRADE_REPORT_REF,
        allow_candidate=allow_candidate_registration,
    )
    write_product_report(
        workspace=run_root,
        bundle_id=request.bundle_id,
        request_ref=_run_relative_ref(compile_result.run_workspace_ref, compile_result.product_request_ref),
        product_contract_ref=_run_relative_ref(compile_result.run_workspace_ref, compile_result.product_contract_ref),
        mission_ref=_run_relative_ref(compile_result.run_workspace_ref, compile_result.task_contract_ref),
        mission_run_id=flow_result.run_id,
        verifier_refs=list(mission_result.evidence_refs),
        product_grade_report_ref=PRODUCT_GRADE_REPORT_REF,
        registry_entry=registry_entry,
        package_refs=list(product_grade.package_refs),
        product_grade_outcome_category=product_grade.outcome_category,
    )
    return write_product_report(
        workspace=root,
        bundle_id=request.bundle_id,
        request_ref=compile_result.product_request_ref,
        product_contract_ref=compile_result.product_contract_ref,
        mission_ref=compile_result.task_contract_ref,
        mission_run_id=flow_result.run_id,
        verifier_refs=[
            _outer_run_ref(compile_result.run_workspace_ref, ref)
            for ref in mission_result.evidence_refs
        ],
        product_grade_report_ref=_outer_run_ref(compile_result.run_workspace_ref, PRODUCT_GRADE_REPORT_REF),
        registry_entry=_outer_registry_entry(compile_result.run_workspace_ref, registry_entry),
        package_refs=[
            _outer_run_ref(compile_result.run_workspace_ref, ref)
            for ref in product_grade.package_refs
        ],
        product_grade_outcome_category=product_grade.outcome_category,
    )


def _write_task_contract_hard_check(
    run_root: Path,
    request: SkillFoundryRequest,
    run_workspace_ref: str,
) -> None:
    write_json_ref(
        run_root,
        SKILLFOUNDRY_HARD_CHECK_RESULT_REF,
        {
            "schema_version": "missionforge_skillfoundry.hard_check_result.v1",
            "bundle_id": request.bundle_id,
            "status": "passed",
            "source_refs": [
                "product_contract/skillfoundry_request.json",
                "product_contract/skill_product_contract.json",
            ],
        },
    )


def _mission_result_from_task_contract_flow(
    mission_id: str,
    result: AgenticFlowResult,
) -> MissionResult:
    status = (
        VerificationStatus.COMPLETED_VERIFIED.value
        if result.status is AgenticFlowStatus.ACCEPTED
        else VerificationStatus.FAILED.value
    )
    evidence_refs = [
        result.refs.judge_report_ref,
        result.refs.decision_ledger_ref,
        *([result.refs.final_package_ref] if result.status is AgenticFlowStatus.ACCEPTED else []),
    ]
    return MissionResult(
        mission_id=mission_id,
        status=status,
        evidence_refs=evidence_refs,
        artifact_refs=list(result.accepted_artifact_refs),
        failed_constraint_ids=[] if result.status is AgenticFlowStatus.ACCEPTED else [result.status.value],
        metrics={
            "task_contract_hash": result.contract_hash,
            "task_contract_status": result.status.value,
        },
    )


def _run_relative_ref(run_workspace_ref: str, ref: str) -> str:
    safe_run_ref = validate_ref(run_workspace_ref, "run_workspace_ref")
    safe_ref = validate_ref(ref, "run_ref")
    prefix = f"{safe_run_ref}/"
    if not safe_ref.startswith(prefix):
        raise ContractValidationError(f"ref is not under run workspace: {safe_ref}")
    return safe_ref[len(prefix):]


def _outer_run_ref(run_workspace_ref: str, ref: str) -> str:
    safe_run_ref = validate_ref(run_workspace_ref, "run_workspace_ref")
    safe_ref = validate_ref(ref, "run_relative_ref")
    return f"{safe_run_ref}/{safe_ref}"


def _outer_registry_entry(run_workspace_ref: str, entry: RegistryEntry) -> RegistryEntry:
    return RegistryEntry(
        entry_id=entry.entry_id,
        bundle_id=entry.bundle_id,
        status=entry.status,
        package_hash=entry.package_hash,
        package_refs=[
            _outer_run_ref(run_workspace_ref, ref)
            for ref in entry.package_refs
        ],
        product_grade_report_ref=_outer_run_ref(run_workspace_ref, entry.product_grade_report_ref),
        registry_decision_ref=_outer_run_ref(run_workspace_ref, entry.registry_decision_ref),
        metadata=dict(entry.metadata),
    )
