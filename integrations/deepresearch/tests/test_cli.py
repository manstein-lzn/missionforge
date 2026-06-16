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

    def test_academic_tool_healthcheck_prints_healthcheck_result(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            expected = {
                "schema_version": "missionforge_deepresearch.tool_healthcheck.v1",
                "request_id": "cli-health",
                "status": "degraded",
                "result_ref": "runs/cli-health/health/tool_healthcheck.json",
                "report_ref": "runs/cli-health/health/tool_healthcheck.md",
            }

            with (
                patch("missionforge_deepresearch.cli.run_deepresearch_tool_healthcheck", return_value=expected) as run_mock,
                patch("builtins.print") as print_mock,
            ):
                exit_code = main(
                    [
                        "academic",
                        "tool-healthcheck",
                        "--topic",
                        "compiler autotuning survey",
                        "--request-id",
                        "cli-health",
                        "--workspace",
                        str(root),
                        "--academic-provider",
                        "openalex",
                        "--search-query",
                        "compiler autotuning survey",
                    ]
                )

            payload = json.loads(print_mock.call_args.args[0])
            call = run_mock.call_args
            self.assertEqual(exit_code, 0)
            self.assertEqual(payload, expected)
            self.assertEqual(call.kwargs["workspace"], root)
            self.assertEqual(call.kwargs["academic_providers"], ("openalex",))
            self.assertEqual(call.kwargs["source_config"].providers, ("openalex",))
            self.assertEqual(call.kwargs["search_intent"].queries, ["compiler autotuning survey"])

    def test_academic_run_cli_maps_research_intensity_to_default_budgets(self) -> None:
        expected = type(
            "Result",
            (),
            {
                "to_dict": lambda self: {
                    "schema_version": "missionforge_deepresearch.run_result.v1",
                    "request_id": "cli-intensity",
                    "status": "draft_ready",
                }
            },
        )()

        with (
            patch("missionforge_deepresearch.cli.run_deepresearch_academic_single_agent", return_value=expected) as run_mock,
            patch("builtins.print") as print_mock,
        ):
            exit_code = main(
                [
                    "academic",
                    "single-agent-run",
                    "--topic",
                    "compiler autotuning survey",
                    "--request-id",
                    "cli-intensity",
                    "--research-intensity",
                    "quick",
                ]
            )

        payload = json.loads(print_mock.call_args.args[0])
        call = run_mock.call_args
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["request_id"], "cli-intensity")
        self.assertEqual(call.args[0].research_intensity.value, "quick")
        self.assertEqual(call.kwargs["source_config"].max_records, 10)
        self.assertEqual(call.kwargs["source_config"].max_search_queries, 3)
        self.assertEqual(call.kwargs["piworker_config"].timeout_seconds, 600)
        self.assertEqual(call.kwargs["piworker_environ"]["MISSIONFORGE_PI_AGENT_MAX_TURNS"], "12")

    def test_academic_reviewed_run_cli_fixture(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)

            with patch("builtins.print") as print_mock:
                exit_code = main(
                    [
                        "academic",
                        "reviewed-run",
                        "--topic",
                        "compiler autotuning survey",
                        "--request-id",
                        "reviewed-cli-demo",
                        "--workspace",
                        str(root),
                        "--reviewer-mode",
                        "fixture",
                        "--review-rounds",
                        "1",
                    ]
                )

            payload = json.loads(print_mock.call_args.args[0])
            self.assertEqual(exit_code, 0)
            self.assertEqual(payload["status"], "draft_ready")
            self.assertEqual(payload["review_round_count"], 1)
            self.assertEqual(
                payload["reviewed_run_result_ref"],
                "runs/reviewed-cli-demo/packages/deepresearch_reviewed_run_result.json",
            )
            self.assertTrue((root / payload["reviewed_run_result_ref"]).exists())

    def test_academic_reviewed_judged_run_cli_fixture(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)

            with patch("builtins.print") as print_mock:
                exit_code = main(
                    [
                        "academic",
                        "reviewed-judged-run",
                        "--topic",
                        "compiler autotuning survey",
                        "--request-id",
                        "reviewed-judged-cli-demo",
                        "--workspace",
                        str(root),
                        "--reviewer-mode",
                        "fixture",
                        "--review-rounds",
                        "1",
                        "--judge-mode",
                        "fixture",
                    ]
                )

            payload = json.loads(print_mock.call_args.args[0])
            self.assertEqual(exit_code, 0)
            self.assertEqual(payload["status"], "accepted")
            self.assertEqual(
                payload["final_package_ref"],
                "runs/reviewed-judged-cli-demo/packages/deepresearch_final_package.json",
            )
            self.assertTrue((root / payload["final_package_ref"]).exists())


if __name__ == "__main__":
    unittest.main()
