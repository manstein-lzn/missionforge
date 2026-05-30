"""Spec-grill LLM node templates and orchestration boundary."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..contracts import ContractValidationError
from .mission_mapper import MissionMappingResult
from .need_griller import NeedGrillResult, need_griller_node_template
from .scout import ScoutResult, WorkspaceScout
from .semantic_coverage import SemanticCoverageResult
from .solution_architect import SolutionArchitectureResult, solution_architect_node_template
from .spec_grill_schema import PlanReviewRecord
from .state import FrontDeskAuthoringSession
from .workspace import FrontDeskWorkspace


@dataclass(frozen=True)
class SpecGrillDraftResult:
    """Refs-first result shell for a FrontDesk spec-grill authoring run."""

    scout: ScoutResult
    grill: NeedGrillResult | None = None
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
            "grill": self.grill.to_dict() if self.grill else None,
            "semantic_coverage": self.semantic_coverage.to_dict() if self.semantic_coverage else None,
            "solution": self.solution.to_dict() if self.solution else None,
            "plan_review": self.plan_review.to_dict() if self.plan_review else None,
            "mapping": self.mapping.to_dict() if self.mapping else None,
            "ready_for_audit": self.ready_for_audit,
        }


def spec_grill_node_templates(session_id: str) -> list[dict[str, Any]]:
    """Return static AI node role/output templates for FrontDesk authoring."""

    return [
        need_griller_node_template(session_id),
        solution_architect_node_template(session_id),
        {
            "node": "frontdesk.mission_ir_mapper",
            "session_id": session_id,
            "role": "Map approved FrontDesk artifacts into MissionIR or an intent bundle using structured refs only.",
            "rules": [
                "Do not use raw conversation as runtime truth.",
                "Do not approve, freeze, run, or verify the mission.",
                "Do not invent product compiler behavior.",
            ],
        },
    ]


class SpecGrillPipeline:
    """Service boundary for future LLM/PiWorker-backed FrontDesk orchestration."""

    def __init__(self, *, registry: object | None = None) -> None:
        self.registry = registry

    def run_to_draft(
        self,
        *,
        session: FrontDeskAuthoringSession,
        workspace: FrontDeskWorkspace,
        auto_policy_review: bool = True,
    ) -> SpecGrillDraftResult:
        session.validate()
        WorkspaceScout().scout(session=session, workspace=workspace)
        raise ContractValidationError(
            "SpecGrillPipeline requires LLM/PiWorker-authored node outputs; deterministic orchestration has been removed"
        )


__all__ = ["SpecGrillDraftResult", "SpecGrillPipeline", "spec_grill_node_templates"]
