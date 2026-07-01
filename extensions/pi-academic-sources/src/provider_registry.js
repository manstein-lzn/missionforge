import {
  arxivQuery,
  clean,
  compactRecord,
  fetchJson,
  fetchText,
  firstText,
  normalizeLocator,
  numberOrNull,
  parseArxivFeed,
  stripDoi,
  stripMarkup,
} from "./utils.js";

export const DEFAULT_NO_KEY_PROVIDERS = [
  "semantic_scholar",
  "arxiv",
  "crossref",
  "dblp",
  "pubmed",
];

export const OPTIONAL_PROVIDER_IDS = [
  "openalex",
  "opencitations",
  "github",
];

export const SEARCH_PROVIDER_IDS = [
  ...DEFAULT_NO_KEY_PROVIDERS,
  "openalex",
  "github",
];

export const ALL_PROVIDER_IDS = [
  ...DEFAULT_NO_KEY_PROVIDERS,
  ...OPTIONAL_PROVIDER_IDS,
];

const OPENALEX_API_KEY_ENV = "OPENALEX_API_KEY";
const SEMANTIC_SCHOLAR_API_KEY_ENV = "SEMANTIC_SCHOLAR_API_KEY";

export function academicProviderCapabilities(params = {}) {
  const policy = providerPolicy(params.provider_policy);
  const requestedProviders = normalizeProviderList(params.providers, ALL_PROVIDER_IDS);
  const providers = ALL_PROVIDER_IDS.map((providerId) => providerCapability(providerId, policy, requestedProviders));
  return {
    schema_version: "missionforge.pi_academic_sources.provider_capabilities.v1",
    provider_policy: policy,
    default_no_key_provider_ids: DEFAULT_NO_KEY_PROVIDERS,
    optional_provider_ids: OPTIONAL_PROVIDER_IDS,
    search_provider_ids: SEARCH_PROVIDER_IDS,
    providers,
    default_search_provider_ids: defaultProviderIds(policy),
    diagnostics: providerDiagnostics(providers),
  };
}

export function defaultProviderIds(policy = "default_no_key") {
  const providers = [...DEFAULT_NO_KEY_PROVIDERS];
  if (policy === "openalex_enhanced" && hasOpenAlexKey()) providers.push("openalex");
  return providers;
}

export function normalizeProviders(value, policy = "default_no_key") {
  const providers = normalizeProviderList(value, SEARCH_PROVIDER_IDS);
  return providers.length ? providers : defaultProviderIds(policy);
}

export async function searchProvider(provider, options) {
  if (provider === "arxiv") return searchArxiv(options);
  if (provider === "openalex") return searchOpenAlex(options);
  if (provider === "semantic_scholar") return searchSemanticScholar(options);
  if (provider === "crossref") return searchCrossref(options);
  if (provider === "dblp") return searchDblp(options);
  if (provider === "pubmed") return searchPubMed(options);
  if (provider === "opencitations") return [];
  if (provider === "github") return searchGitHubRepos(options);
  throw new Error(`unsupported provider: ${provider}`);
}

