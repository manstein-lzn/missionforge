from __future__ import annotations

from tempfile import TemporaryDirectory
import unittest

from missionforge import (
    EvidenceTrustLevel,
    MissionIR,
    ObservationSignalType,
    ObservationSignal,
    ReviewerDecision,
    RuntimeEngine,
    SteeringProposal,
)
from missionforge.contracts import AdaptiveDecision
from missionforge.fake_worker import FakeWorker
from tests.test_ir import sample_mission_payload


class ControlledSteeringRuntimeTests(unittest.TestCase):
    def test_proposal_mode_accepts_provider_proposal_and_records_refs(self) -> None:
        mission = MissionIR.from_dict(sample_mission_payload())
        provider = _ContextProposalProvider()

        with TemporaryDirectory() as tmpdir:
            result = RuntimeEngine(
                workspace=tmpdir,
                worker=FakeWorker(),
                steering_mode="proposal",
                steering_provider=provider,
            ).run(mission)

        self.assertEqual(result.status, "completed_verified")
        self.assertEqual(result.metrics["proposal_count"], 1)
        self.assertEqual(result.metrics["accepted_proposal_count"], 1)
        self.assertTrue(any(ref.endswith("steering_proposal.json") for ref in result.metrics["steering_refs"]))
        self.assertTrue(any(ref.endswith("decision_ledger.jsonl") for ref in result.metrics["steering_refs"]))

    def test_proposal_mode_rejects_unsafe_provider_proposal_without_dispatch(self) -> None:
        mission = MissionIR.from_dict(sample_mission_payload())

        with TemporaryDirectory() as tmpdir:
            result = RuntimeEngine(
                workspace=tmpdir,
                worker=FakeWorker(),
                steering_mode="proposal",
                steering_provider=_UnsafeProposalProvider(),
            ).run(mission)

        self.assertEqual(result.status, "failed")
        self.assertEqual(result.metrics["proposal_status"], "rejected")
        self.assertEqual(result.metrics["rejected_proposal_count"], 1)
        self.assertGreater(result.metrics["unsafe_proposal_rejection_count"], 0)

    def test_observation_interpreter_records_signal_without_closing_failed_verifier(self) -> None:
        payload = sample_mission_payload()
        payload["outputs"]["required_artifacts"] = ["package/SKILL.md", "package/MISSING.md"]
        mission = MissionIR.from_dict(payload)

        with TemporaryDirectory() as tmpdir:
            result = RuntimeEngine(
                workspace=tmpdir,
                worker=FakeWorker(),
                observation_interpreter=_RepairObservationInterpreter(),
            ).run(mission)

        self.assertEqual(result.status, "failed")
        self.assertEqual(result.metrics["observation_signal_count"], 1)
        self.assertTrue(result.metrics["observation_signal_ref"].endswith("observation_signal.json"))
        self.assertTrue(result.metrics["state_correction_ref"].endswith("state_correction.json"))

    def test_reviewer_provider_resolves_delegatable_manual_gate(self) -> None:
        payload = sample_mission_payload()
        payload["verification"]["manual_gates"] = [{"authority": "reviewer", "severity": "blocking"}]
        mission = MissionIR.from_dict(payload)

        with TemporaryDirectory() as tmpdir:
            result = RuntimeEngine(
                workspace=tmpdir,
                worker=FakeWorker(),
                reviewer_provider=_ApprovingReviewerProvider(),
            ).run(mission)

        self.assertEqual(result.status, "completed_verified")
        self.assertEqual(result.metrics["review_packet_count"], 1)
        self.assertEqual(result.metrics["reviewer_decision_count"], 1)


class _ContextProposalProvider:
    def next_proposal(self, context):
        return SteeringProposal(
            proposal_id="proposal-001",
            mission_run_id=context.mission_run_id,
            iteration=context.iteration,
            input_refs=[context.contract_ref],
            recommended_route=AdaptiveDecision.CONTINUE,
            proposed_contract={
                "next_objective": "Write required artifact.",
                "allowed_scope": ["package"],
                "visible_refs": [context.contract_ref],
                "expected_outputs": ["package/SKILL.md"],
                "exit_criteria": ["Verifier reruns."],
                "stop_conditions": ["Contract revision required."],
            },
            source="fake_llm",
            source_refs=[context.contract_ref],
            trust_level=EvidenceTrustLevel.LLM_INTERPRETATION,
            confidence=0.8,
        )


class _UnsafeProposalProvider:
    def next_proposal(self, context):
        return SteeringProposal(
            proposal_id="proposal-unsafe",
            mission_run_id=context.mission_run_id,
            iteration=context.iteration,
            input_refs=[context.contract_ref],
            recommended_route=AdaptiveDecision.CONTINUE,
            proposed_contract={
                "next_objective": "Write outside scope.",
                "allowed_scope": ["outside"],
                "visible_refs": [context.contract_ref],
                "expected_outputs": ["outside/secret.txt"],
            },
            source="fake_llm",
            source_refs=[context.contract_ref],
            trust_level=EvidenceTrustLevel.LLM_INTERPRETATION,
        )


class _RepairObservationInterpreter:
    def interpret_observation(self, context):
        return ObservationSignal(
            signal_id="signal-001",
            mission_run_id=context.mission_run_id,
            iteration=context.iteration,
            observation_ref=context.latest_attempt_ref,
            source_refs=[context.latest_attempt_ref],
            signal_type=ObservationSignalType.MISSING_EVIDENCE,
            safe_summary="The verifier still lacks a required artifact.",
            trust_level=EvidenceTrustLevel.LLM_INTERPRETATION,
            recommended_action=AdaptiveDecision.REPAIR,
            confidence=0.6,
        )


class _ApprovingReviewerProvider:
    def review(self, packet):
        return ReviewerDecision(
            reviewer_id="independent-reviewer",
            decision="approved",
            contract_hash=packet.contract_hash,
            evidence_refs=[packet.contract_ref],
        )


if __name__ == "__main__":
    unittest.main()
