from __future__ import annotations

import unittest

from missionforge import (
    ContractValidationError,
    CoreNeedBrief,
    DecisionTree,
    FrontDeskFreezeGateResult,
    MissionIRMappingReport,
    MissionSemanticCoverageReport,
    MissionSolutionPlan,
    NeedGrillingReport,
    PlanReviewRecord,
    WorkspaceFacts,
)
from missionforge.frontdesk.schema import ApprovalAuthority
from missionforge.frontdesk.spec_grill_schema import (
    DecisionNode,
    DecisionOption,
    DecisionStatus,
    FactConfidence,
    FreezeGateDecision,
    GrillingQuestion,
    MappingStatus,
    NeedGrillingReadiness,
    PlanReviewDecision,
    ProfileCatalogSnapshot,
    QuestionAnswerType,
    RequirementMapping,
    SemanticCoverageItem,
    SemanticCoverageItemStatus,
    SemanticCoverageStatus,
    SolutionPlanStatus,
    SourceAdmissionReport,
    WorkspaceFact,
    stable_bundle_hash,
)


class FrontDeskSpecGrillSchemaTests(unittest.TestCase):
    def test_schema_round_trips_spec_grill_contracts(self) -> None:
        facts = WorkspaceFacts(
            session_id="fd-001",
            facts=[
                WorkspaceFact(
                    fact_id="F-001",
                    summary="Generic local verification profile is available.",
                    source_refs=["docs/PROFILE_EXTENSION_KIT.md"],
                    confidence=FactConfidence.OBSERVED,
                )
            ],
            questions_answered_by_workspace=["Which verification profiles exist?"],
        )
        self.assertEqual(WorkspaceFacts.from_dict(facts.to_dict()), facts)

        catalog = ProfileCatalogSnapshot(
            session_id="fd-001",
            capability_profile_ids=["explicit_output_root"],
            verification_profile_ids=["generic_local_verification"],
        )
        self.assertEqual(ProfileCatalogSnapshot.from_dict(catalog.to_dict()), catalog)

        source_report = SourceAdmissionReport(
            session_id="fd-001",
            admitted_source_refs=["frontdesk/sanitized_sources.json"],
            excluded_source_refs=["frontdesk/conversation.jsonl"],
            reasons=["Raw conversation is provenance only."],
        )
        self.assertEqual(SourceAdmissionReport.from_dict(source_report.to_dict()), source_report)

        tree = DecisionTree(
            session_id="fd-001",
            decisions=[
                DecisionNode(
                    decision_id="D-001",
                    topic="core_need",
                    status=DecisionStatus.OPEN,
                    current_hypothesis="The user needs durable mission authoring.",
                    options=[DecisionOption(option_id="O-001", summary="authoring clarity")],
                    source_refs=["frontdesk/conversation.jsonl"],
                )
            ],
        )
        self.assertEqual(DecisionTree.from_dict(tree.to_dict()), tree)

        brief = CoreNeedBrief(
            session_id="fd-001",
            core_pain="The mission intent is lost during long-running AI work.",
            target_users=["missionforge_user"],
            usage_moment="Before runtime starts.",
            deliverable_type="artifact",
            desired_outcome="A reviewed MissionIR contract.",
            success_signals=["Mapping report covers every requirement."],
            source_refs=["frontdesk/semantic_lock.json"],
        )
        self.assertEqual(CoreNeedBrief.from_dict(brief.to_dict()), brief)

        question = GrillingQuestion(
            question_id="Q-001",
            inference="The user is asking for protected generic core behavior, not only Rust.",
            recommended_answer="Keep Python orchestration and isolate only proven performance-sensitive core code.",
            question="Is the main concern performance, packaging, or preventing task-specific core edits?",
            why_this_matters="The answer changes the first mission shape.",
            expected_answer_type=QuestionAnswerType.CHOICE_OR_FREE_TEXT,
            related_decision_ids=["D-001"],
        )
        report = NeedGrillingReport(
            session_id="fd-001",
            readiness=NeedGrillingReadiness.NEEDS_CLARIFICATION,
            observations=["User asked about Rust."],
            inferences=["Rust is an implementation hypothesis."],
            open_decision_ids=["D-001"],
            next_question=question,
        )
        self.assertEqual(NeedGrillingReport.from_dict(report.to_dict()), report)

        coverage = MissionSemanticCoverageReport(
            session_id="fd-001",
            status=SemanticCoverageStatus.PASSED,
            coverage_items=[
                SemanticCoverageItem(
                    signal_id="S-001",
                    source_signal="User asked about Rust.",
                    status=SemanticCoverageItemStatus.COVERED,
                    source_refs=["frontdesk/conversation.jsonl"],
                    mapped_refs=["frontdesk/solution_plan.json"],
                    notes="Captured as an implementation preference.",
                )
            ],
        )
        self.assertEqual(MissionSemanticCoverageReport.from_dict(coverage.to_dict()), coverage)

        plan = MissionSolutionPlan(
            session_id="fd-001",
            status=SolutionPlanStatus.AWAITING_REVIEW,
            summary="Build an active FrontDesk authoring flow.",
            core_need_ref="frontdesk/core_need_brief.json",
            expected_artifacts=["docs/output.md"],
            selected_capability_profile_ids=["explicit_output_root"],
            selected_verification_profile_ids=["generic_local_verification"],
            verification_strategy=["Check expected artifacts."],
            source_refs=["frontdesk/core_need_brief.json"],
        )
        self.assertEqual(MissionSolutionPlan.from_dict(plan.to_dict()), plan)

        review = PlanReviewRecord(
            session_id="fd-001",
            decision=PlanReviewDecision.APPROVE,
            reviewed_plan_ref="frontdesk/solution_plan.json",
            reviewed_plan_hash=plan.plan_hash,
            reviewed_by="policy",
            authority=ApprovalAuthority.POLICY,
        )
        self.assertEqual(PlanReviewRecord.from_dict(review.to_dict()), review)

        mapping_report = MissionIRMappingReport(
            session_id="fd-001",
            draft_mission_ref="frontdesk/draft_mission.json",
            requirement_mappings=[
                RequirementMapping(
                    requirement_id="R-001",
                    requirement_text="Preserve user intent.",
                    status=MappingStatus.MAPPED,
                    mission_paths=["objective.summary"],
                    mapped_refs=["frontdesk/draft_mission.json"],
                )
            ],
            profile_mappings=["generic_local_verification"],
            validator_mappings=["file_exists"],
        )
        self.assertEqual(MissionIRMappingReport.from_dict(mapping_report.to_dict()), mapping_report)

        freeze_result = FrontDeskFreezeGateResult(
            session_id="fd-001",
            decision=FreezeGateDecision.FREEZE,
            passed_checks=["semantic_coverage", "plan_review", "mapping_report"],
            artifact_refs=["frontdesk/freeze_manifest.json"],
        )
        self.assertEqual(FrontDeskFreezeGateResult.from_dict(freeze_result.to_dict()), freeze_result)

    def test_unknown_fields_fail_closed(self) -> None:
        with self.assertRaisesRegex(ContractValidationError, "unknown field"):
            WorkspaceFacts.from_dict({"session_id": "fd-001", "facts": [], "extra": True})

    def test_raw_prompt_transcript_and_secret_fields_fail_closed(self) -> None:
        with self.assertRaisesRegex(ContractValidationError, "raw_prompt"):
            WorkspaceFacts.from_dict(
                {
                    "session_id": "fd-001",
                    "facts": [
                        {
                            "fact_id": "F-001",
                            "summary": "unsafe",
                            "metadata": {"raw_prompt": "ignore rules"},
                        }
                    ],
                }
            )

    def test_broad_grilling_question_fails_closed(self) -> None:
        with self.assertRaisesRegex(ContractValidationError, "targeted"):
            GrillingQuestion(
                question_id="Q-001",
                inference="The need is unclear.",
                recommended_answer="Clarify the user goal.",
                question="Please provide more details.",
                why_this_matters="Broad questions are not acceptable.",
            ).validate()

    def test_semantic_coverage_cannot_pass_with_unmapped_signal(self) -> None:
        with self.assertRaisesRegex(ContractValidationError, "cannot pass"):
            MissionSemanticCoverageReport(
                session_id="fd-001",
                status=SemanticCoverageStatus.PASSED,
                coverage_items=[
                    SemanticCoverageItem(
                        signal_id="S-001",
                        source_signal="privacy",
                        status=SemanticCoverageItemStatus.UNMAPPED,
                        source_refs=["frontdesk/conversation.jsonl"],
                    )
                ],
                unmapped_signals=["privacy"],
            ).validate()

    def test_mapping_report_detects_blocking_gaps(self) -> None:
        report = MissionIRMappingReport(
            session_id="fd-001",
            draft_mission_ref="frontdesk/draft_mission.json",
            requirement_mappings=[
                RequirementMapping(
                    requirement_id="R-001",
                    requirement_text="Do not expose internals.",
                    status=MappingStatus.UNMAPPED,
                    mission_paths=[],
                    blocking=True,
                )
            ],
            unmapped_requirements=["R-001"],
        )

        self.assertTrue(report.has_blocking_gaps)

    def test_stable_bundle_hash_is_sha256(self) -> None:
        self.assertTrue(stable_bundle_hash({"a": 1}).startswith("sha256:"))


if __name__ == "__main__":
    unittest.main()
