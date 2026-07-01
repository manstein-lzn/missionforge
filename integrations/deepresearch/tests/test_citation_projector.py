from __future__ import annotations

import unittest

from missionforge_deepresearch.citation_projector import project_report_citations


class CitationProjectorTests(unittest.TestCase):
    def test_project_report_citations_rewrites_source_ids_to_anchors(self) -> None:
        markdown = (
            "# Report\n\n"
            "## 摘要与核心发现\n\n"
            "MLIR-to-FPGA work needs source-backed claims [S1].\n\n"
            "## 参考文献\n\n"
            "- [S1] Old reference\n"
        )
        canonical_sources = {
            "schema_version": "missionforge_deepresearch.canonical_sources.v1",
            "sources": [
                {
                    "source_id": "S1",
                    "title": "MLIR to FPGA Compilation",
                    "authors": ["A. Researcher"],
                    "year": 2025,
                    "venue": "FPGA",
                    "identifiers": {"doi": "10.1145/1234567.1234568"},
                    "locators": [
                        {
                            "kind": "doi",
                            "url": "https://doi.org/10.1145/1234567.1234568",
                            "access_status": "unchecked",
                        }
                    ],
                }
            ],
        }

        projection = project_report_citations(markdown=markdown, canonical_sources_payload=canonical_sources)

        self.assertIn("[cite: 1](#ref-1)", projection["projected_markdown"])
        self.assertIn('<a id="ref-1"></a>[1] MLIR to FPGA Compilation.', projection["projected_markdown"])
        self.assertEqual(projection["citation_registry"]["entries"][0]["source_id"], "S1")
        self.assertEqual(projection["validation"]["status"], "passed")

    def test_project_report_citations_fails_for_unknown_source_id(self) -> None:
        projection = project_report_citations(
            markdown="A claim [S999].\n",
            canonical_sources_payload={
                "schema_version": "missionforge_deepresearch.canonical_sources.v1",
                "sources": [],
            },
        )

        self.assertEqual(projection["validation"]["status"], "failed")
        self.assertIn("unknown_source_id:S999", projection["validation"]["failure_codes"])

    def test_project_report_citations_ignores_reference_only_source_ids(self) -> None:
        projection = project_report_citations(
            markdown="# Report\n\nNo cited body claims.\n\n## References\n\n- [S1] Old reference\n",
            canonical_sources_payload={
                "schema_version": "missionforge_deepresearch.canonical_sources.v1",
                "sources": [
                    {
                        "source_id": "S1",
                        "title": "Unused Source",
                        "locators": [{"kind": "url", "url": "https://example.test/source", "access_status": "unchecked"}],
                    }
                ],
            },
        )

        self.assertEqual(projection["validation"]["status"], "passed")
        self.assertEqual(projection["citation_registry"]["entries"], [])

    def test_project_report_citations_ignores_fenced_code_source_ids(self) -> None:
        projection = project_report_citations(
            markdown="# Report\n\n```text\nDo not rewrite [S1].\n```\n\nA real claim [S1].\n",
            canonical_sources_payload={
                "schema_version": "missionforge_deepresearch.canonical_sources.v1",
                "sources": [
                    {
                        "source_id": "S1",
                        "title": "Used Source",
                        "locators": [{"kind": "url", "url": "https://example.test/source", "access_status": "unchecked"}],
                    }
                ],
            },
        )

        self.assertIn("Do not rewrite [S1].", projection["projected_markdown"])
        self.assertIn("A real claim [cite: 1](#ref-1).", projection["projected_markdown"])
        self.assertEqual(projection["validation"]["status"], "passed")


if __name__ == "__main__":
    unittest.main()
