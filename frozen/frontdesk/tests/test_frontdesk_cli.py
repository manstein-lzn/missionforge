from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from missionforge.adapters.cli import MissionCLI, MissionCommandResult
from missionforge.adapters.pi_agent_runtime import PiAgentRuntimeAdapter
from missionforge.frontdesk.cli import _frontdesk_worker_from_args


class FrontDeskCLITests(unittest.TestCase):
    def test_cli_can_construct_default_frontdesk_piworker(self) -> None:
        parser = MissionCLI().run_command
        result = parser(
            [
                "frontdesk",
                "inspect",
                "--workspace",
                ".",
                "--session",
                "frontdesk/session.json",
                "--use-default-piworker",
                "--piworker-provider-mode",
                "faux",
                "--piworker-timeout-seconds",
                "12",
            ]
        )

        self.assertEqual(result.error.code if result.error else "", "missing_state")

    def test_frontdesk_worker_arg_factory_builds_pi_agent_runtime(self) -> None:
        from argparse import Namespace

        worker = _frontdesk_worker_from_args(
            Namespace(
                use_default_piworker=True,
                piworker_provider_mode="faux",
                piworker_provider_config_source="env",
                piworker_model="missionforge-faux",
                piworker_timeout_seconds=12,
            )
        )

        self.assertIsInstance(worker, PiAgentRuntimeAdapter)
        self.assertEqual(worker.config.provider_mode, "faux")
        self.assertEqual(worker.config.model, "missionforge-faux")
        self.assertEqual(worker.config.timeout_seconds, 12)

    def test_frontdesk_draft_fails_closed_without_llm_node(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            cli = MissionCLI()
            start = cli.run_command(
                [
                    "frontdesk",
                    "start",
                    "--workspace",
                    tempdir,
                    "--text",
                    "Build a README for a local package. Expected output is package/README.md and success means the file exists.",
                    "--session-id",
                    "fd-cli",
                ]
            )
            draft = cli.run_command(["frontdesk", "draft", "--workspace", tempdir, "--session", "frontdesk/session.json"])

            self.assertEqual(MissionCommandResult.from_dict(start.to_dict()), start)
            self.assertEqual(start.command, "frontdesk")
            self.assertEqual(start.exit_code, 0)
            self.assertEqual(draft.exit_code, 2)
            self.assertIn("requires an explicit LLM/PiWorker node", draft.error.message if draft.error else "")
            session = json.loads((Path(tempdir) / "frontdesk/session.json").read_text(encoding="utf-8"))
            self.assertEqual(session["status"], "failed_closed")
            self.assertEqual(session["next_action"], "configure_frontdesk_llm")

    def test_freeze_fails_before_approval(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            cli = MissionCLI()
            cli.run_command(
                [
                    "frontdesk",
                    "start",
                    "--workspace",
                    tempdir,
                    "--text",
                    "Build docs. Expected output is docs/output.md and success means the file exists.",
                    "--session-id",
                    "fd-cli",
                ]
            )

            result = cli.run_command(["frontdesk", "freeze", "--workspace", tempdir, "--session", "frontdesk/session.json"])

            self.assertNotEqual(result.exit_code, 0)
            self.assertEqual(result.error.code if result.error else "", "invalid_input")

    def test_inspect_is_refs_only(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            cli = MissionCLI()
            cli.run_command(
                [
                    "frontdesk",
                    "start",
                    "--workspace",
                    tempdir,
                    "--text",
                    "Raw private details stay out of inspect.",
                    "--session-id",
                    "fd-cli",
                ]
            )
            inspect = cli.run_command(["frontdesk", "inspect", "--workspace", tempdir, "--session", "frontdesk/session.json"])
            payload = json.dumps(inspect.to_dict(), sort_keys=True)

            self.assertIn("frontdesk/session.json", payload)
            self.assertNotIn("Raw private details", payload)
            self.assertIn("missing_artifacts", payload)
            self.assertIn("freeze_ready", payload)

    def test_explicit_spec_grill_stops_at_llm_node_without_llm(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            cli = MissionCLI()
            cli.run_command(
                [
                    "frontdesk",
                    "start",
                    "--workspace",
                    tempdir,
                    "--text",
                    "Build docs/output.md. Success means docs/output.md exists.",
                    "--session-id",
                    "fd-cli-explicit",
                ]
            )

            scout = cli.run_command(["frontdesk", "scout", "--workspace", tempdir, "--session", "frontdesk/session.json"])
            grill = cli.run_command(["frontdesk", "grill", "--workspace", tempdir, "--session", "frontdesk/session.json"])

            self.assertEqual(scout.exit_code, 0, scout.error.message if scout.error else "")
            self.assertEqual(grill.exit_code, 2)
            self.assertIn("requires an explicit LLM/PiWorker node", grill.error.message if grill.error else "")
            self.assertFalse((Path(tempdir) / "frontdesk/mission_mapping_report.json").exists())

    def test_inspect_reports_latest_question_and_freeze_readiness(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            cli = MissionCLI()
            cli.run_command(
                [
                    "frontdesk",
                    "start",
                    "--workspace",
                    tempdir,
                    "--text",
                    "I think this should be implemented in Rust.",
                    "--session-id",
                    "fd-cli-question",
                ]
            )
            cli.run_command(["frontdesk", "draft", "--workspace", tempdir, "--session", "frontdesk/session.json"])
            inspect = cli.run_command(["frontdesk", "inspect", "--workspace", tempdir, "--session", "frontdesk/session.json"])

            self.assertEqual(inspect.data["freeze_ready"], False)
            self.assertIn("frontdesk/draft_mission.json", inspect.data["missing_artifacts"])
            self.assertIsNone(inspect.data["latest_question"])
            self.assertEqual(inspect.data["plan_review_status"], "missing")
            self.assertEqual(inspect.data["status"], "failed_closed")
            self.assertEqual(inspect.data["next_action"], "configure_frontdesk_llm")

    def test_invalid_session_ref_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            result = MissionCLI().run_command(
                ["frontdesk", "inspect", "--workspace", tempdir, "--session", "../outside.json"]
            )

            self.assertEqual(result.exit_code, 2)
            self.assertEqual(result.error.code if result.error else "", "invalid_input")

    def test_intent_and_generic_compile_product_commands(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            cli = MissionCLI()
            cli.run_command(
                [
                    "frontdesk",
                    "start",
                    "--workspace",
                    tempdir,
                    "--text",
                    "Build docs/output.md. Success means docs/output.md exists.",
                    "--session-id",
                    "fd-cli-intent",
                ]
            )
            intent = cli.run_command(["frontdesk", "intent", "--workspace", tempdir, "--session", "frontdesk/session.json"])
            compiled = cli.run_command(
                [
                    "frontdesk",
                    "compile-product",
                    "--workspace",
                    tempdir,
                    "--session",
                    "frontdesk/session.json",
                    "--integration-ref",
                    "generic",
                ]
            )

            self.assertEqual(intent.exit_code, 2)
            self.assertEqual(compiled.exit_code, 2)
            self.assertIn("requires an explicit LLM/PiWorker node", intent.error.message if intent.error else "")
            self.assertIn("requires an explicit LLM/PiWorker node", compiled.error.message if compiled.error else "")


if __name__ == "__main__":
    unittest.main()
