from __future__ import annotations

import unittest

import missionforge as mf
from missionforge_deepresearch.product_contract import (
    AcademicResearchRequest,
    ResearchIntensity,
    SeedPaper,
    deepresearch_quality_dimensions,
    research_intensity_profile,
    research_report_section_specs,
    research_report_section_titles,
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
        self.assertEqual(request.seed_papers, [])
        self.assertEqual(request.contract_revision_refs, [])
        self.assertEqual(request.provider_policy, "default_no_key")
        self.assertEqual(request.citation_style, "cite_anchor_v1")

    def test_academic_request_accepts_optional_seed_papers(self) -> None:
        request = AcademicResearchRequest(
            request_id="seed-demo",
            topic="compiler autotuning",
            seed_papers=[
                SeedPaper(kind="doi", value="10.1145/1234567.1234568"),
                {"kind": "arxiv", "value": "2501.01234", "note": "seed preprint"},
            ],
            seed_pdf_refs=["inputs/seeds/paper.pdf"],
            sample_report_ref="inputs/sample_report.md",
            contract_revision_refs=["runs/current/project/revisions/REV1/revision_record.json"],
            target_source_count=100,
            provider_policy="openalex_enhanced",
        )

        payload = request.to_dict()

        self.assertEqual(payload["seed_papers"][0]["kind"], "doi")
        self.assertEqual(payload["contract_revision_refs"], ["runs/current/project/revisions/REV1/revision_record.json"])
        self.assertEqual(payload["target_source_count"], 100)
        self.assertEqual(AcademicResearchRequest.from_dict(payload), request)

    def test_academic_request_rejects_invalid_seed_paper(self) -> None:
        with self.assertRaisesRegex(mf.ContractValidationError, "seed_paper.doi"):
            AcademicResearchRequest(
                request_id="bad-seed",
                topic="compiler autotuning",
                seed_papers=[SeedPaper(kind="doi", value="not-a-doi")],
            ).validate()

    def test_academic_request_rejects_invalid_target_source_count(self) -> None:
        with self.assertRaisesRegex(mf.ContractValidationError, "target_source_count"):
            AcademicResearchRequest.from_dict(
                {
                    "request_id": "bad-count",
                    "topic": "compiler autotuning",
                    "target_source_count": "many",
                }
            )

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
        self.assertEqual(standard.max_sources, 50)
        self.assertEqual(intensive.max_sources, 100)
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

    def test_quality_dimensions_include_expert_report_quality(self) -> None:
        dimensions = {item["dimension_id"]: item for item in deepresearch_quality_dimensions()}

        self.assertIn("insight_depth", dimensions)
        self.assertIn("narrative_coherence", dimensions)
        self.assertIn("genre_fit", dimensions)
        self.assertIn("reader_value", dimensions)
        self.assertIn("non-obvious field insights", dimensions["insight_depth"]["standard"])
        self.assertIn("defensible thesis", dimensions["narrative_coherence"]["standard"])
        self.assertIn("literature reviews", dimensions["genre_fit"]["standard"])
        self.assertIn("target audience", dimensions["reader_value"]["standard"])

    def test_report_sections_default_to_neutral_literature_review_shape(self) -> None:
        specs = research_report_section_specs("zh")
        section_ids = [item["section_id"] for item in specs]

        self.assertEqual(
            section_ids,
            [
                "abstract_and_key_findings",
                "scope_and_method",
                "background_and_problem_definition",
                "research_lines_and_representative_work",
                "comparative_analysis",
                "limitations_counterevidence_and_open_questions",
                "trends_and_future_directions",
                "references",
            ],
        )
        self.assertEqual(research_report_section_titles("zh")[0], "摘要与核心发现")
        self.assertEqual(research_report_section_titles("zh")[-1], "参考文献")
        self.assertIn("范围与方法", specs[1]["aliases"])

    def test_quick_is_not_a_current_public_research_intensity(self) -> None:
        self.assertEqual([item.value for item in ResearchIntensity], ["standard", "intensive"])
        with self.assertRaisesRegex(mf.ContractValidationError, "research_intensity"):
            AcademicResearchRequest(
                request_id="quick-is-not-public",
                topic="compiler autotuning",
                research_intensity="quick",
            )

    def test_request_rejects_unknown_research_intensity(self) -> None:
        with self.assertRaisesRegex(mf.ContractValidationError, "research_intensity"):
            AcademicResearchRequest(
                request_id="bad-intensity",
                topic="compiler autotuning",
                research_intensity="exhaustive",
            )

    def test_request_rejects_nested_request_id(self) -> None:
        with self.assertRaisesRegex(mf.ContractValidationError, "one ref segment"):
            AcademicResearchRequest(request_id="bad/id", topic="compiler autotuning").validate()


if __name__ == "__main__":
    unittest.main()
