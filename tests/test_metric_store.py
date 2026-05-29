from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from missionforge.metric_store import MetricStore
from missionforge.metrics import MetricEvent


class MetricStoreTests(unittest.TestCase):
    def test_metric_store_writes_events_and_projection(self) -> None:
        with TemporaryDirectory() as tmpdir:
            store = MetricStore(tmpdir)
            event = MetricEvent(
                metric_id="ME-000001",
                mission_run_id="run-sample",
                namespace="missionforge.runtime",
                run_ref="runs/run-sample/mission_run.json",
                metric_kind="summary",
                values={"attempt_count": 1},
            )

            events_ref = store.write_events("run-sample", [event])
            projection = store.rebuild_projection("run-sample")
            projection_ref = store.write_projection(projection)

            self.assertEqual(events_ref, "runs/run-sample/metrics/events.jsonl")
            self.assertEqual(projection_ref, "runs/run-sample/metrics/projection.json")
            self.assertTrue(Path(tmpdir, events_ref).is_file())
            self.assertTrue(Path(tmpdir, projection_ref).is_file())
            self.assertEqual(store.load_events("run-sample"), [event])
            self.assertEqual(store.load_projection("run-sample"), projection)


if __name__ == "__main__":
    unittest.main()
