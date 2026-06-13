from __future__ import annotations

import tempfile
import unittest

from missionforge import ContractValidationError
from missionforge.frontdesk import FrontDesk
from missionforge.frontdesk.schema import (
    MissionPlan,
    ProfileRecommendation,
    ProfileRecommendationKind,
    ProfileRecommendationSet,
)
from missionforge.frontdesk.spec_grill_schema import (
    CoreNeedBrief,
    DecisionNode,
    DecisionOption,
    DecisionStatus,
    DecisionTree,
    MissionSolutionPlan,
    NeedGrillingReadiness,
    NeedGrillingReport,
    PlanRiskRegister,
    SolutionPlanStatus,
)
from missionforge.frontdesk.state import (
    CORE_NEED_BRIEF_REF,
    DECISION_TREE_REF,
    MISSION_PLAN_REF,
    NEED_GRILLING_REPORT_REF,
    PLAN_RISK_REGISTER_REF,
    PROFILE_RECOMMENDATIONS_REF,
    SOLUTION_PLAN_MARKDOWN_REF,
    SOLUTION_PLAN_REF,
)
from tests.frontdesk_llm_fixtures import ScriptedFrontDeskPiWorker


class FrontDeskSpecGrillServiceTests(unittest.TestCase):
    def test_explicit_service_steps_stop_at_llm_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            frontdesk = FrontDesk(workspace=tempdir)
            session = frontdesk.start(
                "Build docs/output.md. Success means docs/output.md exists.",
                session_id="fd-service-steps",
            )

            scout = frontdesk.scout(session.session_ref)
            with self.assertRaisesRegex(ContractValidationError, "requires an explicit LLM/PiWorker node"):
                frontdesk.grill(session.session_ref)
            inspect = frontdesk.inspect(session.session_ref)

            self.assertIn("generic_local_verification", scout.profile_catalog_snapshot.verification_profile_ids)
            self.assertEqual(inspect.status, "failed_closed")
            self.assertEqual(inspect.next_action, "configure_frontdesk_llm")

    def test_draft_fails_closed_instead_of_shallow_deterministic_draft(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            frontdesk = FrontDesk(workspace=tempdir)
            session = frontdesk.start(
                "Build docs/output.md. Success means docs/output.md exists.",
                session_id="fd-service-draft",
            )

            with self.assertRaisesRegex(ContractValidationError, "requires an explicit LLM/PiWorker node"):
                frontdesk.draft(session.session_ref)

            self.assertFalse(frontdesk.workspace.exists("frontdesk/need_grilling_report.json"))
            self.assertFalse(frontdesk.workspace.exists("frontdesk/draft_mission.json"))

    def test_scripted_piworker_path_grills_covers_and_plans(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            frontdesk = FrontDesk(
                workspace=tempdir,
                worker=_scripted_full_worker(session_id="fd-scripted-service"),
            )
            session = frontdesk.start(
                "Build docs/output.md. Success means docs/output.md exists.",
                session_id="fd-scripted-service",
            )

            grill = frontdesk.grill(session.session_ref)
            coverage = frontdesk.cover_semantics(session.session_ref)
            solution = frontdesk.plan_solution(session.session_ref)
            inspect = frontdesk.inspect(session.session_ref)

            self.assertEqual(grill.core_need_brief.desired_outcome, "Build docs/output.md.")
            self.assertEqual(coverage.coverage_report.status.value, "passed")
            self.assertIn("docs/output.md", solution.mission_plan.expected_artifacts)
            self.assertEqual(inspect.status, "draft_ready")
            self.assertEqual(inspect.next_action, "build_intent_bundle")
            self.assertTrue(inspect.refs["need_griller_execution_ref"].endswith("/need_griller/execution.json"))
            self.assertTrue(
                inspect.refs["solution_architect_execution_ref"].endswith("/solution_architect/execution.json")
            )


def _scripted_full_worker(*, session_id: str) -> ScriptedFrontDeskPiWorker:
    decision_tree = DecisionTree(
        session_id=session_id,
        decisions=[
            DecisionNode(
                decision_id="D-output",
                topic="desired_output",
                status=DecisionStatus.CONFIRMED,
                current_hypothesis="Build docs/output.md.",
                options=[DecisionOption(option_id="O-doc", summary="Create the requested doc artifact.")],
                blocking=True,
                source_refs=["frontdesk/session.json"],
                chosen_option_id="O-doc",
            )
        ],
    )
    core_need = CoreNeedBrief(
        session_id=session_id,
        core_pain="The user needs a bounded documentation artifact.",
        target_users=["missionforge_user"],
        usage_moment="Before runtime handoff.",
        deliverable_type="artifact",
        desired_outcome="Build docs/output.md.",
        success_signals=["docs/output.md exists."],
        constraints=[],
        non_goals=["Do not use raw conversation as runtime truth."],
        source_refs=["frontdesk/session.json"],
    )
    report = NeedGrillingReport(
        session_id=session_id,
        readiness=NeedGrillingReadiness.CORE_NEED_READY,
        observations=["The desired artifact is explicit."],
        inferences=["Build docs/output.md."],
        confirmed_requirements=["docs/output.md exists."],
        open_decision_ids=[],
        next_question=None,
        decision_tree_ref=DECISION_TREE_REF,
        core_need_brief_ref=CORE_NEED_BRIEF_REF,
    )
    solution_plan = MissionSolutionPlan(
        session_id=session_id,
        status=SolutionPlanStatus.AWAITING_REVIEW,
        summary="Create docs/output.md and verify it exists.",
        core_need_ref=CORE_NEED_BRIEF_REF,
        mvp_scope=["Build docs/output.md."],
        future_scope=[],
        rejected_directions=["Do not add product-specific runtime logic."],
        expected_artifacts=["docs/output.md"],
        selected_capability_profile_ids=["user_provided_evidence_only", "explicit_output_root"],
        selected_verification_profile_ids=["generic_local_verification"],
        verification_strategy=["Verify docs/output.md exists."],
        risks=[],
        authority_requirements=["plan_review"],
        source_refs=[CORE_NEED_BRIEF_REF],
    )
    risk_register = PlanRiskRegister(
        session_id=session_id,
        risks=[],
        mitigations=["Keep raw conversation provenance-only."],
        source_refs=[CORE_NEED_BRIEF_REF],
    )
    recommendations = ProfileRecommendationSet(
        session_id=session_id,
        recommendations=[
            ProfileRecommendation(
                profile_id="user_provided_evidence_only",
                kind=ProfileRecommendationKind.CAPABILITY,
                rationale="Use admitted source refs only.",
            ),
            ProfileRecommendation(
                profile_id="explicit_output_root",
                kind=ProfileRecommendationKind.CAPABILITY,
                rationale="Expected output root is explicit.",
            ),
            ProfileRecommendation(
                profile_id="generic_local_verification",
                kind=ProfileRecommendationKind.VERIFICATION,
                rationale="The artifact can be checked locally.",
            ),
        ],
    )
    mission_plan = MissionPlan(
        session_id=session_id,
        expected_artifacts=["docs/output.md"],
        constraints=[],
        validators=[{"validator_type": "file_exists", "path": "docs/output.md"}],
        manual_gates=[],
        risk_notes=[],
    )
    return ScriptedFrontDeskPiWorker(
        {
            DECISION_TREE_REF: decision_tree,
            CORE_NEED_BRIEF_REF: core_need,
            NEED_GRILLING_REPORT_REF: report,
            SOLUTION_PLAN_REF: solution_plan,
            PLAN_RISK_REGISTER_REF: risk_register,
            PROFILE_RECOMMENDATIONS_REF: recommendations,
            MISSION_PLAN_REF: mission_plan,
        },
        text_payloads={SOLUTION_PLAN_MARKDOWN_REF: "# Solution Plan\n\nCreate docs/output.md.\n"},
    )


if __name__ == "__main__":
    unittest.main()
