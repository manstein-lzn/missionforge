from __future__ import annotations

import unittest

from missionforge import ContractValidationError
from missionforge.frontdesk import RequirementsElicitor, ScriptedFrontDeskLLMClient
from tests.test_frontdesk_compiler import sample_frontdesk_artifacts


class FrontDeskElicitorTests(unittest.TestCase):
    def test_vague_input_produces_clarification_question(self) -> None:
        semantic_lock, brief, _profiles, _plan, _approval, _sources = sample_frontdesk_artifacts()
        client = ScriptedFrontDeskLLMClient(
            [
                {
                    "session_id": "fd-compiler",
                    "readiness": "needs_clarification",
                    "semantic_lock": semantic_lock.to_dict(),
                    "mission_brief": brief.to_dict(),
                    "questions": [
                        {
                            "question_id": "Q-001",
                            "text": "What output should MissionForge verify?",
                            "reason": "The deliverable is not concrete enough.",
                        }
                    ],
                }
            ]
        )
        result = RequirementsElicitor().elicit(
            session_id="fd-compiler",
            user_summary="make something",
            client=client,
        )

        self.assertEqual(result.readiness, "needs_clarification")
        self.assertEqual(result.questions[0].question_id, "Q-001")

    def test_invalid_output_fails_closed(self) -> None:
        client = ScriptedFrontDeskLLMClient([{"session_id": "fd-001", "readiness": "draft_ready"}])

        with self.assertRaises(ContractValidationError):
            RequirementsElicitor().elicit(session_id="fd-001", user_summary="build docs", client=client)


if __name__ == "__main__":
    unittest.main()
