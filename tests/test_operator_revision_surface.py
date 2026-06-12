from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from missionforge.ir import MissionIR
from missionforge.adapters.cli import MissionCLI
from tests.revision_repair_helpers import run_and_apply_split_revision
from tests.test_ir import sample_mission_payload


class OperatorRevisionSurfaceTests(unittest.TestCase):
    def test_inspect_surfaces_current_contract_and_revision_refs(self) -> None:
        mission = MissionIR.from_dict(sample_mission_payload())

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            revision = run_and_apply_split_revision(root, mission)

            result = MissionCLI().run_command(["inspect", "--workspace", str(root), "--run", "run-sample-mission"])

        self.assertEqual(result.exit_code, 0)
        self.assertEqual(result.data["current_contract_ref"], revision.new_contract_ref)
        self.assertEqual(result.data["current_contract_hash"], revision.new_contract_hash)
        self.assertEqual(result.data["latest_revision_ref"], revision.revision_decision_ref.replace("decision.json", "revision.json"))
        self.assertIn("runs/run-sample-mission/revisions/revision-000001/revision.json", result.data["revision_refs"])
        self.assertIn(revision.new_contract_ref, result.refs)
        self.assertIn("runs/run-sample-mission/revisions/revision-000001/revision.json", result.refs)
        self.assertNotIn("expanded_mission", result.data)


if __name__ == "__main__":
    unittest.main()
