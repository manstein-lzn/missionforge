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
      soft_compact_ratio: 0.8,
      hard_compact_ratio: 0.9,
      cache_aware: true,
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
    contextWindow: () => 100000,
    metrics: () => ({ cache_read_tokens: 123, cache_write_tokens: 45 }),
  });

  projector.project([toolResultMessage({ toolCallId: "bash-call-3", text: largeOutput })]);
  const diagnostics = projector.diagnostics(input);

  assert.equal(diagnostics.schema_version, CONTEXT_PROJECTION_SCHEMA_VERSION);
  assert.equal(diagnostics.projection_count, 1);
  assert.deepEqual(diagnostics.context_projection_config, input.context_projection_config);
  assert.equal(diagnostics.projected_observations.length, 1);
  assert.equal(diagnostics.projected_observations[0].observation_id, "tool-observation-000003");
  assert.equal(diagnostics.projected_observations[0].projected_bytes > 0, true);
  assert.equal(diagnostics.model_context_window, 100000);
  assert.equal(diagnostics.cache_read_tokens, 123);
  assert.equal(diagnostics.cache_write_tokens, 45);
  assert.equal(diagnostics.recommended_action, "continue");
  assert.equal(diagnostics.context_budget.schema_version, "missionforge.context_budget.v1");
  assert.equal(diagnostics.context_budget.usable_input_budget > 0, true);
  assert.equal(diagnostics.memory_layers.stable_authority_prefix.kept_first, true);
  assert.equal(diagnostics.pressure_ratio >= 0, true);
  assert.equal(JSON.stringify(diagnostics).includes(largeOutput.slice(0, 80)), false);
});

test("ContextProjector archives older messages into a flat segment stub", () => {
  const messages = Array.from({ length: 30 }, (_value, index) => ({
    role: "user",
    content: [{ type: "text", text: `message-${index}` }],
    timestamp: index,
  }));
  const input = {
    call_id: "WU-000001",
    attempt_dir_ref: "attempts/WU-000001",
    context_observations_ref: "attempts/WU-000001/context/tool_observations.jsonl",
    context_projection_config: {
      schema_version: "missionforge.pi_agent_context_projection_config.v1",
      large_observation_bytes: 8192,
      soft_compact_ratio: 0.8,
      hard_compact_ratio: 0.9,
      cache_aware: true,
    },
  };
  const projector = new ContextProjector({
    observations: () => [],
    currentTurnIndex: () => 10,
  });

  const projected = projector.project(messages, "", undefined, input);
  const diagnostics = projector.diagnostics(input);

  assert.equal(projected.length, 25);
  assert.equal(projected[0].content[0].text.includes("context/segments/catalog.json"), true);
  assert.equal(diagnostics.memory_layers.archived_history.archived_message_count, 6);
  assert.deepEqual(diagnostics.memory_layers.archived_history.segment_refs, [
    "attempts/WU-000001/context/segments/segment-000001.jsonl",
  ]);
});

test("ContextProjector does not split assistant tool calls from their tool results", () => {
  const messages = [
    ...Array.from({ length: 12 }, (_value, index) => ({
      role: "user",
      content: [{ type: "text", text: `prefix-${index}` }],
      timestamp: index,
    })),
    {
      role: "assistant",
      api: "openai-responses",
      content: [
        { type: "toolCall", id: "call_keep_1|fc_keep_1", name: "read", arguments: { path: "refs/a.json" } },
        { type: "toolCall", id: "call_keep_2|fc_keep_2", name: "read", arguments: { path: "refs/b.json" } },
      ],
      timestamp: 20,
    },
    toolResultMessage({
      toolCallId: "call_keep_1|fc_keep_1",
      text: "result one",
      timestamp: 21,
    }),
    toolResultMessage({
      toolCallId: "call_keep_2|fc_keep_2",
      text: "result two",
      timestamp: 22,
    }),
    ...Array.from({ length: 23 }, (_value, index) => ({
      role: "user",
      content: [{ type: "text", text: `tail-${index}` }],
      timestamp: index + 30,
    })),
  ];
  const input = {
    call_id: "WU-000001",
    attempt_dir_ref: "attempts/WU-000001",
    context_observations_ref: "attempts/WU-000001/context/tool_observations.jsonl",
  };
  const projector = new ContextProjector({
    observations: () => [],
    currentTurnIndex: () => 10,
  });

  const projected = projector.project(messages, "", undefined, input);
  const diagnostics = projector.diagnostics(input);

  assert.equal(projected.length, 27);
  assert.equal(projected[0].content[0].text.includes("archived_message_count: 12"), true);
  assert.equal(diagnostics.memory_layers.archived_history.archived_message_count, 12);
  assert.equal(projected[1].role, "assistant");
  assert.equal(projected[1].content[0].id, "call_keep_1|fc_keep_1");
  assert.equal(projected[1].content[1].id, "call_keep_2|fc_keep_2");
  assert.equal(projected[2].role, "toolResult");
  assert.equal(projected[3].role, "toolResult");
});

test("ContextProjector injects long memory before archived and projected history", () => {
  const longMemoryMessage = {
    role: "user",
    content: [
      {
        type: "text",
        text: "[MissionForge long-memory packet]\npacket_ref: attempts/WU-000001/context/long_memory_packet.json\n",
      },
    ],
    timestamp: 1,
  };
  const messages = Array.from({ length: 30 }, (_value, index) => ({
    role: "user",
    content: [{ type: "text", text: `message-${index}` }],
    timestamp: index + 10,
  }));
  const input = {
    call_id: "WU-000001",
    attempt_dir_ref: "attempts/WU-000001",
    context_observations_ref: "attempts/WU-000001/context/tool_observations.jsonl",
    context_projection_config: {
      schema_version: "missionforge.pi_agent_context_projection_config.v1",
      large_observation_bytes: 8192,
      soft_compact_ratio: 0.8,
      hard_compact_ratio: 0.9,
      cache_aware: true,
    },
  };
  const projector = new ContextProjector({
    observations: () => [],
    currentTurnIndex: () => 10,
    longMemory: () => ({
      packet: null,
      message: longMemoryMessage,
      diagnostics: {
        provider_enabled: true,
        packet_ref: "attempts/WU-000001/context/long_memory_packet.json",
        provider: "mem0",
        advisory_only: true,
        degraded: false,
        memory_count: 1,
        catalog_hit_count: 1,
        budget_tokens: 2000,
        estimated_tokens: 42,
        warnings: [],
      },
    }),
  });

  const projected = projector.project(messages, "", undefined, input);
  const diagnostics = projector.diagnostics(input);

  assert.equal(projected[0], longMemoryMessage);
  assert.equal(projected[1].content[0].text.includes("[MissionForge archived context segment]"), true);
  assert.equal(projected[2].content[0].text, "message-6");
  assert.equal(diagnostics.memory_layers.long_memory.provider_enabled, true);
  assert.equal(diagnostics.memory_layers.long_memory.provider, "mem0");
  assert.equal(diagnostics.memory_layers.long_memory.degraded, false);
  assert.equal(diagnostics.memory_layers.long_memory.memory_count, 1);
  assert.equal(diagnostics.memory_layers.long_memory.catalog_hit_count, 1);
});

function toolResultMessage({ toolCallId, text, details = undefined, timestamp = 1 }) {
  return {
    role: "toolResult",
    toolCallId,
    toolName: "bash",
    content: [{ type: "text", text }],
    details,
    isError: false,
    timestamp,
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
