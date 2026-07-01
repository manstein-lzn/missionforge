export const USER_AGENT = "MissionForge-PiAcademicSources/0.2";

export async function fetchJson(url, signal, options = {}) {
  const response = await fetchWithTimeout(url, signal, {
    accept: options.accept ?? "application/json",
    headers: options.headers,
  });
  const text = await response.text();
  if (!response.ok) throw new Error(`HTTP ${response.status}: ${text.slice(0, 300)}`);
  return JSON.parse(text);
}

export async function fetchText(url, signal, options = {}) {
  const response = await fetchWithTimeout(url, signal, {
    accept: options.accept ?? "text/plain, text/html, application/xml, */*",
    headers: options.headers,
  });
  const text = await response.text();
  if (!response.ok) throw new Error(`HTTP ${response.status}: ${text.slice(0, 300)}`);
  return text;
}

async function fetchWithTimeout(url, parentSignal, options) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 20000);
  const abort = () => controller.abort();
  if (parentSignal) parentSignal.addEventListener("abort", abort, { once: true });
  try {
    return await fetch(url, {
      signal: controller.signal,
      headers: {
        "user-agent": USER_AGENT,
        accept: options.accept,
        ...(options.headers ?? {}),
      },
    });
  } finally {
    clearTimeout(timeout);
    if (parentSignal) parentSignal.removeEventListener("abort", abort);
  }
}

export function jsonToolResult(payload) {
  const text = JSON.stringify(payload, null, 2);
  return {
    content: [{ type: "text", text }],
    details: payload,
  };
}

export function compactRecord(record) {
  return Object.fromEntries(
    Object.entries(record).filter(([_key, value]) => {
      if (value === null || value === undefined) return false;
      if (typeof value === "string" && value.length === 0) return false;
      if (Array.isArray(value) && value.length === 0) return false;
      return true;
    }),
  );
}

export function clean(value) {
  return typeof value === "string" ? value.replace(/\s+/g, " ").trim() : "";
}

export function numberOrNull(value) {
  return Number.isFinite(value) ? Number(value) : null;
}

export function boundedInt(value, fallback, min, max) {
  const number = Number.isFinite(value) ? Math.trunc(value) : fallback;
  return Math.max(min, Math.min(max, number));
}

export function optionalYear(value) {
  if (value === undefined || value === null) return null;
  const year = Math.trunc(Number(value));
  if (!Number.isFinite(year) || year < 1900 || year > 2200) throw new Error("year is out of range");
  return year;
}

export function truncate(value, limit) {
  const text = clean(value);
  return text.length <= limit ? text : `${text.slice(0, limit - 1).trimEnd()}...`;
}

export function firstText(value) {
  if (Array.isArray(value)) return clean(value.find((item) => typeof item === "string") ?? "");
  return clean(value);
}

export function stripDoi(value) {
  return clean(value).replace(/^https?:\/\/(dx\.)?doi\.org\//i, "").toLowerCase();
}

export function stripMarkup(value) {
  return clean(value).replace(/<[^>]+>/g, " ");
}

export function normalizeLocator(locator) {
  const text = clean(locator);
  const lower = text.toLowerCase();
  if (lower.startsWith("doi:")) return { kind: "doi", value: stripDoi(text.slice(4)) };
  if (/^10\.\d{4,9}\//i.test(text)) return { kind: "doi", value: stripDoi(text) };
  if (lower.includes("doi.org/")) return { kind: "doi", value: stripDoi(text.split(/doi\.org\//i).pop()) };
  if (lower.startsWith("pmid:")) return { kind: "pmid", value: text.slice(5).replace(/\D/g, "") };
  if (/^pmc\d+$/i.test(text)) return { kind: "pmcid", value: text.toUpperCase() };
  if (lower.startsWith("arxiv:")) return { kind: "arxiv", value: text.slice(6).replace(/^abs\//, "") };
  if (lower.includes("arxiv.org/abs/")) return { kind: "arxiv", value: text.split("/abs/").pop() };
  if (/^https:\/\/openalex\.org\/w/i.test(text)) return { kind: "openalex", value: text };
  if (/^w\d+$/i.test(text)) return { kind: "openalex", value: text.toUpperCase() };
  const github = text.match(/^https?:\/\/github\.com\/([^/\s]+\/[^/\s#?]+)/i);
  if (github) return { kind: "github_repo", value: github[1].replace(/\.git$/, "") };
  if (/^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/.test(text)) return { kind: "github_repo", value: text };
  return { kind: "url", value: text };
}

export function arxivQuery(query) {
  const terms = query.match(/[A-Za-z0-9_+-]+/g) ?? [];
  return terms.length ? terms.slice(0, 12).map((term) => `all:${term}`).join(" AND ") : `all:${query}`;
}

export function parseArxivFeed(xml) {
  const entries = xml.match(/<entry\b[\s\S]*?<\/entry>/g) ?? [];
  return entries.map((entry) => ({
    id: xmlTag(entry, "id"),
    title: xmlTag(entry, "title"),
    published: xmlTag(entry, "published"),
    updated: xmlTag(entry, "updated"),
    summary: xmlTag(entry, "summary"),
    doi: xmlTag(entry, "arxiv:doi"),
    authors: [...entry.matchAll(/<author\b[\s\S]*?<\/author>/g)]
      .map((match) => xmlTag(match[0], "name"))
      .filter(Boolean),
  }));
}

export function xmlTag(xml, tag) {
  const escaped = tag.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const match = xml.match(new RegExp(`<${escaped}\\b[^>]*>([\\s\\S]*?)<\\/${escaped}>`, "i"));
  return match ? xmlDecode(match[1]) : "";
}

export function xmlDecode(text) {
  return clean(
    text
      .replace(/<!\[CDATA\[([\s\S]*?)\]\]>/g, "$1")
      .replace(/&lt;/g, "<")
      .replace(/&gt;/g, ">")
      .replace(/&amp;/g, "&")
      .replace(/&quot;/g, '"')
      .replace(/&#39;/g, "'"),
  );
}
