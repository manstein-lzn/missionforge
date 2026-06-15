from __future__ import annotations

from dataclasses import dataclass, replace
import json
import os
from pathlib import Path
import tempfile
import unittest

from missionforge.adapters.pi_agent_provider_config import load_codex_current_provider
from missionforge.adapters.pi_agent_runtime import (
    PI_AGENT_OUTPUT_SCHEMA_VERSION,
    PiAgentCommandResult,
    PiAgentExecutorNode,
    PiAgentJudgeNode,
    PiAgentRuntimeAdapter,
    PiAgentCallSpec,
    PiAgentRuntimeConfig,
    SubprocessPiAgentCommandRunner,
)
from missionforge.agent_packets import AgentExecutionPacket, AgentExecutionStatus, HardCheckStatus, JudgePacket, JudgeReportDecision
from missionforge.contracts import ContractValidationError, stable_json_hash
from missionforge.evidence_store import InMemoryEvidenceStore
from missionforge.piworker_call import PiWorkerCall, PiWorkerCallResult, PiWorkerCallRole


def sample_piworker_call() -> PiWorkerCall:
    return PiWorkerCall(
        call_id="WU-000001",
        role=PiWorkerCallRole.EXECUTOR,
        contract_id="mission-001",
        contract_hash="sha256:" + "a" * 64,
        contract_ref="mission/frozen_contract.json",
        objective="Produce deterministic PI Agent output.",
        visible_refs=["mission/frozen_contract.json"],
        writable_refs=["package"],
        expected_output_refs=["package/SKILL.md"],
    )


def sample_judge_packet() -> JudgePacket:
    return JudgePacket.from_dict(
        {
            "packet_id": "judge-packet-001",
            "schema_version": "judge_packet.v1",
            "role": "judge_piworker",
            "contract_id": "contract-001",
            "contract_hash": "sha256:" + "a" * 64,
            "contract_ref": "contract/task_contract.json",
            "judge_rubric_ref": "projections/judge_rubric.json",
            "execution_packet_ref": "packets/execution_packet.json",
            "execution_report_ref": "reports/execution_report.json",
            "report_ref": "reports/judge_report.json",
            "hard_check_status": "passed",
            "artifact_refs": ["artifacts/final.md"],
            "evidence_refs": ["reports/tool_events.jsonl"],
            "hard_check_refs": ["reports/hard_checks.json"],
        }
    )


def execution_packet_payload() -> dict[str, object]:
    return {
        "packet_id": "WU-000001",
        "schema_version": "agent_execution_packet.v1",
        "role": "executor_piworker",
        "contract_id": "contract-001",
        "contract_hash": "sha256:" + "a" * 64,
        "contract_ref": "contract/task_contract.json",
        "worker_brief_ref": "projections/worker_brief.json",
        "worker_brief_hash": None,
        "workspace_policy_ref": "policy/workspace_policy.json",
        "workspace_policy_hash": None,
        "permission_manifest_ref": "policy/permission_manifest.json",
        "permission_manifest_hash": None,
        "report_ref": "reports/execution_report.json",
        "expected_artifact_refs": ["artifacts/final.md"],
        "allowed_input_refs": ["contract/task_contract.json", "projections/judge_rubric.json"],
        "writable_refs": ["artifacts", "reports"],
    }


