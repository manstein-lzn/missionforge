from __future__ import annotations

import json
import unittest

from missionforge import ContractValidationError
from missionforge.frontdesk import MissionPlanner, RequirementsElicitor, ScriptedFrontDeskLLMClient
from tests.test_frontdesk_compiler import sample_frontdesk_artifacts


class FrontDeskLLMBoundaryTests(unittest.TestCase):
    def test_model_output_cannot_approve_or_freeze(self) -> None:
        semantic_lock, brief, _profiles, _plan, _approval, _sources = sample_frontdesk_artifacts()
        response = {
            "session_id": "fd-compiler",
            "readiness": "draft_ready",
            "semantic_lock": semantic_lock.to_dict(),
            "mission_brief": brief.to_dict(),
            "questions": [],
            "authoring_approval": {"approved_by": "model"},
        }
        client = ScriptedFrontDeskLLMClient([response])

        with self.assertRaisesRegex(ContractValidationError, "unknown field"):
            RequirementsElicitor().elicit(session_id="fd-compiler", user_summary="build docs", client=client)

    def test_provider_secret_markers_do_not_pass_schema_validation(self) -> None:
        _semantic_lock, brief, profiles, plan, _approval, _sources = sample_frontdesk_artifacts()
        payload = profiles.to_dict()
        payload["recommendations"][0]["requirements"] = {"api_key": "secret"}
        client = ScriptedFrontDeskLLMClient(
            [{"session_id": "fd-compiler", "profile_recommendations": payload, "mission_plan": plan.to_dict()}]
        )

        with self.assertRaisesRegex(ContractValidationError, "api_key"):
            MissionPlanner().plan(session_id="fd-compiler", brief=brief.to_dict(), client=client)

    def test_llm_node_payloads_do_not_embed_raw_provider_output(self) -> None:
        _semantic_lock, brief, profiles, plan, _approval, _sources = sample_frontdesk_artifacts()
        client = ScriptedFrontDeskLLMClient(
            [{"session_id": "fd-compiler", "profile_recommendations": profiles.to_dict(), "mission_plan": plan.to_dict()}]
        )
        result = MissionPlanner().plan(session_id="fd-compiler", brief=brief.to_dict(), client=client)
        result_text = json.dumps(result.to_dict(), sort_keys=True)

        self.assertNotIn("raw_model_output", result_text)
        self.assertNotIn("provider_payload", result_text)


if __name__ == "__main__":
    unittest.main()
