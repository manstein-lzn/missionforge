import assert from "node:assert/strict";
import test from "node:test";

import { ContextProjector, CONTEXT_PROJECTION_SCHEMA_VERSION } from "../dist/context-projector.js";
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

test("ContextProjector keeps demote_after_turn output for immediate follow-up", () => {
  const messages = [
    toolResultMessage({
      toolCallId: "bash-call-1",
      text: "large output remains visible for the immediate follow-up",
    }),
  ];
  const projector = new ContextProjector({
    observations: () => [observation({ tool_call_id: "bash-call-1", turn_index: 1 })],
    currentTurnIndex: () => 2,
  });

  const projected = projector.project(messages);

  assert.equal(projected[0], messages[0]);
  assert.equal(projected[0].content[0].text, "large output remains visible for the immediate follow-up");
});

test("ContextProjector stubs stale large tool output without mutating transcript", () => {
  const largeOutput = "large output\n".repeat(1000);
  const messages = [
    toolResultMessage({
      toolCallId: "bash-call-2",
      text: largeOutput,
      details: { fullOutputPath: "/tmp/pi-bash-abcdef01.log" },
    }),
  ];
  const projector = new ContextProjector({
    observations: () => [
      observation({
        observation_id: "tool-observation-000002",
        tool_call_id: "bash-call-2",
        turn_index: 1,
        raw_ref: "attempts/WU-000001/context/raw/000002-bash-bash-call-2-output.txt",
      }),
    ],
    currentTurnIndex: () => 3,
  });

  const projected = projector.project(messages);
  const projectedMessage = projected[0];
  const stub = projectedMessage.content[0].text;

  assert.notEqual(projectedMessage, messages[0]);
  assert.equal(messages[0].content[0].text, largeOutput);
  assert.equal(stub.includes(CONTEXT_PROJECTION_SCHEMA_VERSION), true);
  assert.equal(stub.includes("tool-observation-000002"), true);
  assert.equal(stub.includes("raw_ref: attempts/WU-000001/context/raw/000002-bash-bash-call-2-output.txt"), true);
  assert.equal(stub.includes("content_hash: sha256:"), true);
  assert.equal(stub.includes(largeOutput.slice(0, 80)), false);
  assert.equal(stub.includes("fullOutputPath"), false);
  assert.equal(Object.hasOwn(projectedMessage, "details"), false);
});

test("ContextProjector diagnostics report refs-only projection metadata", () => {
  const largeOutput = "diagnostic large output\n".repeat(800);
  const input = {
    call_id: "WU-000001",
    context_observations_ref: "attempts/WU-000001/context/tool_observations.jsonl",
    context_projection_config: {
      schema_version: "missionforge.pi_agent_context_projection_config.v1",
      large_observation_bytes: 8192,
    },
  };
  const projector = new ContextProjector({
    observations: () => [
      observation({
        observation_id: "tool-observation-000003",
        tool_call_id: "bash-call-3",
        turn_index: 1,
      }),
    ],
    currentTurnIndex: () => 3,
  });

  projector.project([toolResultMessage({ toolCallId: "bash-call-3", text: largeOutput })]);
  const diagnostics = projector.diagnostics(input);

  assert.equal(diagnostics.schema_version, CONTEXT_PROJECTION_SCHEMA_VERSION);
  assert.equal(diagnostics.projection_count, 1);
  assert.deepEqual(diagnostics.context_projection_config, input.context_projection_config);
  assert.equal(diagnostics.projected_observations.length, 1);
  assert.equal(diagnostics.projected_observations[0].observation_id, "tool-observation-000003");
  assert.equal(diagnostics.projected_observations[0].projected_bytes > 0, true);
  assert.equal(JSON.stringify(diagnostics).includes(largeOutput.slice(0, 80)), false);
});

function toolResultMessage({ toolCallId, text, details = undefined }) {
  return {
    role: "toolResult",
    toolCallId,
    toolName: "bash",
    content: [{ type: "text", text }],
    details,
    isError: false,
    timestamp: 1,
  };
}

function observation(overrides = {}) {
  return {
    schema_version: "missionforge.pi_agent_tool_observation.v1",
    observation_id: "tool-observation-000001",
    call_id: "WU-000001",
    turn_index: 1,
    tool_call_id: "bash-call-1",
    tool_name: "bash",
    status: "ok",
    created_at: "2026-06-13T00:00:00.000Z",
    content_hash: `sha256:${"a".repeat(64)}`,
    content_bytes: 12000,
    content_lines: 1000,
    inline_policy: "demote_after_turn",
    raw_ref: "attempts/WU-000001/context/raw/000001-bash-bash-call-1-output.txt",
    ...overrides,
  };
}
