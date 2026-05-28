from __future__ import annotations

import unittest

from missionforge.contracts import ContractValidationError, EvidenceTrustLevel, ProposalValidationStatus
from missionforge.steering import ProposalValidationResult, StateCorrection, SteeringProposal


class SteeringContractTests(unittest.TestCase):
    def test_steering_proposal_round_trip(self) -> None:
        proposal = SteeringProposal.from_dict(
            {
                "proposal_id": "SP-001",
                "mission_run_id": "run-001",
                "iteration": 1,
                "input_refs": ["mission/state_001.json"],
                "recommended_route": "repair",
                "proposed_contract": {"next_objective": "Repair the missing artifact."},
                "rationale": "Verifier found one missing artifact.",
                "risks": ["The missing artifact may hide a broader issue."],
                "confidence": 0.5,
            }
        )

        self.assertEqual(SteeringProposal.from_dict(proposal.to_dict()), proposal)

    def test_steering_proposal_rejects_invalid_confidence(self) -> None:
        payload = {
            "proposal_id": "SP-001",
            "mission_run_id": "run-001",
            "iteration": 1,
            "input_refs": ["mission/state_001.json"],
            "recommended_route": "repair",
            "confidence": 1.2,
        }

        with self.assertRaises(ContractValidationError):
            SteeringProposal.from_dict(payload)

    def test_steering_proposal_cannot_claim_closure(self) -> None:
        payload = {
            "proposal_id": "SP-001",
            "mission_run_id": "run-001",
            "iteration": 1,
            "input_refs": ["mission/state_001.json"],
            "recommended_route": "complete",
            "confidence": 0.8,
        }

        with self.assertRaises(ContractValidationError):
            SteeringProposal.from_dict(payload)

    def test_rejected_proposal_requires_reason(self) -> None:
        with self.assertRaises(ContractValidationError):
            ProposalValidationResult(
                proposal_id="SP-001",
                status=ProposalValidationStatus.REJECTED,
                reasons=[],
            ).to_dict()

    def test_proposal_validation_result_round_trip(self) -> None:
        result = ProposalValidationResult(
            proposal_id="SP-001",
            status=ProposalValidationStatus.ACCEPTED,
            reasons=[],
            accepted_contract_ref="work_units/WU-001.json",
        )

        self.assertEqual(ProposalValidationResult.from_dict(result.to_dict()), result)

    def test_state_correction_round_trip(self) -> None:
        correction = StateCorrection.from_dict(
            {
                "corrected_field": "known_bad",
                "source_ref": "verification/result.json",
                "trust_level": "verifier_result",
                "correction": "Required artifact is missing.",
            }
        )

        self.assertEqual(correction.trust_level, EvidenceTrustLevel.VERIFIER_RESULT)
        self.assertEqual(StateCorrection.from_dict(correction.to_dict()), correction)


if __name__ == "__main__":
    unittest.main()
