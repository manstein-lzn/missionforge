"""LLM-assisted FrontDesk mission planner boundary."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..contracts import ContractValidationError, ensure_json_value, require_mapping, require_non_empty_str
from ..profiles import ProfileRegistry
from .elicitor import FrontDeskLLMClient
from .schema import MissionPlan, ProfileRecommendationSet, reject_raw_authoring_fields


@dataclass(frozen=True)
class PlanningResult:
    """Validated mission planning output."""

    session_id: str
    profile_recommendations: ProfileRecommendationSet
    mission_plan: MissionPlan

    @classmethod
    def from_dict(cls, payload: dict[str, Any], *, registry: ProfileRegistry | None = None) -> "PlanningResult":
        data = require_mapping(payload, "planning_result")
        _reject_unknown(data, {"session_id", "profile_recommendations", "mission_plan"}, "planning_result")
        reject_raw_authoring_fields(data, "planning_result")
        result = cls(
            session_id=require_non_empty_str(data.get("session_id"), "planning_result.session_id"),
            profile_recommendations=ProfileRecommendationSet.from_dict(
                require_mapping(data.get("profile_recommendations"), "planning_result.profile_recommendations")
            ),
            mission_plan=MissionPlan.from_dict(require_mapping(data.get("mission_plan"), "planning_result.mission_plan")),
        )
        result.validate(registry=registry)
        return result

    def validate(self, *, registry: ProfileRegistry | None = None) -> None:
        if self.profile_recommendations.session_id != self.session_id or self.mission_plan.session_id != self.session_id:
            raise ContractValidationError("planning_result session ids do not match")
        active_registry = registry or ProfileRegistry.builtins()
        for profile in self.profile_recommendations.selected_capability_profiles:
            active_registry.get_capability(profile.profile_id)
        for profile in self.profile_recommendations.selected_verification_profiles:
            active_registry.get_verification(profile.profile_id)

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "session_id": self.session_id,
            "profile_recommendations": self.profile_recommendations.to_dict(),
            "mission_plan": self.mission_plan.to_dict(),
        }


class MissionPlanner:
    """Schema-validating planner wrapper."""

    def __init__(self, *, registry: ProfileRegistry | None = None) -> None:
        self.registry = registry

    def plan(self, *, session_id: str, brief: dict[str, Any], client: FrontDeskLLMClient) -> PlanningResult:
        registry = self.registry or ProfileRegistry.builtins()
        payload = {
            "node": "mission_planner",
            "session_id": session_id,
            "brief": brief,
            "available_capability_profiles": registry.capability_profile_ids(),
            "available_verification_profiles": registry.verification_profile_ids(),
            "contract": "Return PlanningResult JSON only. Do not approve or freeze.",
        }
        response = ensure_json_value(client.complete_json(payload), "planner.response")
        return PlanningResult.from_dict(require_mapping(response, "planner.response"), registry=registry)


def _reject_unknown(data: dict[str, Any], allowed: set[str], field_name: str) -> None:
    extra = sorted(set(data) - allowed)
    if extra:
        raise ContractValidationError(f"{field_name} contains unknown field(s): {', '.join(extra)}")
