from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from missionforge.ir import MissionIR
from missionforge.runner import MissionRuntime
from missionforge.metric_store import MetricStore
from tests.test_ir import sample_mission_payload


class RuntimeMetricBoundaryTests(unittest.TestCase):
    def test_runtime_writes_metric_refs_without_changing_status(self) -> None:
        mission = MissionIR.from_dict(sample_mission_payload())

        with TemporaryDirectory() as tmpdir:
            result = MissionRuntime(workspace=tmpdir).run(mission)
            root = Path(tmpdir)
            run = json.loads((root / "runs/run-sample-mission/mission_run.json").read_text(encoding="utf-8"))
            store = MetricStore(root)
            projection = store.load_projection("run-sample-mission")

            self.assertEqual(result.status, "completed_verified")
            self.assertEqual(result.metrics["metric_events_ref"], "runs/run-sample-mission/metrics/events.jsonl")
            self.assertEqual(result.metrics["metric_projection_ref"], "runs/run-sample-mission/metrics/projection.json")
            self.assertEqual(run["metrics"]["metric_projection_ref"], result.metrics["metric_projection_ref"])
            self.assertIn("missionforge.runtime", projection.namespaces)
            self.assertIn("missionforge.worker.pi_agent", projection.namespaces)
            self.assertEqual(projection.namespaces["missionforge.runtime"]["attempt_count"], 1)

    def test_runtime_routing_does_not_depend_on_adapter_private_metric_values(self) -> None:
        mission = MissionIR.from_dict(sample_mission_payload())

        with TemporaryDirectory() as tmpdir:
            result = MissionRuntime(workspace=tmpdir).run(mission)
            root = Path(tmpdir)
            metrics_path = root / "attempts/WU-000001/pi_agent_metrics.json"
            metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
            metrics["redesign_required"] = True
            metrics["unsafe_proposal_rejection_count"] = 99
            metrics_path.write_text(json.dumps(metrics, sort_keys=True), encoding="utf-8")
            projection = MetricStore(root).load_projection("run-sample-mission")

            self.assertEqual(result.status, "completed_verified")
            self.assertNotIn("redesign_required", projection.diagnostic_flags)
            self.assertNotIn("unsafe_steering_proposal_rejected", projection.diagnostic_flags)


if __name__ == "__main__":
    unittest.main()
