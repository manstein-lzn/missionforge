from __future__ import annotations

from tempfile import TemporaryDirectory
import unittest

from missionforge import JsonWorkspaceStore, MissionIR, MissionRuntime
from tests.test_ir import sample_mission_payload


class RuntimeStoreIntegrationTests(unittest.TestCase):
    def test_json_store_loads_runtime_outputs_without_layout_change(self) -> None:
        mission = MissionIR.from_dict(sample_mission_payload())

        with TemporaryDirectory() as tmpdir:
            MissionRuntime(workspace=tmpdir).run(mission)
            store = JsonWorkspaceStore(tmpdir)
            run = store.load_mission_run("run-sample-mission")
            attempts = store.load_attempts("run-sample-mission")
            metric_projection = store.read_json("runs/run-sample-mission/metrics/projection.json")

            self.assertEqual(run.attempts_ref, "runs/run-sample-mission/attempts.jsonl")
            self.assertEqual(run.artifact_hygiene_ref, "runs/run-sample-mission/artifact_hygiene.json")
            self.assertEqual(len(attempts), 1)
            self.assertIn("missionforge.runtime", metric_projection["namespaces"])


if __name__ == "__main__":
    unittest.main()
