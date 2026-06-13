from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from missionforge.adapters.cli import MissionCLI
from tests.operator_state_fixtures import seed_revision


class OperatorRevisionSurfaceTests(unittest.TestCase):
    def test_inspect_surfaces_current_contract_and_revision_refs(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            new_contract_ref, new_contract_hash = seed_revision(root)

            result = MissionCLI().run_command(["inspect", "--workspace", str(root), "--run", "run-sample-mission"])

        self.assertEqual(result.exit_code, 0)
        self.assertEqual(result.data["current_contract_ref"], new_contract_ref)
        self.assertEqual(result.data["current_contract_hash"], new_contract_hash)
        self.assertEqual(result.data["latest_revision_ref"], "runs/run-sample-mission/revisions/revision-000001/revision.json")
        self.assertIn("runs/run-sample-mission/revisions/revision-000001/revision.json", result.data["revision_refs"])
        self.assertIn(new_contract_ref, result.refs)
        self.assertIn("runs/run-sample-mission/revisions/revision-000001/revision.json", result.refs)
        self.assertNotIn("expanded_mission", result.data)


if __name__ == "__main__":
    unittest.main()
