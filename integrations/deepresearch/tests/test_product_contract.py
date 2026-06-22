from __future__ import annotations

import unittest

from missionforge.contracts import ContractValidationError
from missionforge_deepresearch.product_contract import (
    AcademicResearchRequest,
    ResearchIntensity,
    research_intensity_profile,
)


def sample_request() -> AcademicResearchRequest:
    return AcademicResearchRequest(
        request_id="npu-compiler-survey",
        topic="NPU compiler autotuning kernel autogen LLM harness",
        audience="R&D compiler team",
        language="zh",
        previous_run_refs=["runs/previous/packages/deepresearch_run_result.json"],
        constraints=["Prefer evidence-grounded claims."],
        non_goals=["Do not write a market research report."],
    )


class ProductContractTests(unittest.TestCase):
    def test_academic_request_round_trips(self) -> None:
        request = sample_request()

        self.assertEqual(AcademicResearchRequest.from_dict(request.to_dict()), request)
        self.assertEqual(request.research_intensity, ResearchIntensity.STANDARD)
        self.assertEqual(request.previous_run_refs, ["runs/previous/packages/deepresearch_run_result.json"])

    def test_academic_request_accepts_research_intensity(self) -> None:
        request = AcademicResearchRequest(
            request_id="intensive-demo",
            topic="compiler autotuning",
            research_intensity="intensive",
        )

        payload = request.to_dict()

        self.assertEqual(request.research_intensity, ResearchIntensity.INTENSIVE)
        self.assertEqual(payload["research_intensity"], "intensive")
        self.assertEqual(AcademicResearchRequest.from_dict(payload), request)
        self.assertGreater(
            research_intensity_profile(ResearchIntensity.INTENSIVE).max_sources,
            research_intensity_profile(ResearchIntensity.STANDARD).max_sources,
        )

    def test_intensity_profiles_keep_kernel_v2_budget_shape(self) -> None:
        standard = research_intensity_profile(ResearchIntensity.STANDARD)
        intensive = research_intensity_profile(ResearchIntensity.INTENSIVE)

        self.assertGreater(intensive.max_sources, standard.max_sources)
        self.assertGreater(intensive.min_source_records, standard.min_source_records)
        self.assertGreater(intensive.max_review_rounds, standard.max_review_rounds)
        self.assertGreater(intensive.piworker_timeout_seconds, standard.piworker_timeout_seconds)
        self.assertNotIn("max_turns", standard.to_dict())

    def test_intensity_guidance_keeps_standard_and_intensive_boundaries(self) -> None:
        standard = research_intensity_profile(ResearchIntensity.STANDARD)
        intensive = research_intensity_profile(ResearchIntensity.INTENSIVE)

        self.assertNotIn("experimental", [item.value for item in ResearchIntensity])
        self.assertIn("repository-metadata survey", standard.guidance)
        self.assertIn("Do not claim code-level audit", standard.guidance)
        self.assertIn("repository/code-audit-backed technical report", intensive.guidance)
        self.assertIn("Inspect repository files", intensive.guidance)
        self.assertIn("Do not install projects", intensive.guidance)
        self.assertIn("run benchmarks", intensive.guidance)

    def test_quick_is_not_a_current_public_research_intensity(self) -> None:
        self.assertEqual([item.value for item in ResearchIntensity], ["standard", "intensive"])
        with self.assertRaisesRegex(ContractValidationError, "research_intensity"):
            AcademicResearchRequest(
                request_id="quick-is-not-public",
                topic="compiler autotuning",
                research_intensity="quick",
            )

    def test_request_rejects_unknown_research_intensity(self) -> None:
        with self.assertRaisesRegex(ContractValidationError, "research_intensity"):
            AcademicResearchRequest(
                request_id="bad-intensity",
                topic="compiler autotuning",
                research_intensity="exhaustive",
            )

    def test_request_rejects_nested_request_id(self) -> None:
        with self.assertRaisesRegex(ContractValidationError, "one ref segment"):
            AcademicResearchRequest(request_id="bad/id", topic="compiler autotuning").validate()


if __name__ == "__main__":
    unittest.main()
