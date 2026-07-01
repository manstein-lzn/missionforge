import { StringEnum } from "@earendil-works/pi-ai";
import { Type } from "typebox";

import {
  academicFetch,
  academicProviderCapabilities,
  academicSearch,
  citationLookup,
  repoSearch,
  SEARCH_PROVIDER_IDS,
} from "./src/academic_sources.js";

const PROVIDER_POLICIES = ["default_no_key", "openalex_enhanced"];

export default function academicSourcesExtension(pi) {
  pi.registerTool({
    name: "academic_provider_capabilities",
    label: "Academic Provider Capabilities",
    description:
      "Report available academic source providers, default no-key providers, optional enhancements, and missing configuration.",
    promptSnippet:
      "Inspect academic provider capabilities before planning large searches. Default literature acquisition must work without provider keys.",
    promptGuidelines: [
      "Use academic_provider_capabilities before a broad academic literature run.",
      "Treat OpenAlex as an optional enhancement that requires configuration; missing OpenAlex is not a task failure.",
      "Record disabled optional providers and provider failures as source gaps rather than hiding them.",
    ],
    parameters: Type.Object({
      provider_policy: Type.Optional(
        StringEnum(PROVIDER_POLICIES, {
          description: "Provider policy. Defaults to default_no_key; openalex_enhanced enables OpenAlex only when configured.",
        }),
      ),
      providers: Type.Optional(
        Type.Array(Type.String(), {
          description: "Optional provider ids to inspect.",
        }),
      ),
    }),
    execute: async (_toolCallId, params) => {
      const result = academicProviderCapabilities(params);
      return jsonToolResult(result);
    },
  });

  pi.registerTool({
    name: "academic_search",
    label: "Academic Search",
    description:
      "Search academic indexes and return normalized source records. This tool does not rank sources semantically.",
    promptSnippet:
      "Search the default no-key scholarly sources first: Semantic Scholar, arXiv, Crossref, DBLP, and PubMed. OpenAlex is an optional configured enhancement.",
    promptGuidelines: [
      "Use academic_search to build or refresh the evidence set before making scholarly claims.",
      "Use academic_fetch on promising locators before relying on specific technical details.",
      "Do not assume OpenAlex is available unless provider capabilities say it is enabled.",
    ],
    parameters: Type.Object({
      query: Type.Optional(Type.String({ description: "Single search query written by the researcher." })),
      queries: Type.Optional(
        Type.Array(
          Type.Object({
            query: Type.String({ description: "Search query written by the researcher." }),
            query_id: Type.Optional(Type.String({ description: "Stable search-plan query id such as Q1." })),
            query_family_id: Type.Optional(Type.String({ description: "Stable search-plan query family id." })),
            providers: Type.Optional(Type.Array(StringEnum(SEARCH_PROVIDER_IDS))),
            since_year: Type.Optional(Type.Number()),
            limit: Type.Optional(Type.Number()),
          }),
          {
            description:
              "Optional batch of independent search-plan queries. The tool runs providers within each query and queries within the batch concurrently.",
          },
        ),
      ),
      providers: Type.Optional(
        Type.Array(StringEnum(SEARCH_PROVIDER_IDS), {
          description:
            "Providers to query. Defaults to no-key semantic_scholar, arxiv, crossref, dblp, and pubmed. openalex is used only when configured or explicitly requested.",
        }),
      ),
      provider_policy: Type.Optional(
        StringEnum(PROVIDER_POLICIES, {
          description: "Defaults to default_no_key. Use openalex_enhanced only when OpenAlex is configured.",
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
    description: "Fetch metadata or content for a URL, DOI, arXiv ID, PubMed ID, OpenAlex work, or GitHub repository locator.",
    promptSnippet: "Fetch source metadata/content for URLs, DOI/arXiv/PubMed/OpenAlex locators, or GitHub repositories.",
    promptGuidelines: [
      "Use academic_fetch to verify titles, abstracts, publication metadata, repository state, or source text.",
      "Use OpenAlex locators only when provider capabilities show OpenAlex is configured.",
    ],
    parameters: Type.Object({
      locator: Type.String({
        description: "URL, DOI, arXiv ID/URL, PubMed ID, OpenAlex ID/URL, GitHub repo URL, or provider locator.",
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
    description: "Inspect citation or reference neighborhoods through no-key providers, with OpenAlex enhancement when configured.",
    promptSnippet: "Look up cited-by or reference neighborhoods through Semantic Scholar/OpenCitations and optional OpenAlex.",
    promptGuidelines: [
      "Use citation_lookup when you need historical roots, follow-up work, or citation-neighborhood coverage.",
      "Treat citation neighborhoods as discovery evidence, not as final semantic support without fetching source metadata/content.",
    ],
    parameters: Type.Object({
      locator: Type.String({ description: "DOI, Semantic Scholar paper id/URL, OpenAlex work ID/URL, PubMed ID, or paper URL." }),
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

function jsonToolResult(payload) {
  const text = JSON.stringify(payload, null, 2);
  return {
    content: [{ type: "text", text }],
    details: payload,
  };
}
