from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from missionforge import ContractValidationError
from missionforge.frontdesk import FrontDesk
from missionforge.adapters.pi_agent_runtime import PiAgentRuntimeAdapter, PiAgentRuntimeConfig
from tests.frontdesk_llm_fixtures import seed_llm_authored_frontdesk_artifacts


class FrontDeskServiceTests(unittest.TestCase):
    def test_frontdesk_can_be_built_with_default_piworker(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            frontdesk = FrontDesk.with_default_piworker(
                workspace=tempdir,
                piworker_config=PiAgentRuntimeConfig(command=("pi-agent-runtime",)),
            )

            self.assertIsInstance(frontdesk.worker, PiAgentRuntimeAdapter)
            self.assertEqual(frontdesk.worker.config.command, ("pi-agent-runtime",))

    def test_draft_fails_closed_without_llm_node(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            frontdesk = FrontDesk(workspace=tempdir)
            session = frontdesk.start("Build a README for a local package.", session_id="fd-service")
            session = frontdesk.answer(session.session_ref, "The expected output is package/README.md.")

            with self.assertRaisesRegex(ContractValidationError, "requires an explicit LLM/PiWorker node"):
                frontdesk.draft(session.session_ref)
            inspect = frontdesk.inspect(session.session_ref)

            self.assertEqual(inspect.status, "failed_closed")
            self.assertEqual(inspect.next_action, "configure_frontdesk_llm")

    def test_inspect_is_refs_only(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            frontdesk = FrontDesk(workspace=tempdir)
            session = frontdesk.start("Secret raw wording should stay in provenance only.", session_id="fd-inspect")
            inspect_text = str(frontdesk.inspect(session.session_ref).to_dict())

            self.assertIn("frontdesk/session.json", inspect_text)
            self.assertNotIn("Secret raw wording", inspect_text)

    def test_seeded_llm_artifacts_allow_intent_bundle_without_raw_text_truth(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            frontdesk = FrontDesk(workspace=tempdir)
            session = frontdesk.start(
                "Build docs for the public API. Expected output is docs/output.md and success means the file exists.",
                session_id="fd-draft",
            )
            seed_llm_authored_frontdesk_artifacts(
                frontdesk,
                session.session_ref,
                expected_artifacts=["docs/output.md"],
            )
            frontdesk.build_intent_bundle(session.session_ref)
            semantic_lock = frontdesk.workspace.read_json("frontdesk/semantic_lock.json")

            self.assertIn("requirement_clauses", semantic_lock)
            self.assertNotIn("conversation", semantic_lock)
            self.assertTrue((Path(tempdir) / "frontdesk/intent_bundle.json").exists())
            self.assertEqual(
                frontdesk.workspace.read_json("frontdesk/sanitized_sources.json")["excluded_source_refs"],
                ["frontdesk/conversation.jsonl"],
            )


if __name__ == "__main__":
    unittest.main()
