import { StringEnum } from "@earendil-works/pi-ai";
import { Type } from "typebox";

const SEARCH_PROVIDERS = ["arxiv", "openalex", "semantic_scholar", "crossref", "github"];
const DEFAULT_PROVIDERS = ["openalex", "semantic_scholar", "arxiv", "crossref"];
const USER_AGENT = "MissionForge-PiAcademicSources/0.1";

export default function academicSourcesExtension(pi) {
  pi.registerTool({
    name: "academic_search",
    label: "Academic Search",
    description:
      "Search academic indexes and return normalized source records. This tool does not rank sources semantically.",
    promptSnippet: "Search arXiv, OpenAlex, Semantic Scholar, Crossref, and optional GitHub repositories.",
    promptGuidelines: [
      "Use academic_search to build or refresh the evidence set before making scholarly claims.",
      "Use academic_fetch on promising locators before relying on specific technical details.",
    ],
    parameters: Type.Object({
      query: Type.String({ description: "Search query written by the researcher." }),
      providers: Type.Optional(
        Type.Array(StringEnum(SEARCH_PROVIDERS), {
          description: "Providers to query. Defaults to openalex, semantic_scholar, arxiv, crossref.",
        }),
      ),
      since_year: Type.Optional(Type.Number({ description: "Optional lower bound publication year." })),
      limit: Type.Optional(Type.Number({ description: "Maximum records per provider, default 10, maximum 50." })),
    }),
    execute: async (_toolCallId, params, signal) => {
      const result = await academicSearch(params, signal);
      return jsonToolResult(result);
    },
  });

  pi.registerTool({
    name: "academic_fetch",
    label: "Academic Fetch",
    description: "Fetch metadata or content for a URL, DOI, arXiv ID, OpenAlex work, or GitHub repository locator.",
    promptSnippet: "Fetch source metadata/content for URLs, DOI/arXiv/OpenAlex locators, or GitHub repositories.",
    promptGuidelines: [
      "Use academic_fetch to verify titles, abstracts, publication metadata, repository state, or source text.",
    ],
    parameters: Type.Object({
      locator: Type.String({
        description: "URL, DOI, arXiv ID/URL, OpenAlex ID/URL, GitHub repo URL, or provider locator.",
      }),
      max_chars: Type.Optional(Type.Number({ description: "Maximum fetched text characters, default 12000." })),
    }),
    execute: async (_toolCallId, params, signal) => {
      const result = await academicFetch(params, signal);
      return jsonToolResult(result);
    },
  });

  pi.registerTool({
    name: "citation_lookup",
    label: "Citation Lookup",
    description: "Use OpenAlex to inspect references or citing works for a source locator.",
    promptSnippet: "Look up cited-by or reference neighborhoods through OpenAlex.",
    promptGuidelines: [
      "Use citation_lookup when you need historical roots, follow-up work, or citation-neighborhood coverage.",
    ],
    parameters: Type.Object({
      locator: Type.String({ description: "DOI, OpenAlex work ID/URL, paper URL, or source locator." }),
      direction: StringEnum(["cited_by", "references"], { description: "Citation direction." }),
      limit: Type.Optional(Type.Number({ description: "Maximum records, default 10, maximum 25." })),
    }),
    execute: async (_toolCallId, params, signal) => {
      const result = await citationLookup(params, signal);
      return jsonToolResult(result);
    },
  });

  pi.registerTool({
    name: "repo_search",
    label: "Repository Search",
    description: "Search GitHub repositories and return normalized repository evidence records.",
    promptSnippet: "Search GitHub repositories relevant to academic or engineering research.",
    promptGuidelines: [
      "Use repo_search to connect papers to implementations, benchmarks, and active engineering artifacts.",
    ],
    parameters: Type.Object({
      query: Type.String({ description: "GitHub repository search query." }),
      limit: Type.Optional(Type.Number({ description: "Maximum repositories, default 10, maximum 50." })),
    }),
    execute: async (_toolCallId, params, signal) => {
      const result = await repoSearch(params, signal);
      return jsonToolResult(result);
    },
  });
}

