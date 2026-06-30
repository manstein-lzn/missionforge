from __future__ import annotations

import contextlib
import importlib.util
import io
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest

from missionforge.adapters.cli import MissionRunView, build_mission_run_view, main, render_mission_run_view
from missionforge.contracts import assert_refs_only_payload


EXAMPLE_PATH = Path(__file__).resolve().parents[1] / "examples" / "kernel_host_toolkit_example.py"


def _load_example_module():
    spec = importlib.util.spec_from_file_location("kernel_host_toolkit_example_for_cli", EXAMPLE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("failed to load kernel_host_toolkit_example")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class AdapterCliTests(unittest.TestCase):
    def test_build_mission_run_view_is_refs_only(self) -> None:
        example = _load_example_module()
        with TemporaryDirectory() as tmp:
            summary = example.run_demo(tmp)
            view = build_mission_run_view(tmp, flow_result_ref=summary["flow_result_ref"])

            self.assertIsInstance(view, MissionRunView)
            self.assertEqual(view.status, "accepted")
            self.assertEqual(view.snapshot_status, "accepted")
            self.assertEqual(view.pending_user_event_count, 0)
            self.assertIn("reports/implementation_brief.md", view.artifact_refs)
            assert_refs_only_payload(view.to_dict(), "adapter_cli.view")

    def test_plain_render_does_not_expand_artifact_bodies(self) -> None:
        example = _load_example_module()
        with TemporaryDirectory() as tmp:
            summary = example.run_demo(tmp)
            view = build_mission_run_view(tmp, flow_result_ref=summary["flow_result_ref"])
            rendered = render_mission_run_view(view)

            self.assertIn("status: accepted", rendered)
            self.assertIn("flow_result:", rendered)
            self.assertIn("reports/implementation_brief.md", rendered)
            self.assertNotIn("The host application supplies the product logic.", rendered)

    def test_status_view_surfaces_usage_context_and_tool_activity_without_bodies(self) -> None:
        example = _load_example_module()
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            summary = example.run_demo(tmp)
            flow_result = json.loads((root / summary["flow_result_ref"]).read_text(encoding="utf-8"))
            first_step_ref = flow_result["step_record_refs"][0]
            first_step = json.loads((root / first_step_ref).read_text(encoding="utf-8"))
            metrics_ref = "attempts/observer/metrics.json"
            observations_ref = "attempts/observer/context/tool_observations.jsonl"
            projection_ref = "attempts/observer/context/projection.json"
            thrash_ref = "attempts/observer/context/thrash_diagnostics.json"
            checkpoint_ref = "kernel/demo-flow/steps/writer/context/checkpoint.json"
            (root / metrics_ref).parent.mkdir(parents=True, exist_ok=True)
            (root / metrics_ref).write_text(
                json.dumps(
                    {
                        "total_tokens": 130,
                        "input_tokens": 100,
                        "output_tokens": 30,
                        "cache_read_tokens": 20,
                        "tool_call_count": 2,
                        "provider_reported_cost_usd": 0.0123,
                    },
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
            (root / observations_ref).parent.mkdir(parents=True, exist_ok=True)
            (root / observations_ref).write_text(
                json.dumps(
                    {
                        "schema_version": "missionforge.pi_agent_tool_observation.v1",
                        "observation_id": "tool-observation-000001",
                        "call_id": "observer-call",
                        "turn_index": 1,
                        "tool_call_id": "tool-call-1",
                        "tool_name": "read",
                        "status": "ok",
                        "content_hash": "sha256:" + "3" * 64,
                        "content_bytes": 64,
                        "content_lines": 3,
                        "inline_policy": "ref_only",
                        "source_ref": "reports/implementation_brief.md",
                    },
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
            (root / projection_ref).write_text(
                json.dumps(
                    {
                        "schema_version": "missionforge.pi_agent_context_projection.v1",
                        "call_id": "observer-call",
                        "created_at": "2026-06-25T00:00:00+00:00",
                        "context_observations_ref": observations_ref,
                        "estimated_input_tokens": 90,
                        "pressure_ratio": 0.75,
                        "recommended_action": "prepare_checkpoint",
                        "context_budget": {"usable_input_budget": 120},
                    },
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
            (root / thrash_ref).write_text(
                json.dumps(
                    {
                        "schema_version": "missionforge.context_thrash_diagnostics.v1",
                        "diagnostics_id": "thrash-observer",
                        "phase_label": "runtime",
                        "observations": [
                            {
                                "schema_version": "missionforge.context_read_observation.v1",
                                "observation_id": "read-000001",
                                "source_ref": "reports/implementation_brief.md",
                                "source_hash": "sha256:" + "4" * 64,
                                "source_range": {},
                                "query_ref": None,
                                "query_hash": None,
                                "tool_name": "read",
                                "count": 2,
                                "normalized_metadata": {"origin": "pi_agent_runtime_tool_observations"},
                            }
                        ],
                        "repeated_observation_ids": ["read-000001"],
                        "expected_reread_observation_ids": [],
                        "recommended_action": "prepare_checkpoint",
                        "metadata": {},
                    },
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
            first_step["metric_refs"] = [metrics_ref]
            first_step["metadata"]["runtime_refs"] = [observations_ref, projection_ref, thrash_ref]
            first_step["metadata"]["context_checkpoint_ref"] = checkpoint_ref
            (root / first_step_ref).write_text(json.dumps(first_step, sort_keys=True, indent=2) + "\n", encoding="utf-8")

            view = build_mission_run_view(tmp, flow_result_ref=summary["flow_result_ref"])
            rendered = render_mission_run_view(view)

        self.assertEqual(view.usage_totals["input_tokens"], 100)
        self.assertEqual(view.usage_totals["cached_input_tokens"], 20)
        self.assertEqual(view.context_pressure["ratio"], "0.50")
        self.assertEqual(view.context_pressure["remaining_tokens"], 199)
        self.assertEqual(view.tool_activity["latest_tool_name"], "read")
        self.assertEqual(view.tool_activity["repeated_read_count"], 1)
        self.assertIn(thrash_ref, view.tool_activity["context_thrash_diagnostics_refs"])
        self.assertTrue(view.context_engine_refs)
        self.assertIn(checkpoint_ref, view.context_engine_refs)
        self.assertIn(observations_ref, view.tool_activity_refs)
        self.assertIn("usage: input=100 cached=20 output=30 total=130", rendered)
        self.assertIn("context_pressure: ratio=0.50 used_tokens=199 limit_tokens=398", rendered)
        self.assertIn("repeated_reads=1", rendered)
        self.assertIn("context_thrash_diagnostics:", rendered)
        self.assertIn("context_engine:", rendered)
        self.assertNotIn("The host application supplies the product logic.", rendered)
        assert_refs_only_payload(view.to_dict(), "adapter_cli.rich_view")

    def test_cli_json_observer_outputs_machine_view(self) -> None:
        example = _load_example_module()
        with TemporaryDirectory() as tmp:
            summary = example.run_demo(tmp)
            stdout = io.StringIO()
            exit_code = main(
                [
                    "tui",
                    "--workspace",
                    tmp,
                    "--flow-result-ref",
                    summary["flow_result_ref"],
                    "--json",
                ],
                output_stream=stdout,
            )

            self.assertEqual(exit_code, 0)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["status"], "accepted")
            self.assertEqual(payload["flow_result_ref"], summary["flow_result_ref"])
            assert_refs_only_payload(payload, "adapter_cli.payload")

    def test_cli_missing_ref_reports_boundary_error_without_traceback(self) -> None:
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            exit_code = main(["status", "--workspace", "/tmp", "--flow-result-ref", "missing/flow_result.json"])

        self.assertEqual(exit_code, 1)
        self.assertIn("missionforge adapter error:", stderr.getvalue())
        self.assertNotIn("Traceback", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
