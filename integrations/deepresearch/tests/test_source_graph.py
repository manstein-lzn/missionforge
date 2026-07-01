from __future__ import annotations

import unittest

from missionforge_deepresearch.source_graph import project_source_graph


class SourceGraphTests(unittest.TestCase):
    def test_project_source_graph_dedupes_exact_identifiers(self) -> None:
        source_packet = {
            "schema_version": "missionforge_deepresearch.source_packet.v1",
            "request_id": "source-graph-demo",
            "source_records": [
                {
                    "source_id": "S1",
                    "provider": "semantic_scholar",
                    "title": "MLIR to FPGA Compilation",
                    "authors": ["A. Researcher"],
                    "year": 2025,
                    "doi": "10.1145/1234567.1234568",
                    "locator": "https://doi.org/10.1145/1234567.1234568",
                    "evidence_strength": "abstract",
                },
                {
                    "source_id": "S2",
                    "provider": "crossref",
                    "title": "MLIR-to-FPGA Compilation",
                    "year": 2025,
                    "doi": "https://doi.org/10.1145/1234567.1234568",
                    "locator": "10.1145/1234567.1234568",
                    "evidence_strength": "metadata",
                },
            ],
        }

        projection = project_source_graph(source_packet)
        canonical_sources = projection["canonical_sources"]["sources"]
        dedupe_entries = projection["dedupe_map"]["entries"]

        self.assertEqual(len(canonical_sources), 1)
        self.assertEqual(canonical_sources[0]["source_id"], "S1")
        self.assertEqual(canonical_sources[0]["identifiers"]["doi"], "10.1145/1234567.1234568")
        self.assertEqual(canonical_sources[0]["provider_provenance"], ["semantic_scholar", "crossref"])
        self.assertEqual(dedupe_entries[0]["canonical_source_id"], "S1")
        self.assertEqual(dedupe_entries[1]["canonical_source_id"], "S1")

    def test_project_source_graph_uses_normalized_title_fallback(self) -> None:
        source_packet = {
            "schema_version": "missionforge_deepresearch.source_packet.v1",
            "request_id": "source-graph-title",
            "source_records": [
                {"source_id": "S1", "title": "A Survey of Agent Tool Use", "locator": "https://example.test/a"},
                {"source_id": "S2", "title": "A survey: of agent-tool use", "locator": "https://example.test/b"},
            ],
        }

        projection = project_source_graph(source_packet)

        self.assertEqual(len(projection["canonical_sources"]["sources"]), 1)
        self.assertEqual(projection["dedupe_map"]["entries"][0]["dedupe_reason"], "normalized_title")

    def test_project_source_graph_keeps_unknown_records_separate(self) -> None:
        source_packet = {
            "schema_version": "missionforge_deepresearch.source_packet.v1",
            "request_id": "source-graph-unknown",
            "source_records": [
                {"source_id": "S1", "locator": "https://example.test/a"},
                {"source_id": "S2", "locator": "https://example.test/b"},
            ],
        }

        projection = project_source_graph(source_packet)

        self.assertEqual(len(projection["canonical_sources"]["sources"]), 2)
        self.assertEqual(projection["dedupe_map"]["entries"][0]["dedupe_reason"], "unknown_record")


if __name__ == "__main__":
    unittest.main()
