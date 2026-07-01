import { createHash } from "node:crypto";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { basename, dirname, join, normalize, resolve, sep } from "node:path";

const GROBID_BASE_URL_ENV = "GROBID_BASE_URL";
const PDF_CAPABILITIES_SCHEMA_VERSION = "missionforge.pi_pdf_sources.provider_capabilities.v1";
const GROBID_PARSE_RESULT_SCHEMA_VERSION = "missionforge.pi_pdf_sources.grobid_parse_result.v1";
const GROBID_DIAGNOSTICS_SCHEMA_VERSION = "missionforge.pi_pdf_sources.grobid_diagnostics.v1";
const TEI_METADATA_SCHEMA_VERSION = "missionforge.pi_pdf_sources.tei_metadata.v1";
const TEI_SECTIONS_SCHEMA_VERSION = "missionforge.pi_pdf_sources.tei_sections.v1";
const TEI_REFERENCES_SCHEMA_VERSION = "missionforge.pi_pdf_sources.tei_references.v1";
const TEI_PROVENANCE_SCHEMA_VERSION = "missionforge.pi_pdf_sources.tei_provenance.v1";

export async function pdfProviderCapabilities(params = {}, signal) {
  const baseUrl = normalizeBaseUrl(process.env[GROBID_BASE_URL_ENV]);
  const providers = [
    {
      provider: "grobid",
      status: baseUrl ? "configured" : "disabled",
      missing_config: !baseUrl,
      required_env: GROBID_BASE_URL_ENV,
      role: "scholarly_pdf_parser",
    },
  ];
  if (baseUrl && params.check_service === true) {
    providers[0] = {
      ...providers[0],
      service_status: await checkGrobidService(baseUrl, signal),
    };
  }
  return {
    schema_version: PDF_CAPABILITIES_SCHEMA_VERSION,
    providers,
    diagnostics: providers
      .filter((provider) => provider.missing_config)
      .map((provider) => ({
        provider: provider.provider,
        code: "optional_pdf_provider_config_missing",
        severity: "info",
        message: `${provider.required_env} is not configured`,
      })),
  };
}

export async function grobidParsePdf(params = {}, signal) {
  const pdfRef = requireInputPdfRef(params.pdf_ref);
  const outputPrefixRef = requireOutputPrefixRef(params.output_prefix_ref);
  const workspaceRoot = process.cwd();
  const pdfPath = resolveWorkspaceRef(workspaceRoot, pdfRef);
  const outputPrefixPath = resolveWorkspaceRef(workspaceRoot, outputPrefixRef);
  const diagnosticsRef = `${outputPrefixRef}/diagnostics.json`;
  const teiRef = `${outputPrefixRef}/grobid.tei.xml`;
  const manifestRef = `${outputPrefixRef}/manifest.json`;
  const parseResultRef = `${outputPrefixRef}/parse_result.json`;
  const projectionRefs = projectionRefsForPrefix(outputPrefixRef);
  const baseUrl = normalizeBaseUrl(process.env[GROBID_BASE_URL_ENV]);
  const pdfBytes = await readFile(pdfPath);
  const manifest = {
    schema_version: "missionforge.pi_pdf_sources.pdf_manifest.v1",
    pdf_ref: pdfRef,
    output_prefix_ref: outputPrefixRef,
    sha256: `sha256:${createHash("sha256").update(pdfBytes).digest("hex")}`,
    byte_length: pdfBytes.length,
    parser: "grobid",
    parser_configured: Boolean(baseUrl),
    parse_result_ref: parseResultRef,
    projection_refs: projectionRefs,
  };
  await writeJsonRef(workspaceRoot, manifestRef, manifest);
  if (!baseUrl) {
    const diagnostics = diagnosticsPayload({
      status: "unavailable",
      pdf_ref: pdfRef,
      output_prefix_ref: outputPrefixRef,
      reason_codes: ["grobid_base_url_missing"],
      message: `${GROBID_BASE_URL_ENV} is not configured`,
    });
    await writeJsonRef(workspaceRoot, diagnosticsRef, diagnostics);
    const result = {
      schema_version: GROBID_PARSE_RESULT_SCHEMA_VERSION,
      status: "unavailable",
      pdf_ref: pdfRef,
      output_prefix_ref: outputPrefixRef,
      parse_result_ref: parseResultRef,
      manifest_ref: manifestRef,
      tei_ref: "",
      diagnostics_ref: diagnosticsRef,
      projection_refs: emptyProjectionRefs(),
    };
    await writeJsonRef(workspaceRoot, parseResultRef, result);
    return result;
  }
  try {
    const tei = await callGrobidFulltext({
      baseUrl,
      pdfBytes,
      filename: basename(pdfRef),
      includeCoordinates: params.include_coordinates !== false,
      signal,
    });
    await writeTextFile(join(outputPrefixPath, "grobid.tei.xml"), tei);
    const projections = projectGrobidTei({
      tei,
      pdfRef,
      teiRef,
      manifestRef,
      diagnosticsRef,
      parseResultRef,
      outputPrefixRef,
    });
    await writeJsonRef(workspaceRoot, projectionRefs.metadata_ref, projections.metadata);
    await writeJsonRef(workspaceRoot, projectionRefs.sections_ref, projections.sections);
    await writeJsonRef(workspaceRoot, projectionRefs.references_ref, projections.references);
    await writeJsonRef(workspaceRoot, projectionRefs.provenance_ref, projections.provenance);
    const diagnostics = diagnosticsPayload({
      status: "completed",
      pdf_ref: pdfRef,
      output_prefix_ref: outputPrefixRef,
      reason_codes: [],
      message: "GROBID fulltext parsing completed.",
      tei_ref: teiRef,
      tei_char_count: tei.length,
      projection_refs: projectionRefs,
    });
    await writeJsonRef(workspaceRoot, diagnosticsRef, diagnostics);
    const result = {
      schema_version: GROBID_PARSE_RESULT_SCHEMA_VERSION,
      status: "completed",
      pdf_ref: pdfRef,
      output_prefix_ref: outputPrefixRef,
      parse_result_ref: parseResultRef,
      manifest_ref: manifestRef,
      tei_ref: teiRef,
      diagnostics_ref: diagnosticsRef,
      projection_refs: projectionRefs,
    };
    await writeJsonRef(workspaceRoot, parseResultRef, result);
    return result;
  } catch (error) {
    const diagnostics = diagnosticsPayload({
      status: "failed",
      pdf_ref: pdfRef,
      output_prefix_ref: outputPrefixRef,
      reason_codes: ["grobid_request_failed"],
      message: String(error?.message ?? error).slice(0, 500),
    });
    await writeJsonRef(workspaceRoot, diagnosticsRef, diagnostics);
    const result = {
      schema_version: GROBID_PARSE_RESULT_SCHEMA_VERSION,
      status: "failed",
      pdf_ref: pdfRef,
      output_prefix_ref: outputPrefixRef,
      parse_result_ref: parseResultRef,
      manifest_ref: manifestRef,
      tei_ref: "",
      diagnostics_ref: diagnosticsRef,
      projection_refs: emptyProjectionRefs(),
    };
    await writeJsonRef(workspaceRoot, parseResultRef, result);
    return result;
  }
}

