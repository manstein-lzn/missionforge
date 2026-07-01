# MissionForge Pi PDF Sources

Local Pi extension for PDF seed ingestion in DeepResearch.

The extension does not implement a custom PDF parser. It delegates scholarly
PDF parsing to external providers such as GROBID and records diagnostics when a
provider is unavailable. PDF refs are workspace refs; absolute paths and path
traversal are rejected by the extension before any file access.

Tools:

- `pdf_provider_capabilities`: report configured PDF parsing providers.
- `grobid_parse_pdf`: submit an authorized workspace PDF ref to a configured
  GROBID service and write raw TEI plus diagnostics under an output ref prefix.

Configuration:

- `GROBID_BASE_URL`: optional GROBID service URL, for example
  `http://localhost:8070`.

Missing GROBID configuration is not a task failure. DeepResearch records the
PDF gap and continues from topic, seed metadata, and public scholarly sources.
