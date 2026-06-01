from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from typing import Any, cast

from missionforge.contracts import ContractValidationError
from missionforge import (
    AgentExecutionPacket,
    AgentExecutionReport,
    AgentExecutionStatus,
    AgenticFlowRunner,
    AgenticFlowStatus,
    AgentWorkspace,
    HardCheckStatus,
    JudgePacket,
    JudgeReport,
    JudgeReportDecision,
    ProductCompileStatus,
    ProductTaskContractCompileResult,
    TaskContract,
    TaskContractProductIntegration,
)
from missionforge.frontdesk import (
    FrontDeskIntentBundle,
    IntentBundleReadiness,
    IntentGenericRefs,
    ProductContextSnapshot,
    SlotValue,
    SlotValueStatus,
)
from missionforge_skillfoundry import (
    SkillFoundryFrontDeskIntegration,
    SkillFoundryTaskContractCompileResult,
    compile_frontdesk_task_contract,
    compile_skillfoundry_task_contract,
    load_skillfoundry_task_contract,
)
from missionforge_skillfoundry.task_contract_compiler import SKILLFOUNDRY_HARD_CHECK_RESULT_REF
from missionforge.adapters.pi_agent_runtime import (
    PI_AGENT_OUTPUT_SCHEMA_VERSION,
    PiAgentCommandResult,
    PiAgentExecutorNode,
    PiAgentRuntimeAdapter,
    PiAgentRuntimeConfig,
)

from test_product_contract import sample_request


