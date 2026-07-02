# MissionForge Pi PDF Sources

Local Pi extension for PDF seed ingestion in DeepResearch.

The extension does not implement a custom PDF parser or OCR engine. It
delegates scholarly PDF parsing to external providers such as GROBID and
optionally delegates scanned-PDF OCR to a configured OCR provider. PDF refs are
workspace refs; absolute paths and path traversal are rejected by the extension
before any file access.

Tools:

- `pdf_provider_capabilities`: report configured PDF parsing providers.
- `grobid_parse_pdf`: submit an authorized workspace PDF ref to a configured
  GROBID service and write raw TEI, diagnostics, parse result, metadata,
  sections, references, page spans, and provenance JSON under a
  `sources/seed_pdfs/...` output ref prefix.
- `ocr_parse_pdf`: submit an authorized workspace PDF ref to a configured OCR
  service and write OCR diagnostics, bounded OCR text, and page-span evidence
  refs under the same output prefix.

Configuration:

- `GROBID_BASE_URL`: optional GROBID service URL, for example
  `http://localhost:8070`.
- `PDF_OCR_BASE_URL`: optional OCR fallback service URL. The service is
  expected to accept `POST /api/ocrPdf` with a PDF form upload and return JSON
  pages or plain text.

Missing GROBID or OCR configuration is not a task failure. DeepResearch records
the PDF gap and continues from topic, seed metadata, and public scholarly
sources.
