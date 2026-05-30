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
    DirectPiWorkerBenchmarkRunner,
    DirectPiWorkerCommandResult,
    DirectPiWorkerConfig,
)
from missionforge.benchmark.direct_piworker import DIRECT_PIWORKER_INPUT_SCHEMA_VERSION
from missionforge.metrics import MetricEvent


DIRECT_MAIN = Path(__file__).resolve().parents[1] / "workers" / "pi-agent-runtime" / "dist" / "direct-main.js"


class RecordingDirectRunner:
    def __init__(self) -> None:
        self.captured_input: dict[str, object] | None = None
        self.captured_env: dict[str, str] | None = None

    def run(
        self,
        command,
        *,
        input_path: Path,
        cwd: Path,
        timeout_seconds: int,
        env,
    ) -> DirectPiWorkerCommandResult:
        self.captured_env = dict(env)
        payload = json.loads(input_path.read_text(encoding="utf-8"))
        self.captured_input = payload
        workspace_ref = str(payload["workspace_ref"])
        output_ref = str(payload["output_ref"])
        session_ref = str(payload["session_ref"])
        events_ref = str(payload["events_ref"])
        metrics_ref = str(payload["metrics_ref"])
        artifact_ref = str(payload["expected_output_refs"][0])
        artifact_path = cwd / workspace_ref / artifact_ref
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_text("# Direct Skill\n", encoding="utf-8")
        metrics = {
            "tool_call_count": 1,
            "total_tokens": 10,
            "input_tokens": 6,
            "output_tokens": 4,
            "cache_read_tokens": 2,
            "cache_write_tokens": 1,
            "provider_reported_cost_usd": 0.05,
            "tool_latency_ms_total": 7,
            "tool_latency_ms_by_name": {"write": 7},
            "time_to_first_tool_ms": 3,
            "time_to_first_artifact_ms": 5,
            "commands_run": [],
            "tests_run": [],
        }
        output = {
            "schema_version": "missionforge.pi_agent_direct_output.v1",
            "benchmark_run_id": payload["benchmark_run_id"],
            "task_id": payload["task_id"],
            "seed": payload["seed"],
            "status": "completed",
            "workspace_ref": workspace_ref,
            "produced_artifacts": [artifact_ref],
            "changed_refs": [artifact_ref],
            "failures": [],
            "worker_claims": ["direct worker says done"],
            "input_ref": payload["input_ref"],
            "output_ref": output_ref,
            "session_ref": session_ref,
            "events_ref": events_ref,
            "metrics_ref": metrics_ref,
            "duration_ms": 11,
            "metrics": metrics,
        }
        _write_text(cwd / output_ref, json.dumps(output, sort_keys=True, indent=2) + "\n")
        _write_text(cwd / session_ref, "{}\n")
        _write_text(cwd / events_ref, "{}\n")
        _write_text(cwd / metrics_ref, json.dumps(metrics, sort_keys=True) + "\n")
        return DirectPiWorkerCommandResult(returncode=0)


