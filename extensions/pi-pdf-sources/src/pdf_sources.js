import { createHash } from "node:crypto";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { basename, dirname, join, normalize, resolve, sep } from "node:path";

const GROBID_BASE_URL_ENV = "GROBID_BASE_URL";
const PDF_CAPABILITIES_SCHEMA_VERSION = "missionforge.pi_pdf_sources.provider_capabilities.v1";
const GROBID_PARSE_RESULT_SCHEMA_VERSION = "missionforge.pi_pdf_sources.grobid_parse_result.v1";
const GROBID_DIAGNOSTICS_SCHEMA_VERSION = "missionforge.pi_pdf_sources.grobid_diagnostics.v1";

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
    return {
      schema_version: GROBID_PARSE_RESULT_SCHEMA_VERSION,
      status: "unavailable",
      pdf_ref: pdfRef,
      output_prefix_ref: outputPrefixRef,
      manifest_ref: manifestRef,
      tei_ref: "",
      diagnostics_ref: diagnosticsRef,
    };
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
    const diagnostics = diagnosticsPayload({
      status: "completed",
      pdf_ref: pdfRef,
      output_prefix_ref: outputPrefixRef,
      reason_codes: [],
      message: "GROBID fulltext parsing completed.",
      tei_ref: teiRef,
      tei_char_count: tei.length,
    });
    await writeJsonRef(workspaceRoot, diagnosticsRef, diagnostics);
    return {
      schema_version: GROBID_PARSE_RESULT_SCHEMA_VERSION,
      status: "completed",
      pdf_ref: pdfRef,
      output_prefix_ref: outputPrefixRef,
      manifest_ref: manifestRef,
      tei_ref: teiRef,
      diagnostics_ref: diagnosticsRef,
    };
  } catch (error) {
    const diagnostics = diagnosticsPayload({
      status: "failed",
      pdf_ref: pdfRef,
      output_prefix_ref: outputPrefixRef,
      reason_codes: ["grobid_request_failed"],
      message: String(error?.message ?? error).slice(0, 500),
    });
    await writeJsonRef(workspaceRoot, diagnosticsRef, diagnostics);
    return {
      schema_version: GROBID_PARSE_RESULT_SCHEMA_VERSION,
      status: "failed",
      pdf_ref: pdfRef,
      output_prefix_ref: outputPrefixRef,
      manifest_ref: manifestRef,
      tei_ref: "",
      diagnostics_ref: diagnosticsRef,
    };
  }
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
  if (!ref.startsWith("inputs/seed_pdfs/")) {
    throw new Error("grobid_parse_pdf.output_prefix_ref must be under inputs/seed_pdfs/");
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
