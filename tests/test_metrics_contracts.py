from __future__ import annotations

import unittest

from missionforge.contracts import ContractValidationError
from missionforge.metrics import MetricEvent, MetricProjection, MetricTrustLevel, project_metric_events


class MetricContractTests(unittest.TestCase):
    def test_metric_event_round_trip(self) -> None:
        event = MetricEvent(
            metric_id="ME-000001",
            mission_run_id="run-sample",
            namespace="missionforge.worker.pi_agent",
            source_ref="attempts/WU-000001/pi_agent_metrics.json",
            run_ref="runs/run-sample/mission_run.json",
            metric_kind="counter",
            values={"tool_call_count": 3, "token_count": 1200, "duration_ms": 7400},
            trust_level=MetricTrustLevel.ADAPTER_DIAGNOSTIC.value,
            tags=["worker", "pi_agent"],
        )

        self.assertEqual(MetricEvent.from_dict(event.to_dict()), event)

    def test_rejects_unsafe_ref_and_raw_payload(self) -> None:
        with self.assertRaises(ContractValidationError):
            MetricEvent(
                metric_id="ME-000001",
                mission_run_id="run-sample",
                namespace="missionforge.runtime",
                source_ref="../outside.json",
                metric_kind="summary",
                values={"attempt_count": 1},
            ).validate()

        with self.assertRaises(ContractValidationError):
            MetricEvent(
                metric_id="ME-000002",
                mission_run_id="run-sample",
                namespace="missionforge.runtime",
                run_ref="runs/run-sample/mission_run.json",
                metric_kind="summary",
                values={"raw_prompt": "do work"},
            ).validate()

    def test_rejects_product_namespace_under_missionforge(self) -> None:
        with self.assertRaises(ContractValidationError):
            MetricEvent(
                metric_id="ME-000001",
                mission_run_id="run-sample",
                namespace="missionforge.skillfoundry",
                run_ref="runs/run-sample/mission_run.json",
                metric_kind="summary",
                values={"count": 1},
            ).validate()

    def test_projection_is_deterministic_and_flags_diagnostics(self) -> None:
        events = [
            MetricEvent(
                metric_id="ME-000002",
                mission_run_id="run-sample",
                namespace="missionforge.steering",
                run_ref="runs/run-sample/mission_run.json",
                metric_kind="counter",
                values={"unsafe_proposal_rejection_count": 1},
            ),
            MetricEvent(
                metric_id="ME-000001",
                mission_run_id="run-sample",
                namespace="missionforge.runtime",
                run_ref="runs/run-sample/mission_run.json",
                metric_kind="summary",
                values={"attempt_count": 1},
            ),
        ]

        projection = project_metric_events(
            mission_run_id="run-sample",
            events=list(reversed(events)),
            metric_event_refs=["runs/run-sample/metrics/events.jsonl"],
        )

        self.assertEqual(MetricProjection.from_dict(projection.to_dict()), projection)
        self.assertEqual(projection.namespaces["missionforge.runtime"]["attempt_count"], 1)
        self.assertIn("unsafe_steering_proposal_rejected", projection.diagnostic_flags)


if __name__ == "__main__":
    unittest.main()
