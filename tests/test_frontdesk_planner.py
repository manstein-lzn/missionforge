from __future__ import annotations

import unittest

from missionforge import ContractValidationError
from missionforge.frontdesk import MissionPlanner, ScriptedFrontDeskLLMClient
from tests.test_frontdesk_compiler import sample_frontdesk_artifacts


class FrontDeskPlannerTests(unittest.TestCase):
    def test_clear_input_produces_draft_plan(self) -> None:
        _semantic_lock, brief, profiles, plan, _approval, _sources = sample_frontdesk_artifacts()
        client = ScriptedFrontDeskLLMClient(
            [
                {
                    "session_id": "fd-compiler",
                    "profile_recommendations": profiles.to_dict(),
                    "mission_plan": plan.to_dict(),
                }
            ]
        )
        result = MissionPlanner().plan(session_id="fd-compiler", brief=brief.to_dict(), client=client)

        self.assertEqual(result.mission_plan.expected_artifacts, ["package/README.md"])
        self.assertEqual(result.profile_recommendations.selected_verification_profiles[0].profile_id, "generic_local_verification")

    def test_planner_only_accepts_known_profiles(self) -> None:
        _semantic_lock, brief, profiles, plan, _approval, _sources = sample_frontdesk_artifacts()
        payload = profiles.to_dict()
        payload["recommendations"][0]["profile_id"] = "unknown_profile"
        client = ScriptedFrontDeskLLMClient(
            [{"session_id": "fd-compiler", "profile_recommendations": payload, "mission_plan": plan.to_dict()}]
        )

        with self.assertRaisesRegex(ContractValidationError, "unknown capability profile"):
            MissionPlanner().plan(session_id="fd-compiler", brief=brief.to_dict(), client=client)


if __name__ == "__main__":
    unittest.main()
