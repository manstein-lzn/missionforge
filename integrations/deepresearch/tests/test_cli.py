from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from missionforge_deepresearch.cli import main


class CliTests(unittest.TestCase):
    def test_academic_single_agent_run_prints_run_result(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)

            with patch("builtins.print") as print_mock:
                exit_code = main(
                    [
                        "academic",
                        "single-agent-run",
                        "--topic",
                        "compiler autotuning survey",
                        "--request-id",
                        "cli-demo",
                        "--workspace",
                        str(root),
                    ]
                )

            payload = json.loads(print_mock.call_args.args[0])
            self.assertEqual(exit_code, 0)
            self.assertEqual(payload["status"], "draft_ready")
            self.assertEqual(payload["run_result_ref"], "runs/cli-demo/packages/deepresearch_run_result.json")
            self.assertTrue((root / payload["run_result_ref"]).exists())


if __name__ == "__main__":
    unittest.main()