def execution_report_payload() -> dict[str, object]:
    packet = execution_packet_payload()
    return {
        "report_id": "execution-report-001",
        "schema_version": "agent_execution_report.v1",
        "role": "executor_piworker",
        "packet_id": packet["packet_id"],
        "packet_ref": "packets/execution_packet.json",
        "packet_hash": stable_json_hash(packet),
        "contract_id": packet["contract_id"],
        "contract_hash": packet["contract_hash"],
        "contract_ref": packet["contract_ref"],
        "status": "completed",
        "produced_artifact_refs": ["artifacts/final.md"],
        "changed_refs": ["artifacts/final.md", "reports/execution_report.json"],
        "evidence_refs": ["reports/execution_report.json"],
        "metric_refs": ["reports/execution_metrics.json"],
    }


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
            context_observations_ref = str(self.captured_input["context_observations_ref"])
            context_projection_ref = str(self.captured_input["context_projection_ref"])
            context_projection_config = dict(self.captured_input["context_projection_config"])
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
                "call_id": "WU-000001",
                "status": "completed",
                "produced_artifacts": [artifact_ref],
                "changed_refs": [
                    artifact_ref,
                    output_ref,
                    session_ref,
                    events_ref,
                    metrics_ref,
                    savepoints_ref,
                    context_observations_ref,
                    context_projection_ref,
                ],
                "commands_run": ["fake-pi-agent"],
                "tests_run": [],
                "failures": [],
                "worker_claims": list(self.worker_claims)
                if self.worker_claims is not None
                else ["PI Agent says the artifact is done."],
                "verifier_evidence": [
                    artifact_ref,
                    events_ref,
                    metrics_ref,
                    savepoints_ref,
                    context_observations_ref,
                    context_projection_ref,
                ],
                "new_unknowns": [],
                "recommended_next_steps": ["Run verifier."],
                "verification_status": "not_run",
                "input_ref": str(self.captured_input["input_ref"]),
                "output_ref": output_ref,
                "session_ref": session_ref,
                "events_ref": events_ref,
                "metrics_ref": metrics_ref,
                "savepoints_ref": savepoints_ref,
                "context_observations_ref": context_observations_ref,
                "context_projection_ref": context_projection_ref,
                "duration_ms": 1,
                "metrics": metrics,
            }
            _write_text(cwd / session_ref, "{}\n")
            _write_text(cwd / events_ref, "{}\n")
            _write_text(cwd / metrics_ref, json.dumps(metrics, sort_keys=True) + "\n")
            _write_text(cwd / context_observations_ref, "")
            _write_text(
                cwd / context_projection_ref,
                json.dumps(
                    {
                        "schema_version": "missionforge.pi_agent_context_projection.v1",
                        "call_id": "WU-000001",
                        "created_at": "2026-01-01T00:00:00+00:00",
                        "context_observations_ref": context_observations_ref,
                        "projection_count": 0,
                        "latest_turn_index": 0,
                        "input_message_count": 0,
                        "projected_message_count": 0,
                        "context_projection_config": context_projection_config,
                        "projected_observations": [],
                        "active_observations": [],
                        "warnings": [],
                    },
                    sort_keys=True,
                )
                + "\n",
            )
            if self.write_savepoints:
                _write_text(cwd / savepoints_ref, '{"schema_version": "missionforge.pi_agent_runtime_savepoint.v1"}\n')
            _write_text(cwd / output_ref, json.dumps(payload, sort_keys=True, indent=2) + "\n")
        return self.result


