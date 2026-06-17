import assert from "node:assert/strict";
import test from "node:test";

import { resolveProviderConfig } from "../dist/provider-config.js";

test("resolveProviderConfig creates a live OpenAI Responses model", () => {
  const config = resolveProviderConfig({
    MISSIONFORGE_PI_AGENT_PROVIDER: "live",
    MISSIONFORGE_PI_AGENT_MODEL: "gpt-5.5",
    MISSIONFORGE_PI_AGENT_BASE_URL: "https://example.test/v1",
    MISSIONFORGE_PI_AGENT_API_KEY: "sk-live-secret",
    MISSIONFORGE_PI_AGENT_REASONING: "low",
    MISSIONFORGE_PI_AGENT_MAX_TURNS: "2",
    MISSIONFORGE_PI_AGENT_TOOL_TIMEOUT_SECONDS: "3",
    MISSIONFORGE_PI_AGENT_CANCEL_AFTER_TURNS: "1",
    MISSIONFORGE_PI_AGENT_COMPACT_AFTER_TURNS: "1",
    MISSIONFORGE_PI_AGENT_CONTEXT_WINDOW: "64000",
  });

  assert.equal(config.mode, "live");
  assert.equal(config.model.id, "gpt-5.5");
  assert.equal(config.model.api, "openai-responses");
  assert.equal(config.model.baseUrl, "https://example.test/v1");
  assert.equal(config.apiKey, "sk-live-secret");
  assert.equal(config.reasoning, "low");
  assert.equal(config.maxTurns, 2);
  assert.equal(config.toolTimeoutSeconds, 3);
  assert.equal(config.cancelAfterTurns, 1);
  assert.equal(config.compactAfterTurns, 1);
  assert.equal(config.model.contextWindow, 64000);
});

test("resolveProviderConfig validates cancellation and compaction turn fields", () => {
  assert.throws(
    () =>
      resolveProviderConfig({
        MISSIONFORGE_PI_AGENT_PROVIDER: "faux",
        MISSIONFORGE_PI_AGENT_CANCEL_AFTER_TURNS: "0",
      }),
    /Invalid positive integer/,
  );
  assert.throws(
    () =>
      resolveProviderConfig({
        MISSIONFORGE_PI_AGENT_PROVIDER: "faux",
        MISSIONFORGE_PI_AGENT_COMPACT_AFTER_TURNS: "0",
      }),
    /Invalid positive integer/,
  );
  assert.throws(
    () =>
      resolveProviderConfig({
        MISSIONFORGE_PI_AGENT_PROVIDER: "faux",
        MISSIONFORGE_PI_AGENT_CONTEXT_WINDOW: "0",
      }),
    /Invalid positive integer/,
  );
});

test("resolveProviderConfig fails closed for incomplete live config", () => {
  assert.throws(
    () =>
      resolveProviderConfig({
        MISSIONFORGE_PI_AGENT_PROVIDER: "live",
        MISSIONFORGE_PI_AGENT_MODEL: "gpt-5.5",
        MISSIONFORGE_PI_AGENT_BASE_URL: "https://example.test/v1",
      }),
    /MISSIONFORGE_PI_AGENT_API_KEY is required/,
  );
});

test("resolveProviderConfig validates live budget fields", () => {
  assert.throws(
    () =>
      resolveProviderConfig({
        MISSIONFORGE_PI_AGENT_PROVIDER: "live",
        MISSIONFORGE_PI_AGENT_MODEL: "gpt-5.5",
        MISSIONFORGE_PI_AGENT_BASE_URL: "https://example.test/v1",
        MISSIONFORGE_PI_AGENT_API_KEY: "sk-live-secret",
        MISSIONFORGE_PI_AGENT_MAX_TURNS: "0",
      }),
    /Invalid positive integer/,
  );
});

test("resolveProviderConfig defaults to enough turns for multi-artifact live work", () => {
  const config = resolveProviderConfig({
    MISSIONFORGE_PI_AGENT_PROVIDER: "live",
    MISSIONFORGE_PI_AGENT_MODEL: "gpt-5.5",
    MISSIONFORGE_PI_AGENT_BASE_URL: "https://example.test/v1",
    MISSIONFORGE_PI_AGENT_API_KEY: "sk-live-secret",
  });

  assert.equal(config.maxTurns, 12);
});
