import assert from "node:assert/strict";
import test from "node:test";

import {
  academicProviderCapabilities,
  academicSearch,
} from "../src/academic_sources.js";

test("default provider policy does not include OpenAlex", () => {
  const previousKey = process.env.OPENALEX_API_KEY;
  delete process.env.OPENALEX_API_KEY;
  try {
    const capabilities = academicProviderCapabilities();
    assert.equal(capabilities.provider_policy, "default_no_key");
    assert.deepEqual(capabilities.default_search_provider_ids, [
      "semantic_scholar",
      "arxiv",
      "crossref",
      "dblp",
      "pubmed",
    ]);
    assert.ok(!capabilities.default_search_provider_ids.includes("openalex"));
    const openAlex = capabilities.providers.find((provider) => provider.provider === "openalex");
    assert.equal(openAlex.status, "disabled");
    assert.equal(openAlex.missing_secret, true);
  } finally {
    restoreOpenAlexKey(previousKey);
  }
});

test("OpenAlex enhanced policy includes OpenAlex only when configured", () => {
  const previousKey = process.env.OPENALEX_API_KEY;
  process.env.OPENALEX_API_KEY = "test-key";
  try {
    const capabilities = academicProviderCapabilities({ provider_policy: "openalex_enhanced" });
    assert.equal(capabilities.provider_policy, "openalex_enhanced");
    assert.ok(capabilities.default_search_provider_ids.includes("openalex"));
    const openAlex = capabilities.providers.find((provider) => provider.provider === "openalex");
    assert.equal(openAlex.status, "enabled");
    assert.equal(openAlex.missing_secret, false);
  } finally {
    restoreOpenAlexKey(previousKey);
  }
});

test("OpenAlex enhanced policy still no-keys cleanly when missing key", () => {
  const previousKey = process.env.OPENALEX_API_KEY;
  delete process.env.OPENALEX_API_KEY;
  try {
    const capabilities = academicProviderCapabilities({ provider_policy: "openalex_enhanced" });
    assert.equal(capabilities.provider_policy, "openalex_enhanced");
    assert.ok(!capabilities.default_search_provider_ids.includes("openalex"));
    const diagnostic = capabilities.diagnostics.find((item) => item.provider === "openalex");
    assert.equal(diagnostic.code, "optional_provider_secret_missing");
  } finally {
    restoreOpenAlexKey(previousKey);
  }
});

test("academic_search defaults to no-key provider ids", async () => {
  const previousKey = process.env.OPENALEX_API_KEY;
  delete process.env.OPENALEX_API_KEY;
  const previousFetch = globalThis.fetch;
  const seenUrls = [];
  globalThis.fetch = async (url) => {
    seenUrls.push(String(url));
    return new Response(fakeProviderBody(String(url)), { status: 200 });
  };
  try {
    const result = await academicSearch({ query: "mlir fpga", limit: 1 }, undefined);
    assert.deepEqual(result.providers, ["semantic_scholar", "arxiv", "crossref", "dblp", "pubmed"]);
    assert.equal(result.provider_policy, "default_no_key");
    assert.ok(seenUrls.some((url) => url.includes("api.semanticscholar.org")));
    assert.ok(seenUrls.some((url) => url.includes("export.arxiv.org")));
    assert.ok(seenUrls.some((url) => url.includes("api.crossref.org")));
    assert.ok(seenUrls.some((url) => url.includes("dblp.org")));
    assert.ok(seenUrls.some((url) => url.includes("eutils.ncbi.nlm.nih.gov")));
    assert.ok(!seenUrls.some((url) => url.includes("api.openalex.org")));
  } finally {
    globalThis.fetch = previousFetch;
    restoreOpenAlexKey(previousKey);
  }
});

test("explicit OpenAlex search fails closed when key is absent", async () => {
  const previousKey = process.env.OPENALEX_API_KEY;
  delete process.env.OPENALEX_API_KEY;
  try {
    const result = await academicSearch({ query: "mlir fpga", providers: ["openalex"], limit: 1 }, undefined);
    assert.deepEqual(result.providers, ["openalex"]);
    assert.equal(result.records.length, 0);
    assert.equal(result.provider_reports[0].provider, "openalex");
    assert.equal(result.provider_reports[0].status, "failed");
    assert.match(result.provider_reports[0].message, /OPENALEX_API_KEY/);
  } finally {
    restoreOpenAlexKey(previousKey);
  }
});

function fakeProviderBody(url) {
  if (url.includes("api.semanticscholar.org")) return JSON.stringify({ data: [] });
  if (url.includes("export.arxiv.org")) return "<?xml version=\"1.0\"?><feed></feed>";
  if (url.includes("api.crossref.org")) return JSON.stringify({ message: { items: [] } });
  if (url.includes("dblp.org")) return JSON.stringify({ result: { hits: { hit: [] } } });
  if (url.includes("esearch.fcgi")) return JSON.stringify({ esearchresult: { idlist: [] } });
  return "{}";
}

function restoreOpenAlexKey(value) {
  if (value === undefined) {
    delete process.env.OPENALEX_API_KEY;
  } else {
    process.env.OPENALEX_API_KEY = value;
  }
}
