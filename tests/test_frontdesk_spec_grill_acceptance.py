from __future__ import annotations

import tempfile
import unittest

from missionforge import ContractValidationError, FrontDesk
from missionforge.frontdesk.mission_mapper import MissionIRMapper
from missionforge.frontdesk.schema import ApprovalAuthority
from tests.frontdesk_llm_fixtures import seed_llm_authored_frontdesk_artifacts


class FrontDeskSpecGrillAcceptanceTests(unittest.TestCase):
    def test_vague_implementation_input_fails_closed_without_llm(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            frontdesk = FrontDesk(workspace=tempdir)
            session = frontdesk.start("I think this should be implemented in Rust.", session_id="fd-accept-vague")

            with self.assertRaisesRegex(ContractValidationError, "requires an explicit LLM/PiWorker node"):
                frontdesk.draft(session.session_ref)
            inspect = frontdesk.inspect(session.session_ref)

            self.assertEqual(inspect.status, "failed_closed")
            self.assertEqual(inspect.next_action, "configure_frontdesk_llm")
            self.assertFalse(frontdesk.workspace.exists("frontdesk/draft_mission.json"))

    def test_complete_input_reaches_frozen_contract_through_spec_grill(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            frontdesk = FrontDesk(workspace=tempdir)
            session = frontdesk.start(
                "Build docs/output.md. Success means docs/output.md exists and privacy remains protected.",
                session_id="fd-accept-complete",
            )

            seed_llm_authored_frontdesk_artifacts(
                frontdesk,
                session.session_ref,
                expected_artifacts=["docs/output.md"],
                constraints=["privacy remains protected"],
            )
            frontdesk.review_plan(session.session_ref, reviewed_by="user", authority=ApprovalAuthority.USER)
            MissionIRMapper().map(session=frontdesk.load_session(session.session_ref), workspace=frontdesk.workspace)
            audit = frontdesk.audit(session.session_ref)
            frontdesk.approve(session.session_ref, approved_by="user")
            result = frontdesk.freeze(session.session_ref)

            self.assertEqual(audit.decision.value, "approve")
            self.assertTrue(frontdesk.workspace.exists("frontdesk/semantic_coverage.json"))
            self.assertTrue(frontdesk.workspace.exists("frontdesk/solution_plan.json"))
            self.assertTrue(frontdesk.workspace.exists("frontdesk/plan_review.json"))
            self.assertTrue(frontdesk.workspace.exists("frontdesk/mission_mapping_report.json"))
            self.assertTrue(frontdesk.workspace.exists(result.frozen_contract_ref))


if __name__ == "__main__":
    unittest.main()
