"""Thin SkillFoundry product facade over MissionForge runtime."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from missionforge.agentic_flow import AgenticFlowResult, AgenticFlowRunner, AgenticFlowStatus
from missionforge.agent_packets import HardCheckStatus
from missionforge.contracts import ContractValidationError, VerificationStatus, validate_ref
from missionforge.ir import MissionIR
from missionforge.piworker_runtime import create_default_task_contract_flow
from missionforge.runner import MissionRuntime
from missionforge.runner import MissionResult
from missionforge.state import mission_run_id_for

from .compiler import SkillFoundryCompileResult, compile_skillfoundry_bundle
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
from .workspace import read_json_ref, write_json_ref


def run_skillfoundry_bundle_build(
    request: SkillFoundryRequest,
    *,
    workspace: str | Path = ".",
    runtime: MissionRuntime | None = None,
    max_attempts: int = 1,
    pi_agent_config: Any | None = None,
    allow_candidate_registration: bool = True,
) -> SkillFoundryProductReport:
    """Compatibility MissionIR runtime path; new work should use TaskContract flow."""

    compile_result = compile_skillfoundry_bundle(request, workspace=workspace)
    mission = _load_mission(workspace, compile_result)
    active_runtime = runtime or MissionRuntime(workspace=workspace, max_attempts=max_attempts, pi_agent_config=pi_agent_config)
    mission_result = active_runtime.run(mission)
    validate_skill_bundle(
        workspace=workspace,
        bundle_id=request.bundle_id,
        matrix_ref=compile_result.acceptance_matrix_ref or "product_contract/product_acceptance_matrix.json",
        report_ref=BUNDLE_VALIDATION_REPORT_REF,
    )
    product_grade = evaluate_product_grade(
        workspace=workspace,
        bundle_id=request.bundle_id,
        mission_result=mission_result,
        bundle_validation_report_ref=BUNDLE_VALIDATION_REPORT_REF,
        report_ref=PRODUCT_GRADE_REPORT_REF,
    )
    registry_entry = register_skill_bundle(
        workspace=workspace,
        product_grade_report_ref=PRODUCT_GRADE_REPORT_REF,
        allow_candidate=allow_candidate_registration,
    )
    return write_product_report(
        workspace=workspace,
        bundle_id=request.bundle_id,
        request_ref=compile_result.request_ref or "product_contract/skillfoundry_request.json",
        product_contract_ref=compile_result.product_contract_ref or "product_contract/skill_product_contract.json",
        mission_ref=compile_result.mission_ir_ref,
        mission_run_id=mission_run_id_for(mission.mission_id),
        verifier_refs=list(mission_result.evidence_refs),
        product_grade_report_ref=PRODUCT_GRADE_REPORT_REF,
        registry_entry=registry_entry,
        package_refs=list(product_grade.package_refs),
        product_grade_outcome_category=product_grade.outcome_category,
    )


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


def _load_mission(workspace: str | Path, compile_result: SkillFoundryCompileResult) -> MissionIR:
    payload = read_json_ref(workspace, compile_result.mission_ir_ref, "mission_ir")
    return MissionIR.from_dict(payload)


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