class SkillFoundryTaskContractCompilerTests(unittest.TestCase):
    def test_request_compiles_to_task_contract_workspace_and_permissions(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            _write_source_fixture(root)

            result = compile_skillfoundry_task_contract(sample_request(), workspace=root)
            task_contract, workspace_policy, permission_manifest = load_skillfoundry_task_contract(root, result)

            self.assertEqual(SkillFoundryTaskContractCompileResult.from_dict(result.to_dict()), result)
            self.assertEqual(task_contract.product_id, "skillfoundry")
            self.assertEqual(task_contract.contract_hash, result.contract_hash)
            self.assertEqual(workspace_policy.workspace_root_ref, result.run_workspace_ref)
            self.assertEqual(workspace_policy.artifact_root_refs, ["package"])
            self.assertIn("package", permission_manifest.writable_refs)
            self.assertIn("reports", permission_manifest.writable_refs)
            self.assertEqual(
                [ref for clause in task_contract.required_outputs for ref in clause.refs],
                ["package/SKILL.md", "package/skillfoundry.bundle.json", "package/README.md"],
            )
            self.assertTrue(all(item.refs for item in task_contract.semantic_acceptance))
            self.assertIn("product_contract/skill_product_contract.json", task_contract.product_contract_refs)
            self.assertIn("frontdesk/sanitized_task.json", task_contract.source_refs)
            self.assertIn("frontdesk", workspace_policy.input_refs)
            self.assertIn("frontdesk", permission_manifest.readable_refs)
            self.assertTrue((root / result.task_contract_ref).exists())
            self.assertTrue((root / result.workspace_policy_ref).exists())
            self.assertTrue((root / result.permission_manifest_ref).exists())
            self.assertTrue((root / result.run_workspace_ref / "frontdesk/sanitized_task.json").exists())

    def test_missing_source_refs_are_not_advertised_as_worker_readable_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)

            result = compile_skillfoundry_task_contract(sample_request(), workspace=root)
            task_contract, workspace_policy, permission_manifest = load_skillfoundry_task_contract(root, result)
            compile_report = json.loads((root / result.compile_report_ref).read_text(encoding="utf-8"))

            self.assertNotIn("frontdesk/sanitized_task.json", task_contract.source_refs)
            self.assertNotIn("frontdesk", workspace_policy.input_refs)
            self.assertNotIn("frontdesk", permission_manifest.readable_refs)
            self.assertEqual(compile_report["materialized_source_refs"], [])
            self.assertEqual(compile_report["unavailable_source_refs"], ["frontdesk/sanitized_task.json"])

    def test_task_contract_compile_result_is_refs_only_and_not_mission_ir_shaped(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            result = compile_skillfoundry_task_contract(sample_request(), workspace=tempdir)
            payload_text = json.dumps(result.to_dict(), sort_keys=True)

            self.assertNotIn("mission_ir_ref", payload_text)
            self.assertNotIn("Create a prompt-only Codex skill", payload_text)
            self.assertIn("task_contract_ref", payload_text)
            self.assertEqual(result.hard_check_refs, [SKILLFOUNDRY_HARD_CHECK_RESULT_REF])

    def test_task_contract_compile_result_requires_refs_under_run_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            result = compile_skillfoundry_task_contract(sample_request(), workspace=tempdir)
            payload = result.to_dict()
            payload["task_contract_ref"] = "runs/other/contract/task_contract.json"

            with self.assertRaisesRegex(ContractValidationError, "under run_workspace_ref"):
                SkillFoundryTaskContractCompileResult.from_dict(payload)

    def test_frontdesk_integration_exposes_product_neutral_task_contract_result(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            integration = SkillFoundryFrontDeskIntegration(bundle_id="release-review")

            result = integration.compile_task_contract(_frontdesk_bundle(), workspace=tempdir)

            self.assertIsInstance(integration, TaskContractProductIntegration)
            self.assertEqual(ProductTaskContractCompileResult.from_dict(result.to_dict()), result)
            self.assertEqual(result.status, ProductCompileStatus.COMPILED)
            self.assertEqual(result.product_id, "skillfoundry")
            self.assertTrue(result.task_contract_ref)
            self.assertFalse(result.to_dict().get("mission_ir_ref"))

    def test_public_frontdesk_task_contract_function_is_default_compile_surface(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            result = compile_frontdesk_task_contract(_frontdesk_bundle(), workspace=tempdir, bundle_id="release-review")

            self.assertEqual(result.status, ProductCompileStatus.COMPILED)
            self.assertTrue(result.task_contract_ref)
            self.assertFalse(result.to_dict().get("mission_ir_ref"))

    def test_frontdesk_integration_returns_clarification_without_task_contract(self) -> None:
        integration = SkillFoundryFrontDeskIntegration(bundle_id="release-review")

        result = integration.compile_task_contract(_frontdesk_bundle(include_profile=False), workspace=".")

        self.assertEqual(result.status, ProductCompileStatus.NEEDS_CLARIFICATION)
        self.assertEqual(result.missing_slot_ids, ["bundle_profile"])
        self.assertFalse(result.task_contract_ref)

    def test_skillfoundry_task_contract_runs_through_offline_agentic_flow(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            compile_result = compile_skillfoundry_task_contract(sample_request(), workspace=root)
            task_contract, workspace_policy, permission_manifest = load_skillfoundry_task_contract(root, compile_result)
            _write_hard_check(root, compile_result.run_workspace_ref)

            result = AgenticFlowRunner(root).run(
                run_id="skillfoundry-demo",
                contract=task_contract,
                workspace_policy=workspace_policy,
                permission_manifest=permission_manifest,
                executor=_SkillFoundryPackageExecutor(),
                judge=_AcceptingSkillFoundryJudge(),
                hard_check_status=HardCheckStatus.PASSED,
                hard_check_refs=list(compile_result.hard_check_refs),
            )

            self.assertEqual(result.status, AgenticFlowStatus.ACCEPTED)
            self.assertEqual(
                result.accepted_artifact_refs,
                ["package/SKILL.md", "package/skillfoundry.bundle.json", "package/README.md"],
            )
            self.assertTrue((root / compile_result.run_workspace_ref / "ledgers/decision_ledger.jsonl").exists())


    def test_skillfoundry_task_contract_runs_through_pi_runtime_executor_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            compile_result = compile_skillfoundry_task_contract(sample_request(), workspace=root)
            task_contract, workspace_policy, permission_manifest = load_skillfoundry_task_contract(root, compile_result)
            _write_hard_check(root, compile_result.run_workspace_ref)
            runner = _SkillFoundryPiRuntimeRunner()
            executor = PiAgentExecutorNode(
                workspace_root=root / compile_result.run_workspace_ref,
                adapter=PiAgentRuntimeAdapter(
                    PiAgentRuntimeConfig(command=("pi-agent-runtime",)),
                    runner=runner,
                ),
            )

            result = AgenticFlowRunner(root).run(
                run_id="skillfoundry-pi-runtime-demo",
                contract=task_contract,
                workspace_policy=workspace_policy,
                permission_manifest=permission_manifest,
                executor=executor,
                judge=_AcceptingSkillFoundryJudge(),
                hard_check_status=HardCheckStatus.PASSED,
                hard_check_refs=list(compile_result.hard_check_refs),
            )

            self.assertEqual(result.status, AgenticFlowStatus.ACCEPTED)
            self.assertEqual(result.accepted_artifact_refs, ["package/SKILL.md", "package/skillfoundry.bundle.json", "package/README.md"])
            self.assertTrue((root / compile_result.run_workspace_ref / "attempts/skillfoundry-pi-runtime-demo-execution-packet/pi_agent_input.json").exists())
            self.assertEqual(runner.captured_input["permission_manifest"]["writable_refs"], ["package", "attempts", "reports", "ledgers"])

    def test_pi_runtime_executor_boundary_preserves_changed_refs_for_authorization(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            compile_result = compile_skillfoundry_task_contract(sample_request(), workspace=root)
            task_contract, workspace_policy, permission_manifest = load_skillfoundry_task_contract(root, compile_result)
            _write_hard_check(root, compile_result.run_workspace_ref)
            executor = PiAgentExecutorNode(
                workspace_root=root / compile_result.run_workspace_ref,
                adapter=PiAgentRuntimeAdapter(
                    PiAgentRuntimeConfig(command=("pi-agent-runtime",)),
                    runner=_SkillFoundryPiRuntimeRunner(extra_changed_refs=["ledgers/decision_ledger.jsonl"]),
                ),
            )

            with self.assertRaisesRegex(ContractValidationError, "runtime-owned ref"):
                AgenticFlowRunner(root).run(
                    run_id="skillfoundry-pi-runtime-denied-change",
                    contract=task_contract,
                    workspace_policy=workspace_policy,
                    permission_manifest=permission_manifest,
                    executor=executor,
                    judge=_AcceptingSkillFoundryJudge(),
                    hard_check_status=HardCheckStatus.PASSED,
                    hard_check_refs=list(compile_result.hard_check_refs),
                )


class _SkillFoundryPiRuntimeRunner:
    def __init__(self, *, extra_changed_refs: list[str] | None = None) -> None:
        self.captured_input: dict[str, Any] = {}
        self.extra_changed_refs = list(extra_changed_refs or [])

    def run(self, command, *, input_path: Path, cwd: Path, timeout_seconds: int, env) -> PiAgentCommandResult:
        self.captured_input = json.loads(input_path.read_text(encoding="utf-8"))
        contract_payload = cast(dict[str, Any], self.captured_input["contract"])
        expected_outputs = [str(ref) for ref in contract_payload["expected_outputs"]]
        for ref in expected_outputs:
            path = cwd / ref
            path.parent.mkdir(parents=True, exist_ok=True)
            if ref.endswith(".json"):
                path.write_text(
                    json.dumps(
                        {
                            "schema_version": "skillfoundry.bundle.v1",
                            "bundle_id": "release-review",
                            "bundle_profile": "prompt_only",
                            "entrypoint": "SKILL.md",
                            "capability_surface": {},
                            "runtime_assets": [],
                            "data_assets": [],
                            "references": [],
                            "environment": {},
                            "permissions": {},
                            "verification": {},
                            "distribution": {},
                        },
                        sort_keys=True,
                    )
                    + "\n",
                    encoding="utf-8",
                )
            else:
                path.write_text("# Release Notes Review Skill\n", encoding="utf-8")
        output_ref = str(self.captured_input["output_ref"])
        session_ref = str(self.captured_input["session_ref"])
        events_ref = str(self.captured_input["events_ref"])
        metrics_ref = str(self.captured_input["metrics_ref"])
        savepoints_ref = str(self.captured_input["savepoints_ref"])
        metrics = {"tool_call_count": 1, "total_tokens": 11, "tool_error_count": 0}
        _write_ref(cwd, session_ref, "{}\n")
        _write_ref(cwd, events_ref, "{}\n")
        _write_ref(cwd, metrics_ref, json.dumps(metrics, sort_keys=True) + "\n")
        _write_ref(cwd, savepoints_ref, '{"schema_version": "missionforge.pi_agent_runtime_savepoint.v1"}\n')
        _write_ref(
            cwd,
            output_ref,
            json.dumps(
                {
                    "schema_version": PI_AGENT_OUTPUT_SCHEMA_VERSION,
                    "work_unit_id": self.captured_input["work_unit_id"],
                    "status": "completed",
                    "produced_artifacts": expected_outputs,
                    "changed_refs": [*expected_outputs, *self.extra_changed_refs],
                    "commands_run": [],
                    "tests_run": [],
                    "failures": [],
                    "worker_claims": ["assistant_final_text_present:length=20"],
                    "verifier_evidence": expected_outputs,
                    "new_unknowns": [],
                    "recommended_next_steps": [],
                    "verification_status": "not_run",
                    "input_ref": self.captured_input["input_ref"],
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
        return PiAgentCommandResult(returncode=0)


def _write_ref(root: Path, ref: str, text: str) -> None:
    path = root / ref
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")

class _SkillFoundryPackageExecutor:
    def execute(
        self,
        packet: AgentExecutionPacket,
        *,
        packet_ref: str,
        workspace: AgentWorkspace,
    ) -> AgentExecutionReport:
        workspace.write_text("package/SKILL.md", "# Release Notes Review Skill\n")
        workspace.write_text(
            "package/skillfoundry.bundle.json",
            json.dumps(
                {
                    "schema_version": "skillfoundry.bundle.v1",
                    "bundle_id": packet.contract_id,
                    "bundle_profile": "prompt_only",
                    "entrypoint": "SKILL.md",
                    "capability_surface": {},
                    "runtime_assets": [],
                    "data_assets": [],
                    "references": [],
                    "environment": {},
                    "permissions": {},
                    "verification": {},
                    "distribution": {},
                },
                sort_keys=True,
            ),
        )
        workspace.write_text("package/README.md", "# Release Notes Review Skill\n")
        workspace.write_text("reports/executor_evidence.md", "package files written")
        return AgentExecutionReport(
            report_id="skillfoundry-execution-report",
            packet_id=packet.packet_id,
            packet_ref=packet_ref,
            contract_id=packet.contract_id,
            contract_hash=packet.contract_hash,
            contract_ref=packet.contract_ref,
            status=AgentExecutionStatus.COMPLETED,
            produced_artifact_refs=list(packet.expected_artifact_refs),
            changed_refs=list(packet.expected_artifact_refs),
            evidence_refs=["reports/executor_evidence.md"],
        )


class _AcceptingSkillFoundryJudge:
    def judge(
        self,
        packet: JudgePacket,
        *,
        packet_ref: str,
        workspace: AgentWorkspace,
    ) -> JudgeReport:
        workspace.write_text("reports/judge_rationale.md", "offline SkillFoundry package accepted")
        return JudgeReport(
            report_id="skillfoundry-judge-report",
            packet_id=packet.packet_id,
            packet_ref=packet_ref,
            contract_id=packet.contract_id,
            contract_hash=packet.contract_hash,
            contract_ref=packet.contract_ref,
            decision=JudgeReportDecision.ACCEPTED,
            hard_check_status=packet.hard_check_status,
            rationale_refs=["reports/judge_rationale.md"],
            evidence_refs=[packet.execution_report_ref, *packet.hard_check_refs],
            accepted_artifact_refs=list(packet.artifact_refs),
        )


def _frontdesk_bundle(*, include_profile: bool = True) -> FrontDeskIntentBundle:
    slot_values = [
        SlotValue(slot_id="capability_goal", status=SlotValueStatus.INFERRED, value="Review release notes."),
        SlotValue(slot_id="target_user", status=SlotValueStatus.INFERRED, value="release engineer"),
        SlotValue(slot_id="trigger_scenarios", status=SlotValueStatus.INFERRED, value=["When release notes need review."]),
        SlotValue(slot_id="non_trigger_scenarios", status=SlotValueStatus.INFERRED, value=["When no package is needed."]),
        SlotValue(slot_id="required_package_outputs", status=SlotValueStatus.INFERRED, value=["package/SKILL.md"]),
        SlotValue(slot_id="privacy_boundary", status=SlotValueStatus.INFERRED, value=["Use admitted refs only."]),
        SlotValue(slot_id="distribution_boundary", status=SlotValueStatus.INFERRED, value=["Local distribution only."]),
    ]
    if include_profile:
        slot_values.append(SlotValue(slot_id="bundle_profile", status=SlotValueStatus.INFERRED, value="prompt_only"))
    return FrontDeskIntentBundle(
        session_id="fd",
        intent_bundle_ref="frontdesk/intent_bundle.json",
        generic_refs=IntentGenericRefs(session_ref="frontdesk/session.json"),
        evidence_refs=["frontdesk/core_need_brief.json"],
        product_context=ProductContextSnapshot(product_id="skillfoundry", display_name="SkillFoundry"),
        slot_values=slot_values,
        readiness=IntentBundleReadiness.READY_FOR_PRODUCT_COMPILE,
    )


def _write_hard_check(root: Path, run_workspace_ref: str) -> None:
    path = root / run_workspace_ref / SKILLFOUNDRY_HARD_CHECK_RESULT_REF
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{"status": "passed", "source": "offline-skillfoundry-fixture"}\n', encoding="utf-8")


def _write_source_fixture(root: Path) -> None:
    path = root / "frontdesk/sanitized_task.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{"summary_ref": "frontdesk/intent_bundle.json"}\n', encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
