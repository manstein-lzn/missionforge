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
                    "Build a README for a local package.",
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
            cli.run_command(["frontdesk", "start", "--workspace", tempdir, "--text", "Build docs.", "--session-id", "fd-cli"])
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

    def test_invalid_session_ref_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            result = MissionCLI().run_command(
                ["frontdesk", "inspect", "--workspace", tempdir, "--session", "../outside.json"]
            )

            self.assertEqual(result.exit_code, 2)
            self.assertEqual(result.error.code if result.error else "", "invalid_input")


if __name__ == "__main__":
    unittest.main()
