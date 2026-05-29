from __future__ import annotations

import tempfile
import unittest

from missionforge import ContractValidationError, FrontDesk


class FrontDeskSpecGrillFreezeGateTests(unittest.TestCase):
    def test_freeze_requires_complete_spec_grill_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            frontdesk = FrontDesk(workspace=tempdir)
            session = frontdesk.start(
                "Build docs/output.md. Success means docs/output.md exists.",
                session_id="fd-freeze-missing",
            )
            frontdesk.workspace.write_json(
                "frontdesk/authoring_approval.json",
                {
                    "session_id": "fd-freeze-missing",
                    "approved_by": "user",
                    "authority": "user",
                    "approved_ref": "frontdesk/mission_plan.json",
                    "approved_hash": "sha256:abc",
                },
            )

            with self.assertRaisesRegex(ContractValidationError, "complete spec-grill"):
                frontdesk.freeze(session.session_ref)

            self.assertTrue(frontdesk.workspace.exists("frontdesk/freeze_gate_result.json"))

    def test_full_spec_grill_flow_freezes_and_writes_gate_result(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            frontdesk = FrontDesk(workspace=tempdir)
            session = frontdesk.start(
                "Build docs/output.md. Success means docs/output.md exists.",
                session_id="fd-freeze",
            )

            session = frontdesk.draft(session.session_ref)
            audit = frontdesk.audit(session.session_ref)
            approval = frontdesk.approve(session.session_ref, approved_by="user")
            result = frontdesk.freeze(session.session_ref)
            gate_result = frontdesk.workspace.read_json("frontdesk/freeze_gate_result.json")

            self.assertEqual(audit.decision.value, "approve")
            self.assertTrue(approval.approved_hash.startswith("sha256:"))
            self.assertEqual(gate_result["decision"], "freeze")
            self.assertEqual(gate_result["failed_checks"], [])
            self.assertTrue(frontdesk.workspace.exists(result.frozen_contract_ref))

    def test_freeze_rejects_stale_authoring_approval_hash(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            frontdesk = FrontDesk(workspace=tempdir)
            session = frontdesk.start(
                "Build docs/output.md. Success means docs/output.md exists.",
                session_id="fd-freeze-stale",
            )
            session = frontdesk.draft(session.session_ref)
            frontdesk.audit(session.session_ref)
            frontdesk.approve(session.session_ref, approved_by="user")
            mission_brief = frontdesk.workspace.read_json("frontdesk/mission_brief.json")
            mission_brief["goal"] = "Changed after approval."
            frontdesk.workspace.write_json("frontdesk/mission_brief.json", mission_brief)

            with self.assertRaisesRegex(ContractValidationError, "approval hash"):
                frontdesk.freeze(session.session_ref)

            gate_result = frontdesk.workspace.read_json("frontdesk/freeze_gate_result.json")
            self.assertIn("authoring_approval_hash", gate_result["failed_checks"])

    def test_freeze_writes_gate_result_for_stale_plan_review_hash(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            frontdesk = FrontDesk(workspace=tempdir)
            session = frontdesk.start(
                "Build docs/output.md. Success means docs/output.md exists.",
                session_id="fd-freeze-plan-stale",
            )
            session = frontdesk.draft(session.session_ref)
            frontdesk.audit(session.session_ref)
            frontdesk.approve(session.session_ref, approved_by="user")
            solution_plan = frontdesk.workspace.read_json("frontdesk/solution_plan.json")
            solution_plan["summary"] = "Changed after plan review."
            frontdesk.workspace.write_json("frontdesk/solution_plan.json", solution_plan)

            with self.assertRaisesRegex(ContractValidationError, "plan review hash"):
                frontdesk.freeze(session.session_ref)

            gate_result = frontdesk.workspace.read_json("frontdesk/freeze_gate_result.json")
            self.assertIn("plan_review_hash", gate_result["failed_checks"])


if __name__ == "__main__":
    unittest.main()