async function academicSearch(params, signal) {
  const query = clean(params.query);
  if (!query) throw new Error("academic_search.query is required");
  const providers = normalizeProviders(params.providers);
  const limit = boundedInt(params.limit, 10, 1, 50);
  const sinceYear = optionalYear(params.since_year);
  const providerResults = await Promise.all(
    providers.map(async (provider) => {
      try {
        const records = await searchProvider(provider, { query, limit, sinceYear, signal });
        return {
          provider,
          status: "completed",
          record_count: records.length,
          records,
        };
      } catch (error) {
        return {
          provider,
          status: "failed",
          error_type: error?.constructor?.name ?? "Error",
          message: String(error?.message ?? error).slice(0, 500),
          record_count: 0,
          records: [],
        };
      }
    }),
  );
  return {
    schema_version: "missionforge.pi_academic_sources.search_result.v1",
    query,
    providers,
    since_year: sinceYear,
    records: providerResults.flatMap((item) => item.records),
    provider_reports: providerResults.map(({ records: _records, ...report }) => report),
  };
}

async function academicFetch(params, signal) {
  const locator = clean(params.locator);
  if (!locator) throw new Error("academic_fetch.locator is required");
  const maxChars = boundedInt(params.max_chars, 12000, 1000, 50000);
  const normalized = normalizeLocator(locator);
  if (normalized.kind === "doi") {
    const url = `https://api.crossref.org/works/${encodeURIComponent(normalized.value)}`;
    const payload = await fetchJson(url, signal);
    return {
      schema_version: "missionforge.pi_academic_sources.fetch_result.v1",
      locator,
      locator_kind: "doi",
      record: normalizeCrossrefItem(payload?.message ?? {}),
      raw: truncate(JSON.stringify(payload, null, 2), maxChars),
    };
  }
  if (normalized.kind === "arxiv") {
    const url = `https://export.arxiv.org/api/query?id_list=${encodeURIComponent(normalized.value)}`;
    const text = await fetchText(url, signal);
    const records = parseArxivFeed(text).map((item) => normalizeArxivItem(item));
    return {
      schema_version: "missionforge.pi_academic_sources.fetch_result.v1",
      locator,
      locator_kind: "arxiv",
      record: records[0] ?? null,
      raw: truncate(text, maxChars),
    };
  }
  if (normalized.kind === "openalex") {
    const work = await fetchOpenAlexWork(normalized.value, signal);
    return {
      schema_version: "missionforge.pi_academic_sources.fetch_result.v1",
      locator,
      locator_kind: "openalex",
      record: normalizeOpenAlexItem(work),
      raw: truncate(JSON.stringify(work, null, 2), maxChars),
    };
  }
  if (normalized.kind === "github_repo") {
    const payload = await fetchJson(`https://api.github.com/repos/${normalized.value}`, signal);
    return {
      schema_version: "missionforge.pi_academic_sources.fetch_result.v1",
      locator,
      locator_kind: "github_repo",
      record: normalizeGitHubRepo(payload),
      raw: truncate(JSON.stringify(payload, null, 2), maxChars),
    };
  }
  const text = await fetchText(locator, signal);
  return {
    schema_version: "missionforge.pi_academic_sources.fetch_result.v1",
    locator,
    locator_kind: "url",
    content_type: "text",
    text: truncate(text, maxChars),
  };
}

async function citationLookup(params, signal) {
  const locator = clean(params.locator);
  if (!locator) throw new Error("citation_lookup.locator is required");
  const direction = params.direction === "references" ? "references" : "cited_by";
  const limit = boundedInt(params.limit, 10, 1, 25);
  const work = await fetchOpenAlexWorkByLocator(locator, signal);
  let records = [];
  if (direction === "cited_by") {
    const workId = openAlexShortId(work.id);
    const url = new URL("https://api.openalex.org/works");
    url.searchParams.set("filter", `cites:${workId}`);
    url.searchParams.set("per-page", String(limit));
    const payload = await fetchJson(url.toString(), signal);
    records = (payload.results ?? []).map((item) => normalizeOpenAlexItem(item));
  } else {
    const refs = Array.isArray(work.referenced_works) ? work.referenced_works.slice(0, limit) : [];
    const items = await Promise.all(
      refs.map(async (ref) => {
        try {
          return normalizeOpenAlexItem(await fetchOpenAlexWork(ref, signal));
        } catch {
          return {
            provider: "openalex",
            source_type: "academic_index_work",
            title: "",
            url: ref,
            locator: ref,
          };
        }
      }),
    );
    records = items;
  }
  return {
    schema_version: "missionforge.pi_academic_sources.citation_lookup_result.v1",
    locator,
    direction,
    seed: normalizeOpenAlexItem(work),
    records,
  };
}

