from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from missionforge_deepresearch.experimental import (
    DeepResearchQualityEvaluationResult,
    FixtureDirectBaselineAdapter,
    FixtureQualityEvaluatorAdapter,
    load_deepresearch_quality_evaluation_result,
    run_deepresearch_quality_evaluation,
)
from missionforge_deepresearch.experimental.quality_evaluation import (
    DIRECT_BASELINE_CALL_REF,
    DIRECT_BASELINE_STRUCTURAL_CHECK_REF,
    EVALUATION_REPORT_REF,
    EVALUATION_SCORECARD_REF,
    _direct_baseline_permission_manifest,
)

from test_product_contract import sample_request


class QualityEvaluationTests(unittest.TestCase):
    def test_quality_evaluation_runs_missionforge_and_direct_baseline(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)

            result = run_deepresearch_quality_evaluation(
                sample_request(),
                workspace=root,
                direct_adapter=FixtureDirectBaselineAdapter(),
            )
            loaded = load_deepresearch_quality_evaluation_result(root, result.evaluation_result_ref)

            self.assertEqual(loaded, result)
            self.assertEqual(result.status, "comparison_ready")
            self.assertEqual(result.run_workspace_ref, "runs/npu-compiler-survey")
            self.assertTrue((root / result.evaluation_result_ref).exists())
            self.assertTrue((root / result.missionforge_run_result_ref).exists())
            self.assertTrue((root / result.direct_run_result_ref).exists())
            self.assertTrue((root / result.evaluation_report_ref).exists())
            self.assertTrue((root / result.scorecard_ref).exists())
            self.assertNotIn("\"accepted\"", (root / result.evaluation_result_ref).read_text(encoding="utf-8"))

            run_root = root / result.run_workspace_ref
            self.assertTrue((run_root / DIRECT_BASELINE_CALL_REF).exists())
            self.assertTrue((run_root / DIRECT_BASELINE_STRUCTURAL_CHECK_REF).exists())
            direct_manifest = json.loads(
                (run_root / "policy/direct_baseline_permission_manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(direct_manifest["workspace_policy_ref"], "policy/workspace_policy.json")
            scorecard = json.loads((run_root / EVALUATION_SCORECARD_REF).read_text(encoding="utf-8"))
            self.assertEqual(scorecard["authority"], "triage_only_not_acceptance")

    def test_quality_evaluation_cli_prints_result(self) -> None:
        from missionforge_deepresearch.cli import main

        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)

            with patch("builtins.print") as print_mock:
                exit_code = main(
                    [
                        "academic",
                        "quality-eval",
                        "--topic",
                        "compiler autotuning survey",
                        "--request-id",
                        "quality-cli-demo",
                        "--workspace",
                        str(root),
                        "--direct-baseline-mode",
                        "fixture",
                    ]
                )

            payload = json.loads(print_mock.call_args.args[0])
            self.assertEqual(exit_code, 0)
            self.assertEqual(payload["status"], "comparison_ready")
            self.assertEqual(
                payload["evaluation_result_ref"],
                "runs/quality-cli-demo/packages/deepresearch_quality_evaluation_result.json",
            )
            self.assertTrue((root / payload["evaluation_report_ref"]).exists())

    def test_piworker_evaluator_adapter_path_writes_evaluator_refs(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)

            result = run_deepresearch_quality_evaluation(
                sample_request(),
                workspace=root,
                direct_adapter=FixtureDirectBaselineAdapter(),
                evaluator_mode="piworker",
                evaluator_adapter=FixtureQualityEvaluatorAdapter(),
            )

            run_root = root / result.run_workspace_ref
            self.assertEqual(result.status, "comparison_ready")
            self.assertTrue((run_root / EVALUATION_REPORT_REF).exists())
            self.assertTrue((run_root / EVALUATION_SCORECARD_REF).exists())
            evaluator_manifest = json.loads(
                (run_root / "policy/quality_evaluator_permission_manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(evaluator_manifest["workspace_policy_ref"], "policy/workspace_policy.json")


class QualityEvaluationContractTests(unittest.TestCase):
    def test_result_round_trips_refs_first_payload(self) -> None:
        payload = {
            "schema_version": "missionforge_deepresearch.quality_evaluation_result.v1",
            "request_id": "demo",
            "status": "comparison_ready",
            "run_workspace_ref": "runs/demo",
            "evaluation_result_ref": "runs/demo/packages/deepresearch_quality_evaluation_result.json",
            "missionforge_run_result_ref": "runs/demo/packages/deepresearch_run_result.json",
            "direct_run_result_ref": "runs/demo/packages/direct_baseline_run_result.json",
            "evaluation_report_ref": "runs/demo/evaluation/quality_comparison_report.md",
            "scorecard_ref": "runs/demo/evaluation/quality_scorecard.json",
            "evidence_refs": ["runs/demo/evaluation/quality_scorecard.json"],
            "metric_refs": [],
        }
        result = DeepResearchQualityEvaluationResult.from_dict(payload)

        self.assertEqual(result.to_dict(), payload)

    def test_direct_baseline_manifest_inherits_workspace_policy_ref(self) -> None:
        from missionforge.task_contract import NetworkPolicy, PermissionManifest

        source_manifest = PermissionManifest(
            manifest_id="source-permissions",
            workspace_policy_ref="policy/workspace_policy.json",
            network_policy=NetworkPolicy.ENABLED,
        )

        direct_manifest = _direct_baseline_permission_manifest(source_manifest, "demo")

        self.assertEqual(direct_manifest.workspace_policy_ref, "policy/workspace_policy.json")
        self.assertEqual(direct_manifest.network_policy, NetworkPolicy.ENABLED)


if __name__ == "__main__":
    unittest.main()
