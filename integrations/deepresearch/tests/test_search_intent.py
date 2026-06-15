from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from missionforge.contracts import ContractValidationError
from missionforge.piworker_call import PiWorkerCallResultStatus
from missionforge_deepresearch.search_intent import (
    AcademicSearchIntent,
    FixtureSearchIntentAdapter,
    SEARCH_INTENT_REF,
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


if __name__ == "__main__":
    unittest.main()