async function repoSearch(params, signal) {
  const query = clean(params.query);
  if (!query) throw new Error("repo_search.query is required");
  const limit = boundedInt(params.limit, 10, 1, 50);
  const url = new URL("https://api.github.com/search/repositories");
  url.searchParams.set("q", query);
  url.searchParams.set("sort", "stars");
  url.searchParams.set("order", "desc");
  url.searchParams.set("per_page", String(limit));
  const payload = await fetchJson(url.toString(), signal);
  return {
    schema_version: "missionforge.pi_academic_sources.repo_search_result.v1",
    query,
    records: (payload.items ?? []).map((item) => normalizeGitHubRepo(item)),
    total_count: typeof payload.total_count === "number" ? payload.total_count : null,
  };
}

async function searchProvider(provider, options) {
  if (provider === "arxiv") return searchArxiv(options);
  if (provider === "openalex") return searchOpenAlex(options);
  if (provider === "semantic_scholar") return searchSemanticScholar(options);
  if (provider === "crossref") return searchCrossref(options);
  if (provider === "github") return (await repoSearch({ query: options.query, limit: options.limit }, options.signal)).records;
  throw new Error(`unsupported provider: ${provider}`);
}

async function searchArxiv({ query, limit, sinceYear, signal }) {
  const url = new URL("https://export.arxiv.org/api/query");
  url.searchParams.set("search_query", arxivQuery(query));
  url.searchParams.set("start", "0");
  url.searchParams.set("max_results", String(Math.min(limit, 50)));
  url.searchParams.set("sortBy", "relevance");
  url.searchParams.set("sortOrder", "descending");
  const text = await fetchText(url.toString(), signal);
  return parseArxivFeed(text)
    .map((item) => normalizeArxivItem(item))
    .filter((item) => !sinceYear || !item.year || item.year >= sinceYear);
}

async function searchOpenAlex({ query, limit, sinceYear, signal }) {
  const url = new URL("https://api.openalex.org/works");
  url.searchParams.set("search", query);
  url.searchParams.set("per-page", String(limit));
  if (sinceYear) url.searchParams.set("filter", `from_publication_date:${sinceYear}-01-01`);
  const payload = await fetchJson(url.toString(), signal);
  return (payload.results ?? []).map((item) => normalizeOpenAlexItem(item));
}

async function searchSemanticScholar({ query, limit, sinceYear, signal }) {
  const url = new URL("https://api.semanticscholar.org/graph/v1/paper/search");
  url.searchParams.set("query", query);
  url.searchParams.set("limit", String(Math.min(limit, 100)));
  url.searchParams.set("fields", "title,year,authors,venue,citationCount,abstract,url,externalIds,publicationDate");
  if (sinceYear) url.searchParams.set("year", `${sinceYear}-`);
  const payload = await fetchJson(url.toString(), signal);
  return (payload.data ?? []).map((item) => normalizeSemanticScholarItem(item));
}

async function searchCrossref({ query, limit, sinceYear, signal }) {
  const url = new URL("https://api.crossref.org/works");
  url.searchParams.set("query.bibliographic", query);
  url.searchParams.set("rows", String(Math.min(limit, 100)));
  url.searchParams.set("sort", "relevance");
  url.searchParams.set("order", "desc");
  if (sinceYear) url.searchParams.set("filter", `from-pub-date:${sinceYear}-01-01`);
  const payload = await fetchJson(url.toString(), signal);
  return (payload?.message?.items ?? []).map((item) => normalizeCrossrefItem(item));
}

async function fetchOpenAlexWorkByLocator(locator, signal) {
  const normalized = normalizeLocator(locator);
  if (normalized.kind === "openalex") return fetchOpenAlexWork(normalized.value, signal);
  if (normalized.kind === "doi") return fetchOpenAlexWork(`https://doi.org/${normalized.value}`, signal);
  if (normalized.kind === "url") return fetchOpenAlexWork(normalized.value, signal);
  throw new Error(`OpenAlex lookup needs DOI, OpenAlex ID, or URL locator: ${locator}`);
}

async function fetchOpenAlexWork(locator, signal) {
  const url = locator.startsWith("http")
    ? `https://api.openalex.org/works/${encodeURIComponent(locator)}`
    : `https://api.openalex.org/works/${encodeURIComponent(locator)}`;
  return fetchJson(url, signal);
}

function normalizeProviders(value) {
  const providers = Array.isArray(value) && value.length ? value : DEFAULT_PROVIDERS;
  return [...new Set(providers.map((item) => clean(item)).filter((item) => SEARCH_PROVIDERS.includes(item)))];
}

