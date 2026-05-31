from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import tempfile
import unittest

from missionforge.adapters.pi_agent_runtime import (
    PI_AGENT_OUTPUT_SCHEMA_VERSION,
    PiAgentCommandResult,
    PiAgentRuntimeAdapter,
    PiAgentRuntimeConfig,
    SubprocessPiAgentCommandRunner,
)
from missionforge.contracts import ContractValidationError
from missionforge.evidence_store import InMemoryEvidenceStore
from missionforge.work_unit import WorkUnitContract


def sample_work_unit() -> WorkUnitContract:
    return WorkUnitContract(
        work_unit_id="WU-000001",
        mission_id="mission-001",
        iteration=1,
        next_objective="Produce deterministic PI Agent output.",
        allowed_scope=["package"],
        visible_refs=["mission/frozen_contract.json"],
        expected_outputs=["package/SKILL.md"],
        exit_criteria=["Verifier runs."],
        stop_conditions=["Halt control is active."],
    )


@dataclass
class RecordingRunner:
    result: PiAgentCommandResult = PiAgentCommandResult(returncode=0)
    output_payload: dict[str, object] | None = None
    write_output: bool = True
    artifact_content: str = "# Skill\n"
    worker_claims: tuple[str, ...] | None = None
    write_savepoints: bool = True
    captured_env: dict[str, str] | None = None
    captured_input: dict[str, object] | None = None

    def run(self, command, *, input_path: Path, cwd: Path, timeout_seconds: int, env) -> PiAgentCommandResult:
        self.captured_env = dict(env)
        self.captured_input = json.loads(input_path.read_text(encoding="utf-8"))
        if self.write_output:
            artifact_ref = "package/SKILL.md"
            (cwd / artifact_ref).parent.mkdir(parents=True, exist_ok=True)
            (cwd / artifact_ref).write_text(self.artifact_content, encoding="utf-8")
            output_ref = str(self.captured_input["output_ref"])
            session_ref = str(self.captured_input["session_ref"])
            events_ref = str(self.captured_input["events_ref"])
            metrics_ref = str(self.captured_input["metrics_ref"])
            savepoints_ref = str(self.captured_input["savepoints_ref"])
            metrics = {
                "tool_call_count": 1,
                "total_tokens": 7,
                "input_tokens": 5,
                "output_tokens": 2,
                "cache_read_tokens": 3,
                "cache_write_tokens": 1,
                "input_cost_usd": 0.01,
                "output_cost_usd": 0.02,
                "cache_read_cost_usd": 0.003,
                "cache_write_cost_usd": 0.004,
                "provider_reported_cost_usd": 0.037,
                "tool_error_count": 0,
                "tool_latency_ms_total": 12,
                "tool_latency_ms_by_name": {"write": 12},
                "command_count": 0,
                "test_command_count": 0,
                "command_failure_count": 0,
                "time_to_first_tool_ms": 1,
                "time_to_first_artifact_ms": 2,
            }
            payload = self.output_payload or {
                "schema_version": PI_AGENT_OUTPUT_SCHEMA_VERSION,
                "work_unit_id": "WU-000001",
                "status": "completed",
                "produced_artifacts": [artifact_ref],
                "changed_refs": [artifact_ref, output_ref, session_ref, events_ref, metrics_ref, savepoints_ref],
                "commands_run": ["fake-pi-agent"],
                "tests_run": [],
                "failures": [],
                "worker_claims": list(self.worker_claims)
                if self.worker_claims is not None
                else ["PI Agent says the artifact is done."],
                "verifier_evidence": [artifact_ref, events_ref, metrics_ref, savepoints_ref],
                "new_unknowns": [],
                "recommended_next_steps": ["Run verifier."],
                "verification_status": "not_run",
                "input_ref": str(self.captured_input["input_ref"]),
                "output_ref": output_ref,
                "session_ref": session_ref,
                "events_ref": events_ref,
                "metrics_ref": metrics_ref,
                "savepoints_ref": savepoints_ref,
                "duration_ms": 1,
                "metrics": metrics,
            }
            _write_text(cwd / session_ref, "{}\n")
            _write_text(cwd / events_ref, "{}\n")
            _write_text(cwd / metrics_ref, json.dumps(metrics, sort_keys=True) + "\n")
            if self.write_savepoints:
                _write_text(cwd / savepoints_ref, '{"schema_version": "missionforge.pi_agent_runtime_savepoint.v1"}\n')
            _write_text(cwd / output_ref, json.dumps(payload, sort_keys=True, indent=2) + "\n")
        return self.result


