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

export async function academicSearch(params, signal) {
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
