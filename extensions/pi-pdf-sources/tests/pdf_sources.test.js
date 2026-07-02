import assert from "node:assert/strict";
import { mkdir, mkdtemp, readFile, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";

import {
  grobidParsePdf,
  ocrParsePdf,
  pdfProviderCapabilities,
} from "../src/pdf_sources.js";

test("pdf_provider_capabilities reports missing GROBID as optional", async () => {
  const previous = process.env.GROBID_BASE_URL;
  delete process.env.GROBID_BASE_URL;
  try {
    const capabilities = await pdfProviderCapabilities();
    assert.equal(capabilities.schema_version, "missionforge.pi_pdf_sources.provider_capabilities.v1");
    assert.equal(capabilities.providers[0].provider, "grobid");
    assert.equal(capabilities.providers[0].status, "disabled");
    assert.equal(capabilities.diagnostics[0].code, "optional_pdf_provider_config_missing");
  } finally {
    restoreGrobidBaseUrl(previous);
  }
});

test("grobid_parse_pdf writes unavailable diagnostics when GROBID is not configured", async () => {
  const previous = process.env.GROBID_BASE_URL;
  delete process.env.GROBID_BASE_URL;
  const workspace = await mkdtemp(join(tmpdir(), "missionforge-pdf-"));
  const previousCwd = process.cwd();
  process.chdir(workspace);
  await mkdir(join(workspace, "inputs/seed_pdfs"), { recursive: true });
  await writeFile(join(workspace, "inputs/seed_pdfs/001-paper.pdf"), "%PDF-1.4\n", "utf-8");
  try {
    const result = await grobidParsePdf({
      pdf_ref: "inputs/seed_pdfs/001-paper.pdf",
      output_prefix_ref: "sources/seed_pdfs/001-paper",
    });
    const diagnostics = JSON.parse(await readFile(join(workspace, result.diagnostics_ref), "utf-8"));
    const manifest = JSON.parse(await readFile(join(workspace, result.manifest_ref), "utf-8"));
    const parseResult = JSON.parse(await readFile(join(workspace, result.parse_result_ref), "utf-8"));
    assert.equal(result.status, "unavailable");
    assert.equal(result.tei_ref, "");
    assert.equal(diagnostics.status, "unavailable");
    assert.deepEqual(diagnostics.reason_codes, ["grobid_base_url_missing"]);
    assert.equal(manifest.pdf_ref, "inputs/seed_pdfs/001-paper.pdf");
    assert.match(manifest.sha256, /^sha256:/);
    assert.equal(parseResult.status, "unavailable");
    assert.equal(parseResult.parse_result_ref, "sources/seed_pdfs/001-paper/parse_result.json");
  } finally {
    process.chdir(previousCwd);
    restoreGrobidBaseUrl(previous);
  }
});

test("grobid_parse_pdf posts PDF to GROBID and writes TEI", async () => {
  const previous = process.env.GROBID_BASE_URL;
  process.env.GROBID_BASE_URL = "http://grobid.test";
  const previousFetch = globalThis.fetch;
  const workspace = await mkdtemp(join(tmpdir(), "missionforge-pdf-"));
  const previousCwd = process.cwd();
  process.chdir(workspace);
  await mkdir(join(workspace, "inputs/seed_pdfs"), { recursive: true });
  await writeFile(join(workspace, "inputs/seed_pdfs/001-paper.pdf"), "%PDF-1.4\n", "utf-8");
  const seenUrls = [];
  globalThis.fetch = async (url) => {
    seenUrls.push(String(url));
    return new Response(
      `<TEI>
        <teiHeader>
          <fileDesc>
            <titleStmt>
              <title>MissionForge PDF Parsing</title>
              <author><persName><forename>Ada</forename><surname>Lovelace</surname></persName></author>
            </titleStmt>
            <sourceDesc>
              <biblStruct><analytic><title>MissionForge PDF Parsing</title></analytic><idno type="DOI">10.1234/example</idno></biblStruct>
            </sourceDesc>
          </fileDesc>
          <profileDesc><abstract><p>Structured parsing abstract.</p></abstract></profileDesc>
        </teiHeader>
        <text>
          <body><div coords="1,10,20,30,40"><head>Introduction</head><p>Parsed paragraph.</p></div></body>
          <back><listBibl><biblStruct xml:id="b1"><analytic><title>Related Work</title><author><persName><surname>Turing</surname></persName></author></analytic><idno type="DOI">10.5555/related</idno></biblStruct></listBibl></back>
        </text>
      </TEI>`,
      { status: 200 },
    );
  };
  try {
    const result = await grobidParsePdf({
      pdf_ref: "inputs/seed_pdfs/001-paper.pdf",
      output_prefix_ref: "sources/seed_pdfs/001-paper",
    });
    const tei = await readFile(join(workspace, result.tei_ref), "utf-8");
    const diagnostics = JSON.parse(await readFile(join(workspace, result.diagnostics_ref), "utf-8"));
    const metadata = JSON.parse(await readFile(join(workspace, result.projection_refs.metadata_ref), "utf-8"));
    const sections = JSON.parse(await readFile(join(workspace, result.projection_refs.sections_ref), "utf-8"));
    const references = JSON.parse(await readFile(join(workspace, result.projection_refs.references_ref), "utf-8"));
    const pageSpans = JSON.parse(await readFile(join(workspace, result.projection_refs.page_spans_ref), "utf-8"));
    const provenance = JSON.parse(await readFile(join(workspace, result.projection_refs.provenance_ref), "utf-8"));
    const parseResult = JSON.parse(await readFile(join(workspace, result.parse_result_ref), "utf-8"));
    assert.equal(result.status, "completed");
    assert.ok(seenUrls.includes("http://grobid.test/api/processFulltextDocument"));
    assert.match(tei, /MissionForge PDF Parsing/);
    assert.equal(diagnostics.status, "completed");
    assert.equal(diagnostics.tei_ref, "sources/seed_pdfs/001-paper/grobid.tei.xml");
    assert.equal(metadata.title, "MissionForge PDF Parsing");
    assert.equal(metadata.authors[0].full_name, "Ada Lovelace");
    assert.equal(metadata.parse_result_ref, "sources/seed_pdfs/001-paper/parse_result.json");
    assert.equal(sections.sections[0].heading, "Introduction");
    assert.equal(sections.sections[0].provenance.page_refs[0], "page:1");
    assert.equal(pageSpans.spans[0].page_ref, "page:1");
    assert.equal(pageSpans.spans[0].source, "grobid_coords");
    assert.equal(references.references[0].title, "Related Work");
    assert.equal(provenance.counts.reference_count, 1);
    assert.equal(provenance.counts.page_span_count, pageSpans.spans.length);
    assert.equal(provenance.parse_result_ref, "sources/seed_pdfs/001-paper/parse_result.json");
    assert.equal(parseResult.projection_refs.metadata_ref, "sources/seed_pdfs/001-paper/metadata.json");
    assert.equal(parseResult.projection_refs.page_spans_ref, "sources/seed_pdfs/001-paper/page_spans.json");
  } finally {
    process.chdir(previousCwd);
    globalThis.fetch = previousFetch;
    restoreGrobidBaseUrl(previous);
  }
});

test("ocr_parse_pdf writes unavailable diagnostics when OCR is not configured", async () => {
  const previous = process.env.PDF_OCR_BASE_URL;
  delete process.env.PDF_OCR_BASE_URL;
  const workspace = await mkdtemp(join(tmpdir(), "missionforge-pdf-"));
  const previousCwd = process.cwd();
  process.chdir(workspace);
  await mkdir(join(workspace, "inputs/seed_pdfs"), { recursive: true });
  await writeFile(join(workspace, "inputs/seed_pdfs/001-paper.pdf"), "%PDF-1.4\n", "utf-8");
  try {
    const result = await ocrParsePdf({
      pdf_ref: "inputs/seed_pdfs/001-paper.pdf",
      output_prefix_ref: "sources/seed_pdfs/001-paper",
    });
    const diagnostics = JSON.parse(await readFile(join(workspace, result.ocr_diagnostics_ref), "utf-8"));
    assert.equal(result.status, "unavailable");
    assert.equal(result.page_spans_ref, "");
    assert.deepEqual(diagnostics.reason_codes, ["ocr_base_url_missing"]);
  } finally {
    process.chdir(previousCwd);
    restorePdfOcrBaseUrl(previous);
  }
});

test("ocr_parse_pdf delegates to configured OCR provider and writes page spans", async () => {
  const previous = process.env.PDF_OCR_BASE_URL;
  process.env.PDF_OCR_BASE_URL = "http://ocr.test";
  const previousFetch = globalThis.fetch;
  const workspace = await mkdtemp(join(tmpdir(), "missionforge-pdf-"));
  const previousCwd = process.cwd();
  process.chdir(workspace);
  await mkdir(join(workspace, "inputs/seed_pdfs"), { recursive: true });
  await writeFile(join(workspace, "inputs/seed_pdfs/001-paper.pdf"), "%PDF-1.4\n", "utf-8");
  const seenUrls = [];
  globalThis.fetch = async (url) => {
    seenUrls.push(String(url));
    return new Response(
      JSON.stringify({
        pages: [
          {
            page: 1,
            blocks: [
              { text: "Scanned page text.", bbox: [10, 20, 30, 40] },
            ],
          },
        ],
      }),
      { status: 200, headers: { "content-type": "application/json" } },
    );
  };
  try {
    const result = await ocrParsePdf({
      pdf_ref: "inputs/seed_pdfs/001-paper.pdf",
      output_prefix_ref: "sources/seed_pdfs/001-paper",
    });
    const pageSpans = JSON.parse(await readFile(join(workspace, result.page_spans_ref), "utf-8"));
    const ocrText = await readFile(join(workspace, result.ocr_text_ref), "utf-8");
    const diagnostics = JSON.parse(await readFile(join(workspace, result.ocr_diagnostics_ref), "utf-8"));
    assert.equal(result.status, "completed");
    assert.ok(seenUrls.includes("http://ocr.test/api/ocrPdf"));
    assert.equal(pageSpans.spans[0].source, "ocr_fallback");
    assert.equal(pageSpans.spans[0].page_ref, "page:1");
    assert.match(ocrText, /Scanned page text/);
    assert.equal(diagnostics.page_span_count, 1);
  } finally {
    process.chdir(previousCwd);
    globalThis.fetch = previousFetch;
    restorePdfOcrBaseUrl(previous);
  }
});

test("grobid_parse_pdf rejects unsafe refs", async () => {
  await assert.rejects(
    () => grobidParsePdf({ pdf_ref: "../secret.pdf", output_prefix_ref: "inputs/seed_pdfs/bad" }),
    /safe workspace ref/,
  );
  await assert.rejects(
    () => grobidParsePdf({ pdf_ref: "reports/file.pdf", output_prefix_ref: "inputs/seed_pdfs/bad" }),
    /under inputs/,
  );
  await assert.rejects(
    () => grobidParsePdf({ pdf_ref: "inputs/a.pdf", output_prefix_ref: "reports/bad" }),
    /under sources\/seed_pdfs/,
  );
});

function restoreGrobidBaseUrl(value) {
  if (value === undefined) {
    delete process.env.GROBID_BASE_URL;
  } else {
    process.env.GROBID_BASE_URL = value;
  }
}

function restorePdfOcrBaseUrl(value) {
  if (value === undefined) {
    delete process.env.PDF_OCR_BASE_URL;
  } else {
    process.env.PDF_OCR_BASE_URL = value;
  }
}
