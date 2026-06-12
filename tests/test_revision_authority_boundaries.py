from __future__ import annotations

import unittest

from missionforge import ContractValidationError, ReviewerDecision
from missionforge.ir import MissionIR
from missionforge.steering import ContractAdjustmentRequest
from missionforge.freeze import freeze_mission
from missionforge.revision import MissionRevisionRequest, MissionRevisionWorkflow
from tests.test_ir import sample_mission_payload


class RevisionAuthorityBoundaryTests(unittest.TestCase):
    def test_stale_base_contract_hash_is_rejected(self) -> None:
        mission = MissionIR.from_dict(sample_mission_payload())
        old_contract = freeze_mission(mission)
        request = MissionRevisionRequest.from_adjustment(
            ContractAdjustmentRequest.from_dict(
                {
                    "request_id": "adjust-001",
                    "mission_run_id": "run-sample-mission",
                    "iteration": 1,
                    "contract_ref": "mission/frozen_contract.json",
                    "requested_change": "split",
                    "reason": "Split work.",
                    "evidence_refs": ["runs/run-sample-mission/attempts.jsonl"],
                    "authority_required": "harness",
                }
            ),
            base_contract_ref="mission/frozen_contract.json",
            base_contract_hash="sha256:stale",
            request_ref="runs/run-sample-mission/revisions/revision-000001/request.json",
            revision_id="revision-000001",
        )
        decision = MissionRevisionWorkflow().decide(request)

        with self.assertRaises(ContractValidationError):
            MissionRevisionWorkflow().apply(
                mission,
                request,
                decision,
                old_contract=old_contract,
                new_contract_ref="runs/run-sample-mission/revisions/revision-000001/frozen_contract.json",
                decision_ref="runs/run-sample-mission/revisions/revision-000001/decision.json",
            )

    def test_reviewer_approval_must_match_current_contract_hash(self) -> None:
        mission = MissionIR.from_dict(sample_mission_payload())
        old_contract = freeze_mission(mission)
        request = MissionRevisionRequest.from_adjustment(
            ContractAdjustmentRequest.from_dict(
                {
                    "request_id": "adjust-002",
                    "mission_run_id": "run-sample-mission",
                    "iteration": 1,
                    "contract_ref": "mission/frozen_contract.json",
                    "requested_change": "review_required",
                    "reason": "Require review.",
                    "evidence_refs": ["runs/run-sample-mission/attempts.jsonl"],
                    "authority_required": "reviewer",
                }
            ),
            base_contract_ref="mission/frozen_contract.json",
            base_contract_hash=old_contract.contract_hash,
            request_ref="runs/run-sample-mission/revisions/revision-000001/request.json",
            revision_id="revision-000001",
        )
        stale_review = ReviewerDecision(
            reviewer_id="reviewer-1",
            decision="approved",
            contract_hash="sha256:stale",
            evidence_refs=["reviews/reviewer-decision.json"],
        )

        with self.assertRaises(ContractValidationError):
            MissionRevisionWorkflow().decide(
                request,
                reviewer_decision=stale_review,
                reviewer_decision_ref="reviews/reviewer-decision.json",
            )


if __name__ == "__main__":
    unittest.main()
