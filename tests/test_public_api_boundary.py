from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import missionforge
from missionforge.adapters.pi_agent_runtime import PiAgentExecutorNode, PiAgentJudgeNode, PiAgentRuntimeConfig
from missionforge.agentic_flow import AgenticFlowRunner


class PublicApiBoundaryTests(unittest.TestCase):
    def test_package_root_is_the_programmer_kernel_surface(self) -> None:
        expected = {
            "ArtifactRef",
            "ContractClause",
            "ContractValidationError",
            "CapabilityGrant",
            "EvidenceLedger",
            "EvidenceRecord",
            "EvidenceRef",
            "FileEvidenceStore",
            "FinalPackage",
            "HostSandboxRunner",
            "InMemoryEvidenceStore",
            "JudgeRubric",
            "MissionForgeError",
            "NetworkPolicy",
            "PermissionManifest",
            "PiWorkerCall",
            "PiWorkerCallAdapter",
            "PiWorkerCallResult",
            "PiWorkerCallResultStatus",
            "PiWorkerCallRole",
            "ProductCompileStatus",
            "ProductIntegration",
            "ProductTaskContractCompileResult",
            "Ref",
            "SandboxMode",
            "SandboxProfile",
            "ToolGateway",
            "ToolGatewayRequest",
            "ToolGatewayResult",
            "TaskContract",
            "TaskContractFlowPreset",
            "TaskContractProductIntegration",
            "TaskContractRevision",
            "WorkerBrief",
            "WorkspacePolicy",
            "assert_refs_only_payload",
            "build_judge_rubric",
            "build_worker_brief",
            "create_capability_grant",
            "create_default_piworker_adapter",
            "create_default_task_contract_flow",
            "create_sandbox_profile_from_workspace",
            "project_judge_rubric",
            "project_worker_brief",
            "replay_decision_ledger",
            "run_piworker_call",
            "stable_json_hash",
            "validate_ref",
        }

        self.assertEqual(set(missionforge.__all__), expected)
        for symbol in expected:
            self.assertTrue(hasattr(missionforge, symbol), symbol)

    def test_package_root_does_not_export_internal_or_high_level_surfaces(self) -> None:
        forbidden = {
            "ActiveMissionContract",
            "AgentExecutionPacket",
            "AgentExecutionReport",
            "AgenticFlowRunner",
            "AgenticFlowStatus",
            "AttemptInputManifest",
            "CapabilityProfile",
            "ContractManifest",
            "DecisionLedgerEventKind",
            "ExecutionReport",
            "ExpandedMission",
            "FrontDesk",
            "FrozenMissionContract",
            "JudgePacket",
            "JudgeReport",
            "MetricEvent",
            "MissionIR",
            "MissionResult",
            "MissionRevision",
            "MissionRunAudit",
            "MissionRuntime",
            "PiAgentRuntimeAdapter",
            "PiWorkerRuntimeFactory",
            "ProfilePack",
            "RepairBrief",
            "RepairTicket",
            "RevisionAppliedRecord",
            "RevisionPendingRecord",
            "RuntimeContractView",
            "RuntimeEngine",
            "SkillFoundryMissionCompiler",
            "TaskRevisionDecision",
            "TaskRevisionRequest",
            "Verifier",
            "WorkUnitCompiler",
            "WorkUnitContract",
            "WorkUnitHarness",
            "WorkerInvocation",
            "WorkerResult",
            "apply_mission_revision",
            "build_run_audit",
            "expand_mission",
            "freeze_mission",
            "pi_agent_runtime",
            "piworker",
            "run_repair_directive_with_default_piworker",
            "run_revision_draft_with_default_piworker",
            "skillfoundry",
        }

        for symbol in forbidden:
            self.assertNotIn(symbol, missionforge.__all__)
            self.assertFalse(hasattr(missionforge, symbol), symbol)

    def test_package_root_exposes_task_contract_default_flow_factory_only(self) -> None:
        with TemporaryDirectory() as tmpdir:
            preset = missionforge.create_default_task_contract_flow(
                tmpdir,
                piworker_config=PiAgentRuntimeConfig(command=("pi-agent-runtime",)),
            )

            self.assertIsInstance(preset, missionforge.TaskContractFlowPreset)
            self.assertIsInstance(preset.runner, AgenticFlowRunner)
            self.assertIsInstance(preset.executor, PiAgentExecutorNode)
            self.assertIsInstance(preset.judge, PiAgentJudgeNode)
            self.assertEqual(Path(preset.runner.root), Path(tmpdir))


if __name__ == "__main__":
    unittest.main()