export async function fetchByLocator(locator, maxChars, signal) {
  const normalized = normalizeLocator(locator);
  if (normalized.kind === "doi") {
    const url = `https://api.crossref.org/works/${encodeURIComponent(normalized.value)}`;
    const payload = await fetchJson(url, signal);
    return {
      schema_version: "missionforge.pi_academic_sources.fetch_result.v1",
      locator,
      locator_kind: "doi",
      record: normalizeCrossrefItem(payload?.message ?? {}),
      raw: truncateJson(payload, maxChars),
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
      raw: truncateJson(work, maxChars),
    };
  }
  if (normalized.kind === "pmid" || normalized.kind === "pmcid") {
    const record = await fetchPubMedRecord(normalized.value, signal);
    return {
      schema_version: "missionforge.pi_academic_sources.fetch_result.v1",
      locator,
      locator_kind: normalized.kind,
      record,
      raw: JSON.stringify(record, null, 2),
    };
  }
  if (normalized.kind === "github_repo") {
    const payload = await fetchJson(`https://api.github.com/repos/${normalized.value}`, signal);
    return {
      schema_version: "missionforge.pi_academic_sources.fetch_result.v1",
      locator,
      locator_kind: "github_repo",
      record: normalizeGitHubRepo(payload),
      raw: truncateJson(payload, maxChars),
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

export async function lookupCitations(params, signal) {
  const locator = clean(params.locator);
  const direction = params.direction === "references" ? "references" : "cited_by";
  const limit = Math.max(1, Math.min(25, Number.isFinite(params.limit) ? Math.trunc(params.limit) : 10));
  const providers = citationProvidersFor(locator);
  const providerResults = await Promise.all(
    providers.map(async (provider) => {
      try {
        const records = await citationLookupProvider(provider, { locator, direction, limit, signal });
        return { provider, status: "completed", record_count: records.length, records };
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
    schema_version: "missionforge.pi_academic_sources.citation_lookup_result.v2",
    locator,
    direction,
    provider_reports: providerResults.map(({ records: _records, ...report }) => report),
    records: providerResults.flatMap((item) => item.records),
  };
}

export async function searchGitHubRepos({ query, limit, signal }) {
  return (await searchGitHubRepoResult({ query, limit, signal })).records;
}

export async function searchGitHubRepoResult({ query, limit, signal }) {
  const url = new URL("https://api.github.com/search/repositories");
  url.searchParams.set("q", query);
  url.searchParams.set("sort", "stars");
  url.searchParams.set("order", "desc");
  url.searchParams.set("per_page", String(limit));
  const payload = await fetchJson(url.toString(), signal);
  return {
    records: (payload.items ?? []).map((item) => normalizeGitHubRepo(item)),
    total_count: typeof payload.total_count === "number" ? payload.total_count : null,
  };
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
  requireOpenAlexKey();
  const url = new URL("https://api.openalex.org/works");
  url.searchParams.set("search", query);
  url.searchParams.set("per-page", String(limit));
  if (sinceYear) url.searchParams.set("filter", `from_publication_date:${sinceYear}-01-01`);
  attachOpenAlexAuth(url);
  const payload = await fetchJson(url.toString(), signal);
  return (payload.results ?? []).map((item) => normalizeOpenAlexItem(item));
}

async function searchSemanticScholar({ query, limit, sinceYear, signal }) {
  const url = new URL("https://api.semanticscholar.org/graph/v1/paper/search");
  url.searchParams.set("query", query);
  url.searchParams.set("limit", String(Math.min(limit, 100)));
  url.searchParams.set("fields", "title,year,authors,venue,citationCount,abstract,url,externalIds,publicationDate");
  if (sinceYear) url.searchParams.set("year", `${sinceYear}-`);
  const headers = hasSemanticScholarKey() ? { "x-api-key": process.env[SEMANTIC_SCHOLAR_API_KEY_ENV] } : {};
  const payload = await fetchJson(url.toString(), signal, { headers });
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

async function searchDblp({ query, limit, sinceYear, signal }) {
  const url = new URL("https://dblp.org/search/publ/api");
  url.searchParams.set("q", query);
  url.searchParams.set("format", "json");
  url.searchParams.set("h", String(Math.min(limit, 100)));
  const payload = await fetchJson(url.toString(), signal);
  const hits = payload?.result?.hits?.hit ?? [];
  return hits.map((hit) => normalizeDblpItem(hit?.info ?? {})).filter((item) => !sinceYear || !item.year || item.year >= sinceYear);
}

async function searchPubMed({ query, limit, sinceYear, signal }) {
  const searchUrl = new URL("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi");
  searchUrl.searchParams.set("db", "pubmed");
  searchUrl.searchParams.set("term", sinceYear ? `${query} AND ${sinceYear}:3000[pdat]` : query);
  searchUrl.searchParams.set("retmode", "json");
  searchUrl.searchParams.set("retmax", String(Math.min(limit, 100)));
  const searchPayload = await fetchJson(searchUrl.toString(), signal);
  const ids = searchPayload?.esearchresult?.idlist ?? [];
  if (!ids.length) return [];
  const summaryUrl = new URL("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi");
  summaryUrl.searchParams.set("db", "pubmed");
  summaryUrl.searchParams.set("id", ids.join(","));
  summaryUrl.searchParams.set("retmode", "json");
  const summaryPayload = await fetchJson(summaryUrl.toString(), signal);
  return ids
    .map((id) => normalizePubMedSummary(summaryPayload?.result?.[id] ?? {}))
    .filter((item) => !sinceYear || !item.year || item.year >= sinceYear);
}

async function fetchPubMedRecord(id, signal) {
  const summaryUrl = new URL("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi");
  summaryUrl.searchParams.set("db", "pubmed");
  summaryUrl.searchParams.set("id", id.replace(/^PMC/i, ""));
  summaryUrl.searchParams.set("retmode", "json");
  const payload = await fetchJson(summaryUrl.toString(), signal);
  const record = payload?.result?.[id] ?? Object.values(payload?.result ?? {}).find((item) => item?.uid);
  return normalizePubMedSummary(record ?? {});
}

async function citationLookupProvider(provider, options) {
  if (provider === "openalex") return lookupOpenAlexCitations(options);
  if (provider === "opencitations") return lookupOpenCitations(options);
  if (provider === "semantic_scholar") return lookupSemanticScholarCitations(options);
  return [];
}

async function lookupOpenAlexCitations({ locator, direction, limit, signal }) {
  if (!hasOpenAlexKey()) return [];
  const work = await fetchOpenAlexWorkByLocator(locator, signal);
  if (direction === "cited_by") {
    const workId = openAlexShortId(work.id);
    const url = new URL("https://api.openalex.org/works");
    url.searchParams.set("filter", `cites:${workId}`);
    url.searchParams.set("per-page", String(limit));
    attachOpenAlexAuth(url);
    const payload = await fetchJson(url.toString(), signal);
    return (payload.results ?? []).map((item) => normalizeOpenAlexItem(item));
  }
  const refs = Array.isArray(work.referenced_works) ? work.referenced_works.slice(0, limit) : [];
  return Promise.all(
    refs.map(async (ref) => {
      try {
        return normalizeOpenAlexItem(await fetchOpenAlexWork(ref, signal));
      } catch {
        return compactRecord({
          provider: "openalex",
          source_type: "academic_index_work",
          title: "",
          url: ref,
          locator: ref,
        });
      }
    }),
  );
}

async function lookupOpenCitations({ locator, direction, limit, signal }) {
  const normalized = normalizeLocator(locator);
  if (normalized.kind !== "doi") return [];
  const endpoint = direction === "references" ? "references" : "citations";
  const url = `https://opencitations.net/index/api/v2/${endpoint}/doi:${encodeURIComponent(normalized.value)}`;
  const payload = await fetchJson(url, signal);
  return (Array.isArray(payload) ? payload : []).slice(0, limit).map((item) => normalizeOpenCitationsItem(item, direction));
}

async function lookupSemanticScholarCitations({ locator, direction, limit, signal }) {
  const normalized = normalizeLocator(locator);
  const paperId = normalized.kind === "doi" ? `DOI:${normalized.value}` : clean(locator);
  const endpoint = direction === "references" ? "references" : "citations";
  const url = new URL(`https://api.semanticscholar.org/graph/v1/paper/${encodeURIComponent(paperId)}/${endpoint}`);
  url.searchParams.set("limit", String(limit));
  url.searchParams.set("fields", "title,year,authors,venue,citationCount,abstract,url,externalIds,publicationDate");
  const headers = hasSemanticScholarKey() ? { "x-api-key": process.env[SEMANTIC_SCHOLAR_API_KEY_ENV] } : {};
  const payload = await fetchJson(url.toString(), signal, { headers });
  return (payload.data ?? []).map((item) => normalizeSemanticScholarItem(item.citedPaper ?? item.citingPaper ?? item.paper ?? item));
}

function citationProvidersFor(locator) {
  const normalized = normalizeLocator(locator);
  const providers = ["semantic_scholar"];
  if (normalized.kind === "doi") providers.push("opencitations");
  if (hasOpenAlexKey()) providers.push("openalex");
  return providers;
}

function providerPolicy(value) {
  return value === "openalex_enhanced" ? "openalex_enhanced" : "default_no_key";
}

function normalizeProviderList(value, allowed) {
  if (!Array.isArray(value)) return [];
  return [...new Set(value.map((item) => clean(item)).filter((item) => allowed.includes(item)))];
}

function providerCapability(providerId, policy, requestedProviders) {
  const requested = requestedProviders.includes(providerId);
  const isDefault = DEFAULT_NO_KEY_PROVIDERS.includes(providerId);
  const enabledByDefault = defaultProviderIds(policy).includes(providerId);
  const available = providerAvailable(providerId);
  const requiresSecret = providerId === "openalex";
  const optional = OPTIONAL_PROVIDER_IDS.includes(providerId) || requiresSecret;
  return {
    provider: providerId,
    default_no_key: isDefault,
    optional,
    requested,
    enabled_by_default: enabledByDefault,
    available,
    requires_secret: requiresSecret,
    missing_secret: requiresSecret && !hasOpenAlexKey(),
    capabilities: providerCapabilities(providerId),
    status: available ? (enabledByDefault || requested ? "enabled" : "available_optional") : "disabled",
    reason: providerUnavailableReason(providerId),
  };
}

function providerAvailable(providerId) {
  if (providerId === "openalex") return hasOpenAlexKey();
  return true;
}

function providerUnavailableReason(providerId) {
  if (providerId === "openalex" && !hasOpenAlexKey()) return `missing ${OPENALEX_API_KEY_ENV}`;
  return "";
}

function providerCapabilities(providerId) {
  if (providerId === "github") return ["repository_search", "fetch"];
  if (providerId === "opencitations") return ["citation_lookup"];
  if (providerId === "openalex") return ["search", "fetch", "citation_lookup", "oa_locator_enrichment"];
  if (providerId === "pubmed") return ["search", "fetch"];
  return ["search", "fetch"];
}

function providerDiagnostics(providers) {
  return providers
    .filter((provider) => provider.missing_secret || provider.reason)
    .map((provider) => ({
      provider: provider.provider,
      severity: provider.default_no_key ? "warning" : "info",
      code: provider.missing_secret ? "optional_provider_secret_missing" : "provider_unavailable",
      message: provider.reason || `${provider.provider} unavailable`,
    }));
}

function hasOpenAlexKey() {
  return Boolean(clean(process.env[OPENALEX_API_KEY_ENV]));
}

function requireOpenAlexKey() {
  if (!hasOpenAlexKey()) throw new Error(`${OPENALEX_API_KEY_ENV} is required for the OpenAlex enhancement provider`);
}

function hasSemanticScholarKey() {
  return Boolean(clean(process.env[SEMANTIC_SCHOLAR_API_KEY_ENV]));
}

function attachOpenAlexAuth(url) {
  const key = clean(process.env[OPENALEX_API_KEY_ENV]);
  if (key) url.searchParams.set("api_key", key);
}

async function fetchOpenAlexWorkByLocator(locator, signal) {
  requireOpenAlexKey();
  const normalized = normalizeLocator(locator);
  if (normalized.kind === "openalex") return fetchOpenAlexWork(normalized.value, signal);
  if (normalized.kind === "doi") return fetchOpenAlexWork(`https://doi.org/${normalized.value}`, signal);
  if (normalized.kind === "url") return fetchOpenAlexWork(normalized.value, signal);
  throw new Error(`OpenAlex lookup needs DOI, OpenAlex ID, or URL locator: ${locator}`);
}

async function fetchOpenAlexWork(locator, signal) {
  requireOpenAlexKey();
  const url = new URL(`https://api.openalex.org/works/${encodeURIComponent(locator)}`);
  attachOpenAlexAuth(url);
  return fetchJson(url.toString(), signal);
}

function normalizeOpenAlexItem(item) {
  const source = item?.primary_location?.source ?? {};
  const bestLocation = item?.best_oa_location ?? item?.primary_location ?? {};
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
    url: clean(item?.doi) || clean(item?.id) || clean(bestLocation?.landing_page_url),
    doi: stripDoi(clean(item?.doi)),
    abstract: abstractFromOpenAlex(item?.abstract_inverted_index),
    citation_count: numberOrNull(item?.cited_by_count),
    open_access_url: clean(item?.open_access?.oa_url) || clean(bestLocation?.pdf_url),
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
    arxiv_id: clean(external?.ArXiv),
    pubmed_id: clean(external?.PubMed),
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
  const arxivId = url ? url.split("/").pop() : "";
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
    arxiv_id: arxivId,
    abstract: clean(item.summary),
    citation_count: null,
    locator: arxivId ? `arxiv:${arxivId}` : "",
  });
}

function normalizeDblpItem(item) {
  const authors = Array.isArray(item?.authors?.author)
    ? item.authors.author.map((author) => (typeof author === "string" ? author : author?.text)).map(clean).filter(Boolean)
    : [item?.authors?.author?.text ?? item?.authors?.author].map(clean).filter(Boolean);
  return compactRecord({
    provider: "dblp",
    source_type: "academic_index_work",
    title: clean(item?.title),
    authors,
    year: numberOrNull(Number(item?.year)),
    venue: clean(item?.venue),
    url: clean(item?.url),
    doi: stripDoi(clean(item?.doi)),
    locator: clean(item?.key) || clean(item?.url),
  });
}

function normalizePubMedSummary(item) {
  const articleIds = Array.isArray(item?.articleids) ? item.articleids : [];
  const doi = articleIds.find((entry) => entry.idtype === "doi")?.value ?? "";
  const pmc = articleIds.find((entry) => entry.idtype === "pmc")?.value ?? "";
  const authors = Array.isArray(item?.authors) ? item.authors.map((author) => clean(author?.name)).filter(Boolean) : [];
  return compactRecord({
    provider: "pubmed",
    source_type: "biomedical_index_work",
    title: clean(item?.title),
    authors,
    year: pubmedYear(item),
    published: clean(item?.pubdate) || clean(item?.epubdate),
    venue: clean(item?.fulljournalname) || clean(item?.source),
    url: item?.uid ? `https://pubmed.ncbi.nlm.nih.gov/${item.uid}/` : "",
    doi: stripDoi(clean(doi)),
    pubmed_id: clean(item?.uid),
    pmc_id: clean(pmc),
    locator: item?.uid ? `pmid:${item.uid}` : "",
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

function normalizeOpenCitationsItem(item, direction) {
  const doi = direction === "references" ? item?.cited : item?.citing;
  return compactRecord({
    provider: "opencitations",
    source_type: "citation_edge",
    title: "",
    doi: stripDoi(clean(doi)),
    locator: clean(doi) ? `doi:${stripDoi(clean(doi))}` : "",
    evidence_note: `OpenCitations ${direction} edge`,
  });
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

function pubmedYear(item) {
  const text = clean(item?.pubdate) || clean(item?.epubdate);
  const match = text.match(/\b(19|20|21)\d{2}\b/);
  return match ? Number(match[0]) : null;
}

function openAlexShortId(id) {
  const text = clean(id);
  return text.includes("/") ? text.split("/").pop() : text;
}

function truncateJson(value, maxChars) {
  return truncate(JSON.stringify(value, null, 2), maxChars);
}

function truncate(value, limit) {
  const text = clean(value);
  return text.length <= limit ? text : `${text.slice(0, limit - 1).trimEnd()}...`;
}