export function projectGrobidTei({ tei, pdfRef, teiRef, manifestRef, diagnosticsRef, parseResultRef, outputPrefixRef }) {
  const sourceRefs = {
    pdf_ref: pdfRef,
    tei_ref: teiRef,
    manifest_ref: manifestRef,
    diagnostics_ref: diagnosticsRef,
    parse_result_ref: parseResultRef,
  };
  const titleStmt = firstBlock(tei, "titleStmt");
  const sourceDesc = firstBlock(tei, "sourceDesc");
  const profileDesc = firstBlock(tei, "profileDesc");
  const abstractBlock = firstBlock(profileDesc, "abstract");
  const metadata = {
    schema_version: TEI_METADATA_SCHEMA_VERSION,
    output_prefix_ref: outputPrefixRef,
    ...sourceRefs,
    title: firstTagText(titleStmt, "title") || firstTagText(sourceDesc, "title"),
    authors: extractAuthors(titleStmt || sourceDesc),
    abstract: textFromXml(abstractBlock).slice(0, 12000),
    identifiers: extractIdentifiers(tei),
    publication: extractPublication(sourceDesc),
    availability: clean(firstTagText(tei, "availability")),
  };
  const sections = {
    schema_version: TEI_SECTIONS_SCHEMA_VERSION,
    output_prefix_ref: outputPrefixRef,
    ...sourceRefs,
    sections: extractSections(tei),
  };
  const references = {
    schema_version: TEI_REFERENCES_SCHEMA_VERSION,
    output_prefix_ref: outputPrefixRef,
    ...sourceRefs,
    references: extractReferences(tei),
  };
  const provenance = {
    schema_version: TEI_PROVENANCE_SCHEMA_VERSION,
    output_prefix_ref: outputPrefixRef,
    ...sourceRefs,
    derived_refs: projectionRefsForPrefix(outputPrefixRef),
    extraction_method: "grobid_tei_structural_projection",
    limitations: [
      "Projection is structural and deterministic; it does not semantically verify PDF content.",
      "Page numbers and exact spans are included only when GROBID coordinate attributes are present.",
      "Text snippets are bounded derived views; raw TEI remains the authoritative parsed artifact.",
    ],
    counts: {
      section_count: sections.sections.length,
      reference_count: references.references.length,
      author_count: metadata.authors.length,
    },
  };
  return { metadata, sections, references, provenance };
}

