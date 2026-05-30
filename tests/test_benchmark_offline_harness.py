from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from missionforge.benchmark import (
    BenchmarkBudget,
    BenchmarkMode,
    BenchmarkTask,
    OfflineBenchmarkHarness,
    OfflineTrialOutcome,
)
from missionforge.benchmark.contracts import BenchmarkAggregate, BenchmarkSummary
from missionforge.contracts import ContractValidationError
from missionforge.metrics import MetricEvent


class OfflineBenchmarkHarnessTests(unittest.TestCase):
    def test_records_trial_metric_events_and_deterministic_aggregate(self) -> None:
        task = sample_task()
        with TemporaryDirectory() as tmpdir:
            harness = OfflineBenchmarkHarness(tmpdir)
            task_ref = harness.write_task(task)
            self.assertEqual(task_ref, "benchmarks/tasks/task-001/task.json")

            first = harness.record_trial(
                benchmark_run_id="bench-001",
                task=task,
                mode=BenchmarkMode.DIRECT_PIWORKER_CHAT,
                seed=1,
                outcome=OfflineTrialOutcome(
                    accepted=True,
                    artifact_refs=["package/SKILL.md"],
                    metric_values={
                        "time_to_accepted_deliverable_ms": 600000,
                        "wall_duration_ms": 600000,
                        "estimated_cost_usd": 2.0,
                        "cost_source": "pricing_table",
                        "pricing_table_id": "fixture-prices",
                        "total_tokens": 1000,
                        "tool_call_count": 3,
                        "user_turn_count": 2,
                    },
                ),
            )
            second = harness.record_trial(
                benchmark_run_id="bench-001",
                task=task,
                mode=BenchmarkMode.MISSIONFORGE_RUNTIME_ONLY,
                seed=1,
                outcome=OfflineTrialOutcome(
                    accepted=False,
                    comparable=True,
                    artifact_refs=["package/SKILL.md"],
                    metric_values={
                        "wall_duration_ms": 900000,
                        "estimated_cost_usd": 3.0,
                        "cost_source": "pricing_table",
                        "pricing_table_id": "fixture-prices",
                        "total_tokens": 1500,
                        "tool_call_count": 5,
                        "repair_count": 1,
                    },
                    failure_taxonomy=["hidden_acceptance_failed"],
                ),
            )
            aggregate_ref, report_ref, aggregate = harness.write_aggregate(
                benchmark_run_id="bench-001",
                records=[second, first],
            )

            root = Path(tmpdir)
            self.assertTrue((root / first.trial_ref).is_file())
            self.assertTrue((root / first.summary_ref).is_file())
            self.assertTrue((root / first.metric_events_ref).is_file())
            self.assertTrue((root / first.review_packet_ref).is_file())
            self.assertTrue((root / aggregate_ref).is_file())
            self.assertTrue((root / report_ref).is_file())

            summary_payload = json.loads((root / first.summary_ref).read_text(encoding="utf-8"))
            self.assertEqual(BenchmarkSummary.from_dict(summary_payload), first.summary)

            metric_payload = json.loads((root / first.metric_events_ref).read_text(encoding="utf-8").splitlines()[0])
            metric_event = MetricEvent.from_dict(metric_payload)
            self.assertEqual(metric_event.namespace, "missionforge.harness")
            self.assertEqual(metric_event.values["accepted"], True)
            self.assertEqual(metric_event.source_ref, first.summary_ref)
            self.assertEqual(metric_event.run_ref, first.trial_ref)

            review_packet = json.loads((root / first.review_packet_ref).read_text(encoding="utf-8"))
            self.assertNotIn("mode", review_packet)
            self.assertEqual(review_packet["artifact_refs"], ["package/SKILL.md"])

            aggregate_payload = json.loads((root / aggregate_ref).read_text(encoding="utf-8"))
            self.assertEqual(BenchmarkAggregate.from_dict(aggregate_payload), aggregate)
            self.assertEqual(aggregate.trial_count, 2)
            self.assertEqual(aggregate.accepted_count, 1)
            self.assertEqual(aggregate.failure_taxonomy_counts["hidden_acceptance_failed"], 1)
            self.assertEqual(
                aggregate.mode_summaries["direct_piworker_chat"]["cost_per_accepted_deliverable_usd"],
                2.0,
            )

            report = (root / report_ref).read_text(encoding="utf-8")
            self.assertIn("# MissionForge Benchmark Report: bench-001", report)
            self.assertIn("direct_piworker_chat", report)
            self.assertNotIn("raw transcript", report.lower())

            aggregate_ref_again, report_ref_again, aggregate_again = harness.write_aggregate(
                benchmark_run_id="bench-001",
                records=[first, second],
            )
            self.assertEqual(aggregate_ref_again, aggregate_ref)
            self.assertEqual(report_ref_again, report_ref)
            self.assertEqual(aggregate_again.to_dict(), aggregate.to_dict())
            self.assertEqual((root / report_ref_again).read_text(encoding="utf-8"), report)

    def test_harness_rejects_unsafe_metric_payloads(self) -> None:
        with TemporaryDirectory() as tmpdir:
            harness = OfflineBenchmarkHarness(tmpdir)
            with self.assertRaises(ContractValidationError):
                harness.record_trial(
                    benchmark_run_id="bench-001",
                    task=sample_task(),
                    mode=BenchmarkMode.OFFLINE_HARNESS,
                    seed=1,
                    outcome=OfflineTrialOutcome(
                        accepted=False,
                        metric_values={"provider_payload": "not allowed"},
                    ),
                )


def sample_task() -> BenchmarkTask:
    return BenchmarkTask(
        task_id="task-001",
        task_family="skillfoundry",
        difficulty="medium",
        initial_user_text_ref="benchmarks/tasks/task-001/user_statement.txt",
        allowed_source_refs=[],
        expected_output_refs=["package/SKILL.md"],
        budget=BenchmarkBudget(
            max_wall_minutes=45,
            max_total_tokens=250000,
            max_cost_usd=10.0,
            max_user_turns=6,
        ),
        acceptance_refs=["benchmarks/tasks/task-001/acceptance/hidden_checks.json"],
    )


if __name__ == "__main__":
    unittest.main()
