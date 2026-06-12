from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import missionforge
from missionforge.adapters.pi_agent_runtime import PiAgentExecutorNode, PiAgentJudgeNode, PiAgentRuntimeConfig


class PublicApiBoundaryTests(unittest.TestCase):
    def test_package_root_does_not_export_runtime_contract_internals(self) -> None:
        forbidden = {
            "ActiveMissionContract",
            "RuntimeContractView",
            "PiAgentRuntimeAdapter",
            "FauxPiWorkerAdapter",
            "SkillFoundryMissionCompiler",
            "skillfoundry",
            "pi_agent_runtime",
            "piworker",
        }

        for symbol in forbidden:
            self.assertNotIn(symbol, missionforge.__all__)
            self.assertFalse(hasattr(missionforge, symbol), symbol)

    def test_package_root_keeps_stable_extension_contracts(self) -> None:
        expected = {
            "MissionIR",
            "MissionRuntime",
            "MissionResult",
            "MetricEvent",
            "MetricProjection",
            "MissionRevision",
            "JsonWorkspaceStore",
            "RunStore",
            "ArtifactStore",
            "EventLogStore",
            "ProfilePack",
            "ProfileRegistry",
            "MissionRunAudit",
            "build_run_audit",
            "TaskContractFlowPreset",
            "create_default_task_contract_flow",
            "PiWorkerRuntimeFactory",
            "create_default_piworker_adapter",
            "PiWorkerCall",
            "PiWorkerCallResult",
            "PiWorkerCallRole",
            "PiWorkerCallResultStatus",
        }

        for symbol in expected:
            self.assertIn(symbol, missionforge.__all__)
            self.assertTrue(hasattr(missionforge, symbol), symbol)

    def test_package_root_exposes_primary_task_contract_piworker_surface(self) -> None:
        expected = {
            "AgentExecutionPacket",
            "AgentExecutionReport",
            "AgenticFlowResult",
            "AgenticFlowRunner",
            "AgenticFlowStatus",
            "DecisionLedgerEventKind",
            "FinalPackage",
            "JudgePacket",
            "JudgeReport",
            "JudgeRubric",
            "PermissionManifest",
            "PiWorkerCall",
            "PiWorkerCallResult",
            "PiWorkerCallResultStatus",
            "PiWorkerCallRole",
            "RepairBrief",
            "RepairExecutionDirective",
            "RepairTicket",
            "RevisionAppliedRecord",
            "RevisionExecutionDirective",
            "RevisionPendingRecord",
            "TaskContract",
            "TaskContractDecisionLedgerEntry",
            "TaskRevisionDecision",
            "TaskRevisionRequest",
            "WorkerBrief",
            "WorkspacePolicy",
            "apply_task_contract_revision",
            "build_repair_execution_directive",
            "build_repair_rejudge_packet",
            "build_repair_ticket",
            "build_revision_execution_directive",
            "build_revision_judge_result",
            "build_revision_pending_record",
            "build_revision_rejudge_packet",
            "create_default_task_contract_flow",
            "load_revision_draft_contract",
            "replay_decision_ledger",
            "run_repair_directive_with_default_piworker",
            "run_revision_draft_with_default_piworker",
        }

        for symbol in expected:
            self.assertIn(symbol, missionforge.__all__)
            self.assertTrue(hasattr(missionforge, symbol), symbol)

    def test_package_root_exposes_task_contract_default_flow(self) -> None:
        with TemporaryDirectory() as tmpdir:
            preset = missionforge.create_default_task_contract_flow(
                tmpdir,
                piworker_config=PiAgentRuntimeConfig(command=("pi-agent-runtime",)),
            )

            self.assertIsInstance(preset, missionforge.TaskContractFlowPreset)
            self.assertIsInstance(preset.runner, missionforge.AgenticFlowRunner)
            self.assertIsInstance(preset.executor, PiAgentExecutorNode)
            self.assertIsInstance(preset.judge, PiAgentJudgeNode)
            self.assertEqual(Path(preset.runner.root), Path(tmpdir))


if __name__ == "__main__":
    unittest.main()
