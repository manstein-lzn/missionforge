from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from missionforge import ContractValidationError, FrontDeskWorkspace


class FrontDeskWorkspaceTests(unittest.TestCase):
    def test_json_and_jsonl_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            workspace = FrontDeskWorkspace(tempdir)
            workspace.write_json("frontdesk/session.json", {"session_id": "fd-001"})
            workspace.append_jsonl("frontdesk/events.jsonl", {"event": "created"})

            self.assertEqual(workspace.read_json("frontdesk/session.json")["session_id"], "fd-001")
            self.assertEqual(workspace.read_jsonl("frontdesk/events.jsonl"), [{"event": "created"}])
            self.assertTrue((Path(tempdir) / "frontdesk/session.json").exists())

    def test_ref_escape_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            workspace = FrontDeskWorkspace(tempdir)
            with self.assertRaises(ContractValidationError):
                workspace.write_json("../escape.json", {"bad": True})

    def test_provenance_text_is_not_json_truth(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            workspace = FrontDeskWorkspace(tempdir)
            workspace.write_text_provenance("frontdesk/turns/turn-001.txt", "raw user wording")

            self.assertEqual(
                (Path(tempdir) / "frontdesk/turns/turn-001.txt").read_text(encoding="utf-8"),
                "raw user wording",
            )


if __name__ == "__main__":
    unittest.main()