class PiAgentRuntimeAdapterTests(unittest.TestCase):
    def test_config_rejects_secret_metadata(self) -> None:
        with self.assertRaisesRegex(ContractValidationError, "sensitive"):
            PiAgentRuntimeConfig(command=("node", "runtime.js"), metadata={"nested": {"api_key": "secret"}})

    def test_config_validates_follow_up_repair(self) -> None:
        with self.assertRaisesRegex(ContractValidationError, "previous_output_ref"):
            PiAgentRuntimeConfig(
                command=("node", "runtime.js"),
                repair_mode="follow_up",
                verifier_failures=("missing output",),
                repair_prompt="Create the missing output.",
            )

        config = PiAgentRuntimeConfig(
            command=("node", "runtime.js"),
            repair_mode="follow_up",
            verifier_failures=("missing output",),
            failed_constraints=("C-artifact",),
            previous_output_ref="attempts/WU-000001/pi_agent_output.json",
            repair_prompt="Create the missing output.",
        )

        self.assertEqual(config.repair_mode, "follow_up")

    def test_adapter_invokes_runner_and_maps_refs_only_execution_report(self) -> None:
        runner = RecordingRunner()
        config = PiAgentRuntimeConfig(command=("pi-agent-runtime",))
        store = InMemoryEvidenceStore()

        with tempfile.TemporaryDirectory() as tempdir:
            result = PiAgentRuntimeAdapter(config, runner=runner).run(
                sample_work_unit(),
                workspace=tempdir,
                evidence_store=store,
            )
            root = Path(tempdir)
            input_payload = json.loads((root / "attempts/WU-000001/pi_agent_input.json").read_text(encoding="utf-8"))
            report_payload = json.loads(
                (root / "attempts/WU-000001/pi_agent_execution_report.json").read_text(encoding="utf-8")
            )

        self.assertEqual(result.worker_result.status, "completed")
        self.assertEqual(result.execution_report.produced_artifacts, ["package/SKILL.md"])
        self.assertEqual(result.execution_report.worker_claims, ["worker_claim_present:length=35"])
        self.assertEqual(result.execution_report.metrics["provider_mode"], "faux")
        self.assertEqual(result.execution_report.metrics["total_tokens"], 7)
        self.assertEqual(result.execution_report.metrics["input_tokens"], 5)
        self.assertEqual(result.execution_report.metrics["output_tokens"], 2)
        self.assertEqual(result.execution_report.metrics["cache_read_tokens"], 3)
        self.assertEqual(result.execution_report.metrics["cache_write_tokens"], 1)
        self.assertEqual(result.execution_report.metrics["provider_reported_cost_usd"], 0.037)
        self.assertEqual(result.execution_report.metrics["tool_error_count"], 0)
        self.assertEqual(result.execution_report.metrics["tool_latency_ms_total"], 12)
        self.assertEqual(result.execution_report.metrics["command_count"], 0)
        self.assertEqual(result.execution_report.metrics["test_command_count"], 0)
        self.assertEqual(result.execution_report.metrics["command_failure_count"], 0)
        self.assertEqual(result.execution_report.metrics["time_to_first_tool_ms"], 1)
        self.assertEqual(result.execution_report.metrics["time_to_first_artifact_ms"], 2)
        self.assertNotIn("tool_latency_ms_by_name", result.execution_report.metrics)
        self.assertEqual(input_payload["schema_version"], "missionforge.pi_agent_runtime_input.v1")
        self.assertEqual(input_payload["repair"]["mode"], "none")
        self.assertEqual(input_payload["savepoints_ref"], "attempts/WU-000001/pi_agent_savepoints.jsonl")
        self.assertEqual(input_payload["permission_manifest"]["schema_version"], "permission_manifest.v1")
        self.assertEqual(input_payload["permission_manifest"]["writable_refs"], ["package"])
        self.assertEqual(input_payload["permission_manifest"]["allowed_commands"], [])
        self.assertNotIn("api_key", json.dumps(input_payload).lower())
        self.assertNotIn("# Skill", json.dumps(report_payload))
        self.assertNotIn("PI Agent says the artifact is done.", json.dumps(report_payload))
        self.assertEqual([record.evidence_ref.kind for record in store.snapshot().records], ["pi_agent_runtime_event"] * 3)

    def test_adapter_summarizes_safe_looking_worker_claim_slugs(self) -> None:
        runner = RecordingRunner(worker_claims=("sk-live-secret-456:length=18",))

        with tempfile.TemporaryDirectory() as tempdir:
            result = PiAgentRuntimeAdapter(
                PiAgentRuntimeConfig(command=("pi-agent-runtime",)),
                runner=runner,
            ).run(sample_work_unit(), workspace=tempdir, evidence_store=InMemoryEvidenceStore())
            report_payload = json.loads(
                Path(tempdir, "attempts/WU-000001/pi_agent_execution_report.json").read_text(encoding="utf-8")
            )

        serialized_report = json.dumps(report_payload, sort_keys=True)
        self.assertEqual(result.execution_report.worker_claims, ["worker_claim_present:length=28"])
        self.assertNotIn("sk-live-secret-456", serialized_report)

    def test_adapter_passes_follow_up_repair_envelope(self) -> None:
        runner = RecordingRunner()
        config = PiAgentRuntimeConfig(
            command=("pi-agent-runtime",),
            repair_mode="follow_up",
            verifier_failures=("expected output was not produced",),
            failed_constraints=("C-artifact",),
            previous_output_ref="attempts/WU-000001/pi_agent_output.json",
            repair_prompt="Repair the missing artifact.",
        )

        with tempfile.TemporaryDirectory() as tempdir:
            result = PiAgentRuntimeAdapter(config, runner=runner).run(
                sample_work_unit(),
                workspace=tempdir,
                evidence_store=InMemoryEvidenceStore(),
            )

        self.assertEqual(result.worker_result.status, "completed")
        self.assertIsNotNone(runner.captured_input)
        repair = runner.captured_input["repair"]  # type: ignore[index]
        self.assertEqual(repair["mode"], "follow_up")
        self.assertEqual(repair["failed_constraints"], ["C-artifact"])
        self.assertEqual(repair["previous_output_ref"], "attempts/WU-000001/pi_agent_output.json")

    def test_with_repair_clones_adapter_with_repair_envelope(self) -> None:
        runner = RecordingRunner()
        adapter = PiAgentRuntimeAdapter(PiAgentRuntimeConfig(command=("pi-agent-runtime",)), runner=runner)
        repair_adapter = adapter.with_repair(
            verifier_failures=["missing output"],
            failed_constraints=["C-artifact"],
            previous_output_ref="attempts/WU-000001/pi_agent_output.json",
            repair_prompt="Create the missing output.",
        )

        with tempfile.TemporaryDirectory() as tempdir:
            result = repair_adapter.run(
                sample_work_unit(),
                workspace=tempdir,
                evidence_store=InMemoryEvidenceStore(),
            )

        self.assertEqual(result.worker_result.status, "completed")
        self.assertIsNotNone(runner.captured_input)
        self.assertEqual(runner.captured_input["repair"]["mode"], "follow_up")  # type: ignore[index]

    def test_command_failure_redacts_secret_from_artifacts_and_evidence(self) -> None:
        secret = "sk-live-secret-456"
        runner = RecordingRunner(
            result=PiAgentCommandResult(
                returncode=2,
                stdout=f"raw {secret}",
                stderr=f"Authorization: Bearer {secret}",
            ),
            write_output=False,
        )
        config = PiAgentRuntimeConfig(command=("pi-agent-runtime",), provider_mode="live", provider_config_source="env")
        store = InMemoryEvidenceStore()

        with tempfile.TemporaryDirectory() as tempdir:
            result = PiAgentRuntimeAdapter(
                config,
                runner=runner,
                environ={
                    "MISSIONFORGE_PI_AGENT_MODEL": "gpt-5.5",
                    "MISSIONFORGE_PI_AGENT_BASE_URL": "https://right.codes/codex/v1",
                    "MISSIONFORGE_PI_AGENT_API_KEY": secret,
                },
            ).run(sample_work_unit(), workspace=tempdir, evidence_store=store)
            serialized_workspace = "\n".join(
                path.read_text(encoding="utf-8") for path in Path(tempdir).rglob("*") if path.is_file()
            )

        self.assertEqual(result.worker_result.status, "failed")
        self.assertEqual(runner.captured_env["MISSIONFORGE_PI_AGENT_API_KEY"], secret)
        self.assertNotIn(secret, serialized_workspace)
        self.assertNotIn(secret, json.dumps(store.snapshot().to_dict(), sort_keys=True))
        self.assertNotIn("MISSIONFORGE_PI_AGENT_API_KEY", json.dumps(store.snapshot().to_dict(), sort_keys=True))
        self.assertIn("<redacted>", serialized_workspace)

    def test_live_config_failure_happens_before_child_process_invocation(self) -> None:
        runner = RecordingRunner()
        config = PiAgentRuntimeConfig(command=("pi-agent-runtime",), provider_mode="live", provider_config_source="env")

        with tempfile.TemporaryDirectory() as tempdir:
            with self.assertRaisesRegex(ContractValidationError, "missing"):
                PiAgentRuntimeAdapter(config, runner=runner, environ={}).run(
                    sample_work_unit(),
                    workspace=tempdir,
                    evidence_store=InMemoryEvidenceStore(),
                )

        self.assertIsNone(runner.captured_input)
        self.assertIsNone(runner.captured_env)

    def test_timeout_missing_output_and_invalid_json_are_worker_failures(self) -> None:
        cases = [
            RecordingRunner(result=PiAgentCommandResult(returncode=-1, timed_out=True), write_output=False),
            RecordingRunner(write_output=False),
            _InvalidJsonRunner(),
        ]

        for runner in cases:
            with self.subTest(runner=type(runner).__name__):
                with tempfile.TemporaryDirectory() as tempdir:
                    result = PiAgentRuntimeAdapter(
                        PiAgentRuntimeConfig(command=("pi-agent-runtime",)),
                        runner=runner,
                    ).run(sample_work_unit(), workspace=tempdir, evidence_store=InMemoryEvidenceStore())
                    output = json.loads(
                        Path(tempdir, "attempts/WU-000001/pi_agent_output.json").read_text(encoding="utf-8")
                    )

                self.assertEqual(result.worker_result.status, "failed")
                self.assertEqual(output["status"], "failed")

    def test_completed_output_missing_savepoints_is_rewritten_as_failure(self) -> None:
        runner = RecordingRunner(write_savepoints=False)

        with tempfile.TemporaryDirectory() as tempdir:
            result = PiAgentRuntimeAdapter(
                PiAgentRuntimeConfig(command=("pi-agent-runtime",)),
                runner=runner,
            ).run(sample_work_unit(), workspace=tempdir, evidence_store=InMemoryEvidenceStore())
            output = json.loads(
                Path(tempdir, "attempts/WU-000001/pi_agent_output.json").read_text(encoding="utf-8")
            )

        self.assertEqual(result.worker_result.status, "failed")
        self.assertEqual(output["status"], "failed")
        self.assertIn("savepoint artifact is missing", " ".join(output["failures"]))

    def test_out_of_scope_produced_artifact_is_rewritten_as_failure(self) -> None:
        runner = RecordingRunner(
            output_payload={
                "schema_version": PI_AGENT_OUTPUT_SCHEMA_VERSION,
                "work_unit_id": "WU-000001",
                "status": "completed",
                "produced_artifacts": ["outside/SKILL.md"],
                "changed_refs": ["outside/SKILL.md"],
                "commands_run": ["fake-pi-agent"],
                "tests_run": [],
                "failures": [],
                "worker_claims": ["done"],
                "verifier_evidence": ["outside/SKILL.md"],
                "new_unknowns": [],
                "recommended_next_steps": ["Run verifier."],
                "verification_status": "not_run",
                "input_ref": "attempts/WU-000001/pi_agent_input.json",
                "output_ref": "attempts/WU-000001/pi_agent_output.json",
                "session_ref": "attempts/WU-000001/pi_agent_session.jsonl",
                "events_ref": "attempts/WU-000001/pi_agent_events.jsonl",
                "metrics_ref": "attempts/WU-000001/pi_agent_metrics.json",
                "savepoints_ref": "attempts/WU-000001/pi_agent_savepoints.jsonl",
                "duration_ms": 1,
                "metrics": {},
            }
        )

        with tempfile.TemporaryDirectory() as tempdir:
            result = PiAgentRuntimeAdapter(
                PiAgentRuntimeConfig(command=("pi-agent-runtime",)),
                runner=runner,
            ).run(sample_work_unit(), workspace=tempdir, evidence_store=InMemoryEvidenceStore())

        self.assertEqual(result.worker_result.status, "failed")
        self.assertIn("outside/SKILL.md", result.execution_report.produced_artifacts)

    def test_default_command_invokes_node_faux_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            result = PiAgentRuntimeAdapter(PiAgentRuntimeConfig()).run(
                sample_work_unit(),
                workspace=tempdir,
                evidence_store=InMemoryEvidenceStore(),
            )
            root = Path(tempdir)

            self.assertEqual(result.worker_result.status, "completed")
            self.assertTrue((root / "package/SKILL.md").exists())
            self.assertTrue((root / "attempts/WU-000001/pi_agent_output.json").exists())
            self.assertTrue((root / "attempts/WU-000001/pi_agent_events.jsonl").exists())
            self.assertTrue((root / "attempts/WU-000001/pi_agent_session.jsonl").exists())
            self.assertTrue((root / "attempts/WU-000001/pi_agent_metrics.json").exists())
            self.assertTrue((root / "attempts/WU-000001/pi_agent_savepoints.jsonl").exists())

    def test_subprocess_runner_builds_default_runtime_when_dist_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            runtime_dir = root / "runtime"
            dist_dir = runtime_dir / "dist"
            bin_dir = root / "bin"
            dist_dir.mkdir(parents=True)
            bin_dir.mkdir()
            (runtime_dir / "package.json").write_text('{"scripts":{"build":"true"}}\n', encoding="utf-8")
            npm_log = root / "npm.log"
            fake_npm = bin_dir / "npm"
            fake_npm.write_text(
                "#!/bin/sh\n"
                f"echo \"$@\" >> {npm_log}\n"
                "if [ \"$1\" = \"run\" ]; then mkdir -p ../runtime/dist; echo 'setup' > ../runtime/dist/main.js; fi\n",
                encoding="utf-8",
            )
            fake_node = bin_dir / "node"
            fake_node.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            fake_npm.chmod(0o755)
            fake_node.chmod(0o755)
            input_path = root / "input.json"
            input_path.write_text("{}\n", encoding="utf-8")
            env = {"PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}"}

            result = SubprocessPiAgentCommandRunner().run(
                ("node", str(dist_dir / "main.js")),
                input_path=input_path,
                cwd=root,
                timeout_seconds=10,
                env=env,
            )

            self.assertEqual(result.returncode, 0)
            log = npm_log.read_text(encoding="utf-8")
            self.assertIn("install", log)
            self.assertIn("run build", log)


class _InvalidJsonRunner:
    def run(self, command, *, input_path: Path, cwd: Path, timeout_seconds: int, env) -> PiAgentCommandResult:
        payload = json.loads(input_path.read_text(encoding="utf-8"))
        output_ref = str(payload["output_ref"])
        _write_text(cwd / output_ref, "{invalid json")
        return PiAgentCommandResult(returncode=0)


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
