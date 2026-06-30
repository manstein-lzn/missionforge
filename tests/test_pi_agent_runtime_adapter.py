from __future__ import annotations

from dataclasses import dataclass, replace
import json
import os
from pathlib import Path
import tempfile
import unittest

from missionforge.adapters.pi_agent_runtime import (
    PI_AGENT_OUTPUT_SCHEMA_VERSION,
    PiAgentCommandResult,
    PiAgentRuntimeAdapter,
    PiAgentCallSpec,
    PiAgentRuntimeConfig,
    SubprocessPiAgentCommandRunner,
)
from missionforge.contracts import ContractValidationError
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
    projected_observations: tuple[dict[str, object], ...] = ()
    context_observation_lines: tuple[dict[str, object], ...] = ()

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
            _write_text(
                cwd / context_observations_ref,
                "".join(json.dumps(item, sort_keys=True) + "\n" for item in self.context_observation_lines),
            )
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
                        "projected_observations": list(self.projected_observations),
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

    def test_call_spec_from_call_does_not_make_permission_manifest_visible(self) -> None:
        call = replace(sample_piworker_call(), permission_manifest_ref="policy/permission_manifest.json")

        spec = PiAgentCallSpec.from_call(call)

        self.assertEqual(spec.visible_refs, ["mission/frozen_contract.json"])
        self.assertNotIn("policy/permission_manifest.json", spec.visible_refs)

    def test_adapter_requires_explicit_filesystem_workspace(self) -> None:
        runner = RecordingRunner()

        with self.assertRaisesRegex(ContractValidationError, "explicit filesystem workspace"):
            PiAgentRuntimeAdapter(
                PiAgentRuntimeConfig(command=("pi-agent-runtime",)),
                runner=runner,
            ).run_call(sample_piworker_call(), evidence_store=InMemoryEvidenceStore())

        self.assertIsNone(runner.captured_input)

    def test_adapter_rejects_visible_ref_outside_runtime_permission_manifest_before_runner(self) -> None:
        runner = RecordingRunner()
        call = replace(sample_piworker_call(), permission_manifest_ref="policy/permission_manifest.json")

        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            (root / "policy").mkdir(parents=True, exist_ok=True)
            (root / "policy/permission_manifest.json").write_text(
                json.dumps(
                    {
                        "schema_version": "permission_manifest.v1",
                        "manifest_id": "narrow",
                        "workspace_policy_ref": "policy/workspace_policy.json",
                        "readable_refs": ["other/input.json"],
                        "writable_refs": ["package"],
                        "denied_refs": [],
                        "allowed_tools": ["read", "write", "edit"],
                        "allowed_commands": [],
                        "network_policy": "disabled",
                        "env_allowlist": [],
                        "secret_ref": None,
                        "unsupported_hard_policies": [],
                        "extension_grants": [],
                    },
                    sort_keys=True,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ContractValidationError, "visible ref is not readable"):
                PiAgentRuntimeAdapter(
                    PiAgentRuntimeConfig(command=("pi-agent-runtime",)),
                    runner=runner,
                ).run_call(call, workspace=root, evidence_store=InMemoryEvidenceStore())

        self.assertIsNone(runner.captured_input)

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
            self.assertIsNone(input_payload["long_memory_packet_ref"])
            self.assertEqual(
                input_payload["context_engine"],
                {
                    "schema_version": "missionforge.pi_agent_context_engine.v1",
                    "enabled": False,
                    "context_view_ref": None,
                    "context_compile_request_ref": None,
                    "context_compile_result_ref": None,
                    "context_baseline_ref": None,
                    "context_source_snapshot_ref": None,
                    "context_epoch_ref": None,
                    "context_cache_layout_ref": None,
                    "context_pressure_ref": None,
                    "context_turn_safe_point_ref": None,
                    "context_turn_boundary_ref": None,
                    "context_hash": None,
                    "context_compile_action": "",
                },
            )
            self.assertEqual(
                input_payload["context_projection_config"],
                {
                    "schema_version": "missionforge.pi_agent_context_projection_config.v1",
                    "large_observation_bytes": 8192,
                    "soft_compact_ratio": 0.8,
                    "hard_compact_ratio": 0.9,
                    "cache_aware": True,
                },
            )
            self.assertEqual(input_payload["permission_manifest"]["schema_version"], "permission_manifest.v1")
            self.assertEqual(input_payload["permission_manifest"]["writable_refs"], ["package"])
            self.assertEqual(input_payload["permission_manifest"]["allowed_tools"], ["read", "write", "edit"])
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
            self.assertEqual(projection_payload["context_projection_config"]["soft_compact_ratio"], 0.8)
            self.assertEqual(projection_payload["context_projection_config"]["hard_compact_ratio"], 0.9)
            self.assertIs(projection_payload["context_projection_config"]["cache_aware"], True)
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

    def test_adapter_passes_kernel_context_engine_refs_to_sidecar_input(self) -> None:
        runner = RecordingRunner()
        call = replace(
            sample_piworker_call(),
            metadata={
                "context_projection_ref": "kernel/demo-flow/steps/researcher/context_projection.json",
                "context_compile_request_ref": "kernel/demo-flow/steps/researcher/context/compile_request.json",
                "context_compile_result_ref": "kernel/demo-flow/steps/researcher/context/compile_result.json",
                "context_baseline_ref": "kernel/demo-flow/steps/researcher/context/baseline.json",
                "context_source_snapshot_ref": "kernel/demo-flow/steps/researcher/context/source_snapshot.json",
                "context_epoch_ref": "kernel/demo-flow/steps/researcher/context/epoch.json",
                "context_cache_layout_ref": "kernel/demo-flow/steps/researcher/context/cache_layout.json",
                "context_pressure_ref": "kernel/demo-flow/steps/researcher/context/pressure.json",
                "context_turn_safe_point_ref": "kernel/demo-flow/steps/researcher/context/turn_safe_point.json",
                "context_turn_boundary_ref": "kernel/demo-flow/steps/researcher/context/turn_boundary.json",
                "context_hash": "sha256:" + "b" * 64,
                "context_compile_action": "continue",
            },
        )

        with tempfile.TemporaryDirectory() as tempdir:
            PiAgentRuntimeAdapter(
                PiAgentRuntimeConfig(command=("pi-agent-runtime",)),
                runner=runner,
            ).run_call(call, workspace=tempdir, evidence_store=InMemoryEvidenceStore())

        context_engine = runner.captured_input["context_engine"]
        self.assertTrue(context_engine["enabled"])
        self.assertEqual(
            context_engine["context_view_ref"],
            "kernel/demo-flow/steps/researcher/context_projection.json",
        )
        self.assertEqual(
            context_engine["context_compile_result_ref"],
            "kernel/demo-flow/steps/researcher/context/compile_result.json",
        )
        self.assertEqual(
            context_engine["context_cache_layout_ref"],
            "kernel/demo-flow/steps/researcher/context/cache_layout.json",
        )
        self.assertEqual(context_engine["context_hash"], "sha256:" + "b" * 64)
        self.assertEqual(context_engine["context_compile_action"], "continue")

    def test_adapter_rejects_retry_context_engine_refs_without_same_boundary_declaration(self) -> None:
        runner = RecordingRunner()
        call = replace(
            sample_piworker_call(),
            call_id="WU-000001-attempt-001",
            metadata={
                "kernel_parent_call_id": "WU-000001",
                "context_projection_ref": "kernel/demo-flow/steps/researcher/context_projection.json",
                "context_compile_result_ref": "kernel/demo-flow/steps/researcher/context/compile_result.json",
                "context_turn_boundary_ref": "kernel/demo-flow/steps/researcher/context/turn_boundary.json",
            },
        )

        with tempfile.TemporaryDirectory() as tempdir:
            with self.assertRaisesRegex(ContractValidationError, "same_preflight_boundary"):
                PiAgentRuntimeAdapter(
                    PiAgentRuntimeConfig(command=("pi-agent-runtime",)),
                    runner=runner,
                ).run_call(call, workspace=tempdir, evidence_store=InMemoryEvidenceStore())

        self.assertIsNone(runner.captured_input)

    def test_adapter_accepts_retry_context_engine_refs_with_same_boundary_declaration(self) -> None:
        runner = RecordingRunner()
        call = replace(
            sample_piworker_call(),
            call_id="WU-000001-attempt-001",
            metadata={
                "kernel_parent_call_id": "WU-000001",
                "context_boundary_reuse": "same_preflight_boundary",
                "context_parent_call_id": "WU-000001",
                "context_parent_compile_result_ref": "kernel/demo-flow/steps/researcher/context/compile_result.json",
                "context_parent_turn_boundary_ref": "kernel/demo-flow/steps/researcher/context/turn_boundary.json",
                "context_parent_epoch_ref": "kernel/demo-flow/steps/researcher/context/epoch.json",
                "context_projection_ref": "kernel/demo-flow/steps/researcher/context_projection.json",
                "context_compile_result_ref": "kernel/demo-flow/steps/researcher/context/compile_result.json",
                "context_epoch_ref": "kernel/demo-flow/steps/researcher/context/epoch.json",
                "context_turn_boundary_ref": "kernel/demo-flow/steps/researcher/context/turn_boundary.json",
            },
        )

        with tempfile.TemporaryDirectory() as tempdir:
            PiAgentRuntimeAdapter(
                PiAgentRuntimeConfig(command=("pi-agent-runtime",)),
                runner=runner,
            ).run_call(call, workspace=tempdir, evidence_store=InMemoryEvidenceStore())

        self.assertIsNotNone(runner.captured_input)
        self.assertTrue(runner.captured_input["context_engine"]["enabled"])
        self.assertEqual(
            runner.captured_input["context_engine"]["context_compile_result_ref"],
            "kernel/demo-flow/steps/researcher/context/compile_result.json",
        )

    def test_adapter_materializes_tool_output_projection_records_from_sidecar_diagnostics(self) -> None:
        runner = RecordingRunner(
            projected_observations=(
                {
                    "observation_id": "tool-observation-000001",
                    "tool_call_id": "call-1",
                    "tool_name": "bash",
                    "status": "ok",
                    "inline_policy": "demote_after_turn",
                    "content_hash": "sha256:" + "1" * 64,
                    "content_bytes": 12000,
                    "content_lines": 200,
                    "raw_ref": "attempts/WU-000001/context/raw/000001-bash-call-1-output.txt",
                    "projected_bytes": 400,
                },
            )
        )

        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            result = PiAgentRuntimeAdapter(
                PiAgentRuntimeConfig(command=("pi-agent-runtime",)),
                runner=runner,
            ).run_call(sample_piworker_call(), workspace=root, evidence_store=InMemoryEvidenceStore())
            report_payload = json.loads(
                (root / "attempts/WU-000001/pi_agent_execution_report.json").read_text(encoding="utf-8")
            )
            index_ref = report_payload["metrics"]["tool_output_projection_index_ref"]
            index_payload = json.loads((root / index_ref).read_text(encoding="utf-8"))
            record_ref = index_payload["record_refs"][0]
            projection_ref = index_payload["projection_refs"][0]
            record_payload = json.loads((root / record_ref).read_text(encoding="utf-8"))
            projection_text = (root / projection_ref).read_text(encoding="utf-8")

        self.assertEqual(result.execution_report.metrics["tool_output_projection_count"], 1)
        self.assertEqual(index_payload["schema_version"], "missionforge.tool_output_projection_index.v1")
        self.assertEqual(record_payload["schema_version"], "missionforge.tool_output_projection.v1")
        self.assertEqual(record_payload["policy"], "ref_stub")
        self.assertEqual(record_payload["raw_ref"], "attempts/WU-000001/context/raw/000001-bash-call-1-output.txt")
        self.assertIn("raw_ref: attempts/WU-000001/context/raw/000001-bash-call-1-output.txt", projection_text)
        self.assertIn(index_ref, report_payload["changed_refs"])
        self.assertIn(record_ref, report_payload["changed_refs"])
        self.assertIn(projection_ref, report_payload["changed_refs"])

    def test_adapter_builds_thrash_diagnostics_from_repeated_read_observations(self) -> None:
        source_hash = "sha256:" + "2" * 64
        read_observation = {
            "schema_version": "missionforge.pi_agent_tool_observation.v1",
            "observation_id": "tool-observation-000001",
            "call_id": "WU-000001",
            "turn_index": 1,
            "tool_call_id": "read-call-1",
            "tool_name": "read",
            "status": "ok",
            "created_at": "2026-01-01T00:00:00+00:00",
            "content_hash": "sha256:" + "1" * 64,
            "content_bytes": 10,
            "content_lines": 1,
            "inline_policy": "keep",
            "source_ref": "sources/source_packet.json",
            "source_range": {"offset": 1, "limit": 20},
            "source_hash": source_hash,
            "source_bytes": 200,
        }
        runner = RecordingRunner(
            context_observation_lines=(
                read_observation,
                {**read_observation, "observation_id": "tool-observation-000002", "tool_call_id": "read-call-2"},
            )
        )

        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            result = PiAgentRuntimeAdapter(
                PiAgentRuntimeConfig(command=("pi-agent-runtime",)),
                runner=runner,
            ).run_call(sample_piworker_call(), workspace=root, evidence_store=InMemoryEvidenceStore())
            report_payload = json.loads(
                (root / "attempts/WU-000001/pi_agent_execution_report.json").read_text(encoding="utf-8")
            )
            diagnostics_ref = report_payload["metrics"]["context_thrash_diagnostics_ref"]
            diagnostics_payload = json.loads((root / diagnostics_ref).read_text(encoding="utf-8"))

        self.assertEqual(result.execution_report.metrics["context_read_observation_count"], 1)
        self.assertEqual(result.execution_report.metrics["context_repeated_read_count"], 1)
        self.assertEqual(diagnostics_payload["schema_version"], "missionforge.context_thrash_diagnostics.v1")
        self.assertEqual(diagnostics_payload["recommended_action"], "prepare_checkpoint")
        self.assertEqual(diagnostics_payload["repeated_observation_ids"], ["read-000001"])
        self.assertEqual(diagnostics_payload["observations"][0]["source_ref"], "sources/source_packet.json")
        self.assertEqual(diagnostics_payload["observations"][0]["source_hash"], source_hash)
        self.assertEqual(diagnostics_payload["observations"][0]["source_range"], {"limit": 20, "offset": 1})
        self.assertEqual(diagnostics_payload["observations"][0]["count"], 2)
        self.assertNotIn("source body", json.dumps(diagnostics_payload).lower())
        self.assertIn(diagnostics_ref, report_payload["changed_refs"])

    def test_adapter_treats_existing_expected_refs_as_output_package_refs(self) -> None:
        runner = RecordingRunner()
        call = replace(
            sample_piworker_call(),
            expected_output_refs=["package/SKILL.md", "package/existing.md"],
        )

        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            (root / "package").mkdir(parents=True)
            (root / "package/existing.md").write_text("# Existing\n", encoding="utf-8")

            result = PiAgentRuntimeAdapter(
                PiAgentRuntimeConfig(command=("pi-agent-runtime",)),
                runner=runner,
            ).run_call(call, workspace=root, evidence_store=InMemoryEvidenceStore())
            call_result = PiWorkerCallResult.from_worker_adapter_result(call, result)

        self.assertEqual(result.worker_result.status, "completed")
        self.assertEqual(result.execution_report.produced_artifacts, ["package/SKILL.md", "package/existing.md"])
        self.assertIn("package/SKILL.md", result.execution_report.changed_refs)
        self.assertNotIn("package/existing.md", result.execution_report.changed_refs)
        self.assertEqual(call_result.output_refs, ["package/SKILL.md", "package/existing.md"])

    def test_adapter_recovers_failed_runtime_when_complete_artifact_package_was_written(self) -> None:
        output_ref = "attempts/WU-000001/pi_agent_output.json"
        session_ref = "attempts/WU-000001/pi_agent_session.jsonl"
        events_ref = "attempts/WU-000001/pi_agent_events.jsonl"
        metrics_ref = "attempts/WU-000001/pi_agent_metrics.json"
        savepoints_ref = "attempts/WU-000001/pi_agent_savepoints.jsonl"
        context_observations_ref = "attempts/WU-000001/context/tool_observations.jsonl"
        context_projection_ref = "attempts/WU-000001/context/projection.json"
        runner = RecordingRunner(
            output_payload={
                "schema_version": PI_AGENT_OUTPUT_SCHEMA_VERSION,
                "call_id": "WU-000001",
                "status": "failed",
                "produced_artifacts": ["package/SKILL.md"],
                "changed_refs": [
                    "package/SKILL.md",
                    output_ref,
                    session_ref,
                    events_ref,
                    metrics_ref,
                    savepoints_ref,
                    context_observations_ref,
                    context_projection_ref,
                ],
                "commands_run": [],
                "tests_run": [],
                "failures": ["OpenAI API error (403): insufficient balance"],
                "worker_claims": [],
                "verifier_evidence": [
                    "package/SKILL.md",
                    output_ref,
                    events_ref,
                    metrics_ref,
                    savepoints_ref,
                    context_observations_ref,
                    context_projection_ref,
                ],
                "new_unknowns": [],
                "recommended_next_steps": ["Inspect provider failure."],
                "verification_status": "failed",
                "input_ref": "attempts/WU-000001/pi_agent_input.json",
                "output_ref": output_ref,
                "session_ref": session_ref,
                "events_ref": events_ref,
                "metrics_ref": metrics_ref,
                "savepoints_ref": savepoints_ref,
                "context_observations_ref": context_observations_ref,
                "context_projection_ref": context_projection_ref,
                "duration_ms": 1,
                "metrics": {"tool_error_count": 1, "total_tokens": 123},
            }
        )

        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            result = PiAgentRuntimeAdapter(
                PiAgentRuntimeConfig(command=("pi-agent-runtime",)),
                runner=runner,
            ).run_call(sample_piworker_call(), workspace=root, evidence_store=InMemoryEvidenceStore())
            sidecar_payload = json.loads((root / output_ref).read_text(encoding="utf-8"))

        self.assertEqual(result.worker_result.status, "completed")
        self.assertEqual(result.execution_report.status, "completed")
        self.assertEqual(result.execution_report.produced_artifacts, ["package/SKILL.md"])
        self.assertTrue(result.execution_report.metrics["artifact_package_recovered_after_runtime_failure"])
        self.assertEqual(sidecar_payload["status"], "completed")
        self.assertEqual(sidecar_payload["verification_status"], "review_required")
        self.assertIn("OpenAI API error", json.dumps(sidecar_payload["failures"]))
        self.assertTrue(sidecar_payload["metrics"]["artifact_package_recovered_after_runtime_failure"])

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

    def test_adapter_passes_context_pressure_config(self) -> None:
        runner = RecordingRunner()
        config = PiAgentRuntimeConfig(
            command=("pi-agent-runtime",),
            context_large_observation_bytes=4096,
            context_soft_compact_ratio=0.7,
            context_hard_compact_ratio=0.88,
            context_cache_aware=False,
        )

        with tempfile.TemporaryDirectory() as tempdir:
            PiAgentRuntimeAdapter(config, runner=runner).run_call(
                sample_piworker_call(),
                workspace=tempdir,
                evidence_store=InMemoryEvidenceStore(),
            )

        self.assertIsNotNone(runner.captured_input)
        self.assertEqual(
            runner.captured_input["context_projection_config"],  # type: ignore[index]
            {
                "schema_version": "missionforge.pi_agent_context_projection_config.v1",
                "large_observation_bytes": 4096,
                "soft_compact_ratio": 0.7,
                "hard_compact_ratio": 0.88,
                "cache_aware": False,
            },
        )

    def test_adapter_passes_long_memory_packet_ref(self) -> None:
        runner = RecordingRunner()
        config = PiAgentRuntimeConfig(
            command=("pi-agent-runtime",),
            long_memory_packet_ref="attempts/WU-000001/context/long_memory_packet.json",
        )

        with tempfile.TemporaryDirectory() as tempdir:
            PiAgentRuntimeAdapter(config, runner=runner).run_call(
                sample_piworker_call(),
                workspace=tempdir,
                evidence_store=InMemoryEvidenceStore(),
            )

        self.assertIsNotNone(runner.captured_input)
        self.assertEqual(
            runner.captured_input["long_memory_packet_ref"],  # type: ignore[index]
            "attempts/WU-000001/context/long_memory_packet.json",
        )

    def test_adapter_rejects_long_memory_packet_ref_outside_attempt_dir(self) -> None:
        runner = RecordingRunner()
        config = PiAgentRuntimeConfig(
            command=("pi-agent-runtime",),
            long_memory_packet_ref="context/long_memory_packet.json",
        )

        with tempfile.TemporaryDirectory() as tempdir:
            with self.assertRaisesRegex(ContractValidationError, "long_memory_packet_ref"):
                PiAgentRuntimeAdapter(config, runner=runner).run_call(
                    sample_piworker_call(),
                    workspace=tempdir,
                    evidence_store=InMemoryEvidenceStore(),
                )

        self.assertIsNone(runner.captured_input)

    def test_config_rejects_escaping_long_memory_packet_ref(self) -> None:
        with self.assertRaisesRegex(ContractValidationError, "long_memory_packet_ref"):
            PiAgentRuntimeConfig(
                command=("pi-agent-runtime",),
                long_memory_packet_ref="../long_memory_packet.json",
            )

    def test_with_repair_clones_adapter_with_repair_envelope(self) -> None:
        runner = RecordingRunner()
        adapter = PiAgentRuntimeAdapter(
            PiAgentRuntimeConfig(
                command=("pi-agent-runtime",),
                long_memory_packet_ref="attempts/WU-000001/context/long_memory_packet.json",
            ),
            runner=runner,
        )
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
        self.assertEqual(
            runner.captured_input["long_memory_packet_ref"],  # type: ignore[index]
            "attempts/WU-000001/context/long_memory_packet.json",
        )

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
        serialized_evidence = json.dumps(store.snapshot().to_dict(), sort_keys=True)
        self.assertNotIn(secret, serialized_evidence)
        self.assertNotIn("MISSIONFORGE_PI_AGENT_API_KEY", serialized_evidence)
        self.assertNotIn('"stdout"', serialized_evidence)
        self.assertNotIn('"stderr"', serialized_evidence)
        self.assertIn("stdout_summary", serialized_evidence)
        self.assertIn("stderr_summary", serialized_evidence)
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

    def test_resume_payload_carries_explicit_checkpoint_refs(self) -> None:
        runner = RecordingRunner()
        adapter = PiAgentRuntimeAdapter(
            PiAgentRuntimeConfig(command=("pi-agent-runtime",)),
            runner=runner,
        ).with_resume(
            savepoint_ref="attempts/WU-000001/pi_agent_savepoints.jsonl#turn=1",
            session_ref="attempts/WU-000001/pi_agent_session.jsonl",
            events_ref="attempts/WU-000001/pi_agent_events.jsonl",
            checkpoint_refs=("attempts/WU-000001/context/context_pressure_checkpoint.json",),
            summary_artifact_refs=("attempts/WU-000001/context/summary.json",),
            follow_up_prompt="Continue using the explicit context checkpoint.",
        )

        with tempfile.TemporaryDirectory() as tempdir:
            adapter.run_call(sample_piworker_call(), workspace=tempdir, evidence_store=InMemoryEvidenceStore())

        assert runner.captured_input is not None
        self.assertEqual(
            runner.captured_input["resume"]["checkpoint_refs"],
            ["attempts/WU-000001/context/context_pressure_checkpoint.json"],
        )
        self.assertEqual(
            runner.captured_input["resume"]["summary_artifact_refs"],
            ["attempts/WU-000001/context/summary.json"],
        )
        self.assertEqual(
            runner.captured_input["resume"]["resume_prompt"],
            "Continue using the explicit context checkpoint.",
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
            result = PiAgentRuntimeAdapter(
                PiAgentRuntimeConfig(),
                environ={"MISSIONFORGE_RUNTIME_HOME": str(Path(tempdir) / "runtime-home")},
            ).run_call(
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

    def test_run_call_rejects_call_spec_that_widens_piworker_scope(self) -> None:
        call = sample_piworker_call()
        widened_call_spec = replace(PiAgentCallSpec.from_call(call), allowed_scope=["package", "outside"])

        with tempfile.TemporaryDirectory() as tempdir:
            with self.assertRaisesRegex(ContractValidationError, "allowed_scope"):
                PiAgentRuntimeAdapter(PiAgentRuntimeConfig(command=("pi-agent-runtime",)), runner=RecordingRunner()).run_call(
                    call,
                    workspace=tempdir,
                    evidence_store=InMemoryEvidenceStore(),
                    call_spec=widened_call_spec,
                )

    def test_run_call_can_emit_runtime_progress_events(self) -> None:
        runner = RecordingRunner()
        emitted: list[dict] = []

        with tempfile.TemporaryDirectory() as tempdir:
            result = PiAgentRuntimeAdapter(
                PiAgentRuntimeConfig(command=("pi-agent-runtime",)),
                runner=runner,
            ).run_call(
                sample_piworker_call(),
                workspace=tempdir,
                evidence_store=InMemoryEvidenceStore(),
                runtime_progress_sink=emitted.append,
            )

        self.assertEqual(result.execution_report.status, "completed")
        self.assertGreaterEqual(len(emitted), 1)
        self.assertIn("PiWorker runtime started", emitted[0]["message"])
        self.assertIn("events", emitted[0]["refs"][0])

    def test_subprocess_runner_prepares_default_runtime_dependencies(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            runtime_dir = root / "runtime"
            dist_dir = runtime_dir / "dist"
            bin_dir = root / "bin"
            dist_dir.mkdir(parents=True)
            bin_dir.mkdir()
            (runtime_dir / "package.json").write_text('{"scripts":{"build":"true"}}\n', encoding="utf-8")
            (runtime_dir / "package-lock.json").write_text('{"lockfileVersion":3}\n', encoding="utf-8")
            npm_log = root / "npm.log"
            fake_npm = bin_dir / "npm"
            fake_npm.write_text(
                "#!/bin/sh\n"
                f"echo \"$@\" >> {npm_log}\n"
                "mkdir -p node_modules\n"
                "if [ \"$1\" = \"run\" ]; then mkdir -p dist; echo 'setup' > dist/main.js; fi\n",
                encoding="utf-8",
            )
            fake_node = bin_dir / "node"
            fake_node.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            fake_npm.chmod(0o755)
            fake_node.chmod(0o755)
            input_path = root / "input.json"
            input_path.write_text("{}\n", encoding="utf-8")
            env = {
                "PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}",
                "MISSIONFORGE_RUNTIME_HOME": str(root / "runtime-home"),
            }

            result = SubprocessPiAgentCommandRunner().run(
                ("node", str(dist_dir / "main.js")),
                input_path=input_path,
                cwd=root,
                timeout_seconds=10,
                env=env,
            )

            self.assertEqual(result.returncode, 0)
            log = npm_log.read_text(encoding="utf-8")
            self.assertIn("ci --ignore-scripts", log)


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
