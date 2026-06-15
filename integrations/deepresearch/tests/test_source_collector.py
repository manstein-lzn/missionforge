from __future__ import annotations

import unittest

from missionforge_deepresearch.source_collector import (
    AcademicSourceCollectionConfig,
    collect_live_academic_sources,
)
from missionforge_deepresearch.search_intent import AcademicSearchIntent, SEARCH_INTENT_REF

from test_product_contract import sample_request


class SourceCollectorTests(unittest.TestCase):
    def test_live_collector_builds_refs_first_source_packet(self) -> None:
        request = sample_request()

        result = collect_live_academic_sources(
            request,
            config=AcademicSourceCollectionConfig(
                max_records=5,
                since_year=2023,
                providers=("semantic_scholar", "crossref", "openalex", "arxiv"),
            ),
            fetch_json=_fake_json,
            fetch_text=_fake_arxiv,
        )

        packet = result.source_packet
        self.assertEqual(packet["mode"], "live")
        self.assertEqual(packet["query"], request.topic)
        self.assertEqual(packet["collection_policy"]["query_expansion"], "none")
        self.assertEqual(packet["search_queries"], [request.topic])
        self.assertEqual(packet["search_intent_ref"], SEARCH_INTENT_REF)
        self.assertEqual(packet["collection_policy"]["since_year"], 2023)
        self.assertEqual(len(packet["source_records"]), 5)
        self.assertIn("query", packet["source_records"][0])
        self.assertIn(SEARCH_INTENT_REF, result.source_payloads)
        self.assertIn("sources/live/S001.json", result.source_payloads)
        self.assertEqual(result.collection_report["selected_count"], 5)
        self.assertEqual(result.collection_report["search_query_count"], 1)
        self.assertEqual(result.collection_report["source_record_refs"][0], "sources/live/S001.json")

    def test_live_collector_executes_declared_search_intent_queries(self) -> None:
        request = sample_request()
        seen_urls: list[str] = []

        result = collect_live_academic_sources(
            request,
            config=AcademicSourceCollectionConfig(max_records=10, providers=("crossref",), max_search_queries=3),
            search_intent=AcademicSearchIntent.from_queries(
                request,
                ["compiler autotuning survey", "autotuning compilers", "kernel generation autotuning"],
            ),
            fetch_json=lambda url, timeout: _recording_crossref(url, timeout, seen_urls),
            fetch_text=_fake_arxiv,
        )

        self.assertEqual(
            result.source_packet["search_queries"],
            ["compiler autotuning survey", "autotuning compilers", "kernel generation autotuning"],
        )
        self.assertEqual(result.source_packet["collection_policy"]["query_expansion"], "search_intent")
        self.assertEqual(result.collection_report["search_query_count"], 3)
        self.assertEqual(len(seen_urls), 3)
        self.assertTrue(any("compiler+autotuning+survey" in url for url in seen_urls))
        self.assertTrue(any("autotuning+compilers" in url for url in seen_urls))

    def test_live_collector_deduplicates_by_doi(self) -> None:
        result = collect_live_academic_sources(
            sample_request(),
            config=AcademicSourceCollectionConfig(max_records=10, providers=("semantic_scholar", "openalex", "arxiv")),
            fetch_json=_fake_json,
            fetch_text=_fake_arxiv,
        )

        titles = [record["title"] for record in result.source_packet["source_records"]]

        self.assertEqual(titles.count("Compiler Autotuning Survey"), 1)


def _fake_json(url: str, timeout: float):
    if "api.semanticscholar.org" in url:
        return _fake_semantic_scholar(url, timeout)
    if "api.crossref.org" in url:
        return _fake_crossref(url, timeout)
    if "api.openalex.org" in url:
        return _fake_openalex(url, timeout)
    raise AssertionError(url)


