from __future__ import annotations

import unittest

from missionforge import ContractValidationError
from missionforge.frontdesk import FrontDeskAuthoringSession
from missionforge.frontdesk.schema import FrontDeskStatus


class FrontDeskStateTests(unittest.TestCase):
    def test_new_session_is_refs_only(self) -> None:
        session = FrontDeskAuthoringSession.new("fd-001")
        payload = session.to_dict()

        self.assertEqual(payload["session_ref"], "frontdesk/session.json")
        self.assertEqual(payload["conversation_ref"], "frontdesk/conversation.jsonl")
        self.assertNotIn("conversation", payload)
        self.assertNotIn("messages", payload)

    def test_state_transitions_reject_invalid_jumps(self) -> None:
        session = FrontDeskAuthoringSession.new("fd-001")
        with self.assertRaisesRegex(ContractValidationError, "invalid FrontDesk transition"):
            session.transition(FrontDeskStatus.FROZEN)

    def test_valid_transition_chain_reaches_approved(self) -> None:
        session = (
            FrontDeskAuthoringSession.new("fd-001")
            .transition(FrontDeskStatus.ELICITING)
            .transition(FrontDeskStatus.DRAFT_READY)
            .transition(FrontDeskStatus.APPROVAL_REQUIRED)
            .transition(FrontDeskStatus.APPROVED)
        )

        self.assertEqual(session.status, FrontDeskStatus.APPROVED)
        self.assertEqual(session.next_action, "freeze")

    def test_frozen_state_requires_mission_refs_and_hash(self) -> None:
        session = FrontDeskAuthoringSession.new("fd-001").with_freeze(
            mission_ir_ref="missions/fd-001.mission.json",
            frozen_contract_ref="missions/fd-001.frozen_contract.json",
            contract_hash="sha256:abc",
        )

        self.assertEqual(session.status, FrontDeskStatus.FROZEN)
        self.assertEqual(session.next_action, "handoff_task_contract")

        with self.assertRaisesRegex(ContractValidationError, "contract_hash"):
            FrontDeskAuthoringSession(
                session_id="fd-001",
                status=FrontDeskStatus.FROZEN,
                mission_ir_ref="missions/fd-001.mission.json",
                frozen_contract_ref="missions/fd-001.frozen_contract.json",
            ).validate()


if __name__ == "__main__":
    unittest.main()
