from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from missionforge_deepresearch.experimental import run_deepresearch_tool_healthcheck
from missionforge_deepresearch.source_collector import AcademicSourceCollectionConfig

from test_product_contract import sample_request


class ToolHealthcheckTests(unittest.TestCase):
    def test_healthcheck_writes_refs_and_reports_tool_surfaces(self) -> None:
        request = sample_request()

        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            result = run_deepresearch_tool_healthcheck(
                request,
                workspace=root,
                source_config=AcademicSourceCollectionConfig(
                    max_records=4,
                    since_year=2023,
                    providers=("semantic_scholar", "crossref", "openalex", "arxiv"),
                ),
                fetch_json=_fake_academic_json,
                fetch_text=_fake_arxiv,
                fetch_github_json=_fake_github_json,
                fetch_npm_json=_fake_npm_json,
            )

            self.assertEqual(result["status"], "degraded")
            self.assertEqual(result["request_id"], request.request_id)
            self.assertEqual(result["search_queries"], [request.topic])
            self.assertEqual(len(result["academic_provider_checks"]), 4)
            self.assertTrue(all(record["status"] == "passed" for record in result["academic_provider_checks"]))
            self.assertEqual(result["github_check"]["status"], "passed")
            self.assertEqual(result["scholar_check"]["status"], "unsupported")
            self.assertEqual(
                [record["status"] for record in result["npm_extension_package_checks"]],
                ["passed", "passed"],
            )
            self.assertEqual(
                [record["status"] for record in result["extension_package_checks"]],
                ["passed", "passed", "passed"],
            )
            self.assertEqual(result["extension_package_checks"][0]["surface"], "local_extension_package")
            self.assertTrue((root / result["result_ref"]).is_file())
            self.assertTrue((root / result["report_ref"]).is_file())
            self.assertTrue((root / result["search_intent_ref"]).is_file())

            written = json.loads((root / result["result_ref"]).read_text(encoding="utf-8"))
            report = (root / result["report_ref"]).read_text(encoding="utf-8")
            self.assertEqual(written["schema_version"], "missionforge_deepresearch.tool_healthcheck.v1")
            self.assertIn("Google Scholar", report)

    def test_healthcheck_preserves_provider_failure_reports(self) -> None:
        request = sample_request()

        with tempfile.TemporaryDirectory() as tempdir:
            result = run_deepresearch_tool_healthcheck(
                request,
                workspace=Path(tempdir),
                source_config=AcademicSourceCollectionConfig(
                    max_records=4,
                    since_year=2023,
                    providers=("semantic_scholar",),
                ),
                academic_providers=("semantic_scholar",),
                fetch_json=_failing_semantic_scholar,
                fetch_github_json=_fake_github_json,
                fetch_npm_json=_fake_npm_json,
            )

            semantic = result["academic_provider_checks"][0]
            self.assertEqual(semantic["status"], "failed")
            self.assertEqual(semantic["candidate_count"], 0)
            self.assertEqual(semantic["provider_reports"][0]["status"], "failed")
            self.assertEqual(semantic["provider_reports"][0]["error_type"], "RuntimeError")


def _fake_academic_json(url: str, timeout: float):
    if "api.semanticscholar.org" in url:
        return {
            "data": [
                {
                    "title": "Compiler Autotuning Healthcheck Semantic",
                    "year": 2024,
                    "publicationDate": "2024-01-10",
                    "citationCount": 12,
                    "venue": "Semantic Compiler Venue",
                    "url": "https://semanticscholar.org/paper/healthcheck",
                    "externalIds": {"DOI": "10.1000/health-semantic"},
                    "authors": [{"name": "Ada Compiler"}],
                    "abstract": "A source returned by Semantic Scholar.",
                }
            ]
        }
    if "api.crossref.org" in url:
        return {
            "message": {
                "items": [
                    {
                        "title": ["Compiler Autotuning Healthcheck Crossref"],
                        "DOI": "10.1000/health-crossref",
                        "URL": "https://doi.org/10.1000/health-crossref",
                        "container-title": ["Compiler Journal"],
                        "author": [{"given": "Cara", "family": "Cross"}],
                        "is-referenced-by-count": 4,
                        "issued": {"date-parts": [[2024, 5, 1]]},
                    }
                ]
            }
        }
    if "api.openalex.org" in url:
        return {
            "results": [
                {
                    "id": "https://openalex.org/W-health",
                    "doi": "https://doi.org/10.1000/health-openalex",
                    "display_name": "Compiler Autotuning Healthcheck OpenAlex",
                    "publication_year": 2024,
                    "publication_date": "2024-01-10",
                    "cited_by_count": 11,
                    "primary_location": {"source": {"display_name": "Journal of Compilers"}},
                    "authorships": [{"author": {"display_name": "Ada Compiler"}}],
                }
            ]
        }
    raise AssertionError(url)


def _fake_arxiv(url: str, timeout: float) -> str:
    return """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
  <entry>
    <id>http://arxiv.org/abs/2401.12345v1</id>
    <title>Compiler Autotuning Healthcheck Arxiv</title>
    <published>2024-01-11T00:00:00Z</published>
    <updated>2024-01-12T00:00:00Z</updated>
    <summary>A source returned by arXiv.</summary>
    <author><name>Ada Compiler</name></author>
    <category term="cs.PL"/>
  </entry>
</feed>
"""


def _fake_github_json(url: str, timeout: float):
    if "api.github.com/search/repositories" not in url:
        raise AssertionError(url)
    return {
        "items": [
            {
                "full_name": "example/compiler-autotuning",
                "html_url": "https://github.com/example/compiler-autotuning",
                "stargazers_count": 42,
            }
        ]
    }


def _fake_npm_json(url: str, timeout: float):
    if "pi-web-access" in url:
        return {"name": "pi-web-access", "version": "0.10.7"}
    if "%40juicesharp%2Frpiv-web-tools" in url or "@juicesharp%2Frpiv-web-tools" in url:
        return {"name": "@juicesharp/rpiv-web-tools", "version": "0.1.0"}
    raise AssertionError(url)


def _failing_semantic_scholar(url: str, timeout: float):
    raise RuntimeError("semantic scholar unavailable")


if __name__ == "__main__":
    unittest.main()
