"""Solution planning for FrontDesk spec-grill."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..contracts import ContractValidationError
from ..profiles import ProfileRegistry
from .schema import ProfileRecommendation, ProfileRecommendationKind, ProfileRecommendationSet
from .spec_grill_schema import (
    CoreNeedBrief,
    MissionSemanticCoverageReport,
    MissionSolutionPlan,
    PlanRiskRegister,
    ProfileCatalogSnapshot,
    SolutionPlanStatus,
)
from .state import (
    CORE_NEED_BRIEF_REF,
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
    """Artifacts produced by SolutionArchitect."""

    solution_plan: MissionSolutionPlan
    risk_register: PlanRiskRegister
    profile_recommendations: ProfileRecommendationSet
    solution_plan_markdown: str

    @property
    def refs(self) -> list[str]:
        return [SOLUTION_PLAN_REF, SOLUTION_PLAN_MARKDOWN_REF, PLAN_RISK_REGISTER_REF, PROFILE_RECOMMENDATIONS_REF]

    def to_dict(self) -> dict[str, Any]:
        return {
            "solution_plan": self.solution_plan.to_dict(),
            "risk_register": self.risk_register.to_dict(),
            "profile_recommendations": self.profile_recommendations.to_dict(),
            "solution_plan_markdown_ref": SOLUTION_PLAN_MARKDOWN_REF,
            "refs": list(self.refs),
        }


class SolutionArchitect:
    """Deterministic solution planner for generic FrontDesk missions."""

    def __init__(self, *, registry: ProfileRegistry | None = None) -> None:
        self.registry = registry or ProfileRegistry.builtins()

    def plan(
        self,
        *,
        session: FrontDeskAuthoringSession,
        workspace: FrontDeskWorkspace,
    ) -> SolutionArchitectureResult:
        session.validate()
        core_need = CoreNeedBrief.from_dict(workspace.read_json(CORE_NEED_BRIEF_REF))
        coverage = MissionSemanticCoverageReport.from_dict(workspace.read_json(SEMANTIC_COVERAGE_REF))
        if coverage.status.value != "passed":
            raise ContractValidationError("solution planning requires passing semantic coverage")
        catalog = _load_profile_catalog(workspace, session.session_id, self.registry)
        expected_artifact = _expected_artifact(core_need.success_signals)
        capability_ids = ["user_provided_evidence_only", "explicit_output_root"]
        verification_ids = ["generic_local_verification"]
        _require_known_profiles(catalog, capability_ids, verification_ids)
        plan = MissionSolutionPlan(
            session_id=session.session_id,
            status=SolutionPlanStatus.AWAITING_REVIEW,
            summary=f"Deliver a verifiable MissionIR plan for: {core_need.desired_outcome}",
            core_need_ref=CORE_NEED_BRIEF_REF,
            mvp_scope=[
                core_need.desired_outcome,
                "Map approved requirements into MissionIR before runtime starts.",
            ],
            future_scope=[],
            rejected_directions=[
                "Do not turn raw conversation into runtime task truth.",
                "Do not add product-specific MissionForge core branches.",
            ],
            expected_artifacts=[expected_artifact],
            selected_capability_profile_ids=capability_ids,
            selected_verification_profile_ids=verification_ids,
            verification_strategy=[f"Verify that {expected_artifact} exists."],
            risks=list(core_need.constraints),
            authority_requirements=["plan_review", "authoring_approval"],
            source_refs=[CORE_NEED_BRIEF_REF, SEMANTIC_COVERAGE_REF],
        )
        risk_register = PlanRiskRegister(
            session_id=session.session_id,
            risks=list(core_need.constraints),
            mitigations=[
                "Keep raw conversation provenance-only.",
                "Require deterministic freeze before runtime handoff.",
            ],
            source_refs=[CORE_NEED_BRIEF_REF],
        )
        recommendations = _profile_recommendations(session.session_id, expected_artifact)
        markdown = _solution_plan_markdown(plan)
        workspace.write_json(SOLUTION_PLAN_REF, plan.to_dict())
        workspace.store.write_text(SOLUTION_PLAN_MARKDOWN_REF, markdown)
        workspace.write_json(PLAN_RISK_REGISTER_REF, risk_register.to_dict())
        workspace.write_json(PROFILE_RECOMMENDATIONS_REF, recommendations.to_dict())
        return SolutionArchitectureResult(
            solution_plan=plan,
            risk_register=risk_register,
            profile_recommendations=recommendations,
            solution_plan_markdown=markdown,
        )


def _load_profile_catalog(
    workspace: FrontDeskWorkspace,
    session_id: str,
    registry: ProfileRegistry,
) -> ProfileCatalogSnapshot:
    if workspace.exists(PROFILE_CATALOG_SNAPSHOT_REF):
        return ProfileCatalogSnapshot.from_dict(workspace.read_json(PROFILE_CATALOG_SNAPSHOT_REF))
    return ProfileCatalogSnapshot(
        session_id=session_id,
        capability_profile_ids=registry.capability_profile_ids(),
        verification_profile_ids=registry.verification_profile_ids(),
    )


def _require_known_profiles(
    catalog: ProfileCatalogSnapshot,
    capability_ids: list[str],
    verification_ids: list[str],
) -> None:
    missing_capabilities = sorted(set(capability_ids) - set(catalog.capability_profile_ids))
    missing_verification = sorted(set(verification_ids) - set(catalog.verification_profile_ids))
    if missing_capabilities:
        raise ContractValidationError(f"missing capability profile(s): {', '.join(missing_capabilities)}")
    if missing_verification:
        raise ContractValidationError(f"missing verification profile(s): {', '.join(missing_verification)}")


def _expected_artifact(success_signals: list[str]) -> str:
    for signal in success_signals:
        lowered = signal.lower()
        if "package/readme.md" in lowered:
            return "package/README.md"
        if "package/skill.md" in lowered:
            return "package/SKILL.md"
        if "docs/output.md" in lowered:
            return "docs/output.md"
        for suffix in (".md", ".json", ".txt"):
            if suffix in lowered:
                token = lowered.split(" exists", 1)[0].split()[-1]
                if "/" in token and token.endswith(suffix):
                    return token
        if "readme" in lowered:
            return "package/README.md"
    return "artifacts/frontdesk_output.md"


def _profile_recommendations(session_id: str, expected_artifact: str) -> ProfileRecommendationSet:
    output_root = expected_artifact.split("/", 1)[0] if "/" in expected_artifact else "artifacts"
    return ProfileRecommendationSet(
        session_id=session_id,
        recommendations=[
            ProfileRecommendation(
                profile_id="user_provided_evidence_only",
                kind=ProfileRecommendationKind.CAPABILITY,
                rationale="FrontDesk admits sanitized source refs only.",
            ),
            ProfileRecommendation(
                profile_id="explicit_output_root",
                kind=ProfileRecommendationKind.CAPABILITY,
                rationale="The solution plan declares an output root.",
                requirements={"output_root": output_root},
            ),
            ProfileRecommendation(
                profile_id="generic_local_verification",
                kind=ProfileRecommendationKind.VERIFICATION,
                rationale="The mission can be verified with generic local validators.",
            ),
        ],
    )


def _solution_plan_markdown(plan: MissionSolutionPlan) -> str:
    lines = [
        "# FrontDesk Solution Plan",
        "",
        plan.summary,
        "",
        "Expected artifacts:",
        *[f"- {artifact}" for artifact in plan.expected_artifacts],
        "",
        "Verification strategy:",
        *[f"- {item}" for item in plan.verification_strategy],
        "",
    ]
    return "\n".join(lines)


def plan_frontdesk_solution(
    *,
    session: FrontDeskAuthoringSession,
    workspace: FrontDeskWorkspace,
    registry: ProfileRegistry | None = None,
) -> SolutionArchitectureResult:
    return SolutionArchitect(registry=registry).plan(session=session, workspace=workspace)


__all__ = ["SolutionArchitectureResult", "SolutionArchitect", "plan_frontdesk_solution"]
