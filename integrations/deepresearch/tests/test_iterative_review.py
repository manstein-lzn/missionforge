from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from missionforge.contracts import ContractValidationError
from missionforge_deepresearch import (
    DeepResearchReviewedRunStatus,
    FixtureDeepResearchJudgeAdapter,
)
from missionforge_deepresearch.experimental import (
    FixturePeerReviewerAdapter,
    FixtureReviewedResearcherAdapter,
    load_deepresearch_reviewed_run_result,
    run_deepresearch_academic_reviewed,
    run_deepresearch_academic_reviewed_judged,
)

from test_product_contract import sample_request


class IterativeReviewTests(unittest.TestCase):
    def test_reviewed_run_records_peer_review_and_research_state(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)

            result = run_deepresearch_academic_reviewed(
                sample_request(),
                workspace=root,
                researcher_adapter=FixtureReviewedResearcherAdapter(),
                reviewer_adapter=FixturePeerReviewerAdapter(),
                reviewer_mode="fixture",
                review_rounds=1,
            )
            loaded = load_deepresearch_reviewed_run_result(root, result.reviewed_run_result_ref)

            self.assertEqual(loaded, result)
            self.assertEqual(result.status, DeepResearchReviewedRunStatus.DRAFT_READY)
            self.assertEqual(result.review_round_count, 1)
            self.assertEqual(
                result.reviewed_run_result_ref,
                "runs/npu-compiler-survey/packages/deepresearch_reviewed_run_result.json",
            )
            self.assertEqual(result.final_run_result_ref, "runs/npu-compiler-survey/packages/deepresearch_run_result.json")
            self.assertEqual(result.reviewer_report_refs, ["runs/npu-compiler-survey/reviews/round_01/reviewer_report.md"])
            self.assertEqual(
                result.reviewer_observation_refs,
                ["runs/npu-compiler-survey/reviews/round_01/reviewer_observation.json"],
            )
            self.assertEqual(result.research_state_refs, ["runs/npu-compiler-survey/reviews/round_01/research_state.json"])

            run_root = root / "runs/npu-compiler-survey"
            reviewer_call = json.loads((run_root / "attempts/reviewer/round_01/piworker_call.json").read_text(encoding="utf-8"))
            revision_call = json.loads((run_root / "attempts/researcher/round_01/piworker_call.json").read_text(encoding="utf-8"))
            revision_manifest = json.loads((run_root / "reviews/round_01/revision_permission_manifest.json").read_text(encoding="utf-8"))
            observation = json.loads((run_root / "reviews/round_01/reviewer_observation.json").read_text(encoding="utf-8"))
            state = json.loads((run_root / "reviews/round_01/research_state.json").read_text(encoding="utf-8"))
            final_run = json.loads((root / result.final_run_result_ref).read_text(encoding="utf-8"))
            review_spec = json.loads((run_root / "reviews/round_01/review_spec.json").read_text(encoding="utf-8"))
            observation_schema = json.loads(
                (run_root / "reviews/round_01/reviewer_observation_schema.json").read_text(encoding="utf-8")
            )
            research_state_schema = json.loads(
                (run_root / "reviews/round_01/research_state_schema.json").read_text(encoding="utf-8")
            )

            self.assertEqual(reviewer_call["role"], "judge_piworker")
            self.assertEqual(reviewer_call["metadata"]["authority"], "guidance_only")
            self.assertIn("reviews/round_01/reviewer_observation.json", reviewer_call["expected_output_refs"])
            self.assertIn("reviews/round_01/reviewer_observation_schema.json", reviewer_call["visible_refs"])
            self.assertIn("reviews/round_01/research_state_schema.json", reviewer_call["visible_refs"])
            self.assertEqual(
                review_spec["required_observation_shape"]["schema_version"],
                "missionforge_deepresearch.reviewer_observation.v1",
            )
            self.assertEqual(
                review_spec["required_observation_shape"]["accepted_schema_versions"],
                ["missionforge_deepresearch.reviewer_observation.v1"],
            )
            self.assertNotIn("field_aliases_accepted_for_compatibility", review_spec["required_observation_shape"])
            self.assertEqual(
                review_spec["required_research_state_shape"]["accepted_schema_versions"],
                ["missionforge_deepresearch.research_state.v1"],
            )
            self.assertIn("contract_ref", review_spec["required_research_state_shape"]["required_fields"])
            self.assertIn("source_packet_ref", review_spec["required_research_state_shape"]["required_fields"])
            self.assertIn("reviews/round_01/reviewer_observation_schema.json", review_spec["required_reviewer_observation_schema_ref"])
            self.assertIn("reviews/round_01/research_state_schema.json", review_spec["required_research_state_schema_ref"])
            self.assertEqual(observation_schema["schema_version"], "missionforge_deepresearch.reviewer_observation_schema.v1")
            self.assertEqual(observation_schema["artifact_ref"], "reviews/round_01/reviewer_observation.json")
            self.assertEqual(research_state_schema["schema_version"], "missionforge_deepresearch.research_state_schema.v1")
            self.assertEqual(research_state_schema["artifact_ref"], "reviews/round_01/research_state.json")
            self.assertIn("reviews/round_01/next_research_directive.md", revision_call["visible_refs"])
            self.assertIn("reviews/round_01/reviewer_observation.json", revision_call["visible_refs"])
            self.assertIn("contract_ref", revision_call["objective"])
            self.assertIn("reviews/round_01/research_state.json", revision_call["expected_output_refs"])
            self.assertIn("reviews/round_01/reviewer_observation_schema.json", revision_call["visible_refs"])
            self.assertIn("reviews/round_01/research_state_schema.json", revision_call["visible_refs"])
            self.assertIn("reviews", revision_call["permission_manifest_ref"])
            self.assertIn("reviews", revision_manifest["readable_refs"])
            self.assertIn("reviews", revision_manifest["writable_refs"])
            self.assertEqual(observation["decision"], "continue")
            self.assertEqual(observation["allowed_next_actions"], ["researcher_revision"])
            self.assertEqual(state["schema_version"], "missionforge_deepresearch.research_state.v1")
            self.assertEqual(state["round_index"], 1)
            self.assertEqual(state["posterior_kind"], "review_guided_research_state")
            self.assertEqual(state["prior_state_refs"], [])
            self.assertEqual(state["reviewer_observation_ref"], "reviews/round_01/reviewer_observation.json")
            self.assertIn("reviews/round_01/reviewer_observation.json", state["reviewer_guidance_refs"])
            self.assertIn("belief_updates", state)
            self.assertIn("current_hypotheses", state)
            self.assertIn("confidence_notes", state)
            self.assertIn("unresolved_gaps", state)
            self.assertIn("next_best_actions", state)
            self.assertIn("sources/source_packet.json", state["evidence_refs"])
            self.assertEqual(final_run["status"], "draft_ready")
            self.assertNotIn("\"accepted\"", (root / result.reviewed_run_result_ref).read_text(encoding="utf-8"))

    def test_research_state_feeds_next_review_round_as_prior(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)

            result = run_deepresearch_academic_reviewed(
                sample_request(),
                workspace=root,
                researcher_adapter=FixtureReviewedResearcherAdapter(),
                reviewer_adapter=FixturePeerReviewerAdapter(),
                reviewer_mode="fixture",
                review_rounds=2,
            )

            self.assertEqual(result.status, DeepResearchReviewedRunStatus.DRAFT_READY)
            self.assertEqual(result.review_round_count, 2)
            run_root = root / "runs/npu-compiler-survey"
            round_2_spec = json.loads((run_root / "reviews/round_02/review_spec.json").read_text(encoding="utf-8"))
            round_2_observation = json.loads(
                (run_root / "reviews/round_02/reviewer_observation.json").read_text(encoding="utf-8")
            )
            round_2_state = json.loads((run_root / "reviews/round_02/research_state.json").read_text(encoding="utf-8"))

            self.assertIn("reviews/round_01/research_state.json", round_2_spec["prior_research_state_refs"])
            self.assertIn("reviews/round_01/research_state.json", round_2_observation["state_refs"])
            self.assertEqual(round_2_state["prior_state_refs"], ["reviews/round_01/research_state.json"])

    def test_ready_for_judge_stops_before_revision(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)

            result = run_deepresearch_academic_reviewed(
                sample_request(),
                workspace=root,
                researcher_adapter=FixtureReviewedResearcherAdapter(),
                reviewer_adapter=FixturePeerReviewerAdapter("ready_for_judge"),
                reviewer_mode="fixture",
                review_rounds=1,
            )

            self.assertEqual(result.status, DeepResearchReviewedRunStatus.DRAFT_READY)
            self.assertEqual(result.review_round_count, 1)
            self.assertEqual(result.research_state_refs, [])
            self.assertEqual(result.revision_call_refs, [])
            self.assertEqual(
                result.reviewer_observation_refs,
                ["runs/npu-compiler-survey/reviews/round_01/reviewer_observation.json"],
            )
            run_root = root / "runs/npu-compiler-survey"
            self.assertFalse((run_root / "attempts/researcher/round_01/piworker_call.json").exists())
            self.assertFalse((run_root / "reviews/round_01/revision_permission_manifest.json").exists())
            final_run = json.loads((root / result.final_run_result_ref).read_text(encoding="utf-8"))
            self.assertIn("runs/npu-compiler-survey/reviews/round_01/reviewer_observation.json", final_run["evidence_refs"])

    def test_reviewer_observation_routes_blocked_and_failed_statuses(self) -> None:
        cases = [
            ("tool_blocked", DeepResearchReviewedRunStatus.BLOCKED),
            ("revision_required", DeepResearchReviewedRunStatus.BLOCKED),
            ("rejected", DeepResearchReviewedRunStatus.FAILED),
        ]
        for decision, expected_status in cases:
            with self.subTest(decision=decision), tempfile.TemporaryDirectory() as tempdir:
                root = Path(tempdir)

                result = run_deepresearch_academic_reviewed(
                    sample_request(),
                    workspace=root,
                    researcher_adapter=FixtureReviewedResearcherAdapter(),
                    reviewer_adapter=FixturePeerReviewerAdapter(decision),
                    reviewer_mode="fixture",
                    review_rounds=1,
                )

                self.assertEqual(result.status, expected_status)
                self.assertEqual(result.review_round_count, 1)
                self.assertEqual(result.research_state_refs, [])
                self.assertEqual(result.revision_call_refs, [])
                observation = json.loads(
                    (root / "runs/npu-compiler-survey/reviews/round_01/reviewer_observation.json").read_text(encoding="utf-8")
                )
                self.assertEqual(observation["decision"], decision)

    def test_reviewed_judged_run_does_not_judge_blocked_review(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)

            result = run_deepresearch_academic_reviewed_judged(
                sample_request(),
                workspace=root,
                researcher_adapter=FixtureReviewedResearcherAdapter(),
                reviewer_adapter=FixturePeerReviewerAdapter("tool_blocked"),
                judge_adapter=FixtureDeepResearchJudgeAdapter("accepted"),
                reviewer_mode="fixture",
                review_rounds=1,
            )

            self.assertEqual(result.status, DeepResearchReviewedRunStatus.BLOCKED)
            self.assertFalse((root / "runs/npu-compiler-survey/judge/judge_spec.json").exists())

    def test_review_rounds_cannot_exceed_intensity_budget(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            with self.assertRaisesRegex(ContractValidationError, "max_review_rounds"):
                run_deepresearch_academic_reviewed(
                    sample_request(),
                    workspace=Path(tempdir),
                    reviewer_mode="fixture",
                    review_rounds=99,
                )

    def test_reviewed_judged_run_judges_revised_draft(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)

            result = run_deepresearch_academic_reviewed_judged(
                sample_request(),
                workspace=root,
                researcher_adapter=FixtureReviewedResearcherAdapter(),
                reviewer_adapter=FixturePeerReviewerAdapter(),
                judge_adapter=FixtureDeepResearchJudgeAdapter("accepted"),
                reviewer_mode="fixture",
                review_rounds=1,
            )

            self.assertEqual(result.status, "accepted")
            self.assertTrue((root / result.final_package_ref).exists())
            self.assertTrue((root / "runs/npu-compiler-survey/packages/deepresearch_reviewed_run_result.json").exists())
            judge_spec = json.loads((root / "runs/npu-compiler-survey/judge/judge_spec.json").read_text(encoding="utf-8"))
            judge_call = json.loads((root / "runs/npu-compiler-survey/attempts/judge/piworker_call.json").read_text(encoding="utf-8"))
            judge_manifest = json.loads((root / "runs/npu-compiler-survey/policy/judge_permission_manifest.json").read_text(encoding="utf-8"))
            judge_manual = (root / "runs/npu-compiler-survey/manuals/deepresearch_judge.md").read_text(encoding="utf-8")
            self.assertIn("reviews/round_01/research_state.json", judge_spec["evidence_refs"])
            self.assertIn("reviews", judge_manifest["readable_refs"])
            self.assertIn("review/research-state trail", judge_call["objective"])
            self.assertIn("not acceptance authority", judge_manual)


if __name__ == "__main__":
    unittest.main()
