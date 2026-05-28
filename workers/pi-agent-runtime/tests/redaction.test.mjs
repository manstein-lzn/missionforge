import assert from "node:assert/strict";
import test from "node:test";

import { redactJson, redactText } from "../dist/redaction.js";

test("redactText removes secret env values and inline tokens", () => {
  const text = redactText("api_key=abc12345 token: xyz98765 raw abc12345", {
    MISSIONFORGE_PI_AGENT_API_KEY: "abc12345",
  });
  assert.equal(text.includes("abc12345"), false);
  assert.equal(text.includes("xyz98765"), false);
});

test("redactJson redacts secret-shaped keys", () => {
  const value = redactJson({ nested: { api_key: "abc12345" } });
  assert.deepEqual(value, { nested: { api_key: "<redacted>" } });
});
