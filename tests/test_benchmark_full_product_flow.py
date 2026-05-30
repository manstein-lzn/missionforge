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


if __name__ == "__main__":
    unittest.main()