function normalizeOpenAlexItem(item) {
  const source = item?.primary_location?.source ?? {};
  return compactRecord({
    provider: "openalex",
    source_type: "academic_index_work",
    title: clean(item?.display_name),
    authors: Array.isArray(item?.authorships)
      ? item.authorships.map((author) => clean(author?.author?.display_name)).filter(Boolean).slice(0, 20)
      : [],
    year: numberOrNull(item?.publication_year),
    published: clean(item?.publication_date),
    venue: clean(source?.display_name),
    url: clean(item?.doi) || clean(item?.id) || clean(item?.primary_location?.landing_page_url),
    doi: stripDoi(clean(item?.doi)),
    abstract: abstractFromOpenAlex(item?.abstract_inverted_index),
    citation_count: numberOrNull(item?.cited_by_count),
    locator: clean(item?.id),
  });
}

function normalizeSemanticScholarItem(item) {
  const external = item?.externalIds ?? {};
  return compactRecord({
    provider: "semantic_scholar",
    source_type: "academic_index_work",
    title: clean(item?.title),
    authors: Array.isArray(item?.authors) ? item.authors.map((author) => clean(author?.name)).filter(Boolean) : [],
    year: numberOrNull(item?.year),
    published: clean(item?.publicationDate),
    venue: clean(item?.venue),
    url: clean(item?.url),
    doi: stripDoi(clean(external?.DOI)),
    abstract: clean(item?.abstract),
    citation_count: numberOrNull(item?.citationCount),
    locator: clean(item?.paperId) || clean(item?.url),
  });
}

function normalizeCrossrefItem(item) {
  return compactRecord({
    provider: "crossref",
    source_type: "academic_index_work",
    title: firstText(item?.title),
    authors: Array.isArray(item?.author)
      ? item.author
          .map((author) => [author.given, author.family].map(clean).filter(Boolean).join(" "))
          .filter(Boolean)
      : [],
    year: crossrefYear(item),
    published: crossrefDate(item),
    venue: firstText(item?.["container-title"]),
    url: clean(item?.URL),
    doi: stripDoi(clean(item?.DOI)),
    abstract: stripMarkup(clean(item?.abstract)),
    citation_count: numberOrNull(item?.["is-referenced-by-count"]),
    locator: clean(item?.DOI) || clean(item?.URL),
  });
}

function normalizeArxivItem(item) {
  const url = clean(item.id);
  return compactRecord({
    provider: "arxiv",
    source_type: "preprint_index_record",
    title: clean(item.title),
    authors: item.authors ?? [],
    year: item.published?.slice(0, 4).match(/^\d{4}$/) ? Number(item.published.slice(0, 4)) : null,
    published: clean(item.published),
    venue: "arXiv",
    url,
    doi: stripDoi(clean(item.doi)),
    abstract: clean(item.summary),
    citation_count: null,
    locator: url ? `arxiv:${url.split("/").pop()}` : "",
  });
}

function normalizeGitHubRepo(item) {
  return compactRecord({
    provider: "github",
    source_type: "software_repository",
    title: clean(item?.full_name) || clean(item?.name),
    authors: clean(item?.owner?.login) ? [clean(item.owner.login)] : [],
    year: item?.created_at?.slice(0, 4).match(/^\d{4}$/) ? Number(item.created_at.slice(0, 4)) : null,
    published: clean(item?.created_at),
    updated: clean(item?.updated_at),
    venue: "GitHub",
    url: clean(item?.html_url),
    repository: clean(item?.full_name),
    abstract: clean(item?.description),
    stars: numberOrNull(item?.stargazers_count),
    forks: numberOrNull(item?.forks_count),
    language: clean(item?.language),
    locator: clean(item?.full_name) || clean(item?.html_url),
  });
}

