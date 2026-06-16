from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from missionforge.contracts import ContractValidationError
from missionforge_deepresearch import (
    DeepResearchReviewedRunStatus,
    FixtureDeepResearchJudgeAdapter,
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
            self.assertEqual(result.research_state_refs, ["runs/npu-compiler-survey/reviews/round_01/research_state.json"])

            run_root = root / "runs/npu-compiler-survey"
            reviewer_call = json.loads((run_root / "attempts/reviewer/round_01/piworker_call.json").read_text(encoding="utf-8"))
            revision_call = json.loads((run_root / "attempts/researcher/round_01/piworker_call.json").read_text(encoding="utf-8"))
            state = json.loads((run_root / "reviews/round_01/research_state.json").read_text(encoding="utf-8"))
            final_run = json.loads((root / result.final_run_result_ref).read_text(encoding="utf-8"))

            self.assertEqual(reviewer_call["role"], "judge_piworker")
            self.assertEqual(reviewer_call["metadata"]["authority"], "guidance_only")
            self.assertIn("reviews/round_01/next_research_directive.md", revision_call["visible_refs"])
            self.assertIn("First update sources/source_packet.json", revision_call["objective"])
            self.assertIn("reviews/round_01/research_state.json", revision_call["expected_output_refs"])
            self.assertEqual(state["round_index"], 1)
            self.assertEqual(final_run["status"], "draft_ready")
            self.assertNotIn("\"accepted\"", (root / result.reviewed_run_result_ref).read_text(encoding="utf-8"))

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
            self.assertIn("reviews/round_01/research_state.json", judge_spec["evidence_refs"])


if __name__ == "__main__":
    unittest.main()
