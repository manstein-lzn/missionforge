from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from missionforge.ir import MissionIR
from missionforge.runtime import RuntimeEngine
from tests.revision_repair_helpers import ResumableRevisionWorker, run_and_apply_split_revision
from tests.test_ir import sample_mission_payload


class RuntimeRevisionPreservationTests(unittest.TestCase):
    def test_resume_does_not_clear_recorded_revision_state(self) -> None:
        mission = MissionIR.from_dict(sample_mission_payload())

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            revision = run_and_apply_split_revision(root, mission)
            before = json.loads((root / "runs/run-sample-mission/mission_run.json").read_text(encoding="utf-8"))

            result = RuntimeEngine(workspace=root, worker=ResumableRevisionWorker()).resume(mission)
            after = json.loads((root / "runs/run-sample-mission/mission_run.json").read_text(encoding="utf-8"))

        self.assertEqual(before["current_contract_ref"], revision.new_contract_ref)
        self.assertEqual(after["current_contract_ref"], revision.new_contract_ref)
        self.assertEqual(after["current_contract_hash"], revision.new_contract_hash)
        self.assertEqual(after["revision_refs"], before["revision_refs"])
        self.assertEqual(result.metrics["contract_hash"], revision.new_contract_hash)
        self.assertEqual(result.metrics["current_contract_ref"], revision.new_contract_ref)
        self.assertIn("runs/run-sample-mission/revisions/revision-000001/revision.json", result.metrics["revision_refs"])


if __name__ == "__main__":
    unittest.main()
