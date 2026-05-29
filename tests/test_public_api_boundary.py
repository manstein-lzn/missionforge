from __future__ import annotations

import unittest

import missionforge


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
        }

        for symbol in expected:
            self.assertIn(symbol, missionforge.__all__)
            self.assertTrue(hasattr(missionforge, symbol), symbol)


if __name__ == "__main__":
    unittest.main()
