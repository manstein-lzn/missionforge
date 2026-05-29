"""Spec-grill orchestration helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..profiles import ProfileRegistry
from .mission_mapper import MissionIRMapper, MissionMappingResult
from .need_griller import NeedGrillResult, NeedGriller
from .scout import ScoutResult, WorkspaceScout
from .schema import ApprovalAuthority
from .semantic_coverage import SemanticCoverageChecker, SemanticCoverageResult
from .solution_architect import SolutionArchitect, SolutionArchitectureResult
from .spec_grill_schema import PlanReviewDecision, PlanReviewRecord
from .state import PLAN_REVIEW_REF, SOLUTION_PLAN_REF, FrontDeskAuthoringSession
from .workspace import FrontDeskWorkspace


@dataclass(frozen=True)
class SpecGrillDraftResult:
    """Result of running the deterministic spec-grill path to draft MissionIR."""

    scout: ScoutResult
    grill: NeedGrillResult
    semantic_coverage: SemanticCoverageResult | None = None
    solution: SolutionArchitectureResult | None = None
    plan_review: PlanReviewRecord | None = None
    mapping: MissionMappingResult | None = None

    @property
    def ready_for_audit(self) -> bool:
        return self.mapping is not None

    def to_dict(self) -> dict[str, Any]:
        return {
            "scout": self.scout.to_dict(),
            "grill": self.grill.to_dict(),
            "semantic_coverage": self.semantic_coverage.to_dict() if self.semantic_coverage else None,
            "solution": self.solution.to_dict() if self.solution else None,
            "plan_review": self.plan_review.to_dict() if self.plan_review else None,
            "mapping": self.mapping.to_dict() if self.mapping else None,
            "ready_for_audit": self.ready_for_audit,
        }


class SpecGrillPipeline:
    """Small deterministic pipeline used by FrontDesk service and tests."""

    def __init__(self, *, registry: ProfileRegistry | None = None) -> None:
        self.registry = registry

    def run_to_draft(
        self,
        *,
        session: FrontDeskAuthoringSession,
        workspace: FrontDeskWorkspace,
        auto_policy_review: bool = True,
    ) -> SpecGrillDraftResult:
        scout = WorkspaceScout(registry=self.registry).scout(session=session, workspace=workspace)
        grill = NeedGriller().grill(session=session, workspace=workspace)
        if grill.report.readiness.value != "core_need_ready":
            return SpecGrillDraftResult(scout=scout, grill=grill)
        coverage = SemanticCoverageChecker().cover(session=session, workspace=workspace)
        solution = SolutionArchitect(registry=self.registry).plan(session=session, workspace=workspace)
        plan_review = None
        mapping = None
        if auto_policy_review:
            plan_review = write_policy_plan_review(
                session=session,
                workspace=workspace,
                reviewed_by="frontdesk.policy",
                notes=["Policy review for deterministic offline FrontDesk draft."],
            )
            mapping = MissionIRMapper().map(session=session, workspace=workspace)
        return SpecGrillDraftResult(
            scout=scout,
            grill=grill,
            semantic_coverage=coverage,
            solution=solution,
            plan_review=plan_review,
            mapping=mapping,
        )


def write_policy_plan_review(
    *,
    session: FrontDeskAuthoringSession,
    workspace: FrontDeskWorkspace,
    reviewed_by: str,
    notes: list[str] | None = None,
) -> PlanReviewRecord:
    from .spec_grill_schema import MissionSolutionPlan

    solution_plan = MissionSolutionPlan.from_dict(workspace.read_json(SOLUTION_PLAN_REF))
    review = PlanReviewRecord(
        session_id=session.session_id,
        decision=PlanReviewDecision.APPROVE,
        reviewed_plan_ref=SOLUTION_PLAN_REF,
        reviewed_plan_hash=solution_plan.plan_hash,
        reviewed_by=reviewed_by,
        authority=ApprovalAuthority.POLICY,
        review_notes=list(notes or []),
    )
    workspace.write_json(PLAN_REVIEW_REF, review.to_dict())
    return review


__all__ = ["SpecGrillDraftResult", "SpecGrillPipeline", "write_policy_plan_review"]
