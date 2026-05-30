from __future__ import annotations

import unittest

from missionforge.benchmark import (
    BenchmarkAggregate,
    BenchmarkBudget,
    BenchmarkMode,
    BenchmarkStatus,
    BenchmarkSummary,
    BenchmarkTask,
    BenchmarkTrial,
    OfflineTrialOutcome,
)
from missionforge.benchmark.contracts import build_aggregate
from missionforge.contracts import ContractValidationError


class BenchmarkContractTests(unittest.TestCase):
    def test_task_trial_summary_and_aggregate_round_trip(self) -> None:
        task = sample_task()
        self.assertEqual(BenchmarkTask.from_dict(task.to_dict()), task)

        trial = BenchmarkTrial(
            benchmark_run_id="bench-001",
            task_id=task.task_id,
            mode=BenchmarkMode.DIRECT_PIWORKER_CHAT,
            seed=1,
            workspace_ref="benchmarks/runs/bench-001/trials/task-001/direct_piworker_chat/seed-1/workspace",
            started_at="1970-01-01T00:00:00Z",
            completed_at="1970-01-01T00:00:00Z",
            status=BenchmarkStatus.ACCEPTED,
            artifact_refs=["package/SKILL.md"],
            metric_events_ref="benchmarks/runs/bench-001/trials/task-001/direct_piworker_chat/seed-1/metric_events.jsonl",
            summary_ref="benchmarks/runs/bench-001/trials/task-001/direct_piworker_chat/seed-1/summary.json",
            review_packet_ref="benchmarks/runs/bench-001/trials/task-001/direct_piworker_chat/seed-1/review_packet.json",
        )
        self.assertEqual(BenchmarkTrial.from_dict(trial.to_dict()), trial)

        summary = sample_summary()
        self.assertEqual(BenchmarkSummary.from_dict(summary.to_dict()), summary)

        aggregate = build_aggregate(
            benchmark_run_id="bench-001",
            summaries=[summary],
            summary_refs=["benchmarks/runs/bench-001/trials/task-001/direct_piworker_chat/seed-1/summary.json"],
        )
        self.assertEqual(BenchmarkAggregate.from_dict(aggregate.to_dict()), aggregate)
        self.assertEqual(aggregate.mode_summaries["direct_piworker_chat"]["success_rate_within_budget"], 1.0)

    def test_rejects_unsafe_refs(self) -> None:
        payload = sample_task().to_dict()
        payload["initial_user_text_ref"] = "../outside.txt"
        with self.assertRaises(ContractValidationError):
            BenchmarkTask.from_dict(payload)

        summary = sample_summary().to_dict()
        summary["artifact_refs"] = ["/tmp/outside.txt"]
        with self.assertRaises(ContractValidationError):
            BenchmarkSummary.from_dict(summary)

    def test_rejects_raw_metric_payloads_and_unknown_raw_fields(self) -> None:
        with self.assertRaises(ContractValidationError):
            OfflineTrialOutcome(
                accepted=False,
                status=BenchmarkStatus.FAILED,
                metric_values={"raw_prompt": "do the thing"},
            ).validate()

        with self.assertRaises(ContractValidationError):
            OfflineTrialOutcome.from_dict(
                {
                    "schema_version": "missionforge.offline_trial_outcome.v1",
                    "accepted": False,
                    "metric_values": {"debug": {"raw_prompt": "do the thing"}},
                }
            )

        with self.assertRaises(ContractValidationError):
            BenchmarkAggregate.from_dict(
                {
                    "schema_version": "missionforge.benchmark_aggregate.v1",
                    "benchmark_run_id": "bench-001",
                    "summary_refs": [],
                    "mode_summaries": {
                        "direct_piworker_chat": {"debug": {"provider_payload": "not allowed"}}
                    },
                    "failure_taxonomy_counts": {},
                    "task_count": 0,
                    "trial_count": 0,
                    "accepted_count": 0,
                    "comparable_trial_count": 0,
                }
            )

        payload = sample_summary().to_dict()
        payload["provider_payload"] = {"content": "not allowed"}
        with self.assertRaises(ContractValidationError):
            BenchmarkSummary.from_dict(payload)

    def test_aggregate_is_deterministic(self) -> None:
        left = sample_summary(seed=2, mode=BenchmarkMode.MISSIONFORGE_RUNTIME_ONLY, accepted=False)
        right = sample_summary(seed=1, mode=BenchmarkMode.DIRECT_PIWORKER_CHAT, accepted=True)
        refs = [
            "benchmarks/runs/bench-001/trials/task-001/missionforge_runtime_only/seed-2/summary.json",
            "benchmarks/runs/bench-001/trials/task-001/direct_piworker_chat/seed-1/summary.json",
        ]

        first = build_aggregate(benchmark_run_id="bench-001", summaries=[left, right], summary_refs=refs)
        second = build_aggregate(benchmark_run_id="bench-001", summaries=[right, left], summary_refs=list(reversed(refs)))

        self.assertEqual(first.to_dict(), second.to_dict())


def sample_task() -> BenchmarkTask:
    return BenchmarkTask(
        task_id="task-001",
        task_family="skillfoundry",
        difficulty="medium",
        initial_user_text_ref="benchmarks/tasks/task-001/user_statement.txt",
        allowed_source_refs=["benchmarks/tasks/task-001/source_manifest.json"],
        expected_output_refs=["package/SKILL.md"],
        budget=BenchmarkBudget(
            max_wall_minutes=45,
            max_total_tokens=250000,
            max_cost_usd=10.0,
            max_user_turns=6,
        ),
        acceptance_refs=["benchmarks/tasks/task-001/acceptance/hidden_checks.json"],
    )


def sample_summary(
    *,
    seed: int = 1,
    mode: BenchmarkMode = BenchmarkMode.DIRECT_PIWORKER_CHAT,
    accepted: bool = True,
) -> BenchmarkSummary:
    return BenchmarkSummary(
        task_id="task-001",
        mode=mode,
        seed=seed,
        accepted=accepted,
        status=BenchmarkStatus.ACCEPTED if accepted else BenchmarkStatus.FAILED,
        comparable=True,
        hidden_acceptance_passed=accepted,
        time_to_accepted_deliverable_ms=600000 if accepted else 0,
        wall_duration_ms=600000,
        estimated_cost_usd=2.5,
        total_tokens=1000,
        tool_call_count=4,
        repair_count=0,
        user_turn_count=2,
        failure_taxonomy=[] if accepted else ["hidden_acceptance_failed"],
        artifact_refs=["package/SKILL.md"],
        metric_events_ref=f"benchmarks/runs/bench-001/trials/task-001/{mode.value}/seed-{seed}/metric_events.jsonl",
    )


if __name__ == "__main__":
    unittest.main()
