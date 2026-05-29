"""MissionIR mapping for FrontDesk spec-grill."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..contracts import ContractValidationError
from ..ir import MissionIR
from .compiler import build_mission_ir
from .schema import ApprovalAuthority, AuthoringApproval, MissionBrief, MissionPlan, MissionSemanticLock, ProfileRecommendationSet
from .spec_grill_schema import (
    MappingStatus,
    MissionIRMappingReport,
    MissionSolutionPlan,
    PlanReviewDecision,
    PlanReviewRecord,
    RequirementMapping,
)
from .state import (
    DRAFT_MISSION_REF,
    MISSION_BRIEF_REF,
    MISSION_MAPPING_REPORT_REF,
    MISSION_PLAN_REF,
    PLAN_REVIEW_REF,
    PROFILE_RECOMMENDATIONS_REF,
    SEMANTIC_LOCK_REF,
    SOLUTION_PLAN_REF,
    FrontDeskAuthoringSession,
)
from .workspace import FrontDeskWorkspace


@dataclass(frozen=True)
class MissionMappingResult:
    """Artifacts produced by MissionIRMapper."""

    mission_plan: MissionPlan
    draft_mission: MissionIR
    mapping_report: MissionIRMappingReport

    @property
    def refs(self) -> list[str]:
        return [MISSION_PLAN_REF, DRAFT_MISSION_REF, MISSION_MAPPING_REPORT_REF]

    def to_dict(self) -> dict[str, Any]:
        return {
            "mission_plan": self.mission_plan.to_dict(),
            "draft_mission": self.draft_mission.to_dict(),
            "mission_mapping_report": self.mapping_report.to_dict(),
            "refs": list(self.refs),
        }


class MissionIRMapper:
    """Deterministic mapper from approved solution plan to DraftMissionIR."""

    def map(
        self,
        *,
        session: FrontDeskAuthoringSession,
        workspace: FrontDeskWorkspace,
    ) -> MissionMappingResult:
        session.validate()
        semantic_lock = MissionSemanticLock.from_dict(workspace.read_json(SEMANTIC_LOCK_REF))
        mission_brief = MissionBrief.from_dict(workspace.read_json(MISSION_BRIEF_REF))
        profiles = ProfileRecommendationSet.from_dict(workspace.read_json(PROFILE_RECOMMENDATIONS_REF))
        solution_plan = MissionSolutionPlan.from_dict(workspace.read_json(SOLUTION_PLAN_REF))
        plan_review = PlanReviewRecord.from_dict(workspace.read_json(PLAN_REVIEW_REF))
        if plan_review.decision != PlanReviewDecision.APPROVE:
            raise ContractValidationError("mission mapping requires approved plan review")
        if plan_review.reviewed_plan_hash != solution_plan.plan_hash:
            raise ContractValidationError("mission mapping requires current plan review hash")
        mission_plan = _mission_plan(session.session_id, solution_plan)
        draft_approval = AuthoringApproval(
            session_id=session.session_id,
            approved_by=plan_review.reviewed_by,
            authority=ApprovalAuthority.POLICY,
            approved_ref=PLAN_REVIEW_REF,
            approved_hash=plan_review.reviewed_plan_hash,
            approval_notes=["Draft mapping approval is limited to MissionIR mapping and is not freeze authority."],
        )
        draft_mission = build_mission_ir(
            semantic_lock=semantic_lock,
            mission_brief=mission_brief,
            profile_recommendations=profiles,
            mission_plan=mission_plan,
            approval=draft_approval,
        )
        mapping_report = _mapping_report(session.session_id, semantic_lock, solution_plan, mission_plan)
        if mapping_report.has_blocking_gaps:
            raise ContractValidationError("mission mapping report has blocking gaps")
        workspace.write_json(MISSION_PLAN_REF, mission_plan.to_dict())
        workspace.write_json(DRAFT_MISSION_REF, draft_mission.to_dict())
        workspace.write_json(MISSION_MAPPING_REPORT_REF, mapping_report.to_dict())
        return MissionMappingResult(
            mission_plan=mission_plan,
            draft_mission=draft_mission,
            mapping_report=mapping_report,
        )


def _mission_plan(session_id: str, solution_plan: MissionSolutionPlan) -> MissionPlan:
    constraint_id = f"FD-{session_id}-C-authoring-contract"
    validators = [
        {
            "validator_id": f"V-{session_id}-{index:03d}-artifact-exists",
            "constraint_refs": [constraint_id],
            "type": "file_exists",
            "inputs": {"path": artifact},
        }
        for index, artifact in enumerate(solution_plan.expected_artifacts, start=1)
    ]
    constraints = [
        {
            "constraint_id": constraint_id,
            "kind": "frontdesk_authoring_contract",
            "statement": solution_plan.summary,
            "priority": "must",
            "source_refs": [SOLUTION_PLAN_REF, PLAN_REVIEW_REF],
            "evidence_obligations": list(solution_plan.expected_artifacts),
            "repair_hints": ["Regenerate outputs from the approved FrontDesk solution plan."],
        }
    ]
    return MissionPlan(
        session_id=session_id,
        expected_artifacts=list(solution_plan.expected_artifacts),
        constraints=constraints,
        validators=validators,
        manual_gates=[],
        risk_notes=list(solution_plan.risks),
    )


def _mapping_report(
    session_id: str,
    semantic_lock: MissionSemanticLock,
    solution_plan: MissionSolutionPlan,
    mission_plan: MissionPlan,
) -> MissionIRMappingReport:
    mappings: list[RequirementMapping] = []
    for index, clause in enumerate(semantic_lock.requirement_clauses, start=1):
        mappings.append(
            RequirementMapping(
                requirement_id=f"R-{index:03d}",
                requirement_text=clause,
                status=MappingStatus.MAPPED,
                mission_paths=[
                    "inputs.frontdesk_semantic_lock_ref",
                    "constraints[].source_refs",
                    "verification.validators",
                ],
                mapped_refs=[SEMANTIC_LOCK_REF, DRAFT_MISSION_REF, MISSION_PLAN_REF],
            )
        )
    for index, artifact in enumerate(solution_plan.expected_artifacts, start=len(mappings) + 1):
        mappings.append(
            RequirementMapping(
                requirement_id=f"R-{index:03d}",
                requirement_text=f"Expected artifact: {artifact}",
                status=MappingStatus.MAPPED,
                mission_paths=["outputs.required_artifacts", "verification.required_evidence"],
                mapped_refs=[DRAFT_MISSION_REF, MISSION_PLAN_REF],
            )
        )
    return MissionIRMappingReport(
        session_id=session_id,
        draft_mission_ref=DRAFT_MISSION_REF,
        requirement_mappings=mappings,
        unmapped_requirements=[],
        dropped_requirements=[],
        profile_mappings=[
            *solution_plan.selected_capability_profile_ids,
            *solution_plan.selected_verification_profile_ids,
        ],
        validator_mappings=[validator["type"] for validator in mission_plan.validators if isinstance(validator.get("type"), str)],
    )


def map_frontdesk_mission(
    *,
    session: FrontDeskAuthoringSession,
    workspace: FrontDeskWorkspace,
) -> MissionMappingResult:
    return MissionIRMapper().map(session=session, workspace=workspace)


__all__ = ["MissionIRMapper", "MissionMappingResult", "map_frontdesk_mission"]