@dataclass
class JudgeRecordingRunner:
    result: PiAgentCommandResult = PiAgentCommandResult(returncode=0)
    output_payload: dict[str, object] | None = None
    report_payload: dict[str, object] | None = None
    write_output: bool = True
    captured_env: dict[str, str] | None = None
    captured_input: dict[str, object] | None = None

    def run(self, command, *, input_path: Path, cwd: Path, timeout_seconds: int, env) -> PiAgentCommandResult:
        self.captured_env = dict(env)
        self.captured_input = json.loads(input_path.read_text(encoding="utf-8"))
        if self.write_output:
            output_ref = str(self.captured_input["output_ref"])
            session_ref = str(self.captured_input["session_ref"])
            events_ref = str(self.captured_input["events_ref"])
            metrics_ref = str(self.captured_input["metrics_ref"])
            savepoints_ref = str(self.captured_input["savepoints_ref"])
            context_observations_ref = str(self.captured_input["context_observations_ref"])
            context_projection_ref = str(self.captured_input["context_projection_ref"])
            context_projection_config = dict(self.captured_input["context_projection_config"])
            spec_ref = str(self.captured_input["call_spec"]["visible_refs"][0])
            spec = json.loads((cwd / spec_ref).read_text(encoding="utf-8"))
            report_ref = str(spec["report_ref"])
            packet_ref = str(spec["packet_ref"])
            packet_hash = str(spec["packet_hash"])
            contract_ref = str(spec["contract_ref"])
            call_spec_payload = json.loads((cwd / contract_ref).read_text(encoding="utf-8"))
            contract_hash = str(call_spec_payload["contract_hash"])
            contract_id = str(self.captured_input["mission_id"])
            packet_id = str(self.captured_input["call_id"])
            metrics = {
                "tool_call_count": 1,
                "total_tokens": 9,
                "input_tokens": 6,
                "output_tokens": 3,
                "cache_read_tokens": 0,
                "cache_write_tokens": 0,
                "input_cost_usd": 0.0,
                "output_cost_usd": 0.0,
                "cache_read_cost_usd": 0.0,
                "cache_write_cost_usd": 0.0,
                "provider_reported_cost_usd": 0.0,
                "tool_error_count": 0,
                "tool_latency_ms_total": 8,
                "tool_latency_ms_by_name": {"read": 8},
                "command_count": 0,
                "test_command_count": 0,
                "command_failure_count": 0,
                "time_to_first_tool_ms": 1,
                "time_to_first_artifact_ms": 2,
            }
            accepted_artifact_refs = list(spec["artifact_refs"])
            report_payload = self.report_payload or {
                "schema_version": "judge_report.v1",
                "report_id": "judge-report-001",
                "packet_id": packet_id,
                "packet_ref": packet_ref,
                "packet_hash": packet_hash,
                "contract_id": contract_id,
                "contract_hash": contract_hash,
                "contract_ref": contract_ref,
                "decision": "accepted",
                "hard_check_status": "passed",
                "rationale_refs": ["reports/judge_rationale.md"],
                "evidence_refs": ["reports/execution_report.json"],
                "accepted_artifact_refs": accepted_artifact_refs,
            }
            output_payload = self.output_payload or {
                "schema_version": PI_AGENT_OUTPUT_SCHEMA_VERSION,
                "call_id": packet_id,
                "status": "completed",
                "produced_artifacts": [report_ref],
                "changed_refs": [
                    report_ref,
                    output_ref,
                    session_ref,
                    events_ref,
                    metrics_ref,
                    savepoints_ref,
                    context_observations_ref,
                    context_projection_ref,
                ],
                "commands_run": ["fake-pi-agent"],
                "tests_run": [],
                "failures": [],
                "worker_claims": ["judge_claim_present:length=24"],
                "verifier_evidence": [
                    report_ref,
                    events_ref,
                    metrics_ref,
                    savepoints_ref,
                    context_observations_ref,
                    context_projection_ref,
                ],
                "new_unknowns": [],
                "recommended_next_steps": ["Record judge decision."],
                "verification_status": "not_run",
                "input_ref": str(self.captured_input["input_ref"]),
                "output_ref": output_ref,
                "session_ref": session_ref,
                "events_ref": events_ref,
                "metrics_ref": metrics_ref,
                "savepoints_ref": savepoints_ref,
                "context_observations_ref": context_observations_ref,
                "context_projection_ref": context_projection_ref,
                "duration_ms": 1,
                "metrics": metrics,
            }
            (cwd / report_ref).parent.mkdir(parents=True, exist_ok=True)
            (cwd / report_ref).write_text(json.dumps(report_payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")
            _write_text(cwd / session_ref, "{}\n")
            _write_text(cwd / events_ref, "{}\n")
            _write_text(cwd / metrics_ref, json.dumps(metrics, sort_keys=True) + "\n")
            _write_text(cwd / savepoints_ref, '{"schema_version": "missionforge.pi_agent_runtime_savepoint.v1"}\n')
            _write_text(cwd / context_observations_ref, "")
            _write_text(
                cwd / context_projection_ref,
                json.dumps(
                    {
                        "schema_version": "missionforge.pi_agent_context_projection.v1",
                        "call_id": packet_id,
                        "created_at": "2026-01-01T00:00:00+00:00",
                        "context_observations_ref": context_observations_ref,
                        "projection_count": 0,
                        "latest_turn_index": 0,
                        "input_message_count": 0,
                        "projected_message_count": 0,
                        "context_projection_config": context_projection_config,
                        "projected_observations": [],
                        "active_observations": [],
                        "warnings": [],
                    },
                    sort_keys=True,
                )
                + "\n",
            )
            _write_text(cwd / output_ref, json.dumps(output_payload, sort_keys=True, indent=2) + "\n")
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
            result = PiAgentRuntimeAdapter(config, runner=runner).run_call(
                sample_piworker_call(),
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
            self.assertEqual(input_payload["piworker_call"]["schema_version"], "piworker_call.v1")
            self.assertEqual(input_payload["piworker_call"]["call_id"], "WU-000001")
            self.assertEqual(input_payload["piworker_call"]["expected_output_refs"], ["package/SKILL.md"])
            self.assertEqual(input_payload["piworker_call"]["writable_refs"], ["package"])
            self.assertEqual(input_payload["repair"]["mode"], "none")
            self.assertEqual(input_payload["savepoints_ref"], "attempts/WU-000001/pi_agent_savepoints.jsonl")
            self.assertIsNone(input_payload["extension_lock_ref"])
            self.assertEqual(
                input_payload["context_observations_ref"],
                "attempts/WU-000001/context/tool_observations.jsonl",
            )
            self.assertEqual(input_payload["context_projection_ref"], "attempts/WU-000001/context/projection.json")
            self.assertEqual(input_payload["context_raw_dir_ref"], "attempts/WU-000001/context/raw")
            self.assertEqual(
                input_payload["context_projection_config"],
                {
                    "schema_version": "missionforge.pi_agent_context_projection_config.v1",
                    "large_observation_bytes": 8192,
                },
            )
            self.assertEqual(input_payload["permission_manifest"]["schema_version"], "permission_manifest.v1")
            self.assertEqual(input_payload["permission_manifest"]["writable_refs"], ["package"])
            self.assertEqual(input_payload["permission_manifest"]["allowed_commands"], [])
            self.assertEqual(input_payload["capability_grant"]["schema_version"], "runtime_capability_grant.v1")
            self.assertEqual(input_payload["capability_grant"]["role"], "executor_piworker")
            self.assertEqual(input_payload["sandbox_profile"]["schema_version"], "sandbox_profile.v1")
            self.assertEqual(input_payload["sandbox_profile"]["workspace_root_ref"], "attempts/WU-000001/workspace_view")
            self.assertEqual(
                input_payload["capability_grant"]["workspace_view_ref"],
                input_payload["sandbox_profile"]["workspace_root_ref"],
            )
            self.assertEqual(input_payload["capability_grant"]["permission_manifest_ref"], "attempts/WU-000001/runtime_permission_manifest.json")
            self.assertEqual(input_payload["capability_grant"]["sandbox_profile_ref"], "attempts/WU-000001/sandbox_profile.json")
            self.assertNotIn("api_key", json.dumps(input_payload).lower())
            self.assertNotIn("# Skill", json.dumps(report_payload))
            self.assertNotIn("PI Agent says the artifact is done.", json.dumps(report_payload))
            self.assertIn("attempts/WU-000001/context/tool_observations.jsonl", report_payload["changed_refs"])
            self.assertIn("attempts/WU-000001/context/projection.json", report_payload["changed_refs"])
            self.assertEqual(
                report_payload["metrics"]["context_projection_ref"],
                "attempts/WU-000001/context/projection.json",
            )
            projection_payload = json.loads(
                (root / "attempts/WU-000001/context/projection.json").read_text(encoding="utf-8")
            )
            self.assertEqual(projection_payload["schema_version"], "missionforge.pi_agent_context_projection.v1")
            self.assertEqual(
                projection_payload["context_observations_ref"],
                "attempts/WU-000001/context/tool_observations.jsonl",
            )
            self.assertEqual(projection_payload["context_projection_config"]["large_observation_bytes"], 8192)
            self.assertEqual(
                json.loads((root / "attempts/WU-000001/runtime_workspace_policy.json").read_text(encoding="utf-8"))["schema_version"],
                "workspace_policy.v1",
            )
            self.assertEqual(
                json.loads((root / "attempts/WU-000001/runtime_permission_manifest.json").read_text(encoding="utf-8"))["schema_version"],
                "permission_manifest.v1",
            )
            self.assertEqual(
                json.loads((root / "attempts/WU-000001/sandbox_profile.json").read_text(encoding="utf-8"))["schema_version"],
                "sandbox_profile.v1",
            )
            self.assertEqual([record.evidence_ref.kind for record in store.snapshot().records], ["pi_agent_runtime_event"] * 3)

    def test_adapter_summarizes_safe_looking_worker_claim_slugs(self) -> None:
        runner = RecordingRunner(worker_claims=("sk-live-secret-456:length=18",))

        with tempfile.TemporaryDirectory() as tempdir:
            result = PiAgentRuntimeAdapter(
                PiAgentRuntimeConfig(command=("pi-agent-runtime",)),
                runner=runner,
            ).run_call(sample_piworker_call(), workspace=tempdir, evidence_store=InMemoryEvidenceStore())
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
            result = PiAgentRuntimeAdapter(config, runner=runner).run_call(
                sample_piworker_call(),
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
            result = repair_adapter.run_call(
                sample_piworker_call(),
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
            ).run_call(sample_piworker_call(), workspace=tempdir, evidence_store=store)
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
                PiAgentRuntimeAdapter(config, runner=runner, environ={}).run_call(
                    sample_piworker_call(),
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
                    ).run_call(sample_piworker_call(), workspace=tempdir, evidence_store=InMemoryEvidenceStore())
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
            ).run_call(sample_piworker_call(), workspace=tempdir, evidence_store=InMemoryEvidenceStore())
            output = json.loads(
                Path(tempdir, "attempts/WU-000001/pi_agent_output.json").read_text(encoding="utf-8")
            )

        self.assertEqual(result.worker_result.status, "failed")
        self.assertEqual(output["status"], "failed")
        self.assertIn("savepoint artifact is missing", " ".join(output["failures"]))

    def test_resume_payload_carries_explicit_summary_artifact_refs(self) -> None:
        runner = RecordingRunner()
        adapter = PiAgentRuntimeAdapter(
            PiAgentRuntimeConfig(command=("pi-agent-runtime",)),
            runner=runner,
        ).with_resume(
            savepoint_ref="attempts/WU-000001/pi_agent_savepoints.jsonl#turn=1",
            session_ref="attempts/WU-000001/pi_agent_session.jsonl",
            events_ref="attempts/WU-000001/pi_agent_events.jsonl",
            summary_artifact_refs=("attempts/WU-000001/context/summary.json",),
            follow_up_prompt="Continue using the explicit context summary artifact.",
        )

        with tempfile.TemporaryDirectory() as tempdir:
            adapter.run_call(sample_piworker_call(), workspace=tempdir, evidence_store=InMemoryEvidenceStore())

        assert runner.captured_input is not None
        self.assertEqual(
            runner.captured_input["resume"]["summary_artifact_refs"],
            ["attempts/WU-000001/context/summary.json"],
        )
        self.assertEqual(
            runner.captured_input["resume"]["resume_prompt"],
            "Continue using the explicit context summary artifact.",
        )

    def test_out_of_scope_produced_artifact_is_rewritten_as_failure(self) -> None:
        runner = RecordingRunner(
            output_payload={
                "schema_version": PI_AGENT_OUTPUT_SCHEMA_VERSION,
                "call_id": "WU-000001",
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
            ).run_call(sample_piworker_call(), workspace=tempdir, evidence_store=InMemoryEvidenceStore())

        self.assertEqual(result.worker_result.status, "failed")
        self.assertIn("outside/SKILL.md", result.execution_report.produced_artifacts)

    def test_default_command_invokes_node_faux_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            result = PiAgentRuntimeAdapter(PiAgentRuntimeConfig()).run_call(
                sample_piworker_call(),
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
            self.assertTrue((root / "attempts/WU-000001/context/tool_observations.jsonl").exists())
            self.assertTrue((root / "attempts/WU-000001/context/projection.json").exists())

    def test_pi_agent_executor_node_preserves_packet_hash(self) -> None:
        runner = RecordingRunner()
        adapter = PiAgentRuntimeAdapter(PiAgentRuntimeConfig(command=("pi-agent-runtime",)), runner=runner)
        packet = AgentExecutionPacket(
            packet_id="WU-000001",
            contract_id="contract-001",
            contract_hash="sha256:" + "a" * 64,
            contract_ref="contract/task_contract.json",
            worker_brief_ref="projections/worker_brief.json",
            workspace_policy_ref="policy/workspace_policy.json",
            permission_manifest_ref="policy/permission_manifest.json",
            report_ref="reports/execution_report.json",
            expected_artifact_refs=["package/SKILL.md"],
            allowed_input_refs=["contract/task_contract.json", "projections/worker_brief.json"],
            writable_refs=["package", "reports"],
        )

        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            report = PiAgentExecutorNode(workspace_root=tempdir, adapter=adapter).execute(
                packet,
                packet_ref="packets/execution_packet.json",
                workspace=object(),
            )
            call_result_payload = json.loads(
                (root / "attempts/WU-000001/piworker_call_result.json").read_text(encoding="utf-8")
            )
            self.assertTrue((root / "reports/piworker_runtime/WU-000001/call_result_projection.json").exists())
            self.assertTrue((root / "reports/piworker_runtime/WU-000001/metrics_projection.json").exists())

        self.assertEqual(report.status, AgentExecutionStatus.COMPLETED)
        self.assertEqual(report.produced_artifact_refs, ["package/SKILL.md"])
        self.assertEqual(report.packet_hash, stable_json_hash(packet.to_dict()))
        self.assertEqual(report.changed_refs, ["package/SKILL.md"])
        self.assertEqual(report.evidence_refs, ["reports/piworker_runtime/WU-000001/call_result_projection.json"])
        self.assertEqual(report.metric_refs, ["reports/piworker_runtime/WU-000001/metrics_projection.json"])
        call_result = PiWorkerCallResult.from_dict(call_result_payload)
        self.assertEqual(call_result.output_refs, ["package/SKILL.md"])
        self.assertEqual(call_result.metric_refs, ["attempts/WU-000001/pi_agent_metrics.json"])

    def test_pi_agent_executor_node_does_not_project_to_work_unit_contract(self) -> None:
        runner = RecordingRunner()
        adapter = PiAgentRuntimeAdapter(PiAgentRuntimeConfig(command=("pi-agent-runtime",)), runner=runner)
        packet = AgentExecutionPacket(
            packet_id="WU-000001",
            contract_id="contract-001",
            contract_hash="sha256:" + "a" * 64,
            contract_ref="contract/task_contract.json",
            worker_brief_ref="projections/worker_brief.json",
            workspace_policy_ref="policy/workspace_policy.json",
            permission_manifest_ref="policy/permission_manifest.json",
            report_ref="reports/execution_report.json",
            expected_artifact_refs=["package/SKILL.md"],
            allowed_input_refs=["contract/task_contract.json", "projections/worker_brief.json"],
            writable_refs=["package", "reports"],
        )

        self.assertFalse(hasattr(PiWorkerCall, "to_work_unit_contract"))

        with tempfile.TemporaryDirectory() as tempdir:
            report = PiAgentExecutorNode(workspace_root=tempdir, adapter=adapter).execute(
                packet,
                packet_ref="packets/execution_packet.json",
                workspace=object(),
            )

        self.assertEqual(report.status, AgentExecutionStatus.COMPLETED)
        self.assertIsNotNone(runner.captured_input)
        self.assertNotIn("work_unit_contract", runner.captured_input)
        self.assertEqual(runner.captured_input["call_spec"]["call_id"], "WU-000001")  # type: ignore[index]
        self.assertEqual(runner.captured_input["call_spec"]["allowed_scope"], ["package", "reports"])  # type: ignore[index]

    def test_run_call_rejects_call_spec_that_widens_piworker_scope(self) -> None:
        packet = AgentExecutionPacket(
            packet_id="WU-000001",
            contract_id="contract-001",
            contract_hash="sha256:" + "a" * 64,
            contract_ref="contract/task_contract.json",
            worker_brief_ref="projections/worker_brief.json",
            workspace_policy_ref="policy/workspace_policy.json",
            permission_manifest_ref="policy/permission_manifest.json",
            report_ref="reports/execution_report.json",
            expected_artifact_refs=["package/SKILL.md"],
            allowed_input_refs=["contract/task_contract.json", "projections/worker_brief.json"],
            writable_refs=["package"],
        )
        call = PiWorkerCall.from_execution_packet(packet, packet_ref="packets/execution_packet.json")
        widened_call_spec = replace(PiAgentCallSpec.from_call(call), allowed_scope=["package", "outside"])

        with tempfile.TemporaryDirectory() as tempdir:
            with self.assertRaisesRegex(ContractValidationError, "allowed_scope"):
                PiAgentRuntimeAdapter(PiAgentRuntimeConfig(command=("pi-agent-runtime",)), runner=RecordingRunner()).run_call(
                    call,
                    workspace=tempdir,
                    evidence_store=InMemoryEvidenceStore(),
                    call_spec=widened_call_spec,
                )

    def test_pi_agent_judge_node_preserves_packet_hash_and_report_ref(self) -> None:
        runner = JudgeRecordingRunner()
        adapter = PiAgentRuntimeAdapter(PiAgentRuntimeConfig(command=("pi-agent-runtime",)), runner=runner)
        packet = sample_judge_packet()

        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            (root / "contract").mkdir(parents=True, exist_ok=True)
            (root / "projections").mkdir(parents=True, exist_ok=True)
            (root / "packets").mkdir(parents=True, exist_ok=True)
            (root / "reports").mkdir(parents=True, exist_ok=True)
            (root / "artifacts").mkdir(parents=True, exist_ok=True)
            (root / "contract/task_contract.json").write_text(
                '{"schema_version":"task_contract.v1","contract_id":"contract-001","contract_hash":"sha256:'
                + "a" * 64
                + '"}\n',
                encoding="utf-8",
            )
            (root / "projections/judge_rubric.json").write_text("{}\n", encoding="utf-8")
            (root / "packets/execution_packet.json").write_text(
                json.dumps(execution_packet_payload(), sort_keys=True, indent=2) + "\n",
                encoding="utf-8",
            )
            (root / "reports/execution_report.json").write_text(
                json.dumps(execution_report_payload(), sort_keys=True, indent=2) + "\n",
                encoding="utf-8",
            )
            (root / "reports/hard_checks.json").write_text('{"status":"passed"}\n', encoding="utf-8")
            (root / "reports/tool_events.jsonl").write_text("{}\n", encoding="utf-8")
            (root / "artifacts/final.md").write_text("# final\n", encoding="utf-8")
            (root / "attempts/WU-000001/context/raw").mkdir(parents=True, exist_ok=True)
            (root / "attempts/WU-000001/context/raw/executor-output.txt").write_text(
                "executor raw output body\n",
                encoding="utf-8",
            )
            (root / "attempts/WU-000001/context/tool_observations.jsonl").write_text(
                '{"raw_ref":"attempts/WU-000001/context/raw/executor-output.txt"}\n',
                encoding="utf-8",
            )

            report = PiAgentJudgeNode(workspace_root=tempdir, adapter=adapter).judge(
                packet,
                packet_ref="packets/judge_packet.json",
                workspace=object(),
            )
            call_result_payload = json.loads(
                (root / "attempts/judge-packet-001/piworker_call_result.json").read_text(encoding="utf-8")
            )

            self.assertEqual(report.decision, JudgeReportDecision.ACCEPTED)
            self.assertEqual(report.packet_hash, stable_json_hash(packet.to_dict()))
            self.assertTrue((root / "reports/judge_report.json").exists())
            self.assertIsNotNone(runner.captured_input)
            self.assertEqual(
                runner.captured_input["permission_manifest"]["writable_refs"],
                [
                    "reports/judge_report.json",
                    "reports/judge_rationale.md",
                    "projections/repair_brief.json",
                    "revisions/request.json",
                ],
            )
            self.assertNotIn(
                "attempts/WU-000001/context/raw",
                runner.captured_input["permission_manifest"]["readable_refs"],
            )
            self.assertNotIn(
                "attempts/WU-000001/context/tool_observations.jsonl",
                runner.captured_input["permission_manifest"]["readable_refs"],
            )
            self.assertNotIn("executor raw output body", json.dumps(runner.captured_input, sort_keys=True))
            self.assertEqual(runner.captured_input["call_spec"]["visible_refs"][0], "attempts/judge-packet-001/judge_node_spec.json")
            call_result = PiWorkerCallResult.from_dict(call_result_payload)
            self.assertEqual(call_result.output_refs, ["reports/judge_report.json"])

    def test_pi_agent_judge_node_rejects_failed_hard_checks(self) -> None:
        packet = sample_judge_packet()
        packet_payload = packet.to_dict()
        packet_payload["hard_check_status"] = "failed"
        failed_packet = JudgePacket.from_dict(packet_payload)
        runner = JudgeRecordingRunner(
            report_payload={
                "schema_version": "judge_report.v1",
                "report_id": "judge-report-001",
                "packet_id": "judge-packet-001",
                "packet_ref": "packets/judge_packet.json",
                "packet_hash": stable_json_hash(failed_packet.to_dict()),
                "contract_id": "contract-001",
                "contract_hash": "sha256:" + "a" * 64,
                "contract_ref": "contract/task_contract.json",
                "decision": "rejected",
                "hard_check_status": "failed",
                "rationale_refs": ["reports/judge_rationale.md"],
                "evidence_refs": ["reports/execution_report.json"],
                "accepted_artifact_refs": [],
            }
        )
        adapter = PiAgentRuntimeAdapter(PiAgentRuntimeConfig(command=("pi-agent-runtime",)), runner=runner)

        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            (root / "contract").mkdir(parents=True, exist_ok=True)
            (root / "projections").mkdir(parents=True, exist_ok=True)
            (root / "packets").mkdir(parents=True, exist_ok=True)
            (root / "reports").mkdir(parents=True, exist_ok=True)
            (root / "artifacts").mkdir(parents=True, exist_ok=True)
            (root / "contract/task_contract.json").write_text(
                '{"schema_version":"task_contract.v1","contract_id":"contract-001","contract_hash":"sha256:'
                + "a" * 64
                + '"}\n',
                encoding="utf-8",
            )
            (root / "projections/judge_rubric.json").write_text("{}\n", encoding="utf-8")
            (root / "packets/execution_packet.json").write_text(
                json.dumps(execution_packet_payload(), sort_keys=True, indent=2) + "\n",
                encoding="utf-8",
            )
            (root / "reports/execution_report.json").write_text(
                json.dumps(execution_report_payload(), sort_keys=True, indent=2) + "\n",
                encoding="utf-8",
            )
            (root / "reports/hard_checks.json").write_text('{"status":"failed"}\n', encoding="utf-8")
            (root / "reports/tool_events.jsonl").write_text("{}\n", encoding="utf-8")
            (root / "artifacts/final.md").write_text("# final\n", encoding="utf-8")

            report = PiAgentJudgeNode(workspace_root=tempdir, adapter=adapter).judge(
                failed_packet,
                packet_ref="packets/judge_packet.json",
                workspace=object(),
            )

        self.assertEqual(report.decision, JudgeReportDecision.REJECTED)
        self.assertEqual(report.hard_check_status, HardCheckStatus.FAILED)

    @unittest.skipUnless(
        os.environ.get("MISSIONFORGE_JUDGE_LIVE_SMOKE") == "1",
        "set MISSIONFORGE_JUDGE_LIVE_SMOKE=1 to run the live Judge PiWorker smoke",
    )
    def test_live_codex_current_judge_accepts_tiny_artifact_without_secret_leak(self) -> None:
        provider = load_codex_current_provider()
        self.assertEqual(provider["wire_api"], "responses")
        config = PiAgentRuntimeConfig(
            timeout_seconds=int(os.environ.get("MISSIONFORGE_PI_AGENT_LIVE_TIMEOUT_SECONDS", "240")),
            provider_mode="live",
            provider_config_source="codex_current",
            metadata={"phase": "judge_live_smoke"},
        )
        packet = sample_judge_packet()

        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            (root / "contract").mkdir(parents=True, exist_ok=True)
            (root / "projections").mkdir(parents=True, exist_ok=True)
            (root / "packets").mkdir(parents=True, exist_ok=True)
            (root / "reports").mkdir(parents=True, exist_ok=True)
            (root / "artifacts").mkdir(parents=True, exist_ok=True)
            (root / "contract/task_contract.json").write_text(
                '{"schema_version":"task_contract.v1","contract_id":"contract-001","contract_hash":"sha256:'
                + "a" * 64
                + '"}\n',
                encoding="utf-8",
            )
            (root / "projections/judge_rubric.json").write_text(
                json.dumps(
                    {
                        "schema_version": "judge_rubric.v1",
                        "role": "judge_piworker",
                        "rubric_id": "judge-live-smoke",
                        "contract_id": "contract-001",
                        "contract_ref": "contract/task_contract.json",
                        "hard_check_refs": ["reports/hard_checks.json"],
                        "accepted_artifact_refs": ["artifacts/final.md"],
                        "decision_policy": {
                            "accept": [
                                "execution_report.status == completed",
                                "hard_check_status == passed",
                                "artifacts/final.md exists",
                                "artifacts/final.md contains MissionForge FrontDesk live smoke passed",
                            ],
                            "reject": ["otherwise"],
                        },
                    },
                    sort_keys=True,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            (root / "packets/execution_packet.json").write_text(
                json.dumps(execution_packet_payload(), sort_keys=True, indent=2) + "\n",
                encoding="utf-8",
            )
            (root / "reports/execution_report.json").write_text(
                json.dumps(execution_report_payload(), sort_keys=True, indent=2) + "\n",
                encoding="utf-8",
            )
            (root / "reports/hard_checks.json").write_text('{"status":"passed"}\n', encoding="utf-8")
            (root / "reports/tool_events.jsonl").write_text("{}\n", encoding="utf-8")
            (root / "artifacts/final.md").write_text("MissionForge FrontDesk live smoke passed\n", encoding="utf-8")

            report = PiAgentJudgeNode(workspace_root=tempdir, adapter=PiAgentRuntimeAdapter(config)).judge(
                packet,
                packet_ref="packets/judge_packet.json",
                workspace=object(),
            )
            serialized_workspace = "\n".join(
                path.read_text(encoding="utf-8", errors="replace") for path in root.rglob("*") if path.is_file()
            )

        self.assertEqual(report.decision, JudgeReportDecision.ACCEPTED)
        self.assertEqual(report.packet_hash, stable_json_hash(packet.to_dict()))
        self.assertNotIn("OPENAI_API_KEY", serialized_workspace)
        self.assertNotIn("MISSIONFORGE_PI_AGENT_API_KEY", serialized_workspace)

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
