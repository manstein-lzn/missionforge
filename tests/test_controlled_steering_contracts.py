from __future__ import annotations

import unittest

from missionforge import (
    AuthorityRequirement,
    ContractValidationError,
    ReviewPacket,
    assert_refs_only_payload,
)
from missionforge.steering import (
    ContractAdjustmentRequest,
    ObservationSignal,
    RepairStrategyProposal,
    SteeringContext,
)


class ControlledSteeringContractTests(unittest.TestCase):
    def test_steering_context_round_trip(self) -> None:
        context = SteeringContext.from_dict(
            {
                "mission_run_id": "run-mission-001",
                "mission_id": "mission-001",
                "iteration": 1,
                "contract_ref": "mission/frozen_contract.json",
                "contract_hash": "sha256:abc",
                "mission_run_ref": "runs/run-mission-001/mission_run.json",
                "attempt_refs": [],
                "verification_refs": [],
                "artifact_hygiene_ref": "runs/run-mission-001/artifact_hygiene.json",
                "failed_constraint_ids": [],
                "allowed_output_roots": ["package"],
                "visible_refs": ["mission/frozen_contract.json"],
                "forbidden_actions": ["close_without_verifier"],
                "safe_summary": "Initial dispatch.",
            }
        )

        self.assertEqual(SteeringContext.from_dict(context.to_dict()), context)

    def test_refs_only_payload_rejects_raw_prompt(self) -> None:
        with self.assertRaises(ContractValidationError):
            assert_refs_only_payload({"raw_prompt": "hidden"}, "payload")

    def test_observation_signal_cannot_close_mission(self) -> None:
        with self.assertRaises(ContractValidationError):
            ObservationSignal.from_dict(
                {
                    "signal_id": "signal-001",
                    "mission_run_id": "run-mission-001",
                    "iteration": 1,
                    "observation_ref": "runs/run-mission-001/attempts.jsonl",
                    "source_refs": ["runs/run-mission-001/attempts.jsonl"],
                    "signal_type": "root_cause_hypothesis",
                    "safe_summary": "Looks complete.",
                    "trust_level": "llm_interpretation",
                    "recommended_action": "complete",
                    "confidence": 0.4,
                    "requires_verifier_confirmation": True,
                }
            )

    def test_contract_adjustment_routes_authority(self) -> None:
        shrink = ContractAdjustmentRequest.from_dict(
            {
                "request_id": "adjust-001",
                "mission_run_id": "run-mission-001",
                "iteration": 1,
                "contract_ref": "work_units/WU-000001.json",
                "requested_change": "split",
                "reason": "Split ambiguous work.",
                "evidence_refs": ["runs/run-mission-001/attempts.jsonl"],
                "authority_required": "harness",
            }
        )
        expand = ContractAdjustmentRequest.from_dict(
            {
                "request_id": "adjust-002",
                "mission_run_id": "run-mission-001",
                "iteration": 1,
                "contract_ref": "work_units/WU-000001.json",
                "requested_change": "expand",
                "reason": "Need broader scope.",
                "evidence_refs": ["runs/run-mission-001/attempts.jsonl"],
                "authority_required": "reviewer",
            }
        )

        self.assertEqual(shrink.authority_route(), "harness_authorized")
        self.assertEqual(expand.authority_route(), "review_required")

    def test_contract_adjustment_rejects_weak_expansion_authority(self) -> None:
        with self.assertRaises(ContractValidationError):
            ContractAdjustmentRequest.from_dict(
                {
                    "request_id": "adjust-002",
                    "mission_run_id": "run-mission-001",
                    "iteration": 1,
                    "contract_ref": "work_units/WU-000001.json",
                    "requested_change": "expand",
                    "reason": "Need broader scope.",
                    "evidence_refs": ["runs/run-mission-001/attempts.jsonl"],
                    "authority_required": AuthorityRequirement.HARNESS.value,
                }
            )

    def test_repair_strategy_and_review_packet_round_trip(self) -> None:
        strategy = RepairStrategyProposal.from_dict(
            {
                "strategy_id": "repair-001",
                "mission_run_id": "run-mission-001",
                "iteration": 1,
                "failure_refs": ["verification/result.json"],
                "failed_constraint_ids": ["C-001"],
                "repair_order": ["C-001"],
                "work_unit_splits": [{"contract_ref": "work_units/WU-000001.json"}],
                "risk_notes": ["Root cause may be broader."],
                "stop_conditions": ["Contract revision required."],
                "confidence": 0.7,
            }
        )
        packet = ReviewPacket.from_dict(
            {
                "review_packet_id": "review-packet-001",
                "mission_run_id": "run-mission-001",
                "iteration": 1,
                "reason": "Manual gate.",
                "contract_ref": "mission/frozen_contract.json",
                "contract_hash": "sha256:abc",
                "mission_run_ref": "runs/run-mission-001/mission_run.json",
                "attempt_refs": ["runs/run-mission-001/attempts.jsonl"],
                "verification_refs": [],
                "proposal_refs": [],
                "failed_constraint_ids": [],
                "questions": ["Can the delegatable gate be approved?"],
                "forbidden_decisions": ["override_failed_executable_validator"],
            }
        )

        self.assertEqual(RepairStrategyProposal.from_dict(strategy.to_dict()), strategy)
        self.assertEqual(ReviewPacket.from_dict(packet.to_dict()), packet)


if __name__ == "__main__":
    unittest.main()