async function checkGrobidService(baseUrl, signal) {
  try {
    const response = await fetch(`${baseUrl}/api/isalive`, { method: "GET", signal });
    return response.ok ? "alive" : `http_${response.status}`;
  } catch (error) {
    return `unreachable:${String(error?.message ?? error).slice(0, 160)}`;
  }
}

async function callGrobidFulltext({ baseUrl, pdfBytes, filename, includeCoordinates, signal }) {
  const form = new FormData();
  form.append("input", new Blob([pdfBytes], { type: "application/pdf" }), filename || "input.pdf");
  if (includeCoordinates) {
    form.append("teiCoordinates", "persName,figure,ref,biblStruct,formula,s");
  }
  const response = await fetch(`${baseUrl}/api/processFulltextDocument`, {
    method: "POST",
    body: form,
    signal,
  });
  const text = await response.text();
  if (!response.ok) {
    throw new Error(`GROBID processFulltextDocument failed with HTTP ${response.status}: ${text.slice(0, 300)}`);
  }
  return text;
}

function diagnosticsPayload(payload) {
  return {
    schema_version: GROBID_DIAGNOSTICS_SCHEMA_VERSION,
    ...payload,
  };
}

function projectionRefsForPrefix(outputPrefixRef) {
  return {
    metadata_ref: `${outputPrefixRef}/metadata.json`,
    sections_ref: `${outputPrefixRef}/sections.json`,
    references_ref: `${outputPrefixRef}/references.json`,
    provenance_ref: `${outputPrefixRef}/provenance.json`,
  };
}

function emptyProjectionRefs() {
  return {
    metadata_ref: "",
    sections_ref: "",
    references_ref: "",
    provenance_ref: "",
  };
}

function extractAuthors(xml) {
  return allBlocks(xml, "author").map((author, index) => ({
    author_id: `A${index + 1}`,
    full_name: clean([
      firstTagText(author, "forename"),
      firstTagText(author, "surname"),
    ].filter(Boolean).join(" ")) || textFromXml(author),
    affiliation: textFromXml(firstBlock(author, "affiliation")).slice(0, 500),
  })).filter((author) => author.full_name);
}

function extractIdentifiers(xml) {
  const identifiers = [];
  for (const match of xml.matchAll(/<(?:idno|ref)\b([^>]*)>([\s\S]*?)<\/(?:idno|ref)>/gi)) {
    const attrs = parseAttrs(match[1] ?? "");
    const type = clean(attrs.type || attrs["xml:id"] || attrs.target || "identifier").toLowerCase();
    const value = textFromXml(match[2] ?? "");
    if (value) identifiers.push({ type, value });
  }
  return dedupeRecords(identifiers, (item) => `${item.type}:${item.value.toLowerCase()}`).slice(0, 24);
}

function extractPublication(sourceDesc) {
  const date = firstTagText(sourceDesc, "date");
  const year = (date.match(/\b(19|20|21)\d{2}\b/) ?? [])[0] ?? "";
  return {
    venue: firstTagText(sourceDesc, "publisher") || firstTagText(sourceDesc, "meeting") || firstTagText(sourceDesc, "monogr"),
    date,
    year: year ? Number(year) : null,
  };
}

function extractSections(tei) {
  const textBody = firstBlock(tei, "text");
  const body = firstBlock(textBody, "body") || textBody;
  const divs = allBlocks(body, "div");
  const sectionBlocks = divs.length ? divs : allBlocks(body, "p");
  return sectionBlocks.slice(0, 80).map((block, index) => {
    const heading = firstTagText(block, "head");
    const paragraphs = allBlocks(block, "p").map(textFromXml).filter(Boolean);
    const text = paragraphs.length ? paragraphs.join("\n\n") : textFromXml(block);
    return {
      section_id: `SEC${index + 1}`,
      heading: heading || `Section ${index + 1}`,
      text_preview: text.slice(0, 4000),
      paragraph_count: paragraphs.length || (text ? 1 : 0),
      provenance: provenanceFromBlock(block),
    };
  }).filter((section) => section.text_preview || section.heading);
}

function extractReferences(tei) {
  const listBibl = firstBlock(tei, "listBibl") || tei;
  return allBlocks(listBibl, "biblStruct").slice(0, 300).map((block, index) => {
    const xmlId = (block.match(/\bxml:id=["']([^"']+)["']/i) ?? [])[1] ?? "";
    return {
      reference_id: xmlId || `BIB${index + 1}`,
      title: firstTagText(block, "title"),
      authors: extractAuthors(block).map((author) => author.full_name),
      date: firstTagText(block, "date"),
      identifiers: extractIdentifiers(block),
      raw_citation_preview: textFromXml(block).slice(0, 1500),
      provenance: provenanceFromBlock(block),
    };
  }).filter((reference) => reference.title || reference.raw_citation_preview);
}

