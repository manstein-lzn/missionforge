from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from missionforge import MissionIR, MissionRuntime
from missionforge.benchmark import (
    BenchmarkBudget,
    BenchmarkMode,
    BenchmarkTask,
    MissionForgeFullProductFlowBenchmarkRunner,
    ProductGateOutcome,
)
from missionforge.frontdesk import (
    FrontDeskIntentBundle,
    IntentBundleReadiness,
    IntentGenericRefs,
    ProductContextSnapshot,
    SlotValue,
    SlotValueStatus,
)
from missionforge.frontdesk.schema import MissionPlan, ProfileRecommendation, ProfileRecommendationKind, ProfileRecommendationSet
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
    INTENT_BUNDLE_CANDIDATE_REF,
    MISSION_PLAN_REF,
    NEED_GRILLING_REPORT_REF,
    PLAN_RISK_REGISTER_REF,
    PROFILE_RECOMMENDATIONS_REF,
    SOLUTION_PLAN_MARKDOWN_REF,
    SOLUTION_PLAN_REF,
)
from missionforge.runner import MissionResult
from missionforge_skillfoundry import (
    SkillFoundryFrontDeskIntegration,
    SkillFoundryInquiryProfile,
    evaluate_product_grade,
    validate_skill_bundle,
)
from missionforge_skillfoundry.validators import BUNDLE_VALIDATION_REPORT_REF
from tests.frontdesk_llm_fixtures import ScriptedFrontDeskPiWorker


