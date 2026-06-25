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