class DirectPiWorkerBenchmarkRunnerTests(unittest.TestCase):
    def test_records_direct_trial_summary_and_metric_event(self) -> None:
        task = sample_task()
        runner = RecordingDirectRunner()
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "benchmarks/tasks/task-001").mkdir(parents=True)
            (root / task.initial_user_text_ref).write_text(
                "I need a direct baseline artifact. raw-user-secret-phrase\n",
                encoding="utf-8",
            )
            service = DirectPiWorkerBenchmarkRunner(
                DirectPiWorkerConfig(command=("fake-direct",), provider_mode="faux"),
                runner=runner,
                environ={},
            )

            record = service.run_trial(benchmark_run_id="bench-001", task=task, seed=1, workspace=root)

            self.assertIsNotNone(runner.captured_input)
            assert runner.captured_input is not None
            self.assertEqual(runner.captured_input["schema_version"], DIRECT_PIWORKER_INPUT_SCHEMA_VERSION)
            self.assertEqual(runner.captured_input["runtime"]["runtime_name"], "missionforge.pi_agent_direct_benchmark")
            for forbidden in ("contract", "mission_id", "repair", "resume", "MissionIR", "FrontDesk", "ProductGate"):
                self.assertNotIn(forbidden, json.dumps(runner.captured_input, sort_keys=True))
            self.assertNotIn("raw-user-secret-phrase", json.dumps(runner.captured_input, sort_keys=True))
            self.assertEqual(runner.captured_env, {"MISSIONFORGE_PI_AGENT_PROVIDER": "faux"})

            self.assertEqual(record.trial.mode, BenchmarkMode.DIRECT_PIWORKER_CHAT)
            self.assertEqual(record.trial.status, BenchmarkStatus.ACCEPTED)
            self.assertEqual(record.summary.accepted, True)
            self.assertEqual(record.summary.mode, BenchmarkMode.DIRECT_PIWORKER_CHAT)
            self.assertEqual(record.summary.total_tokens, 10)
            self.assertEqual(record.summary.input_tokens, 6)
            self.assertEqual(record.summary.output_tokens, 4)
            self.assertEqual(record.summary.cache_read_tokens, 2)
            self.assertEqual(record.summary.cache_write_tokens, 1)
            self.assertEqual(record.summary.provider_reported_cost_usd, 0.05)
            self.assertEqual(record.summary.tool_call_count, 1)
            self.assertEqual(record.summary.repair_count, 0)
            self.assertEqual(record.summary.user_turn_count, 1)
            self.assertEqual(
                record.summary.artifact_refs,
                [
                    "benchmarks/runs/bench-001/trials/task-001/direct_piworker_chat/seed-1/workspace/package/SKILL.md"
                ],
            )
            self.assertNotIn("tool_latency_ms_by_name", record.summary.metric_values())

            summary_payload = json.loads((root / record.summary_ref).read_text(encoding="utf-8"))
            self.assertEqual(BenchmarkSummary.from_dict(summary_payload), record.summary)
            metric_payload = json.loads((root / record.metric_events_ref).read_text(encoding="utf-8").splitlines()[0])
            metric_event = MetricEvent.from_dict(metric_payload)
            self.assertEqual(metric_event.namespace, "missionforge.harness")
            self.assertEqual(metric_event.values["accepted"], True)
            self.assertEqual(metric_event.source_ref, record.summary_ref)
            self.assertEqual(metric_event.run_ref, record.trial_ref)

            review_packet = json.loads((root / record.review_packet_ref).read_text(encoding="utf-8"))
            self.assertNotIn("mode", review_packet)
            self.assertEqual(review_packet["direct_output_ref"], record.direct_output_ref)
            self.assertEqual(review_packet["artifact_refs"], record.summary.artifact_refs)

    def test_missing_output_becomes_failed_summary_without_worker_claim_acceptance(self) -> None:
        class MissingOutputRunner(RecordingDirectRunner):
            def run(self, command, *, input_path: Path, cwd: Path, timeout_seconds: int, env) -> DirectPiWorkerCommandResult:
                payload = json.loads(input_path.read_text(encoding="utf-8"))
                output = {
                    "schema_version": "missionforge.pi_agent_direct_output.v1",
                    "benchmark_run_id": payload["benchmark_run_id"],
                    "task_id": payload["task_id"],
                    "seed": payload["seed"],
                    "status": "completed",
                    "workspace_ref": payload["workspace_ref"],
                    "produced_artifacts": [],
                    "changed_refs": [],
                    "failures": [],
                    "worker_claims": ["done"],
                    "input_ref": payload["input_ref"],
                    "output_ref": payload["output_ref"],
                    "session_ref": payload["session_ref"],
                    "events_ref": payload["events_ref"],
                    "metrics_ref": payload["metrics_ref"],
                    "duration_ms": 5,
                    "metrics": {"tool_call_count": 0},
                }
                _write_text(cwd / str(payload["output_ref"]), json.dumps(output, sort_keys=True) + "\n")
                return DirectPiWorkerCommandResult(returncode=0)

        task = sample_task()
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "benchmarks/tasks/task-001").mkdir(parents=True)
            (root / task.initial_user_text_ref).write_text("Build it.\n", encoding="utf-8")
            service = DirectPiWorkerBenchmarkRunner(
                DirectPiWorkerConfig(command=("fake-direct",), provider_mode="faux"),
                runner=MissingOutputRunner(),
                environ={},
            )

            record = service.run_trial(benchmark_run_id="bench-001", task=task, seed=1, workspace=root)

            self.assertEqual(record.summary.accepted, False)
            self.assertEqual(record.summary.status, BenchmarkStatus.FAILED)
            self.assertIn("missing_expected_output", record.summary.failure_taxonomy)

    @unittest.skipUnless(DIRECT_MAIN.is_file(), "pi-agent-runtime dist/direct-main.js is not built")
    def test_default_faux_runner_smoke_writes_collected_summary(self) -> None:
        task = sample_task()
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "benchmarks/tasks/task-001").mkdir(parents=True)
            (root / task.initial_user_text_ref).write_text(
                "Create the expected direct baseline file. private-smoke-phrase\n",
                encoding="utf-8",
            )
            service = DirectPiWorkerBenchmarkRunner(
                DirectPiWorkerConfig(provider_mode="faux", timeout_seconds=60),
                environ={},
            )

            record = service.run_trial(benchmark_run_id="bench-smoke", task=task, seed=1, workspace=root)

            self.assertEqual(record.summary.accepted, True)
            self.assertEqual(record.trial.status, BenchmarkStatus.ACCEPTED)
            self.assertGreater(record.summary.total_tokens, 0)
            public_refs = [
                record.direct_output_ref,
                record.summary_ref,
                record.metric_events_ref,
                record.review_packet_ref,
                record.run_result.events_ref,
                record.run_result.session_ref,
                record.run_result.metrics_ref,
            ]
            public_text = "".join((root / ref).read_text(encoding="utf-8") for ref in public_refs)
            self.assertNotIn("private-smoke-phrase", public_text)
            self.assertNotIn("Create the expected direct baseline file", public_text)


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


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
