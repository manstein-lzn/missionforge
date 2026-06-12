from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from missionforge import EvidenceTrustLevel
from missionforge.ir import MissionIR
from missionforge.runtime import RuntimeEngine
from missionforge.steering import SteeringProposal
from missionforge.adapters.cli import MissionCLI
from missionforge.contracts import AdaptiveDecision
from missionforge.fake_worker import FakeWorker
from tests.test_ir import sample_mission_payload


class OperatorControlledSteeringSurfaceTests(unittest.TestCase):
    def test_inspect_surfaces_steering_refs_read_only(self) -> None:
        mission = MissionIR.from_dict(sample_mission_payload())
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            RuntimeEngine(
                workspace=root,
                worker=FakeWorker(),
                steering_mode="proposal",
                steering_provider=_Provider(),
            ).run(mission)

            result = MissionCLI().run_command(["inspect", "--workspace", str(root), "--run", "run-sample-mission"])

        self.assertEqual(result.exit_code, 0)
        self.assertTrue(result.data["steering_refs"])
        self.assertIn("latest_steering_proposal_ref", result.data["latest_steering_ref_map"])
        self.assertTrue(any(ref.endswith("decision_ledger.jsonl") for ref in result.refs))

    def test_diagnose_surfaces_rejected_steering_proposal(self) -> None:
        mission = MissionIR.from_dict(sample_mission_payload())
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            RuntimeEngine(
                workspace=root,
                worker=FakeWorker(),
                steering_mode="proposal",
                steering_provider=_UnsafeProvider(),
            ).run(mission)

            result = MissionCLI().run_command(["diagnose", "--workspace", str(root), "--run", "run-sample-mission"])

        self.assertEqual(result.exit_code, 0)
        self.assertEqual(result.data["diagnosis"], "steering_proposal_rejected")
        self.assertEqual(result.data["operator_action"], "inspect_steering_refs")


class _Provider:
    def next_proposal(self, context):
        return SteeringProposal(
            proposal_id="proposal-001",
            mission_run_id=context.mission_run_id,
            iteration=context.iteration,
            input_refs=[context.contract_ref],
            recommended_route=AdaptiveDecision.CONTINUE,
            proposed_contract={
                "next_objective": "Write package.",
                "allowed_scope": ["package"],
                "visible_refs": [context.contract_ref],
                "expected_outputs": ["package/SKILL.md"],
            },
            source="fake_llm",
            source_refs=[context.contract_ref],
            trust_level=EvidenceTrustLevel.LLM_INTERPRETATION,
        )


class _UnsafeProvider(_Provider):
    def next_proposal(self, context):
        proposal = super().next_proposal(context)
        proposal.proposed_contract["allowed_scope"] = ["outside"]
        proposal.proposed_contract["expected_outputs"] = ["outside/file.txt"]
        return proposal


if __name__ == "__main__":
    unittest.main()