function provenanceFromBlock(block) {
  const coords = [];
  for (const match of block.matchAll(/\bcoords=["']([^"']+)["']/gi)) {
    coords.push(match[1]);
  }
  const pages = [];
  for (const coord of coords) {
    for (const part of coord.split(";")) {
      const page = part.split(",")[0]?.trim();
      if (page && !pages.includes(page)) pages.push(page);
    }
  }
  return {
    page_refs: pages.slice(0, 20).map((page) => `page:${page}`),
    coordinate_count: coords.length,
  };
}

function firstBlock(xml, tag) {
  return allBlocks(xml, tag)[0] ?? "";
}

function allBlocks(xml, tag) {
  const escaped = tag.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const pattern = new RegExp(`<${escaped}\\b[^>]*>[\\s\\S]*?<\\/${escaped}>`, "gi");
  return typeof xml === "string" ? xml.match(pattern) ?? [] : [];
}

function firstTagText(xml, tag) {
  const block = firstBlock(xml, tag);
  return textFromXml(block);
}

function textFromXml(xml) {
  return xmlDecode(stripTags(stripXmlDeclarations(String(xml ?? ""))));
}

function stripXmlDeclarations(text) {
  return text.replace(/<\?xml[\s\S]*?\?>/gi, "").replace(/<!\[CDATA\[([\s\S]*?)\]\]>/g, "$1");
}

function stripTags(text) {
  return text.replace(/<[^>]+>/g, " ");
}

function xmlDecode(text) {
  return clean(
    text
      .replace(/&lt;/g, "<")
      .replace(/&gt;/g, ">")
      .replace(/&amp;/g, "&")
      .replace(/&quot;/g, '"')
      .replace(/&#39;/g, "'")
      .replace(/&#x([0-9a-f]+);/gi, (_match, hex) => String.fromCodePoint(Number.parseInt(hex, 16)))
      .replace(/&#(\d+);/g, (_match, number) => String.fromCodePoint(Number.parseInt(number, 10))),
  );
}

function parseAttrs(text) {
  const attrs = {};
  for (const match of String(text ?? "").matchAll(/([A-Za-z_:][-A-Za-z0-9_:.]*)=["']([^"']*)["']/g)) {
    attrs[match[1]] = xmlDecode(match[2]);
  }
  return attrs;
}

function clean(value) {
  return typeof value === "string" ? value.replace(/\s+/g, " ").trim() : "";
}

function dedupeRecords(records, keyFn) {
  const result = [];
  const seen = new Set();
  for (const record of records) {
    const key = keyFn(record);
    if (!key || seen.has(key)) continue;
    seen.add(key);
    result.push(record);
  }
  return result;
}

function requireInputPdfRef(value) {
  const ref = requireWorkspaceRef(value, "grobid_parse_pdf.pdf_ref");
  if (!ref.startsWith("inputs/")) {
    throw new Error("grobid_parse_pdf.pdf_ref must be under inputs/");
  }
  if (!ref.toLowerCase().endsWith(".pdf")) {
    throw new Error("grobid_parse_pdf.pdf_ref must point to a .pdf ref");
  }
  return ref;
}

function requireOutputPrefixRef(value) {
  const ref = requireWorkspaceRef(value, "grobid_parse_pdf.output_prefix_ref");
  if (!ref.startsWith("sources/seed_pdfs/")) {
    throw new Error("grobid_parse_pdf.output_prefix_ref must be under sources/seed_pdfs/");
  }
  return ref.replace(/\/+$/, "");
}

function requireWorkspaceRef(value, fieldName) {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${fieldName} is required`);
  }
  const ref = value.trim();
  if (ref.startsWith("/") || ref.includes("\\") || ref.split("/").some((part) => part === ".." || part === "")) {
    throw new Error(`${fieldName} must be a safe workspace ref`);
  }
  return ref;
}

function resolveWorkspaceRef(workspaceRoot, ref) {
  const root = resolve(workspaceRoot);
  const candidate = resolve(root, normalize(ref));
  if (candidate !== root && !candidate.startsWith(root + sep)) {
    throw new Error(`workspace ref escapes root: ${ref}`);
  }
  return candidate;
}

async function writeJsonRef(workspaceRoot, ref, payload) {
  await writeTextFile(resolveWorkspaceRef(workspaceRoot, ref), `${JSON.stringify(payload, null, 2)}\n`);
}

async function writeTextFile(path, text) {
  await mkdir(dirname(path), { recursive: true });
  await writeFile(path, text, "utf-8");
}

function normalizeBaseUrl(value) {
  if (typeof value !== "string" || !value.trim()) return "";
  return value.trim().replace(/\/+$/, "");
}
