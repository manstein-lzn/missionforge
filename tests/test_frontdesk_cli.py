from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from missionforge.adapters.cli import MissionCLI, MissionCommandResult


class FrontDeskCLITests(unittest.TestCase):
    def test_frontdesk_command_happy_path_to_freeze(self) -> None:
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
            audit = cli.run_command(["frontdesk", "audit", "--workspace", tempdir, "--session", "frontdesk/session.json"])
            approve = cli.run_command(
                [
                    "frontdesk",
                    "approve",
                    "--workspace",
                    tempdir,
                    "--session",
                    "frontdesk/session.json",
                    "--approved-by",
                    "user",
                ]
            )
            freeze = cli.run_command(["frontdesk", "freeze", "--workspace", tempdir, "--session", "frontdesk/session.json"])

            for result in (start, draft, audit, approve, freeze):
                self.assertEqual(MissionCommandResult.from_dict(result.to_dict()), result)
                self.assertEqual(result.command, "frontdesk")
                self.assertEqual(result.exit_code, 0)
            self.assertTrue((Path(tempdir) / freeze.data["compile_result"]["mission_ir_ref"]).exists())

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
            cli.run_command(["frontdesk", "draft", "--workspace", tempdir, "--session", "frontdesk/session.json"])

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

    def test_explicit_spec_grill_commands(self) -> None:
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

            commands = [
                ["frontdesk", "scout", "--workspace", tempdir, "--session", "frontdesk/session.json"],
                ["frontdesk", "grill", "--workspace", tempdir, "--session", "frontdesk/session.json"],
                ["frontdesk", "cover-semantics", "--workspace", tempdir, "--session", "frontdesk/session.json"],
                ["frontdesk", "plan", "--workspace", tempdir, "--session", "frontdesk/session.json"],
                [
                    "frontdesk",
                    "review-plan",
                    "--workspace",
                    tempdir,
                    "--session",
                    "frontdesk/session.json",
                    "--reviewed-by",
                    "user",
                ],
                ["frontdesk", "map", "--workspace", tempdir, "--session", "frontdesk/session.json"],
            ]

            for command in commands:
                result = cli.run_command(command)
                self.assertEqual(result.exit_code, 0, result.error.message if result.error else "")

            self.assertTrue((Path(tempdir) / "frontdesk/mission_mapping_report.json").exists())

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
            self.assertIn("performance", inspect.data["latest_question"]["question"])
            self.assertEqual(inspect.data["plan_review_status"], "missing")

    def test_invalid_session_ref_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            result = MissionCLI().run_command(
                ["frontdesk", "inspect", "--workspace", tempdir, "--session", "../outside.json"]
            )

            self.assertEqual(result.exit_code, 2)
            self.assertEqual(result.error.code if result.error else "", "invalid_input")


if __name__ == "__main__":
    unittest.main()
