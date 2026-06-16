from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from missionforge.contracts import ContractValidationError
from missionforge.piworker_call import PiWorkerCallResultStatus
from missionforge.runtime_results import ExecutionReport, WorkerAdapterResult, WorkerResult
from missionforge_deepresearch.search_intent import (
    AcademicSearchIntent,
    FixtureSearchIntentAdapter,
    SEARCH_INTENT_REF,
    SEARCH_INTENT_VALIDATION_REPORT_REF,
    generate_search_intent_with_piworker,
)

from test_product_contract import sample_request


class SearchIntentTests(unittest.TestCase):
    def test_search_intent_round_trips_and_deduplicates_external_queries(self) -> None:
        request = sample_request()

        intent = AcademicSearchIntent.from_queries(
            request,
            ["compiler autotuning survey", "Compiler Autotuning Survey", "kernel generation"],
        )

        self.assertEqual(intent.queries, ["compiler autotuning survey", "kernel generation"])
        self.assertEqual(AcademicSearchIntent.from_dict(intent.to_dict()), intent)

    def test_search_intent_rejects_request_mismatch(self) -> None:
        request = sample_request()
        intent = AcademicSearchIntent(
            request_id=request.request_id,
            topic="different",
            language=request.language,
            queries=["compiler autotuning"],
        )

        with self.assertRaisesRegex(ContractValidationError, "topic must match"):
            intent.validate_for_request(request)

    def test_fixture_piworker_authors_search_intent_artifact(self) -> None:
        request = sample_request()
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)

            result = generate_search_intent_with_piworker(
                request,
                workspace=root,
                adapter=FixtureSearchIntentAdapter(),
            )

            self.assertEqual(result.call_result.status, PiWorkerCallResultStatus.COMPLETED)
            self.assertEqual(result.search_intent.created_by, "piworker")
            self.assertEqual(result.search_intent.queries, [request.topic])
            self.assertTrue((root / SEARCH_INTENT_REF).exists())

    def test_valid_search_intent_artifact_can_survive_runtime_failure(self) -> None:
        request = sample_request()
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)

            result = generate_search_intent_with_piworker(
                request,
                workspace=root,
                adapter=_FailedAfterWriteSearchIntentAdapter(),
            )

            validation = json.loads((root / SEARCH_INTENT_VALIDATION_REPORT_REF).read_text(encoding="utf-8"))
            self.assertEqual(result.call_result.status, PiWorkerCallResultStatus.FAILED)
            self.assertEqual(result.search_intent.queries, [request.topic])
            self.assertEqual(validation["status"], "accepted_valid_artifact_after_runtime_failure")
            self.assertIn(SEARCH_INTENT_VALIDATION_REPORT_REF, result.evidence_refs)


class _FailedAfterWriteSearchIntentAdapter(FixtureSearchIntentAdapter):
    adapter_family = "fixture_failed_after_write_search_intent"

    def run_call(self, call, **kwargs):
        result = super().run_call(call, **kwargs)
        report = ExecutionReport(
            report_id=result.execution_report.report_id,
            call_id=result.execution_report.call_id,
            status="failed",
            produced_artifacts=list(result.execution_report.produced_artifacts),
            changed_refs=list(result.execution_report.changed_refs),
            evidence_refs=list(result.execution_report.evidence_refs),
            worker_claims=["fixture wrote valid artifact but runtime failed"],
            metrics=dict(result.execution_report.metrics),
        )
        return WorkerAdapterResult(
            execution_report=report,
            worker_result=WorkerResult(status="failed", execution_report_ref=result.worker_result.execution_report_ref),
            event_evidence_refs=[],
            metrics=dict(result.metrics),
        )


if __name__ == "__main__":
    unittest.main()
