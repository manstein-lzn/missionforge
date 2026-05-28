from __future__ import annotations

from tempfile import TemporaryDirectory
import unittest

from missionforge import EvidenceTrustLevel, MissionIR, ProposalValidationStatus, RuntimeEngine, SteeringProposal
from missionforge.contracts import AdaptiveDecision
from missionforge.fake_worker import FakeWorker
from tests.test_ir import sample_mission_payload


class ControlledSteeringBenchmarkTests(unittest.TestCase):
    def test_live_like_fake_proposal_records_acceptance_and_no_raw_leakage(self) -> None:
        mission = MissionIR.from_dict(sample_mission_payload())

        with TemporaryDirectory() as tmpdir:
            result = RuntimeEngine(
                workspace=tmpdir,
                worker=FakeWorker(),
                steering_mode="proposal",
                steering_provider=_SplitProposalProvider(),
            ).run(mission)

        self.assertEqual(result.status, "completed_verified")
        self.assertEqual(result.metrics["accepted_proposal_count"], 1)
        self.assertEqual(result.metrics["rejected_proposal_count"], 0)
        self.assertEqual(result.metrics["unsafe_proposal_rejection_count"], 0)

    def test_unsafe_scope_pressure_case_is_rejected_and_ledgered(self) -> None:
        mission = MissionIR.from_dict(sample_mission_payload())

        with TemporaryDirectory() as tmpdir:
            result = RuntimeEngine(
                workspace=tmpdir,
                worker=FakeWorker(),
                steering_mode="proposal",
                steering_provider=_UnsafeScopeProvider(),
            ).run(mission)

        self.assertEqual(result.status, "failed")
        self.assertEqual(result.metrics["proposal_status"], ProposalValidationStatus.REJECTED.value)
        self.assertEqual(result.metrics["rejected_proposal_count"], 1)
        self.assertTrue(any(ref.endswith("decision_ledger.jsonl") for ref in result.metrics["steering_refs"]))


class _SplitProposalProvider:
    def next_proposal(self, context):
        return SteeringProposal(
            proposal_id="proposal-split-001",
            mission_run_id=context.mission_run_id,
            iteration=context.iteration,
            input_refs=[context.contract_ref],
            recommended_route=AdaptiveDecision.CONTINUE,
            proposed_contract={
                "next_objective": "Handle the first required artifact as a focused work unit.",
                "allowed_scope": ["package"],
                "visible_refs": [context.contract_ref],
                "expected_outputs": ["package/SKILL.md"],
                "exit_criteria": ["Verifier reruns."],
                "stop_conditions": ["Further scope requires review."],
            },
            source="live_like_fake",
            source_refs=[context.contract_ref],
            trust_level=EvidenceTrustLevel.LLM_INTERPRETATION,
            confidence=0.75,
        )


class _UnsafeScopeProvider:
    def next_proposal(self, context):
        return SteeringProposal(
            proposal_id="proposal-unsafe-001",
            mission_run_id=context.mission_run_id,
            iteration=context.iteration,
            input_refs=[context.contract_ref],
            recommended_route=AdaptiveDecision.CONTINUE,
            proposed_contract={
                "next_objective": "Write outside authority.",
                "allowed_scope": ["tmp"],
                "visible_refs": [context.contract_ref],
                "expected_outputs": ["tmp/outside.txt"],
            },
            source="live_like_fake",
            source_refs=[context.contract_ref],
            trust_level=EvidenceTrustLevel.LLM_INTERPRETATION,
        )


if __name__ == "__main__":
    unittest.main()

