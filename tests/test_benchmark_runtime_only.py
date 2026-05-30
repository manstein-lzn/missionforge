from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from missionforge.benchmark import (
    BenchmarkBudget,
    BenchmarkMode,
    BenchmarkStatus,
    BenchmarkSummary,
    BenchmarkTask,
    BenchmarkPricingTable,
    MissionForgeRuntimeOnlyBenchmarkRunner,
    ModelTokenPrice,
    RUNTIME_ONLY_RESULT_SCHEMA_VERSION,
    RuntimeOnlyConfig,
)
from missionforge.metrics import MetricEvent
from missionforge.work_unit import ExecutionReport, WorkerResult
from missionforge.workers import WorkerAdapterResult
from tests.test_ir import sample_mission_payload


RUNTIME_MAIN = Path(__file__).resolve().parents[1] / "workers" / "pi-agent-runtime" / "dist" / "main.js"


class RuntimeOnlyBenchmarkRunnerTests(unittest.TestCase):
    def test_records_runtime_only_trial_summary_metric_event_and_review_packet(self) -> None:
        task = sample_task()
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            mission_ir_ref = "benchmarks/tasks/task-001/mission_ir.json"
            _write_json(root / mission_ir_ref, sample_mission_payload())

            record = MissionForgeRuntimeOnlyBenchmarkRunner(
                RuntimeOnlyConfig(max_attempts=1),
                worker=_AllOutputsWorker(),
            ).run_trial(
                benchmark_run_id="bench-001",
                task=task,
                mission_ir_ref=mission_ir_ref,
                seed=1,
                workspace=root,
            )

            self.assertEqual(record.trial.mode, BenchmarkMode.MISSIONFORGE_RUNTIME_ONLY)
            self.assertEqual(record.trial.status, BenchmarkStatus.ACCEPTED)
            self.assertEqual(record.summary.accepted, True)
            self.assertEqual(record.summary.generic_verifier_passed, True)
            self.assertEqual(record.summary.repair_count, 0)
            self.assertEqual(record.summary.total_tokens, 123)
            self.assertEqual(record.summary.input_tokens, 100)
            self.assertEqual(record.summary.output_tokens, 23)
            self.assertEqual(record.summary.cache_read_tokens, 7)
            self.assertEqual(record.summary.cache_write_tokens, 3)
            self.assertEqual(record.summary.tool_call_count, 2)
            self.assertEqual(record.summary.estimated_cost_usd, 0.42)
            self.assertEqual(record.summary.provider_reported_cost_usd, 0.42)
            self.assertEqual(record.summary.cost_source, "provider_reported")
            self.assertEqual(
                record.summary.artifact_refs,
                [
                    "benchmarks/runs/bench-001/trials/task-001/missionforge_runtime_only/seed-1/workspace/package/SKILL.md"
                ],
            )

            runtime_result = json.loads((root / record.runtime_result_ref).read_text(encoding="utf-8"))
            self.assertEqual(runtime_result["schema_version"], RUNTIME_ONLY_RESULT_SCHEMA_VERSION)
            self.assertEqual(runtime_result["mission_ir_ref"], mission_ir_ref)
            self.assertEqual(runtime_result["mission_result"]["status"], "completed_verified")

            summary_payload = json.loads((root / record.summary_ref).read_text(encoding="utf-8"))
            self.assertEqual(BenchmarkSummary.from_dict(summary_payload), record.summary)
            metric_payload = json.loads((root / record.metric_events_ref).read_text(encoding="utf-8").splitlines()[0])
            metric_event = MetricEvent.from_dict(metric_payload)
            self.assertEqual(metric_event.namespace, "missionforge.harness")
            self.assertEqual(metric_event.values["accepted"], True)
            self.assertEqual(metric_event.values["generic_verifier_passed"], True)
            self.assertEqual(metric_event.source_ref, record.summary_ref)
            self.assertEqual(metric_event.run_ref, record.trial_ref)

            review_packet = json.loads((root / record.review_packet_ref).read_text(encoding="utf-8"))
            self.assertNotIn("mode", review_packet)
            self.assertEqual(review_packet["mission_ir_ref"], mission_ir_ref)
            self.assertEqual(review_packet["runtime_result_ref"], record.runtime_result_ref)
            self.assertEqual(review_packet["verification_status"], "completed_verified")
            self.assertEqual(review_packet["repair_count"], 0)
            self.assertTrue(review_packet["runtime_metric_events_ref"].endswith("runs/run-sample-mission/metrics/events.jsonl"))

    def test_runtime_only_captures_repair_count_from_runtime_metrics(self) -> None:
        task = sample_task()
        worker = _RepairableWorker()
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            mission_ir_ref = "benchmarks/tasks/task-001/mission_ir.json"
            _write_json(root / mission_ir_ref, sample_mission_payload())

            record = MissionForgeRuntimeOnlyBenchmarkRunner(
                RuntimeOnlyConfig(max_attempts=2),
                worker=worker,
            ).run_trial(
                benchmark_run_id="bench-001",
                task=task,
                mission_ir_ref=mission_ir_ref,
                seed=1,
                workspace=root,
            )

            self.assertEqual(record.summary.accepted, True)
            self.assertEqual(record.summary.generic_verifier_passed, True)
            self.assertEqual(record.summary.repair_count, 1)
            self.assertEqual(record.mission_result.metrics["attempt_count"], 2)
            self.assertEqual(worker.calls, ["initial", "with_repair", "repair"])
            review_packet = json.loads((root / record.review_packet_ref).read_text(encoding="utf-8"))
            self.assertEqual(review_packet["repair_count"], 1)

    def test_runtime_only_pricing_table_cost_projection_uses_worker_model(self) -> None:
        task = sample_task()
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            mission_ir_ref = "benchmarks/tasks/task-001/mission_ir.json"
            _write_json(root / mission_ir_ref, sample_mission_payload())

            record = MissionForgeRuntimeOnlyBenchmarkRunner(
                RuntimeOnlyConfig(max_attempts=1, pricing_table=_pricing_table()),
                worker=_AllOutputsWorker(model="pi-test-model"),
            ).run_trial(
                benchmark_run_id="bench-001",
                task=task,
                mission_ir_ref=mission_ir_ref,
                seed=1,
                workspace=root,
            )

            self.assertEqual(record.summary.cost_source, "pricing_table")
            self.assertEqual(record.summary.pricing_table_id, "pi-test-2026-05-30")
            self.assertEqual(record.summary.provider_reported_cost_usd, 0.42)
            self.assertAlmostEqual(record.summary.estimated_cost_usd, 0.0003367)

    def test_runtime_only_bypasses_user_text_and_frontdesk_flow(self) -> None:
        task = sample_task(initial_user_text_ref="benchmarks/tasks/task-001/nonexistent_user_text.txt")
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            mission_ir_ref = "benchmarks/tasks/task-001/mission_ir.json"
            _write_json(root / mission_ir_ref, sample_mission_payload())

            record = MissionForgeRuntimeOnlyBenchmarkRunner(
                RuntimeOnlyConfig(max_attempts=1),
                worker=_AllOutputsWorker(),
            ).run_trial(
                benchmark_run_id="bench-001",
                task=task,
                mission_ir_ref=mission_ir_ref,
                seed=1,
                workspace=root,
            )

            self.assertEqual(record.summary.accepted, True)
            public_text = "".join(
                (root / ref).read_text(encoding="utf-8")
                for ref in [record.runtime_result_ref, record.summary_ref, record.review_packet_ref]
            )
            for forbidden in ("FrontDesk", "ProductGate", "raw conversation"):
                self.assertNotIn(forbidden, public_text)

    @unittest.skipUnless(RUNTIME_MAIN.is_file(), "pi-agent-runtime dist/main.js is not built")
    def test_default_pi_agent_faux_runtime_smoke_writes_runtime_only_summary(self) -> None:
        task = sample_task()
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            mission_ir_ref = "benchmarks/tasks/task-001/mission_ir.json"
            _write_json(root / mission_ir_ref, sample_mission_payload())

            record = MissionForgeRuntimeOnlyBenchmarkRunner(RuntimeOnlyConfig(max_attempts=1)).run_trial(
                benchmark_run_id="bench-smoke",
                task=task,
                mission_ir_ref=mission_ir_ref,
                seed=1,
                workspace=root,
            )

            self.assertEqual(record.summary.accepted, True)
            self.assertEqual(record.trial.status, BenchmarkStatus.ACCEPTED)
            self.assertEqual(record.summary.generic_verifier_passed, True)
            self.assertGreater(record.summary.total_tokens, 0)
            self.assertEqual(record.summary.repair_count, 0)
            self.assertTrue((root / record.runtime_result_ref).is_file())
            self.assertTrue((root / record.review_packet_ref).is_file())


