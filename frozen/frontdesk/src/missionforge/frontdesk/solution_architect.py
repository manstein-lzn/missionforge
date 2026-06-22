"""LLM SolutionArchitect contract for FrontDesk spec-grill."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..contracts import ContractValidationError
from ..profiles import ProfileRegistry
from .schema import MissionPlan, ProfileRecommendationSet
from .spec_grill_schema import MissionSolutionPlan, PlanRiskRegister
from .state import (
    CORE_NEED_BRIEF_REF,
    MISSION_PLAN_REF,
    PLAN_RISK_REGISTER_REF,
    PROFILE_CATALOG_SNAPSHOT_REF,
    PROFILE_RECOMMENDATIONS_REF,
    SEMANTIC_COVERAGE_REF,
    SOLUTION_PLAN_MARKDOWN_REF,
    SOLUTION_PLAN_REF,
    FrontDeskAuthoringSession,
)
from .workspace import FrontDeskWorkspace


@dataclass(frozen=True)
class SolutionArchitectureResult:
    """Artifacts produced by an LLM-backed SolutionArchitect node."""

    solution_plan: MissionSolutionPlan
    risk_register: PlanRiskRegister
    profile_recommendations: ProfileRecommendationSet
    mission_plan: MissionPlan
    solution_plan_markdown: str

    @property
    def refs(self) -> list[str]:
        return [
            SOLUTION_PLAN_REF,
            SOLUTION_PLAN_MARKDOWN_REF,
            PLAN_RISK_REGISTER_REF,
            PROFILE_RECOMMENDATIONS_REF,
            MISSION_PLAN_REF,
        ]

    def to_dict(self) -> dict[str, Any]:
        return {
            "solution_plan": self.solution_plan.to_dict(),
            "risk_register": self.risk_register.to_dict(),
            "profile_recommendations": self.profile_recommendations.to_dict(),
            "mission_plan": self.mission_plan.to_dict(),
            "solution_plan_markdown_ref": SOLUTION_PLAN_MARKDOWN_REF,
            "refs": list(self.refs),
        }


def solution_architect_node_template(session_id: str) -> dict[str, Any]:
    """Return the static role and output template for the SolutionArchitect AI node."""

    return {
        "node": "frontdesk.solution_architect",
        "session_id": session_id,
        "role": (
            "Act as a senior product architect. Turn the confirmed need into a bounded MVP, "
            "non-goals, risk register, profile recommendations, and verification strategy."
        ),
        "visible_refs": [CORE_NEED_BRIEF_REF, SEMANTIC_COVERAGE_REF, PROFILE_CATALOG_SNAPSHOT_REF],
        "expected_outputs": [
            SOLUTION_PLAN_REF,
            SOLUTION_PLAN_MARKDOWN_REF,
            PLAN_RISK_REGISTER_REF,
            PROFILE_RECOMMENDATIONS_REF,
            MISSION_PLAN_REF,
        ],
        "output_contract": {
            "solution_plan_ref": SOLUTION_PLAN_REF,
            "solution_plan_markdown_ref": SOLUTION_PLAN_MARKDOWN_REF,
            "plan_risk_register_ref": PLAN_RISK_REGISTER_REF,
            "profile_recommendations_ref": PROFILE_RECOMMENDATIONS_REF,
            "mission_plan_ref": MISSION_PLAN_REF,
        },
        "rules": [
            "Do not compile MissionIR.",
            "Do not approve, freeze, run, or verify the mission.",
            "Do not use raw conversation as product truth.",
            "Use product profile metadata only as inquiry context, not runtime authority.",
        ],
    }


class SolutionArchitect:
    """Service boundary for an LLM-backed SolutionArchitect node."""

    def __init__(self, *, registry: ProfileRegistry | None = None) -> None:
        self.registry = registry or ProfileRegistry.builtins()

    def plan(
        self,
        *,
        session: FrontDeskAuthoringSession,
        workspace: FrontDeskWorkspace,
    ) -> SolutionArchitectureResult:
        session.validate()
        raise ContractValidationError(
            "SolutionArchitect requires an LLM/PiWorker-authored output; deterministic solution planning has been removed"
        )


def plan_frontdesk_solution(
    *,
    session: FrontDeskAuthoringSession,
    workspace: FrontDeskWorkspace,
    registry: ProfileRegistry | None = None,
) -> SolutionArchitectureResult:
    return SolutionArchitect(registry=registry).plan(session=session, workspace=workspace)


__all__ = [
    "SolutionArchitectureResult",
    "SolutionArchitect",
    "plan_frontdesk_solution",
    "solution_architect_node_template",
]
