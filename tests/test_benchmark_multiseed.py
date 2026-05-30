from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tempfile
import unittest

from missionforge.benchmark import (
    AcceptanceCheck,
    AcceptanceCheckKind,
    AcceptancePack,
    AcceptanceVisibility,
    BenchmarkBudget,
    BenchmarkMode,
    BenchmarkStatus,
    BenchmarkSummary,
    BenchmarkTask,
    BenchmarkTrial,
    MultiSeedBenchmarkRunner,
)
from missionforge.json_store import JsonWorkspaceStore


class MultiSeedBenchmarkTests(unittest.TestCase):
    def test_runs_modes_seeds_joins_hidden_acceptance_and_writes_reports(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            task = _write_task(root)
            direct = _FakeModeRunner(
                BenchmarkMode.DIRECT_PIWORKER_CHAT,
                accepted_by_seed={1: True, 2: True},
                content_by_seed={1: "reusable method package", 2: "method package raw_prompt"},
                cost=3.0,
                time_ms=3000,
            )
            full_flow = _FakeModeRunner(
                BenchmarkMode.MISSIONFORGE_FULL_PRODUCT_FLOW,
                accepted_by_seed={1: True, 2: True},
                content_by_seed={1: "reusable method package", 2: "reusable method package"},
                cost=2.0,
                time_ms=2000,
            )
            runtime_only = _FakeModeRunner(
                BenchmarkMode.MISSIONFORGE_RUNTIME_ONLY,
                accepted_by_seed={1: True, 2: True},
                content_by_seed={1: "reusable method package", 2: "reusable method package"},
                comparable=False,
                cost=0.01,
                time_ms=1,
            )
            runner = MultiSeedBenchmarkRunner(
                workspace=root,
                mode_runners={
                    BenchmarkMode.DIRECT_PIWORKER_CHAT: direct,
                    BenchmarkMode.MISSIONFORGE_FULL_PRODUCT_FLOW: full_flow,
                    BenchmarkMode.MISSIONFORGE_RUNTIME_ONLY: runtime_only,
                },
            )

            result = runner.run(
                benchmark_run_id="bench-ms",
                tasks=[task],
                modes=[
                    BenchmarkMode.DIRECT_PIWORKER_CHAT,
                    BenchmarkMode.MISSIONFORGE_FULL_PRODUCT_FLOW,
                    BenchmarkMode.MISSIONFORGE_RUNTIME_ONLY,
                ],
                seeds=[1, 2],
            )

            self.assertTrue((root / result.aggregate_ref).exists())
            self.assertTrue((root / result.report_ref).exists())
            self.assertTrue((root / result.mode_comparison_ref).exists())
            self.assertTrue((root / result.table_data_ref).exists())
            self.assertEqual(len(result.hidden_acceptance_result_refs), 6)
            self.assertEqual(direct.seen_acceptance_refs, [[], []])
            self.assertEqual(full_flow.seen_acceptance_refs, [[], []])
            self.assertEqual(result.aggregate.mode_summaries["direct_piworker_chat"]["accepted_count"], 1)
            self.assertEqual(result.aggregate.mode_summaries["missionforge_full_product_flow"]["accepted_count"], 2)
            self.assertEqual(result.aggregate.mode_summaries["missionforge_runtime_only"]["non_comparable_trial_count"], 2)
            self.assertEqual(result.aggregate.mode_summaries["missionforge_runtime_only"]["comparable_accepted_count"], 0)
            self.assertEqual(result.aggregate.mode_summaries["missionforge_runtime_only"]["estimated_cost_usd"], 0.0)
            self.assertEqual(result.aggregate.mode_summaries["missionforge_runtime_only"]["total_estimated_cost_usd"], 0.02)
            self.assertEqual(result.aggregate.mode_summaries["missionforge_runtime_only"]["avg_time_to_accepted_deliverable_ms"], 0.0)
            self.assertEqual(
                result.aggregate.mode_summaries["missionforge_full_product_flow"]["avg_time_to_accepted_deliverable_ms"],
                2000.0,
            )

            comparisons = JsonWorkspaceStore(root).read_json(result.mode_comparison_ref)
            self.assertEqual(comparisons["winner_by_success_rate"], "missionforge_full_product_flow")
            self.assertEqual(comparisons["winner_by_cost_per_acceptance"], "missionforge_full_product_flow")
            self.assertEqual(comparisons["winner_by_time_to_acceptance"], "missionforge_full_product_flow")
            runtime_delta = next(
                row for row in comparisons["effect_size_rows"] if row["mode"] == "missionforge_runtime_only"
            )
            self.assertEqual(runtime_delta["comparable_accepted_count_delta"], -1)
            self.assertEqual(runtime_delta["total_accepted_count_delta"], 1)
            self.assertNotIn("accepted_count_delta", runtime_delta)
            table_data = JsonWorkspaceStore(root).read_json(result.table_data_ref)
            runtime_row = next(row for row in table_data["mode_rows"] if row["mode"] == "missionforge_runtime_only")
            self.assertEqual(runtime_row["comparable_accepted_count"], 0)
            self.assertEqual(runtime_row["total_accepted_count"], 2)
            self.assertNotIn("accepted_count", runtime_row)
            report = (root / result.report_ref).read_text(encoding="utf-8")
            self.assertIn("cost_per_accepted_deliverable_usd", report)
            self.assertIn("comparable_accepted", report)
            self.assertIn("total_accepted", report)
            self.assertIn("hidden_acceptance_failed", report)


@dataclass(frozen=True)
class _FakeRecord:
    trial: BenchmarkTrial
    summary: BenchmarkSummary
    trial_ref: str
    summary_ref: str
    metric_events_ref: str
    review_packet_ref: str


class _FakeModeRunner:
    def __init__(
        self,
        mode: BenchmarkMode,
        *,
        accepted_by_seed: dict[int, bool],
        content_by_seed: dict[int, str],
        comparable: bool = True,
        cost: float = 1.0,
        time_ms: int = 1000,
    ) -> None:
        self.mode = mode
        self.accepted_by_seed = dict(accepted_by_seed)
        self.content_by_seed = dict(content_by_seed)
        self.comparable = comparable
        self.cost = cost
        self.time_ms = time_ms
        self.seen_acceptance_refs: list[list[str]] = []

    def run_trial(
        self,
        *,
        benchmark_run_id: str,
        task: BenchmarkTask,
        seed: int,
        workspace: str | Path = ".",
        started_at: str = "1970-01-01T00:00:00Z",
        completed_at: str = "1970-01-01T00:00:00Z",
    ) -> _FakeRecord:
        self.seen_acceptance_refs.append(list(task.acceptance_refs))
        root = Path(workspace)
        trial_root = f"benchmarks/runs/{benchmark_run_id}/trials/{task.task_id}/{self.mode.value}/seed-{seed}"
        workspace_ref = f"{trial_root}/workspace"
        trial_ref = f"{trial_root}/trial.json"
        summary_ref = f"{trial_root}/summary.json"
        metric_events_ref = f"{trial_root}/metric_events.jsonl"
        review_packet_ref = f"{trial_root}/review_packet.json"
        artifact_ref = f"{workspace_ref}/package/SKILL.md"
        package_dir = root / workspace_ref / "package"
        package_dir.mkdir(parents=True, exist_ok=True)
        (package_dir / "SKILL.md").write_text(self.content_by_seed[seed], encoding="utf-8")
        accepted = self.accepted_by_seed[seed]
        summary = BenchmarkSummary(
            task_id=task.task_id,
            mode=self.mode,
            seed=seed,
            accepted=accepted,
            status=BenchmarkStatus.ACCEPTED if accepted else BenchmarkStatus.FAILED,
            comparable=self.comparable,
            generic_verifier_passed=accepted,
            hidden_acceptance_passed=False,
            product_gate_status="product_grade" if self.mode == BenchmarkMode.MISSIONFORGE_FULL_PRODUCT_FLOW else "",
            time_to_accepted_deliverable_ms=self.time_ms if accepted else 0,
            wall_duration_ms=self.time_ms,
            estimated_cost_usd=self.cost,
            total_tokens=1000,
            tool_call_count=2,
            artifact_refs=[artifact_ref] if accepted else [],
            metric_events_ref=metric_events_ref,
        )
        trial = BenchmarkTrial(
            benchmark_run_id=benchmark_run_id,
            task_id=task.task_id,
            mode=self.mode,
            seed=seed,
            workspace_ref=workspace_ref,
            started_at=started_at,
            completed_at=completed_at,
            status=BenchmarkStatus.ACCEPTED if accepted else BenchmarkStatus.FAILED,
            artifact_refs=list(summary.artifact_refs),
            metric_events_ref=metric_events_ref,
            summary_ref=summary_ref,
            review_packet_ref=review_packet_ref,
        )
        store = JsonWorkspaceStore(root)
        store.write_json(trial_ref, trial.to_dict())
        store.write_json(summary_ref, summary.to_dict())
        store.write_jsonl(metric_events_ref, [])
        store.write_json(
            review_packet_ref,
            {
                "schema_version": "missionforge.benchmark_review_packet.v1",
                "task_id": task.task_id,
                "seed": seed,
                "artifact_refs": list(summary.artifact_refs),
                "summary_ref": summary_ref,
                "metric_events_ref": metric_events_ref,
            },
        )
        return _FakeRecord(
            trial=trial,
            summary=summary,
            trial_ref=trial_ref,
            summary_ref=summary_ref,
            metric_events_ref=metric_events_ref,
            review_packet_ref=review_packet_ref,
        )


def _write_task(root: Path) -> BenchmarkTask:
    task_dir = root / "benchmarks/tasks/task-ms-001"
    task_dir.mkdir(parents=True, exist_ok=True)
    (task_dir / "user_statement.txt").write_text("Build a reusable local skill package.", encoding="utf-8")
    pack = AcceptancePack(
        pack_id="hidden",
        task_id="task-ms-001",
        visibility=AcceptanceVisibility.HIDDEN,
        checks=[
            AcceptanceCheck(
                check_id="contains-reusable",
                kind=AcceptanceCheckKind.FILE_CONTAINS,
                ref="package/SKILL.md",
                expected_text="reusable",
            ),
            AcceptanceCheck(
                check_id="no-raw-prompt",
                kind=AcceptanceCheckKind.FILE_NOT_CONTAINS,
                ref="package/SKILL.md",
                forbidden_text="raw_prompt",
            ),
        ],
    )
    JsonWorkspaceStore(root).write_json("benchmarks/tasks/task-ms-001/acceptance/hidden_checks.json", pack.to_dict())
    return BenchmarkTask(
        task_id="task-ms-001",
        task_family="engineering_method_skill",
        difficulty="medium",
        initial_user_text_ref="benchmarks/tasks/task-ms-001/user_statement.txt",
        expected_output_refs=["package/SKILL.md"],
        budget=BenchmarkBudget(max_wall_minutes=10, max_total_tokens=50000, max_cost_usd=2.0, max_user_turns=4),
        acceptance_refs=["benchmarks/tasks/task-ms-001/acceptance/hidden_checks.json"],
    )


if __name__ == "__main__":
    unittest.main()