class _AllOutputsWorker:
    def __init__(self, *, model: str | None = None) -> None:
        self.model = model

    def run(self, work_unit, *, workspace=".", evidence_store=None):
        produced = []
        for output_ref in work_unit.expected_outputs:
            artifact = Path(workspace, output_ref)
            artifact.parent.mkdir(parents=True, exist_ok=True)
            artifact.write_text("# runtime-only\n", encoding="utf-8")
            produced.append(output_ref)
        report = ExecutionReport(
            report_id=f"R-{work_unit.work_unit_id}",
            work_unit_id=work_unit.work_unit_id,
            status="completed",
            produced_artifacts=produced,
            changed_refs=produced,
            evidence_refs=[],
            worker_claims=["done"],
            metrics={
                "tool_call_count": 2,
                "total_tokens": 123,
                "input_tokens": 100,
                "output_tokens": 23,
                "cache_read_tokens": 7,
                "cache_write_tokens": 3,
                "provider_reported_cost_usd": 0.42,
                "time_to_first_artifact_ms": 9,
                "metrics_ref": f"attempts/{work_unit.work_unit_id}/pi_agent_metrics.json",
                "tool_latency_ms_by_name": {"write": 7},
            },
        )
        if self.model:
            report.metrics["model"] = self.model
        return WorkerAdapterResult(
            execution_report=report,
            worker_result=WorkerResult(
                status="completed",
                execution_report_ref=f"attempts/{work_unit.work_unit_id}/execution_report.json",
            ),
        )


