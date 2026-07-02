import { Type } from "typebox";

import {
  grobidParsePdf,
  ocrParsePdf,
  pdfProviderCapabilities,
} from "./src/pdf_sources.js";

export default function pdfSourcesExtension(pi) {
  pi.registerTool({
    name: "pdf_provider_capabilities",
    label: "PDF Provider Capabilities",
    description: "Report configured PDF parsing providers such as GROBID.",
    promptSnippet:
      "Inspect PDF parsing capabilities before relying on seed PDFs. Missing GROBID is a source gap, not a task failure.",
    promptGuidelines: [
      "Use this before parsing seed PDFs.",
      "Do not treat missing GROBID or degraded PDF extraction as a fatal research failure.",
      "Record PDF parser diagnostics in seed gaps and coverage artifacts.",
    ],
    parameters: Type.Object({
      check_service: Type.Optional(Type.Boolean({ description: "When true, call the configured provider health endpoint." })),
    }),
    execute: async (_toolCallId, params, signal) => {
      const result = await pdfProviderCapabilities(params, signal);
      return jsonToolResult(result);
    },
  });

  pi.registerTool({
    name: "grobid_parse_pdf",
    label: "GROBID Parse PDF",
    description:
      "Submit an authorized workspace PDF ref to GROBID and write TEI, diagnostics, and structural projection artifacts. This tool does not parse PDF content itself.",
    promptSnippet:
      "Use grobid_parse_pdf for academic seed PDFs when GROBID is configured. Pass only workspace refs under inputs/.",
    promptGuidelines: [
      "Use workspace refs, not absolute paths.",
      "Write parser outputs under a sources/seed_pdfs/... prefix.",
      "On successful GROBID parsing, use the returned metadata/sections/references/page_spans/provenance refs instead of pasting TEI into context.",
      "Treat raw TEI as the authoritative parsed artifact; Markdown summaries are derived views only.",
      "If parsing is unavailable or degraded, record diagnostics and continue with public metadata search.",
    ],
    parameters: Type.Object({
      pdf_ref: Type.String({ description: "Workspace PDF ref under inputs/, for example inputs/seed_pdfs/001-paper.pdf." }),
      output_prefix_ref: Type.String({
        description: "Workspace output prefix under sources/seed_pdfs/, for example sources/seed_pdfs/001-paper.",
      }),
      include_coordinates: Type.Optional(Type.Boolean({ description: "Request TEI coordinates when supported by GROBID." })),
    }),
    execute: async (_toolCallId, params, signal) => {
      const result = await grobidParsePdf(params, signal);
      return jsonToolResult(result);
    },
  });

  pi.registerTool({
    name: "ocr_parse_pdf",
    label: "OCR Parse PDF",
    description:
      "Submit an authorized workspace PDF ref to a configured OCR provider and write page-span evidence artifacts. This tool delegates OCR to an external provider.",
    promptSnippet:
      "Use ocr_parse_pdf only as a fallback for scanned or GROBID-unavailable seed PDFs when PDF_OCR_BASE_URL is configured.",
    promptGuidelines: [
      "Use workspace refs, not absolute paths.",
      "Write OCR outputs under the same sources/seed_pdfs/... prefix used by the seed PDF index.",
      "Do not paste OCR text into chat context; use ocr_text_ref and page_spans_ref as artifact refs.",
      "If OCR is unavailable or degraded, record diagnostics and continue with public metadata search.",
    ],
    parameters: Type.Object({
      pdf_ref: Type.String({ description: "Workspace PDF ref under inputs/, for example inputs/seed_pdfs/001-paper/source.pdf." }),
      output_prefix_ref: Type.String({
        description: "Workspace output prefix under sources/seed_pdfs/, for example sources/seed_pdfs/001-paper.",
      }),
    }),
    execute: async (_toolCallId, params, signal) => {
      const result = await ocrParsePdf(params, signal);
      return jsonToolResult(result);
    },
  });
}

function jsonToolResult(payload) {
  const text = JSON.stringify(payload, null, 2);
  return {
    content: [{ type: "text", text }],
    details: payload,
  };
}