function parseArxivFeed(xml) {
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

function xmlTag(xml, tag) {
  const escaped = tag.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const match = xml.match(new RegExp(`<${escaped}\\b[^>]*>([\\s\\S]*?)<\\/${escaped}>`, "i"));
  return match ? xmlDecode(match[1]) : "";
}

function xmlDecode(text) {
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

function arxivQuery(query) {
  const terms = query.match(/[A-Za-z0-9_+-]+/g) ?? [];
  return terms.length ? terms.slice(0, 12).map((term) => `all:${term}`).join(" AND ") : `all:${query}`;
}

function normalizeLocator(locator) {
  const text = clean(locator);
  const lower = text.toLowerCase();
  if (lower.startsWith("doi:")) return { kind: "doi", value: stripDoi(text.slice(4)) };
  if (/^10\.\d{4,9}\//i.test(text)) return { kind: "doi", value: stripDoi(text) };
  if (lower.includes("doi.org/")) return { kind: "doi", value: stripDoi(text.split(/doi\.org\//i).pop()) };
  if (lower.startsWith("arxiv:")) return { kind: "arxiv", value: text.slice(6).replace(/^abs\//, "") };
  if (lower.includes("arxiv.org/abs/")) return { kind: "arxiv", value: text.split("/abs/").pop() };
  if (/^https:\/\/openalex\.org\/w/i.test(text)) return { kind: "openalex", value: text };
  if (/^w\d+$/i.test(text)) return { kind: "openalex", value: text.toUpperCase() };
  const github = text.match(/^https?:\/\/github\.com\/([^/\s]+\/[^/\s#?]+)/i);
  if (github) return { kind: "github_repo", value: github[1].replace(/\.git$/, "") };
  if (/^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/.test(text)) return { kind: "github_repo", value: text };
  return { kind: "url", value: text };
}

function openAlexShortId(id) {
  const text = clean(id);
  return text.includes("/") ? text.split("/").pop() : text;
}

async function fetchJson(url, signal) {
  const response = await fetchWithTimeout(url, signal, { accept: "application/json" });
  const text = await response.text();
  if (!response.ok) throw new Error(`HTTP ${response.status}: ${text.slice(0, 300)}`);
  return JSON.parse(text);
}

async function fetchText(url, signal) {
  const response = await fetchWithTimeout(url, signal, { accept: "text/plain, text/html, application/xml, */*" });
  const text = await response.text();
  if (!response.ok) throw new Error(`HTTP ${response.status}: ${text.slice(0, 300)}`);
  return text;
}

async function fetchWithTimeout(url, parentSignal, headers) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 20000);
  const abort = () => controller.abort();
  if (parentSignal) parentSignal.addEventListener("abort", abort, { once: true });
  try {
    return await fetch(url, {
      signal: controller.signal,
      headers: {
        "user-agent": USER_AGENT,
        accept: headers.accept,
      },
    });
  } finally {
    clearTimeout(timeout);
    if (parentSignal) parentSignal.removeEventListener("abort", abort);
  }
}

function jsonToolResult(payload) {
  const text = JSON.stringify(payload, null, 2);
  return {
    content: [{ type: "text", text }],
    details: payload,
  };
}

function compactRecord(record) {
  return Object.fromEntries(
    Object.entries(record).filter(([_key, value]) => {
      if (value === null || value === undefined) return false;
      if (typeof value === "string" && value.length === 0) return false;
      if (Array.isArray(value) && value.length === 0) return false;
      return true;
    }),
  );
}

function abstractFromOpenAlex(index) {
  if (!index || typeof index !== "object") return "";
  const positioned = [];
  for (const [word, positions] of Object.entries(index)) {
    if (!Array.isArray(positions)) continue;
    for (const position of positions) {
      if (Number.isInteger(position)) positioned.push([position, word]);
    }
  }
  return positioned.sort((left, right) => left[0] - right[0]).map((item) => item[1]).join(" ");
}

function crossrefYear(item) {
  const parts = item?.published?.["date-parts"]?.[0] ?? item?.["published-print"]?.["date-parts"]?.[0] ?? [];
  return Number.isInteger(parts[0]) ? parts[0] : null;
}

function crossrefDate(item) {
  const parts = item?.published?.["date-parts"]?.[0] ?? item?.["published-print"]?.["date-parts"]?.[0] ?? [];
  if (!Array.isArray(parts) || !parts.length) return "";
  return [parts[0], parts[1], parts[2]]
    .filter((part) => Number.isInteger(part))
    .map((part, index) => (index === 0 ? String(part) : String(part).padStart(2, "0")))
    .join("-");
}

function firstText(value) {
  if (Array.isArray(value)) return clean(value.find((item) => typeof item === "string") ?? "");
  return clean(value);
}

function stripDoi(value) {
  return clean(value).replace(/^https?:\/\/(dx\.)?doi\.org\//i, "").toLowerCase();
}

function stripMarkup(value) {
  return clean(value).replace(/<[^>]+>/g, " ");
}

function truncate(value, limit) {
  const text = clean(value);
  return text.length <= limit ? text : `${text.slice(0, limit - 1).trimEnd()}...`;
}

function clean(value) {
  return typeof value === "string" ? value.replace(/\s+/g, " ").trim() : "";
}

function numberOrNull(value) {
  return Number.isFinite(value) ? Number(value) : null;
}

function boundedInt(value, fallback, min, max) {
  const number = Number.isFinite(value) ? Math.trunc(value) : fallback;
  return Math.max(min, Math.min(max, number));
}

function optionalYear(value) {
  if (value === undefined || value === null) return null;
  const year = Math.trunc(Number(value));
  if (!Number.isFinite(year) || year < 1900 || year > 2200) throw new Error("year is out of range");
  return year;
}