class SkillFoundryFullProductFlowBenchmarkTests(unittest.TestCase):
    def test_colloquial_skillfoundry_task_reaches_product_grade_through_generic_runner(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            _write_user_text(
                root,
                (
                    "我不是想写一个普通脚本。我想把一套工程推进方法沉淀成本地 Codex skill，"
                    "第一版只要 prompt-only 包就行，必须有 package/SKILL.md、manifest 和 README，"
                    "不要把我们的原始对话或任何 provider payload 写进去。"
                ),
            )
            task = _task()
            flow_workspace = (
                root
                / "benchmarks/runs/bench-vb5/trials/sf-vb5-skill/missionforge_full_product_flow/seed-1/workspace"
            )
            runner = MissionForgeFullProductFlowBenchmarkRunner(
                product_integration=SkillFoundryFrontDeskIntegration(bundle_id="vb5-local-skill"),
                product_gate=_SkillFoundryProductGate(bundle_id="vb5-local-skill"),
                frontdesk_worker=_skillfoundry_frontdesk_worker(session_id="fd-sf-vb5-skill-seed-1"),
                runtime=_PackageFixtureRuntime(flow_workspace),
            )

            record = runner.run_trial(
                benchmark_run_id="bench-vb5",
                task=task,
                seed=1,
                workspace=root,
            )

            self.assertEqual(record.trial.mode, BenchmarkMode.MISSIONFORGE_FULL_PRODUCT_FLOW)
            self.assertTrue(record.summary.accepted)
            self.assertTrue(record.summary.generic_verifier_passed)
            self.assertEqual(record.summary.product_compile_status, "compiled")
            self.assertEqual(record.summary.product_gate_status, "product_grade")
            self.assertEqual(record.summary.frontdesk_node_count, 3)
            self.assertEqual(record.summary.frontdesk_worker_call_count, 3)
            self.assertTrue(record.summary.intent_bundle_ready)
            self.assertTrue(record.summary.product_acceptance_coverage_passed)
            self.assertEqual(record.summary.product_gate_blocking_finding_count, 0)
            self.assertIn(
                "benchmarks/runs/bench-vb5/trials/sf-vb5-skill/missionforge_full_product_flow/seed-1/workspace/package/SKILL.md",
                record.summary.artifact_refs,
            )
            self.assertTrue((root / record.product_compile_result_ref).exists())
            self.assertTrue((root / record.product_gate_outcome_ref).exists())
            self.assertTrue((root / record.review_packet_ref).exists())
            self.assertTrue((flow_workspace / "qa/product_grade_report.json").exists())

            metric_events = (root / record.metric_events_ref).read_text(encoding="utf-8")
            self.assertIn('"namespace": "integration.skillfoundry"', metric_events)
            self.assertNotIn("provider_payload", metric_events)
            self.assertNotIn("raw_prompt", metric_events)

    def test_coverage_miss_keeps_trial_unaccepted_even_with_product_grade_status(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            _write_user_text(
                root,
                "我想把复杂工程方法做成一个可复用的本地 Codex skill，但先不要把任何产品专有的覆盖检查当成已完成。",
            )
            task = _task()
            flow_workspace = (
                root
                / "benchmarks/runs/bench-vb5/trials/sf-vb5-skill/missionforge_full_product_flow/seed-2/workspace"
            )
            runner = MissionForgeFullProductFlowBenchmarkRunner(
                product_integration=SkillFoundryFrontDeskIntegration(bundle_id="vb5-local-skill"),
                product_gate=_CoverageMissProductGate(bundle_id="vb5-local-skill"),
                frontdesk_worker=_skillfoundry_frontdesk_worker(session_id="fd-sf-vb5-skill-seed-2"),
                runtime=_PackageFixtureRuntime(flow_workspace),
            )

            record = runner.run_trial(
                benchmark_run_id="bench-vb5",
                task=task,
                seed=2,
                workspace=root,
            )

            self.assertFalse(record.summary.accepted)
            self.assertEqual(record.summary.product_gate_status, "product_grade")
            self.assertFalse(record.summary.product_acceptance_coverage_passed)
            self.assertIn("product_acceptance_coverage_miss", record.summary.failure_taxonomy)
            self.assertIn("product_gate_failed", record.summary.failure_taxonomy)
            metric_events = [
                json.loads(line)
                for line in (root / record.metric_events_ref).read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            integration_event = next(event for event in metric_events if event["namespace"] == "integration.skillfoundry")
            self.assertFalse(integration_event["values"]["product_gate_passed"])


class _SkillFoundryProductGate:
    def __init__(self, *, bundle_id: str) -> None:
        self.bundle_id = bundle_id

    def run_product_gate(
        self,
        *,
        workspace: str | Path,
        task: BenchmarkTask,
        compile_result,
        mission_result: MissionResult,
    ) -> ProductGateOutcome:
        validate_skill_bundle(
            workspace=workspace,
            bundle_id=self.bundle_id,
            matrix_ref=compile_result.product_gate_spec_ref,
            report_ref=BUNDLE_VALIDATION_REPORT_REF,
        )
        report = evaluate_product_grade(
            workspace=workspace,
            bundle_id=self.bundle_id,
            mission_result=mission_result,
            bundle_validation_report_ref=BUNDLE_VALIDATION_REPORT_REF,
        )
        return ProductGateOutcome(
            product_id="skillfoundry",
            status="product_grade" if report.product_grade else "failed",
            result_ref="qa/product_grade_report.json",
            evidence_refs=[BUNDLE_VALIDATION_REPORT_REF, "qa/product_grade_report.json"],
            artifact_refs=list(report.package_refs),
            diagnostic_refs=[report.repair_packet_ref] if report.repair_packet_ref else [],
            product_acceptance_coverage_passed=report.outcome_category != "coverage_miss",
            blocking_finding_count=sum(1 for finding in report.findings if finding.severity == "blocking"),
            outcome_category=report.outcome_category,
        )


class _CoverageMissProductGate(_SkillFoundryProductGate):
    def run_product_gate(
        self,
        *,
        workspace: str | Path,
        task: BenchmarkTask,
        compile_result,
        mission_result: MissionResult,
    ) -> ProductGateOutcome:
        outcome = super().run_product_gate(
            workspace=workspace,
            task=task,
            compile_result=compile_result,
            mission_result=mission_result,
        )
        return ProductGateOutcome(
            product_id=outcome.product_id,
            status=outcome.status,
            result_ref=outcome.result_ref,
            evidence_refs=list(outcome.evidence_refs),
            artifact_refs=list(outcome.artifact_refs),
            diagnostic_refs=list(outcome.diagnostic_refs),
            product_acceptance_coverage_passed=False,
            blocking_finding_count=outcome.blocking_finding_count,
            outcome_category="coverage_miss",
        )


class _PackageFixtureRuntime(MissionRuntime):
    def __init__(self, workspace: Path) -> None:
        self.workspace = workspace

    def run(self, mission: MissionIR) -> MissionResult:
        (self.workspace / "package").mkdir(parents=True, exist_ok=True)
        (self.workspace / "package/SKILL.md").write_text(
            "# Engineering Method Skill\n\nUse admitted refs only and keep raw conversation out of package output.\n",
            encoding="utf-8",
        )
        (self.workspace / "package/skillfoundry.bundle.json").write_text(
            (
                '{"schema_version":"skillfoundry.bundle.v1","bundle_id":"vb5-local-skill",'
                '"bundle_profile":"prompt_only","entrypoint":"SKILL.md",'
                '"capability_surface":{"codex_skill":{"entry_ref":"package/SKILL.md"}},'
                '"runtime_assets":[],"data_assets":[],"references":[],"environment":{},'
                '"permissions":{},"verification":{"matrix_ref":"product_contract/product_acceptance_matrix.json",'
                '"product_grade_ref":"qa/product_grade_report.json"},"distribution":{"status":"local"}}'
            ),
            encoding="utf-8",
        )
        (self.workspace / "package/README.md").write_text(
            "# Engineering Method Skill\n\nLocal prompt-only SkillFoundry package.\n",
            encoding="utf-8",
        )
        return MissionResult(
            mission_id=mission.mission_id,
            status="completed_verified",
            evidence_refs=["evidence/verifier.json"],
            artifact_refs=["package/SKILL.md", "package/skillfoundry.bundle.json", "package/README.md"],
        )


def _skillfoundry_frontdesk_worker(*, session_id: str) -> ScriptedFrontDeskPiWorker:
    expected_artifacts = ["package/SKILL.md", "package/skillfoundry.bundle.json", "package/README.md"]
    source_refs = [CORE_NEED_BRIEF_REF, SOLUTION_PLAN_REF]
    profile = SkillFoundryInquiryProfile()
    decision_tree = DecisionTree(
        session_id=session_id,
        decisions=[
            DecisionNode(
                decision_id="D-skill-package",
                topic="reusable_skill_package",
                status=DecisionStatus.CONFIRMED,
                current_hypothesis="Create a local prompt-only Codex skill package.",
                options=[DecisionOption(option_id="O-prompt-only", summary="Build a prompt-only SkillFoundry package.")],
                blocking=True,
                source_refs=["frontdesk/session.json"],
                chosen_option_id="O-prompt-only",
            )
        ],
    )
    core_need = CoreNeedBrief(
        session_id=session_id,
        core_pain="The user wants reusable engineering method guidance packaged as a local Codex skill.",
        target_users=["local Codex user doing complex engineering work"],
        usage_moment="When repeating the same engineering approach across projects.",
        deliverable_type="skillfoundry_package",
        desired_outcome="Create a prompt-only SkillFoundry package without leaking raw conversation.",
        success_signals=[f"{ref} exists." for ref in expected_artifacts],
        constraints=["Do not include raw conversation or provider payloads.", "Keep package refs under package/."],
        non_goals=["Do not build a service runtime in VB5."],
        source_refs=["frontdesk/session.json"],
    )
    report = NeedGrillingReport(
        session_id=session_id,
        readiness=NeedGrillingReadiness.CORE_NEED_READY,
        observations=["The user wants a reusable local Codex skill, not a one-off script."],
        inferences=["SkillFoundry prompt-only package is the correct product direction."],
        confirmed_requirements=list(core_need.success_signals),
        open_decision_ids=[],
        next_question=None,
        decision_tree_ref=DECISION_TREE_REF,
        core_need_brief_ref=CORE_NEED_BRIEF_REF,
    )
    solution = MissionSolutionPlan(
        session_id=session_id,
        status=SolutionPlanStatus.AWAITING_REVIEW,
        summary="Build a prompt-only SkillFoundry package for reusable engineering-method guidance.",
        core_need_ref=CORE_NEED_BRIEF_REF,
        mvp_scope=["Create package/SKILL.md, package/skillfoundry.bundle.json, and package/README.md."],
        future_scope=["Consider code_runtime only after prompt-only package proves useful."],
        rejected_directions=["Do not embed raw conversation as package content."],
        expected_artifacts=expected_artifacts,
        selected_capability_profile_ids=["user_provided_evidence_only", "explicit_output_root"],
        selected_verification_profile_ids=["generic_local_verification"],
        verification_strategy=[f"Verify {ref} exists." for ref in expected_artifacts],
        risks=["Raw context leakage would invalidate the package."],
        authority_requirements=["product_gate"],
        source_refs=[CORE_NEED_BRIEF_REF],
    )
    risk_register = PlanRiskRegister(
        session_id=session_id,
        risks=["raw_context_leakage"],
        mitigations=["Use refs-only FrontDesk and SkillFoundry artifacts."],
        source_refs=[CORE_NEED_BRIEF_REF],
    )
    recommendations = ProfileRecommendationSet(
        session_id=session_id,
        recommendations=[
            ProfileRecommendation(
                profile_id="user_provided_evidence_only",
                kind=ProfileRecommendationKind.CAPABILITY,
                rationale="Use admitted refs only.",
            ),
            ProfileRecommendation(
                profile_id="explicit_output_root",
                kind=ProfileRecommendationKind.CAPABILITY,
                rationale="All outputs are under package/.",
            ),
            ProfileRecommendation(
                profile_id="generic_local_verification",
                kind=ProfileRecommendationKind.VERIFICATION,
                rationale="Package files can be checked locally.",
            ),
        ],
    )
    mission_plan = MissionPlan(
        session_id=session_id,
        expected_artifacts=expected_artifacts,
        constraints=[],
        validators=[{"validator_type": "file_exists", "path": ref} for ref in expected_artifacts],
        manual_gates=[],
        risk_notes=["ProductGradeGate owns product-grade acceptance."],
    )
    candidate = FrontDeskIntentBundle(
        session_id=session_id,
        intent_bundle_ref=INTENT_BUNDLE_CANDIDATE_REF,
        generic_refs=IntentGenericRefs(session_ref="frontdesk/session.json"),
        product_context=ProductContextSnapshot(
            product_id=profile.product_id,
            display_name=profile.display_name,
            profile_ref="frontdesk/product_inquiry_profile.json",
            profile_hash=profile.profile_hash,
            version=profile.version,
        ),
        slot_values=[
            _slot("capability_goal", "Create a reusable local Codex skill for engineering-method guidance.", source_refs),
            _slot("target_user", "local Codex user doing complex engineering work", source_refs),
            _slot("trigger_scenarios", ["When reusable engineering method guidance should be packaged."], source_refs),
            _slot("non_trigger_scenarios", ["When the user only needs a one-off script."], source_refs),
            _slot("bundle_profile", "prompt_only", source_refs),
            _slot("required_package_outputs", expected_artifacts, source_refs),
            SlotValue(slot_id="runtime_assets_required", status=SlotValueStatus.NOT_APPLICABLE, value=None),
            SlotValue(slot_id="data_assets_required", status=SlotValueStatus.NOT_APPLICABLE, value=None),
            _slot("privacy_boundary", ["Do not include raw conversation or provider payloads."], source_refs),
            _slot("distribution_boundary", ["Local private distribution only."], source_refs),
        ],
        missing_blocking_slots=[],
        readiness=IntentBundleReadiness.READY_FOR_PRODUCT_COMPILE,
        clarification_questions=[],
        evidence_refs=source_refs,
    )
    return ScriptedFrontDeskPiWorker(
        {
            DECISION_TREE_REF: decision_tree,
            CORE_NEED_BRIEF_REF: core_need,
            NEED_GRILLING_REPORT_REF: report,
            SOLUTION_PLAN_REF: solution,
            PLAN_RISK_REGISTER_REF: risk_register,
            PROFILE_RECOMMENDATIONS_REF: recommendations,
            MISSION_PLAN_REF: mission_plan,
            INTENT_BUNDLE_CANDIDATE_REF: candidate,
        },
        text_payloads={SOLUTION_PLAN_MARKDOWN_REF: "# Solution Plan\n\nBuild the SkillFoundry package.\n"},
    )


def _slot(slot_id: str, value, source_refs: list[str]) -> SlotValue:
    return SlotValue(slot_id=slot_id, status=SlotValueStatus.INFERRED, value=value, source_refs=source_refs)


def _task() -> BenchmarkTask:
    return BenchmarkTask(
        task_id="sf-vb5-skill",
        task_family="skillfoundry",
        difficulty="medium",
        initial_user_text_ref="benchmarks/tasks/sf-vb5-skill/user_statement.txt",
        expected_output_refs=["package/SKILL.md", "package/skillfoundry.bundle.json", "package/README.md"],
        budget=BenchmarkBudget(
            max_wall_minutes=45,
            max_total_tokens=250000,
            max_cost_usd=10.0,
            max_user_turns=6,
        ),
        acceptance_refs=["benchmarks/tasks/sf-vb5-skill/acceptance/hidden_checks.json"],
    )


def _write_user_text(root: Path, text: str) -> None:
    path = root / "benchmarks/tasks/sf-vb5-skill/user_statement.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