def _fake_semantic_scholar(url: str, timeout: float):
    if "year=2023-" not in url and "api.semanticscholar.org" in url and "year=" in url:
        raise AssertionError(url)
    return {
        "data": [
            {
                "title": "Compiler Autotuning Survey",
                "year": 2024,
                "publicationDate": "2024-01-10",
                "citationCount": 12,
                "venue": "Semantic Compiler Venue",
                "url": "https://semanticscholar.org/paper/1",
                "externalIds": {"DOI": "10.1000/autotune"},
                "authors": [{"name": "Ada Compiler"}],
                "abstract": "A survey.",
            },
            {
                "title": "Autotuning with Bayesian Optimization",
                "year": 2024,
                "publicationDate": "2024-03-10",
                "citationCount": 8,
                "venue": "Optimization",
                "url": "https://semanticscholar.org/paper/2",
                "externalIds": {},
                "authors": [{"name": "Bo Tuner"}],
                "abstract": "Bayesian optimization for autotuning.",
            },
        ]
    }


def _fake_crossref(url: str, timeout: float):
    if "from-pub-date%3A2023-01-01" not in url and "filter=" in url:
        raise AssertionError(url)
    return {
        "message": {
            "items": [
                {
                    "title": ["Crossref Compiler Optimization"],
                    "DOI": "10.1000/crossref",
                    "URL": "https://doi.org/10.1000/crossref",
                    "container-title": ["Compiler Journal"],
                    "author": [{"given": "Cara", "family": "Cross"}],
                    "is-referenced-by-count": 4,
                    "issued": {"date-parts": [[2024, 5, 1]]},
                    "abstract": "<jats:p>Compiler optimization evidence.</jats:p>",
                }
            ]
        }
    }


def _recording_crossref(url: str, timeout: float, seen_urls: list[str]):
    seen_urls.append(url)
    return _fake_crossref(url, timeout)


def _fake_openalex(url: str, timeout: float):
    if "filter=from_publication_date%3A2023-01-01" not in url and "filter=" in url:
        raise AssertionError(url)
    return {
        "results": [
            {
                "id": "https://openalex.org/W1",
                "doi": "https://doi.org/10.1000/autotune",
                "display_name": "Compiler Autotuning Survey",
                "publication_year": 2024,
                "publication_date": "2024-01-10",
                "cited_by_count": 11,
                "primary_location": {"source": {"display_name": "Journal of Compilers"}},
                "authorships": [{"author": {"display_name": "Ada Compiler"}}],
                "abstract_inverted_index": {"A": [0], "survey": [1]},
            },
            {
                "id": "https://openalex.org/W2",
                "display_name": "Kernel Generation Systems",
                "publication_year": 2025,
                "publication_date": "2025-04-02",
                "cited_by_count": 3,
                "primary_location": {"source": {"display_name": "Systems"}},
                "authorships": [{"author": {"display_name": "Grace Kernel"}}],
                "abstract_inverted_index": {"Kernel": [0], "generation": [1]},
            },
        ]
    }


def _fake_arxiv(url: str, timeout: float) -> str:
    return """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
  <entry>
    <id>http://arxiv.org/abs/2401.00001v1</id>
    <title>Compiler Autotuning Survey</title>
    <published>2024-01-11T00:00:00Z</published>
    <updated>2024-01-12T00:00:00Z</updated>
    <summary>Duplicate DOI record.</summary>
    <author><name>Ada Compiler</name></author>
    <arxiv:doi>10.1000/autotune</arxiv:doi>
    <category term="cs.PL"/>
  </entry>
  <entry>
    <id>http://arxiv.org/abs/2501.00002v1</id>
    <title>LLM Harness Engineering</title>
    <published>2025-01-11T00:00:00Z</published>
    <updated>2025-01-12T00:00:00Z</updated>
    <summary>Harness engineering for large models.</summary>
    <author><name>Lin Harness</name></author>
    <category term="cs.SE"/>
  </entry>
</feed>
"""


if __name__ == "__main__":
    unittest.main()
