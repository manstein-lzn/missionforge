from __future__ import annotations

import unittest

from missionforge import ReviewerDecision
from missionforge.contracts import ContractValidationError


class ReviewerDecisionTests(unittest.TestCase):
    def test_reviewer_decision_round_trip_and_current_validation(self) -> None:
        decision = ReviewerDecision(
            reviewer_id="reviewer",
            decision="approved",
            contract_hash="sha256:contract",
            capsule_id="capsule-1",
            capsule_revision=3,
            evidence_refs=["evidence/review.json"],
            notes="approved",
        )

        self.assertEqual(ReviewerDecision.from_dict(decision.to_dict()), decision)
        decision.validate_current(
            contract_hash="sha256:contract",
            capsule_id="capsule-1",
            capsule_revision=3,
        )

    def test_stale_reviewer_decision_is_rejected(self) -> None:
        decision = ReviewerDecision(
            reviewer_id="reviewer",
            decision="approved",
            contract_hash="sha256:old",
            capsule_id="capsule-1",
            capsule_revision=1,
        )

        with self.assertRaises(ContractValidationError):
            decision.validate_current(contract_hash="sha256:new", capsule_id="capsule-1", capsule_revision=1)

    def test_worker_authored_reviewer_decision_is_rejected(self) -> None:
        with self.assertRaises(ContractValidationError):
            ReviewerDecision(
                reviewer_id="worker",
                decision="approved",
                contract_hash="sha256:contract",
                author_role="worker",
            ).validate()

    def test_needs_changes_is_not_current_approval(self) -> None:
        decision = ReviewerDecision(
            reviewer_id="reviewer",
            decision="needs_changes",
            contract_hash="sha256:contract",
            capsule_id="capsule-1",
            capsule_revision=1,
        )

        with self.assertRaises(ContractValidationError):
            decision.validate_current(contract_hash="sha256:contract", capsule_id="capsule-1", capsule_revision=1)


if __name__ == "__main__":
    unittest.main()
