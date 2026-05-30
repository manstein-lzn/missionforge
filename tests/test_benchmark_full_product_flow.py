from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from missionforge.benchmark import (
    BenchmarkBudget,
    BenchmarkMode,
    BenchmarkStatus,
    BenchmarkSummary,
    BenchmarkTask,
    MissionForgeFullProductFlowBenchmarkRunner,
    ProductGateOutcome,
)
from missionforge.contracts import ContractValidationError
from missionforge.frontdesk import CompilerReadiness, ProductInquiryProfile
from missionforge.product_integration import ProductCompileResult, ProductCompileStatus
from tests.frontdesk_llm_fixtures import ScriptedFrontDeskPiWorker


class FullProductFlowBenchmarkTests(unittest.TestCase):
    def test_fails_closed_and_writes_refs_first_artifacts_without_frontdesk_worker(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            _write_user_text(root, "I need this turned into a reusable product package, but I only know the pain.")
            task = _task()
            runner = MissionForgeFullProductFlowBenchmarkRunner(
                product_integration=_ClarifyingProductIntegration(),
            )

            record = runner.run_trial(
                benchmark_run_id="bench-full-001",
                task=task,
                seed=1,
                workspace=root,
            )

            self.assertEqual(record.trial.mode, BenchmarkMode.MISSIONFORGE_FULL_PRODUCT_FLOW)
            self.assertEqual(record.summary.status, BenchmarkStatus.FAILED)
            self.assertFalse(record.summary.accepted)
            self.assertEqual(record.summary.product_compile_status, ProductCompileStatus.FAILED_CLOSED.value)
            self.assertIn("frontdesk_missing_llm_artifact", record.summary.failure_taxonomy)
            self.assertTrue((root / record.product_compile_result_ref).exists())
            self.assertTrue((root / record.product_gate_outcome_ref).exists())
            self.assertTrue((root / record.full_result_ref).exists())
            self.assertTrue((root / record.summary_ref).exists())
            self.assertTrue((root / record.metric_events_ref).exists())
            self.assertEqual(BenchmarkSummary.from_dict(json.loads((root / record.summary_ref).read_text())), record.summary)

            public_payload = "\n".join(
                [
                    (root / record.summary_ref).read_text(encoding="utf-8"),
                    (root / record.metric_events_ref).read_text(encoding="utf-8"),
                    (root / record.review_packet_ref).read_text(encoding="utf-8"),
                ]
            )
            self.assertNotIn("I need this turned into", public_payload)
            self.assertNotIn("raw_prompt", public_payload)
            self.assertNotIn("provider_payload", public_payload)

    def test_product_gate_outcome_round_trip_rejects_unsafe_refs(self) -> None:
        outcome = ProductGateOutcome(
            product_id="example_product",
            status="product_grade",
            result_ref="qa/product_gate.json",
            evidence_refs=["qa/checks.json"],
            artifact_refs=["package/SKILL.md"],
            product_acceptance_coverage_passed=True,
        )

        self.assertEqual(ProductGateOutcome.from_dict(outcome.to_dict()), outcome)

        payload = outcome.to_dict()
        payload["artifact_refs"] = ["../outside"]
        with self.assertRaises(ContractValidationError):
            ProductGateOutcome.from_dict(payload)

    def test_product_gate_outcome_requires_acceptance_coverage(self) -> None:
        outcome = ProductGateOutcome(
            product_id="example_product",
            status="product_grade",
            product_acceptance_coverage_passed=False,
            blocking_finding_count=0,
        )

        self.assertFalse(outcome.passed)

    def test_frontdesk_schema_validation_failure_is_not_reported_as_missing_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            _write_user_text(root, "Turn my vague idea into a product-ready prompt-only skill.")
            task = _task()
            runner = MissionForgeFullProductFlowBenchmarkRunner(
                product_integration=_ClarifyingProductIntegration(),
                frontdesk_worker=_schema_mismatch_frontdesk_worker(session_id="fd-task-full-001-seed-1"),
            )

            record = runner.run_trial(
                benchmark_run_id="bench-full-schema",
                task=task,
                seed=1,
                workspace=root,
            )

            self.assertFalse(record.summary.accepted)
            self.assertIn("frontdesk_schema_validation_failed", record.summary.failure_taxonomy)
            self.assertNotIn("frontdesk_missing_llm_artifact", record.summary.failure_taxonomy)
            full_result = json.loads((root / record.full_result_ref).read_text(encoding="utf-8"))
            self.assertEqual(full_result["failure_stage"], "frontdesk_grill")
            self.assertEqual(full_result["failure_error_type"], "ContractValidationError")


class _ClarifyingProductIntegration:
    product_id = "example_product"

    def inquiry_profile(self) -> ProductInquiryProfile:
        return ProductInquiryProfile(
            product_id=self.product_id,
            version="v1",
            display_name="Example Product",
            slots=[],
            compiler_readiness=CompilerReadiness(blocking_slot_ids=[]),
        )

    def compile_intent(self, bundle, *, workspace: str | Path = ".") -> ProductCompileResult:
        return ProductCompileResult(
            product_id=self.product_id,
            status=ProductCompileStatus.NEEDS_CLARIFICATION,
            intent_bundle_ref=bundle.intent_bundle_ref,
            missing_slot_ids=["goal"],
            reason="example product needs a goal",
        )


def _task() -> BenchmarkTask:
    return BenchmarkTask(
        task_id="task-full-001",
        task_family="example",
        difficulty="small",
        initial_user_text_ref="benchmarks/tasks/task-full-001/user_statement.txt",
        expected_output_refs=["package/SKILL.md"],
        budget=BenchmarkBudget(
            max_wall_minutes=10,
            max_total_tokens=50000,
            max_cost_usd=2.0,
            max_user_turns=4,
        ),
        acceptance_refs=["benchmarks/tasks/task-full-001/acceptance/hidden_checks.json"],
    )


def _write_user_text(root: Path, text: str) -> None:
    path = root / "benchmarks/tasks/task-full-001/user_statement.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _schema_mismatch_frontdesk_worker(*, session_id: str) -> ScriptedFrontDeskPiWorker:
    return ScriptedFrontDeskPiWorker(
        {
            "frontdesk/decision_tree.json": {
                "schema_version": "missionforge.frontdesk_decision_tree.v1",
                "session_id": session_id,
                "decisions": [
                    {
                        "decision_id": "D-output",
                        "topic": "desired_output",
                        "status": "confirmed",
                        "current_hypothesis": "Create a prompt-only skill.",
                        "options": [
                            {
                                "option_id": "O-skill",
                                "summary": "Create the requested prompt-only skill.",
                            }
                        ],
                        "blocking": True,
                        "source_refs": ["frontdesk/session.json"],
                        "chosen_option_id": "O-skill",
                    }
                ],
            },
            "frontdesk/core_need_brief.json": {
                "schema_version": "missionforge.frontdesk_core_need_brief.v1",
                "session_id": session_id,
                "core_pain": "The user needs a vague idea shaped into a reusable skill.",
                "target_users": ["skill_user"],
                "usage_moment": "Before implementation.",
                "deliverable_type": "prompt-only skill",
                "desired_outcome": "Create a prompt-only skill.",
                "success_signals": ["The skill gives clear guidance."],
                "constraints": [],
                "non_goals": ["Do not include private project context."],
                "source_refs": ["frontdesk/session.json"],
            },
            "frontdesk/need_grilling_report.json": {
                "schema_version": "missionforge.frontdesk_need_grilling_report.v1",
                "session_id": session_id,
                "readiness": "core_need_ready",
                "observations": ["The user asks for a skill."],
                "inferences": ["A prompt-only skill is the target."],
                "confirmed_requirements": ["Create a prompt-only skill."],
                "open_decision_ids": [],
                "next_question": {
                    "question_id": "Q-format",
                    "inference": "The final format is flexible.",
                    "recommended_answer": "Use a compact structured template.",
                    "question": "Which output format should the skill prefer?",
                    "why_this_matters": "It tunes the artifact style.",
                    "blocks_freeze": False,
                    "expected_answer_type": "choice_or_free_text",
                    "related_decision_ids": [],
                    "choices": [
                        {
                            "choice_id": "compact",
                            "summary": "Use a compact template.",
                        }
                    ],
                },
                "decision_tree_ref": "frontdesk/decision_tree.json",
                "core_need_brief_ref": "frontdesk/core_need_brief.json",
            },
        }
    )


if __name__ == "__main__":
    unittest.main()
