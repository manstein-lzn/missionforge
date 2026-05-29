"""Thin SkillFoundry product facade over MissionForge runtime."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from missionforge.ir import MissionIR
from missionforge.runner import MissionRuntime
from missionforge.state import mission_run_id_for

from .compiler import SkillFoundryCompileResult, compile_skillfoundry_bundle
from .product_contract import SkillFoundryRequest
from .product_grade_gate import PRODUCT_GRADE_REPORT_REF, evaluate_product_grade
from .registry import register_skill_bundle
from .reports import SkillFoundryProductReport, write_product_report
from .validators import BUNDLE_VALIDATION_REPORT_REF, validate_skill_bundle
from .workspace import read_json_ref


def run_skillfoundry_bundle_build(
    request: SkillFoundryRequest,
    *,
    workspace: str | Path = ".",
    runtime: MissionRuntime | None = None,
    max_attempts: int = 1,
    pi_agent_config: Any | None = None,
    allow_candidate_registration: bool = True,
) -> SkillFoundryProductReport:
    """Compile, run, validate, grade, register, and report one SkillFoundry bundle."""

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
    )


def _load_mission(workspace: str | Path, compile_result: SkillFoundryCompileResult) -> MissionIR:
    payload = read_json_ref(workspace, compile_result.mission_ir_ref, "mission_ir")
    return MissionIR.from_dict(payload)
