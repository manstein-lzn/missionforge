from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from missionforge_deepresearch.cli import main


class CliTests(unittest.TestCase):
    def test_academic_kernel_v2_run_fixture_prints_accepted_result(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)

            with patch("builtins.print") as print_mock, patch("sys.stderr") as stderr_mock:
                exit_code = main(
                    [
                        "academic",
                        "kernel-v2-run",
                        "--topic",
                        "compiler autotuning survey",
                        "--request-id",
                        "kernel-v2-cli-demo",
                        "--workspace",
                        str(root),
                        "--kernel-v2-adapter-mode",
                        "fixture",
                    ]
                )

            payload = json.loads(print_mock.call_args.args[0])
            stderr_output = "".join(call.args[0] for call in stderr_mock.write.call_args_list)
            self.assertEqual(exit_code, 0)
            self.assertEqual(payload["status"], "accepted")
            self.assertEqual(
                payload["result_ref"],
                "runs/kernel-v2-cli-demo/packages/deepresearch_kernel_v2_result.json",
            )
            self.assertTrue((root / payload["result_ref"]).exists())
            self.assertTrue((root / payload["final_report_ref"]).exists())
            self.assertIn("输出文件：", stderr_output)
            self.assertIn(str(root / payload["final_report_ref"]), stderr_output)
            self.assertIn(str(root / payload["usage_summary_ref"]), stderr_output)
            self.assertIn("Token 用量：", stderr_output)
            self.assertIn("cached_input_tokens: 0", stderr_output)

    def test_academic_kernel_v2_run_prints_missing_outputs_for_blocked_result(self) -> None:
        expected = type(
            "Result",
            (),
            {
                "status": "blocked",
                "final_report_ref": "runs/kernel-v2-blocked/reports/final_report.md",
                "source_packet_ref": "runs/kernel-v2-blocked/sources/source_packet.json",
                "result_ref": "runs/kernel-v2-blocked/packages/deepresearch_kernel_v2_result.json",
                "judge_report_ref": "runs/kernel-v2-blocked/judge/judge_report.json",
                "usage_summary_ref": "runs/kernel-v2-blocked/metrics/usage_summary.json",
                "to_dict": lambda self: {
                    "schema_version": "missionforge_deepresearch.kernel_v2_result.v1",
                    "request_id": "kernel-v2-blocked",
                    "status": "blocked",
                    "final_report_ref": self.final_report_ref,
                    "result_ref": self.result_ref,
                },
            },
        )()

        with (
            tempfile.TemporaryDirectory() as tempdir,
            patch("missionforge_deepresearch.cli.PiAgentRuntimeAdapter"),
            patch("missionforge_deepresearch.cli.run_deepresearch_kernel_v2", return_value=expected),
            patch("builtins.print") as print_mock,
            patch("sys.stderr") as stderr_mock,
        ):
            root = Path(tempdir)
            exit_code = main(
                [
                    "academic",
                    "kernel-v2-run",
                    "--topic",
                    "compiler autotuning survey",
                    "--request-id",
                    "kernel-v2-blocked",
                    "--workspace",
                    str(root),
                ]
            )

        payload = json.loads(print_mock.call_args.args[0])
        stderr_output = "".join(call.args[0] for call in stderr_mock.write.call_args_list)
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["status"], "blocked")
        self.assertNotIn("输出文件：", stderr_output)
        self.assertIn("缺失输出：", stderr_output)
        self.assertIn(str(root / expected.final_report_ref), stderr_output)

    def test_academic_kernel_v2_run_defaults_to_piworker_adapter(self) -> None:
        expected = type(
            "Result",
            (),
            {
                "status": "accepted",
                "result_ref": "runs/kernel-v2-piworker/packages/deepresearch_kernel_v2_result.json",
                "to_dict": lambda self: {
                    "schema_version": "missionforge_deepresearch.kernel_v2_result.v1",
                    "request_id": "kernel-v2-piworker",
                    "status": "accepted",
                    "result_ref": self.result_ref,
                },
            },
        )()
        adapter = object()

        with (
            tempfile.TemporaryDirectory() as tempdir,
            patch("missionforge_deepresearch.cli.PiAgentRuntimeAdapter", return_value=adapter) as adapter_mock,
            patch("missionforge_deepresearch.cli.KernelV2FixtureAdapter") as fixture_mock,
            patch("missionforge_deepresearch.cli.run_deepresearch_kernel_v2", return_value=expected) as run_mock,
            patch("builtins.print") as print_mock,
            patch("sys.stderr"),
        ):
            root = Path(tempdir)
            exit_code = main(
                [
                    "academic",
                    "kernel-v2-run",
                    "--topic",
                    "compiler autotuning survey",
                    "--request-id",
                    "kernel-v2-piworker",
                    "--workspace",
                    str(root),
                    "--piworker-provider-config-source",
                    "explicit",
                    "--piworker-base-url",
                    "http://127.0.0.1:12345",
                    "--piworker-max-turns",
                    "7",
                    "--piworker-timeout-seconds",
                    "99",
                    "--piworker-reasoning",
                    "medium",
                ]
            )

        payload = json.loads(print_mock.call_args.args[0])
        adapter_call = adapter_mock.call_args
        run_call = run_mock.call_args
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["request_id"], "kernel-v2-piworker")
        self.assertEqual(payload["status"], "accepted")
        fixture_mock.assert_not_called()
        self.assertIs(run_call.kwargs["adapter"], adapter)
        self.assertEqual(run_call.kwargs["workspace"], root)
        self.assertFalse(run_call.kwargs["live_extension_mode"])
        self.assertEqual(run_call.args[0].request_id, "kernel-v2-piworker")
        self.assertEqual(adapter_call.args[0].provider_config_source, "explicit")
        self.assertEqual(adapter_call.args[0].metadata["base_url"], "http://127.0.0.1:12345")
        self.assertEqual(adapter_call.args[0].timeout_seconds, 99)
        self.assertEqual(adapter_call.kwargs["environ"]["MISSIONFORGE_PI_AGENT_MAX_TURNS"], "7")
        self.assertEqual(adapter_call.kwargs["environ"]["MISSIONFORGE_PI_AGENT_REASONING"], "medium")

    def test_academic_kernel_v2_run_does_not_set_turn_budget_by_default(self) -> None:
        expected = type(
            "Result",
            (),
            {
                "status": "accepted",
                "result_ref": "runs/kernel-v2-no-turn-budget/packages/deepresearch_kernel_v2_result.json",
                "to_dict": lambda self: {
                    "schema_version": "missionforge_deepresearch.kernel_v2_result.v1",
                    "request_id": "kernel-v2-no-turn-budget",
                    "status": "accepted",
                    "result_ref": self.result_ref,
                },
            },
        )()
        adapter = object()

        with (
            tempfile.TemporaryDirectory() as tempdir,
            patch("missionforge_deepresearch.cli.PiAgentRuntimeAdapter", return_value=adapter) as adapter_mock,
            patch("missionforge_deepresearch.cli.run_deepresearch_kernel_v2", return_value=expected),
            patch("builtins.print"),
            patch("sys.stderr"),
        ):
            root = Path(tempdir)
            exit_code = main(
                [
                    "academic",
                    "kernel-v2-run",
                    "--topic",
                    "compiler autotuning survey",
                    "--request-id",
                    "kernel-v2-no-turn-budget",
                    "--workspace",
                    str(root),
                ]
            )

        self.assertEqual(exit_code, 0)
        self.assertNotIn("MISSIONFORGE_PI_AGENT_MAX_TURNS", adapter_mock.call_args.kwargs["environ"])

    def test_academic_kernel_v2_run_streams_kernel_step_progress(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)

            with patch("builtins.print") as print_mock, patch("sys.stderr") as stderr_mock:
                exit_code = main(
                    [
                        "academic",
                        "kernel-v2-run",
                        "--topic",
                        "compiler autotuning survey",
                        "--request-id",
                        "kernel-v2-watched",
                        "--workspace",
                        str(root),
                        "--kernel-v2-adapter-mode",
                        "fixture",
                        "--stream-progress",
                        "--progress-interval",
                        "0.01",
                    ]
                )

            payload = json.loads(print_mock.call_args.args[0])
            progress_output = "".join(call.args[0] for call in stderr_mock.write.call_args_list)

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["status"], "accepted")
        self.assertIn("Kernel v2 researcher 正在执行。", progress_output)
        self.assertIn("Kernel v2 reviewer 正在执行。", progress_output)
        self.assertIn("Kernel v2 judge 正在执行。", progress_output)
        self.assertIn("Kernel v2 researcher 路由到 reviewer。", progress_output)
        self.assertIn("Kernel v2 judge 路由到 accepted。", progress_output)
        self.assertIn("调研流程完成。", progress_output)


if __name__ == "__main__":
    unittest.main()