class _RepairableWorker:
    def __init__(self, *, repaired: bool = False, calls: list[str] | None = None) -> None:
        self.repaired = repaired
        self.calls = calls if calls is not None else []

    def run(self, work_unit, *, workspace=".", evidence_store=None):
        produced = []
        self.calls.append("repair" if self.repaired else "initial")
        if self.repaired:
            for output_ref in work_unit.expected_outputs:
                artifact = Path(workspace, output_ref)
                artifact.parent.mkdir(parents=True, exist_ok=True)
                artifact.write_text("# repaired runtime-only\n", encoding="utf-8")
                produced.append(output_ref)
        report = ExecutionReport(
            report_id=f"R-{work_unit.work_unit_id}",
            work_unit_id=work_unit.work_unit_id,
            status="completed",
            produced_artifacts=produced,
            changed_refs=produced,
            evidence_refs=[],
            worker_claims=["done"],
            metrics={"repaired": self.repaired},
        )
        return WorkerAdapterResult(
            execution_report=report,
            worker_result=WorkerResult(
                status="completed",
                execution_report_ref=f"attempts/{work_unit.work_unit_id}/execution_report.json",
            ),
        )

    def with_repair(self, **kwargs):
        self.calls.append("with_repair")
        return _RepairableWorker(repaired=True, calls=self.calls)


def sample_task(*, initial_user_text_ref: str = "benchmarks/tasks/task-001/user_statement.txt") -> BenchmarkTask:
    return BenchmarkTask(
        task_id="task-001",
        task_family="skillfoundry",
        difficulty="medium",
        initial_user_text_ref=initial_user_text_ref,
        allowed_source_refs=["benchmarks/tasks/task-001/mission_ir.json"],
        expected_output_refs=["package/SKILL.md"],
        budget=BenchmarkBudget(
            max_wall_minutes=45,
            max_total_tokens=250000,
            max_cost_usd=10.0,
            max_user_turns=0,
        ),
        acceptance_refs=["benchmarks/tasks/task-001/acceptance/hidden_checks.json"],
    )


def _pricing_table() -> BenchmarkPricingTable:
    return BenchmarkPricingTable(
        pricing_table_id="pi-test-2026-05-30",
        effective_date="2026-05-30",
        model_prices={
            "pi-test-model": ModelTokenPrice(
                model="pi-test-model",
                input_per_1m_tokens_usd=1.0,
                output_per_1m_tokens_usd=10.0,
                cache_read_per_1m_tokens_usd=0.1,
                cache_write_per_1m_tokens_usd=2.0,
            )
        },
    )


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
