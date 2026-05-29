"""Deterministic FrontDesk approval and freeze gate."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..contracts import ContractValidationError, require_non_empty_str
from ..profiles import ProfileRegistry
from .compiler import FrontDeskCompileResult, compile_frontdesk_artifacts
from .schema import (
    AuthoringApproval,
    MissionBrief,
    MissionPlan,
    MissionSemanticLock,
    ProfileRecommendationSet,
    SanitizedSourceSet,
)


@dataclass(frozen=True)
class FrontDeskFreezeGate:
    """Freeze only approved, schema-valid FrontDesk artifacts."""

    registry: ProfileRegistry | None = None

    def freeze(
        self,
        *,
        semantic_lock: MissionSemanticLock,
        mission_brief: MissionBrief,
        profile_recommendations: ProfileRecommendationSet,
        mission_plan: MissionPlan,
        approval: AuthoringApproval | None,
        sanitized_sources: SanitizedSourceSet | None = None,
        workspace: str | Path = ".",
    ) -> FrontDeskCompileResult:
        if approval is None:
            raise ContractValidationError("FrontDesk freeze requires authoring approval")
        approval.validate()
        require_non_empty_str(approval.approved_by, "authoring_approval.approved_by")
        return compile_frontdesk_artifacts(
            semantic_lock=semantic_lock,
            mission_brief=mission_brief,
            profile_recommendations=profile_recommendations,
            mission_plan=mission_plan,
            approval=approval,
            sanitized_sources=sanitized_sources,
            workspace=workspace,
            registry=self.registry,
        )


def freeze_frontdesk_artifacts(**kwargs: Any) -> FrontDeskCompileResult:
    return FrontDeskFreezeGate().freeze(**kwargs)
