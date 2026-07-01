import {
  academicProviderCapabilities,
  normalizeProviders,
  searchGitHubRepoResult,
  searchProvider,
  fetchByLocator,
  lookupCitations,
  SEARCH_PROVIDER_IDS,
} from "./provider_registry.js";
import { boundedInt, clean, optionalYear } from "./utils.js";

export { academicProviderCapabilities, SEARCH_PROVIDER_IDS };

export async function academicSearch(params = {}, signal) {
  const queries = normalizeSearchQueries(params);
  if (queries.length > 1 || Array.isArray(params.queries)) {
    return academicSearchBatch(params, queries, signal);
  }
  return academicSearchSingle({ ...params, query: queries[0].query }, signal);
}

async function academicSearchBatch(params = {}, queries, signal) {
  const providerPolicy = params.provider_policy === "openalex_enhanced" ? "openalex_enhanced" : "default_no_key";
  const results = await Promise.all(
    queries.map((item, index) =>
      academicSearchSingle(
        {
          ...params,
          query: item.query,
          providers: item.providers ?? params.providers,
          since_year: item.since_year ?? params.since_year,
          limit: item.limit ?? params.limit,
        },
        signal,
      ).then((result) => ({
        query_id: clean(item.query_id) || `Q${index + 1}`,
        query_family_id: clean(item.query_family_id),
        ...result,
      })),
    ),
  );
  const records = results.flatMap((result) =>
    result.records.map((record) => ({
      ...record,
      query: result.query,
      query_id: result.query_id,
      query_family_id: result.query_family_id,
    })),
  );
  const providerReports = results.flatMap((result) =>
    result.provider_reports.map((report) => ({
      ...report,
      query: result.query,
      query_id: result.query_id,
      query_family_id: result.query_family_id,
    })),
  );
  return {
    schema_version: "missionforge.pi_academic_sources.search_batch_result.v1",
    provider_policy: providerPolicy,
    query_count: results.length,
    queries: results.map(({ records: _records, provider_reports: _reports, ...result }) => result),
    records,
    provider_reports: providerReports,
  };
}

async function academicSearchSingle(params = {}, signal) {
  const query = clean(params.query);
  if (!query) throw new Error("academic_search.query is required");
  const providerPolicy = params.provider_policy === "openalex_enhanced" ? "openalex_enhanced" : "default_no_key";
  const providers = normalizeProviders(params.providers, providerPolicy);
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
    schema_version: "missionforge.pi_academic_sources.search_result.v2",
    query,
    provider_policy: providerPolicy,
    providers,
    since_year: sinceYear,
    records: providerResults.flatMap((item) => item.records),
    provider_reports: providerResults.map(({ records: _records, ...report }) => report),
  };
}

function normalizeSearchQueries(params = {}) {
  const queryItems = Array.isArray(params.queries) ? params.queries : [];
  if (queryItems.length) {
    return queryItems.map((item, index) => {
      const query = clean(item?.query);
      if (!query) throw new Error(`academic_search.queries[${index}].query is required`);
      return {
        query,
        query_id: clean(item.query_id),
        query_family_id: clean(item.query_family_id),
        providers: item.providers,
        since_year: item.since_year,
        limit: item.limit,
      };
    });
  }
  const query = clean(params.query);
  if (!query) throw new Error("academic_search.query or academic_search.queries is required");
  return [{ query }];
}

export async function academicFetch(params, signal) {
  const locator = clean(params.locator);
  if (!locator) throw new Error("academic_fetch.locator is required");
  const maxChars = boundedInt(params.max_chars, 12000, 1000, 50000);
  return fetchByLocator(locator, maxChars, signal);
}

export async function citationLookup(params, signal) {
  const locator = clean(params.locator);
  if (!locator) throw new Error("citation_lookup.locator is required");
  return lookupCitations(params, signal);
}

export async function repoSearch(params, signal) {
  const query = clean(params.query);
  if (!query) throw new Error("repo_search.query is required");
  const limit = boundedInt(params.limit, 10, 1, 50);
  const result = await searchGitHubRepoResult({ query, limit, signal });
  return {
    schema_version: "missionforge.pi_academic_sources.repo_search_result.v1",
    query,
    records: result.records,
    total_count: result.total_count,
  };
}
