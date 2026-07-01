# MissionForge Pi Academic Sources

Local Pi extension for academic DeepResearch source acquisition.

It exposes provider adapters as tools and does not perform research planning,
source ranking, synthesis, or acceptance. PiWorker decides what to search, what
to fetch, when to continue, and how to cite the evidence.

The default provider policy is no-key. A standard academic search does not
require API keys, paid accounts, browser cookies, or manual login. OpenAlex is
available only as an explicit enhancement when `OPENALEX_API_KEY` is configured.

Tools:

- `academic_provider_capabilities`: report enabled default providers, optional
  enhancements, missing provider configuration, and provider capabilities.
- `academic_search`: normalized search over the default no-key stack:
  Semantic Scholar, arXiv, Crossref, DBLP, and PubMed/PMC. OpenAlex can be
  included only when configured.
- `academic_fetch`: fetch a URL, DOI, arXiv locator, PubMed ID, OpenAlex work
  when configured, or GitHub repository locator.
- `citation_lookup`: cited-by/reference lookup through Semantic Scholar,
  OpenCitations for DOI locators, and optional OpenAlex when configured.
- `repo_search`: GitHub repository search.

Google Scholar is intentionally not included because it has no stable public
official API. A user-owned third-party provider can be added as another
extension grant later.

Provider policy:

- `default_no_key`: Semantic Scholar, arXiv, Crossref, DBLP, and PubMed.
- `openalex_enhanced`: includes OpenAlex only when `OPENALEX_API_KEY` is set.

Missing optional providers are returned as diagnostics and should be recorded as
source gaps by the product integration. Missing OpenAlex credentials are not a
task failure.
