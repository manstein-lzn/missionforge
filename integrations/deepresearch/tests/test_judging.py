from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from missionforge.contracts import ContractValidationError
from missionforge_deepresearch import (
    FixtureDeepResearchJudgeAdapter,
    load_deepresearch_final_package,
    load_deepresearch_judged_run_result,
    run_deepresearch_academic_judged,
)
from missionforge_deepresearch.judging import JUDGE_CALL_REF, JUDGE_REPORT_REF, JUDGE_SPEC_REF
from missionforge_deepresearch.runtime import FixtureAcademicResearcherAdapter

from test_product_contract import sample_request


class JudgingTests(unittest.TestCase):
    def test_accepted_judge_writes_final_package(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)

            result = run_deepresearch_academic_judged(
                sample_request(),
                workspace=root,
                researcher_adapter=FixtureAcademicResearcherAdapter(),
                judge_adapter=FixtureDeepResearchJudgeAdapter("accepted"),
            )
            loaded = load_deepresearch_judged_run_result(root, result.judged_run_result_ref)
            final_package = load_deepresearch_final_package(root, result.final_package_ref)

            self.assertEqual(loaded, result)
            self.assertEqual(result.status, "accepted")
            self.assertTrue((root / result.final_package_ref).exists())
            self.assertEqual(final_package.status, "accepted")
            self.assertEqual(len(final_package.accepted_artifact_refs), 5)

            run_root = root / result.run_workspace_ref
            call_payload = json.loads((run_root / JUDGE_CALL_REF).read_text(encoding="utf-8"))
            self.assertEqual(call_payload["role"], "judge_piworker")
            run_payload = (root / result.source_run_result_ref).read_text(encoding="utf-8")
            self.assertNotIn("\"accepted\"", run_payload)

    def test_repair_judge_does_not_write_final_package(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)

            result = run_deepresearch_academic_judged(
                sample_request(),
                workspace=root,
                researcher_adapter=FixtureAcademicResearcherAdapter(),
                judge_adapter=FixtureDeepResearchJudgeAdapter("repair"),
            )

            self.assertEqual(result.status, "repair")
            self.assertEqual(result.final_package_ref, "")
            self.assertTrue(result.repair_brief_ref.endswith("reports/judge_repair_brief.md"))
            self.assertFalse((root / "runs/npu-compiler-survey/packages/deepresearch_final_package.json").exists())

    def test_judge_report_cannot_accept_without_all_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)

            with self.assertRaisesRegex(ContractValidationError, "must accept all artifact refs"):
                run_deepresearch_academic_judged(
                    sample_request(),
                    workspace=root,
                    researcher_adapter=FixtureAcademicResearcherAdapter(),
                    judge_adapter=_BadAcceptedJudgeAdapter(),
                )

    def test_live_shape_judge_report_is_mechanically_normalized(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)

            result = run_deepresearch_academic_judged(
                sample_request(),
                workspace=root,
                researcher_adapter=FixtureAcademicResearcherAdapter(),
                judge_adapter=_LooseLiveShapeJudgeAdapter(),
            )

            self.assertEqual(result.status, "accepted")
            self.assertTrue((root / result.final_package_ref).exists())
            report = json.loads((root / "runs/npu-compiler-survey" / JUDGE_REPORT_REF).read_text(encoding="utf-8"))
            self.assertIn("report_id", report)
            self.assertEqual(report["judge_spec_ref"], "judge/judge_spec.json")
            self.assertEqual(report["judge_rubric_ref"], "projections/judge_rubric.json")
            self.assertEqual(set(report["accepted_artifact_refs"]), set(report["artifact_refs"]))
            self.assertNotIn("artifact_refs_reviewed", report)

    def test_judged_run_cli_fixture(self) -> None:
        from missionforge_deepresearch.cli import main

        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)

            with patch("builtins.print") as print_mock:
                exit_code = main(
                    [
                        "academic",
                        "judged-run",
                        "--topic",
                        "compiler autotuning survey",
                        "--request-id",
                        "judged-cli-demo",
                        "--workspace",
                        str(root),
                        "--judge-mode",
                        "fixture",
                    ]
                )

            payload = json.loads(print_mock.call_args.args[0])
            self.assertEqual(exit_code, 0)
            self.assertEqual(payload["status"], "accepted")
            self.assertEqual(
                payload["final_package_ref"],
                "runs/judged-cli-demo/packages/deepresearch_final_package.json",
            )
            self.assertTrue((root / payload["final_package_ref"]).exists())


class _BadAcceptedJudgeAdapter(FixtureDeepResearchJudgeAdapter):
    adapter_family = "fixture_bad_accepted_deepresearch_judge"

    def run_call(self, *args, **kwargs):
        result = super().run_call(*args, **kwargs)
        workspace = Path(kwargs.get("workspace", ".")).resolve()
        report = json.loads((workspace / JUDGE_REPORT_REF).read_text(encoding="utf-8"))
        report["accepted_artifact_refs"] = report["accepted_artifact_refs"][:-1]
        (workspace / JUDGE_REPORT_REF).write_text(json.dumps(report, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        return result


class _LooseLiveShapeJudgeAdapter(FixtureDeepResearchJudgeAdapter):
    adapter_family = "fixture_loose_live_shape_deepresearch_judge"

    def run_call(self, *args, **kwargs):
        result = super().run_call(*args, **kwargs)
        workspace = Path(kwargs.get("workspace", ".")).resolve()
        report = json.loads((workspace / JUDGE_REPORT_REF).read_text(encoding="utf-8"))
        spec = json.loads((workspace / JUDGE_SPEC_REF).read_text(encoding="utf-8"))
        loose_report = {
            "schema_version": report["schema_version"],
            "request_id": report["request_id"],
            "contract_ref": report["contract_ref"],
            "contract_hash": report["contract_hash"],
            "decision": report["decision"],
            "hard_check_status": report["hard_check_status"],
            "structural_check_status": "passed",
            "artifact_refs_reviewed": report["artifact_refs"],
            "evidence_refs_reviewed": [*report["evidence_refs"], *spec["metric_refs"]],
            "rationale_ref": report["rationale_ref"],
            "findings": [{"severity": "pass", "summary": "Loose live-shaped judge output."}],
        }
        (workspace / JUDGE_REPORT_REF).write_text(
            json.dumps(loose_report, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        return result


if __name__ == "__main__":
    unittest.main()
