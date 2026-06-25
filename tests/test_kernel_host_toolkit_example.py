from __future__ import annotations

import contextlib
import importlib.util
import io
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest

from missionforge import assert_refs_only_payload


EXAMPLE_PATH = Path(__file__).resolve().parents[1] / "examples" / "kernel_host_toolkit_example.py"


def _load_example_module():
    spec = importlib.util.spec_from_file_location("kernel_host_toolkit_example", EXAMPLE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("failed to load kernel_host_toolkit_example")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class KernelHostToolkitExampleTests(unittest.TestCase):
    def test_example_runs_kernel_flow_and_exposes_refs_only_inspection(self) -> None:
        module = _load_example_module()
        with TemporaryDirectory() as tmp:
            summary = module.run_demo(tmp)

            self.assertEqual(summary["inspection"]["status"], "accepted")
            self.assertEqual(summary["inspection"]["snapshot_status"], "accepted")
            self.assertEqual(summary["route"]["target_kind"], "stop")
            self.assertEqual(summary["route"]["terminal_status"], "accepted")
            self.assertEqual(summary["single_step_debug"]["step"]["status"], "completed")
            self.assertEqual(summary["preview"]["step_id"], "writer")
            self.assertIn("reports/implementation_brief.md", summary["inspection"]["artifact_refs"])
            self.assertIn("reviews/judge_decision.json", summary["inspection"]["decision_refs"])
            self.assertTrue((Path(tmp) / "reports" / "implementation_brief.md").is_file())

            assert_refs_only_payload(summary["preview"], "example.preview")
            assert_refs_only_payload(summary["single_step_debug"], "example.single_step_debug")
            assert_refs_only_payload(summary["route"], "example.route")
            assert_refs_only_payload(summary["inspection"], "example.inspection")

            serialized = json.dumps(summary, sort_keys=True)
            self.assertNotIn("DeepResearch", serialized)
            self.assertNotIn("The host application supplies the product logic.", serialized)

    def test_example_cli_prints_json_summary_for_given_workspace(self) -> None:
        module = _load_example_module()
        with TemporaryDirectory() as tmp:
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = module.main(["--workspace", tmp])

            self.assertEqual(exit_code, 0)
            summary = json.loads(stdout.getvalue())
            self.assertEqual(summary["inspection"]["status"], "accepted")
            self.assertEqual(summary["workspace"], tmp)
            self.assertTrue((Path(tmp) / summary["flow_result_ref"]).is_file())


if __name__ == "__main__":
    unittest.main()
