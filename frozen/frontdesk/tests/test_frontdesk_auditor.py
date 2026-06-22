from __future__ import annotations

import unittest

from missionforge.frontdesk import ScriptedFrontDeskLLMClient, SpecAuditor, deterministic_contract_audit
from tests.test_frontdesk_compiler import sample_frontdesk_artifacts


class FrontDeskAuditorTests(unittest.TestCase):
    def test_auditor_returns_valid_route(self) -> None:
        _semantic_lock, _brief, _profiles, plan, _approval, _sources = sample_frontdesk_artifacts()
        client = ScriptedFrontDeskLLMClient(
            [
                {
                    "session_id": "fd-compiler",
                    "audit": {
                        "session_id": "fd-compiler",
                        "decision": "approve",
                        "findings": [],
                        "required_followup_questions": [],
                    },
                }
            ]
        )
        result = SpecAuditor().audit(session_id="fd-compiler", plan=plan.to_dict(), client=client)

        self.assertEqual(result.audit.decision.value, "approve")

    def test_deterministic_audit_blocks_unknown_validator_language(self) -> None:
        semantic_lock, brief, profiles, plan, approval, _sources = sample_frontdesk_artifacts()
        bad_plan = type(plan)(
            session_id=plan.session_id,
            expected_artifacts=plan.expected_artifacts,
            validators=[
                {
                    "validator_id": "V-future",
                    "constraint_refs": [f"FD-{semantic_lock.session_id}-C-authoring-contract"],
                    "type": "future_validator",
                }
            ],
        )
        audit = deterministic_contract_audit(
            semantic_lock=semantic_lock,
            mission_brief=brief,
            profile_recommendations=profiles,
            mission_plan=bad_plan,
            approval=approval,
        )

        self.assertEqual(audit.decision.value, "failed_closed")
        self.assertIn("not declared", audit.findings[0])


if __name__ == "__main__":
    unittest.main()
