# MissionForge Pi Academic Sources

Local Pi extension for academic DeepResearch source acquisition.

It exposes provider adapters as tools and does not perform research planning,
source ranking, synthesis, or acceptance. PiWorker decides what to search, what
to fetch, when to continue, and how to cite the evidence.

Tools:

- `academic_search`: normalized search over arXiv, OpenAlex, Semantic Scholar,
  Crossref, and optional GitHub repositories.
- `academic_fetch`: fetch a URL, DOI, arXiv locator, OpenAlex work, or GitHub
  repository locator.
- `citation_lookup`: OpenAlex-backed cited-by/reference lookup.
- `repo_search`: GitHub repository search.

Google Scholar is intentionally not included because it has no stable public
official API. A user-owned third-party provider can be added as another
extension grant later.
