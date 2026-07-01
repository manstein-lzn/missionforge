from __future__ import annotations

import unittest

from missionforge_deepresearch.source_acquisition import (
    build_fixture_provider_capabilities,
    build_fixture_search_plan,
    parse_provider_hits_jsonl,
    project_coverage_report,
    provider_hits_jsonl_from_source_packet,
)


class SourceAcquisitionTests(unittest.TestCase):
    def test_project_coverage_report_counts_sources_hits_and_provider_status(self) -> None:
        source_packet = {
            "schema_version": "missionforge_deepresearch.source_packet.v1",
            "request_id": "coverage-demo",
            "source_records": [
                {
                    "source_id": "S1",
                    "provider": "semantic_scholar",
                    "title": "Compiler Survey",
                    "year": 2024,
                    "evidence_strength": "abstract",
                },
                {
                    "source_id": "S2",
                    "provider": "arxiv",
                    "title": "Compiler Preprint",
                    "year": 2025,
                    "evidence_strength": "metadata",
                },
            ],
        }
        provider_capabilities = build_fixture_provider_capabilities(
            request_id="coverage-demo",
            provider_policy="default_no_key",
        )
        search_plan = build_fixture_search_plan(
            request_id="coverage-demo",
            topic="compiler survey",
            provider_policy="default_no_key",
            target_source_count=50,
            max_source_count=50,
        )
        provider_hits = parse_provider_hits_jsonl(
            provider_hits_jsonl_from_source_packet(
                request_id="coverage-demo",
                source_packet=source_packet,
                query="compiler survey",
                provider="semantic_scholar",
            )
        )

        report = project_coverage_report(
            request_id="coverage-demo",
            source_packet=source_packet,
            search_plan=search_plan,
            provider_capabilities=provider_capabilities,
            provider_hits=provider_hits,
            target_source_count=50,
        )

        self.assertEqual(report["schema_version"], "missionforge_deepresearch.coverage_report.v1")
        self.assertEqual(report["source_record_count"], 2)
        self.assertEqual(report["provider_record_counts"], {"arxiv": 1, "semantic_scholar": 1})
        self.assertEqual(report["provider_hit_counts"], {"semantic_scholar": 2})
        self.assertEqual(report["year_coverage"]["min_year"], 2024)
        self.assertEqual(report["year_coverage"]["max_year"], 2025)
        self.assertEqual(report["planned_query_family_count"], 1)
        self.assertEqual(report["mechanical_coverage_status"], "below_target")
        self.assertEqual(report["semantic_sufficiency"], "piworker_judge_required")


if __name__ == "__main__":
    unittest.main()
