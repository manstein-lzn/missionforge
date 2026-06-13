from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from missionforge import (
    AgentExecutionPacket,
    AgentExecutionReport,
    AgentExecutionStatus,
    AgentWorkspace,
    JudgePacket,
    JudgeReport,
    JudgeReportDecision,
)
from missionforge.adapters.pi_agent_runtime import (
    PI_AGENT_OUTPUT_SCHEMA_VERSION,
    PiAgentCommandResult,
    PiAgentRuntimeConfig,
)
from missionforge_skillfoundry import (
    SkillBundleManifest,
    SkillFoundryProductReport,
    run_skillfoundry_task_contract_bundle_build,
)
from missionforge_skillfoundry.registry import SkillFoundryRegistry
from missionforge_skillfoundry.workspace import read_json_ref

from test_product_contract import sample_request


class SkillFoundryRuntimeFacadeTests(unittest.TestCase):
    def test_task_contract_runtime_facade_builds_grades_registers_and_reports_prompt_only_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)

            report = run_skillfoundry_task_contract_bundle_build(
                sample_request(),
                workspace=root,
                executor=_TaskContractPackageExecutor(),
                judge=_TaskContractAcceptingJudge(),
            )
            run_root = root / "runs/demo-skill"
            registry = SkillFoundryRegistry.from_dict(
                read_json_ref(run_root, "registry/skillfoundry_registry.json", "registry")
            )
            report_payload = SkillFoundryProductReport.from_dict(
                read_json_ref(root, "reports/skillfoundry_product_report.json", "product_report")
            )
            run_report_payload = SkillFoundryProductReport.from_dict(
                read_json_ref(run_root, "reports/skillfoundry_product_report.json", "run_product_report")
            )

            self.assertEqual(report.final_status, "product_grade_registered")
            self.assertEqual(report_payload, report)
            self.assertEqual(run_report_payload.mission_ref, "contract/task_contract.json")
            self.assertEqual(registry.entries[0].status.value, "product_grade_registered")
            self.assertEqual(report.mission_ref, "runs/demo-skill/contract/task_contract.json")
            self.assertEqual(report.mission_run_id, "skillfoundry-demo-skill-taskcontract")
            self.assertEqual(report.product_grade_report_ref, "runs/demo-skill/qa/product_grade_report.json")
            self.assertTrue((run_root / "package/SKILL.md").exists())
            self.assertTrue((run_root / "package/skillfoundry.bundle.json").exists())
            self.assertTrue((run_root / "package/README.md").exists())
            self.assertTrue((run_root / "qa/product_grade_report.json").exists())

    def test_task_contract_runtime_facade_passes_config_to_default_piworker_flow(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            runner = _TaskContractPiRuntimeRunner()
            config = PiAgentRuntimeConfig(
                command=("pi-agent-runtime",),
                provider_mode="faux",
                provider_config_source="env",
                timeout_seconds=17,
                metadata={"test_marker": "skillfoundry_facade"},
            )

            report = run_skillfoundry_task_contract_bundle_build(
                sample_request(),
                workspace=root,
                pi_agent_config=config,
                piworker_runner=runner,
            )

            self.assertEqual(report.final_status, "product_grade_registered")
            self.assertEqual(
                [item["runtime"]["metadata"]["test_marker"] for item in runner.captured_inputs],
                ["skillfoundry_facade", "skillfoundry_facade"],
            )
            self.assertEqual([item["runtime"]["timeout_seconds"] for item in runner.captured_inputs], [17, 17])
            self.assertEqual(
                [item["piworker_call"]["role"] for item in runner.captured_inputs],
                ["executor_piworker", "judge_piworker"],
            )


class _TaskContractPackageExecutor:
    def execute(
        self,
        packet: AgentExecutionPacket,
        *,
        packet_ref: str,
        workspace: AgentWorkspace,
    ) -> AgentExecutionReport:
        workspace.write_text(
            "package/SKILL.md",
            "---\nname: demo-skill\n---\n# Demo Skill\nUse this skill to review release notes.\n",
        )
        workspace.write_json(
            "package/skillfoundry.bundle.json",
            SkillBundleManifest.prompt_only("demo-skill").to_dict(),
        )
        workspace.write_text("package/README.md", "# Demo Skill\n\nLocal prompt-only bundle.\n")
        workspace.write_text("reports/executor_evidence.md", "package written\n")
        return AgentExecutionReport(
            report_id="skillfoundry-taskcontract-execution-report",
            packet_id=packet.packet_id,
            packet_ref=packet_ref,
            contract_id=packet.contract_id,
            contract_hash=packet.contract_hash,
            contract_ref=packet.contract_ref,
            status=AgentExecutionStatus.COMPLETED,
            produced_artifact_refs=[
                "package/SKILL.md",
                "package/skillfoundry.bundle.json",
                "package/README.md",
            ],
            changed_refs=[
                "package/SKILL.md",
                "package/skillfoundry.bundle.json",
                "package/README.md",
            ],
            evidence_refs=["reports/executor_evidence.md"],
        )


class _TaskContractAcceptingJudge:
    def judge(
        self,
        packet: JudgePacket,
        *,
        packet_ref: str,
        workspace: AgentWorkspace,
    ) -> JudgeReport:
        return JudgeReport(
            report_id="skillfoundry-taskcontract-judge-report",
            packet_id=packet.packet_id,
            packet_ref=packet_ref,
            contract_id=packet.contract_id,
            contract_hash=packet.contract_hash,
            contract_ref=packet.contract_ref,
            decision=JudgeReportDecision.ACCEPTED,
            hard_check_status=packet.hard_check_status,
            evidence_refs=list(packet.evidence_refs),
            accepted_artifact_refs=list(packet.artifact_refs),
        )


class _TaskContractPiRuntimeRunner:
    def __init__(self) -> None:
        self.captured_inputs: list[dict[str, object]] = []

    def run(self, command, *, input_path: Path, cwd: Path, timeout_seconds: int, env) -> PiAgentCommandResult:
        captured_input = json.loads(input_path.read_text(encoding="utf-8"))
        self.captured_inputs.append(captured_input)
        role = captured_input["piworker_call"]["role"]
        if role == "executor_piworker":
            self._write_executor_outputs(cwd, captured_input)
        elif role == "judge_piworker":
            self._write_judge_outputs(cwd, captured_input)
        else:
            raise AssertionError(f"unexpected piworker role: {role}")
        return PiAgentCommandResult(returncode=0)

    def _write_executor_outputs(self, cwd: Path, captured_input: dict[str, object]) -> None:
        call_spec_payload = captured_input["call_spec"]
        if not isinstance(call_spec_payload, dict):
            raise AssertionError("call spec payload must be an object")
        expected_outputs = [str(ref) for ref in call_spec_payload["expected_outputs"]]
        for ref in expected_outputs:
            if ref == "package/skillfoundry.bundle.json":
                _write_text(cwd / ref, json.dumps(SkillBundleManifest.prompt_only("demo-skill").to_dict(), sort_keys=True))
            elif ref == "package/README.md":
                _write_text(cwd / ref, "# Demo Skill\n\nLocal prompt-only bundle.\n")
            else:
                _write_text(cwd / ref, "---\nname: demo-skill\n---\n# Demo Skill\n")
        self._write_pi_agent_output(cwd, captured_input, produced_refs=expected_outputs)

    def _write_judge_outputs(self, cwd: Path, captured_input: dict[str, object]) -> None:
        call_spec_payload = captured_input["call_spec"]
        if not isinstance(call_spec_payload, dict):
            raise AssertionError("call spec payload must be an object")
        spec_ref = str(call_spec_payload["visible_refs"][0])
        spec = json.loads((cwd / spec_ref).read_text(encoding="utf-8"))
        report_ref = str(spec["report_ref"])
        packet_ref = str(spec["packet_ref"])
        packet_hash = str(spec["packet_hash"])
        contract_ref = str(spec["contract_ref"])
        contract = json.loads((cwd / contract_ref).read_text(encoding="utf-8"))
        report_payload = {
            "schema_version": "judge_report.v1",
            "report_id": "skillfoundry-facade-piworker-judge-report",
            "packet_id": str(captured_input["call_id"]),
            "packet_ref": packet_ref,
            "packet_hash": packet_hash,
            "contract_id": str(captured_input["mission_id"]),
            "contract_hash": str(contract["contract_hash"]),
            "contract_ref": contract_ref,
            "decision": "accepted",
            "hard_check_status": "passed",
            "rationale_refs": [],
            "evidence_refs": list(spec["evidence_refs"]),
            "accepted_artifact_refs": list(spec["artifact_refs"]),
        }
        _write_text(cwd / report_ref, json.dumps(report_payload, sort_keys=True, indent=2) + "\n")
        self._write_pi_agent_output(cwd, captured_input, produced_refs=[report_ref])

    def _write_pi_agent_output(
        self,
        cwd: Path,
        captured_input: dict[str, object],
        *,
        produced_refs: list[str],
    ) -> None:
        output_ref = str(captured_input["output_ref"])
        session_ref = str(captured_input["session_ref"])
        events_ref = str(captured_input["events_ref"])
        metrics_ref = str(captured_input["metrics_ref"])
        savepoints_ref = str(captured_input["savepoints_ref"])
        metrics = {"tool_call_count": 1, "total_tokens": 3, "tool_error_count": 0}
        _write_text(cwd / session_ref, "{}\n")
        _write_text(cwd / events_ref, "{}\n")
        _write_text(cwd / metrics_ref, json.dumps(metrics, sort_keys=True) + "\n")
        _write_text(cwd / savepoints_ref, '{"schema_version": "missionforge.pi_agent_runtime_savepoint.v1"}\n')
        _write_text(
            cwd / output_ref,
            json.dumps(
                {
                    "schema_version": PI_AGENT_OUTPUT_SCHEMA_VERSION,
                    "call_id": str(captured_input["call_id"]),
                    "status": "completed",
                    "produced_artifacts": list(produced_refs),
                    "changed_refs": [*produced_refs, output_ref, session_ref, events_ref, metrics_ref, savepoints_ref],
                    "commands_run": [],
                    "tests_run": [],
                    "failures": [],
                    "worker_claims": ["worker_claim_present:length=24"],
                    "verifier_evidence": [*produced_refs, events_ref, metrics_ref, savepoints_ref],
                    "new_unknowns": [],
                    "recommended_next_steps": [],
                    "verification_status": "not_run",
                    "input_ref": str(captured_input["input_ref"]),
                    "output_ref": output_ref,
                    "session_ref": session_ref,
                    "events_ref": events_ref,
                    "metrics_ref": metrics_ref,
                    "savepoints_ref": savepoints_ref,
                    "duration_ms": 1,
                    "metrics": metrics,
                },
                sort_keys=True,
                indent=2,
            )
            + "\n",
        )


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
