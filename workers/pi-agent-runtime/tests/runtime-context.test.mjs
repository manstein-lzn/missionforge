import assert from "node:assert/strict";
import test from "node:test";

import { stripUnreplayableResponsesReasoning } from "../dist/runtime.js";

test("stripUnreplayableResponsesReasoning removes OpenAI Responses thinking blocks only", async () => {
  const messages = [
    { role: "user", content: [{ type: "text", text: "go" }] },
    {
      role: "assistant",
      api: "openai-responses",
      content: [
        { type: "thinking", thinking: "", thinkingSignature: '{"id":"rs_123"}' },
        { type: "toolCall", id: "call_1|fc_1", name: "write", arguments: { path: "package/SKILL.md" } },
        { type: "text", text: "done" },
      ],
    },
    {
      role: "assistant",
      api: "missionforge-faux",
      content: [{ type: "thinking", thinking: "kept" }],
    },
  ];

  const transformed = await stripUnreplayableResponsesReasoning(messages);

  assert.deepEqual(transformed[0], messages[0]);
  assert.deepEqual(transformed[1].content, [
    { type: "toolCall", id: "call_1|fc_1", name: "write", arguments: { path: "package/SKILL.md" } },
    { type: "text", text: "done" },
  ]);
  assert.deepEqual(transformed[2], messages[2]);
});
