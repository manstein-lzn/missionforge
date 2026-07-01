import assert from "node:assert/strict";
import { mkdir, mkdtemp, readFile, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";

import {
  grobidParsePdf,
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
    assert.equal(result.status, "unavailable");
    assert.equal(result.tei_ref, "");
    assert.equal(diagnostics.status, "unavailable");
    assert.deepEqual(diagnostics.reason_codes, ["grobid_base_url_missing"]);
    assert.equal(manifest.pdf_ref, "inputs/seed_pdfs/001-paper.pdf");
    assert.match(manifest.sha256, /^sha256:/);
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
    return new Response("<TEI><text>parsed</text></TEI>", { status: 200 });
  };
  try {
    const result = await grobidParsePdf({
      pdf_ref: "inputs/seed_pdfs/001-paper.pdf",
      output_prefix_ref: "sources/seed_pdfs/001-paper",
    });
    const tei = await readFile(join(workspace, result.tei_ref), "utf-8");
    const diagnostics = JSON.parse(await readFile(join(workspace, result.diagnostics_ref), "utf-8"));
    assert.equal(result.status, "completed");
    assert.ok(seenUrls.includes("http://grobid.test/api/processFulltextDocument"));
    assert.equal(tei, "<TEI><text>parsed</text></TEI>");
    assert.equal(diagnostics.status, "completed");
    assert.equal(diagnostics.tei_ref, "sources/seed_pdfs/001-paper/grobid.tei.xml");
  } finally {
    process.chdir(previousCwd);
    globalThis.fetch = previousFetch;
    restoreGrobidBaseUrl(previous);
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
