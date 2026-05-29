from __future__ import annotations

import unittest

from missionforge import ContractAdjustmentRequest, ContractValidationError, MissionIR
from missionforge.freeze import freeze_mission
from missionforge.revision import MissionRevision, MissionRevisionDecision, MissionRevisionRequest, MissionRevisionWorkflow
from tests.test_ir import sample_mission_payload


def sample_adjustment(change: str = "split", authority: str = "harness") -> ContractAdjustmentRequest:
    return ContractAdjustmentRequest.from_dict(
        {
            "request_id": "adjust-001",
            "mission_run_id": "run-sample-mission",
            "iteration": 1,
            "contract_ref": "mission/frozen_contract.json",
            "requested_change": change,
            "reason": "Revise work shape.",
            "evidence_refs": ["runs/run-sample-mission/attempts.jsonl"],
            "authority_required": authority,
        }
    )


class MissionRevisionContractTests(unittest.TestCase):
    def test_revision_contracts_round_trip(self) -> None:
        mission = MissionIR.from_dict(sample_mission_payload())
        old_contract = freeze_mission(mission)
        request = MissionRevisionRequest.from_adjustment(
            sample_adjustment(),
            base_contract_ref="mission/frozen_contract.json",
            base_contract_hash=old_contract.contract_hash,
            request_ref="runs/run-sample-mission/revisions/revision-000001/request.json",
            revision_id="revision-000001",
        )
        decision = MissionRevisionWorkflow().decide(request)
        revised_mission, new_contract, revision = MissionRevisionWorkflow().apply(
            mission,
            request,
            decision,
            old_contract=old_contract,
            new_contract_ref="runs/run-sample-mission/revisions/revision-000001/frozen_contract.json",
            decision_ref="runs/run-sample-mission/revisions/revision-000001/decision.json",
        )

        self.assertEqual(MissionRevisionRequest.from_dict(request.to_dict()), request)
        self.assertEqual(MissionRevisionDecision.from_dict(decision.to_dict()), decision)
        self.assertEqual(MissionRevision.from_dict(revision.to_dict()), revision)
        self.assertNotEqual(old_contract.contract_hash, new_contract.contract_hash)
        self.assertIn("repair_policy.mission_revisions", revision.changed_fields)
        self.assertEqual(revised_mission.repair_policy["mission_revisions"][0]["revision_id"], "revision-000001")

    def test_unapproved_revision_cannot_apply(self) -> None:
        mission = MissionIR.from_dict(sample_mission_payload())
        old_contract = freeze_mission(mission)
        request = MissionRevisionRequest.from_adjustment(
            sample_adjustment(change="expand", authority="reviewer"),
            base_contract_ref="mission/frozen_contract.json",
            base_contract_hash=old_contract.contract_hash,
            request_ref="runs/run-sample-mission/revisions/revision-000001/request.json",
            revision_id="revision-000001",
        )
        decision = MissionRevisionWorkflow().decide(request)

        self.assertEqual(decision.decision, "needs_review")
        with self.assertRaises(ContractValidationError):
            MissionRevisionWorkflow().apply(
                mission,
                request,
                decision,
                old_contract=old_contract,
                new_contract_ref="runs/run-sample-mission/revisions/revision-000001/frozen_contract.json",
                decision_ref="runs/run-sample-mission/revisions/revision-000001/decision.json",
            )


if __name__ == "__main__":
    unittest.main()
