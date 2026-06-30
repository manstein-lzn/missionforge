import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { mkdir, writeFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import test from "node:test";

import { ContextProjector, CONTEXT_PROJECTION_SCHEMA_VERSION } from "../dist/context-projector.js";
import { loadContextEngineProviderText, stripUnreplayableResponsesReasoning } from "../dist/runtime.js";
import { sampleInput, withWorkspace } from "./helpers.mjs";

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

test("loadContextEngineProviderText renders refs-only admitted ContextView buckets", async () => {
  await withWorkspace(async (root) => {
    const contextViewRef = "kernel/demo-flow/steps/researcher/context_projection.json";
    const compileResultRef = "kernel/demo-flow/steps/researcher/context/compile_result.json";
    const view = withContextHash({
      schema_version: "missionforge.context_view.v1",
      view_id: "demo-flow-researcher-context",
      role: "executor_piworker",
      contract_ref: "contract/task_contract.json",
      contract_hash: `sha256:${"a".repeat(64)}`,
      permission_manifest_ref: "kernel/demo-flow/steps/researcher/permission_manifest.json",
      token_budget: 1000,
      stable_prefix: [
        segment({
          segment_id: "contract",
          kind: "authority",
          source_refs: ["contract/task_contract.json"],
          cache_policy: "stable",
        }),
      ],
      semi_stable_context: [],
      volatile_tail: [
        segment({
          segment_id: "source_packet",
          kind: "artifact_ref",
          source_refs: ["sources/source_packet.json"],
          body_ref: "sources/source_packet_projection.txt",
          token_estimate: 12,
        }),
      ],
      omitted_segments: [
        segment({
          segment_id: "denied_source_refs",
          kind: "runtime_diagnostic",
          source_refs: ["secrets/raw-denied.txt"],
          cache_policy: "no_cache",
          inline_policy: "omitted",
        }),
      ],
      diagnostics_ref: contextViewRef,
    });
    const contextHash = view.context_hash;
    const input = sampleInput({
      context_engine: {
        schema_version: "missionforge.pi_agent_context_engine.v1",
        enabled: true,
        context_view_ref: contextViewRef,
        context_compile_result_ref: compileResultRef,
        context_cache_layout_ref: "kernel/demo-flow/steps/researcher/context/cache_layout.json",
        context_pressure_ref: "kernel/demo-flow/steps/researcher/context/pressure.json",
        context_epoch_ref: "kernel/demo-flow/steps/researcher/context/epoch.json",
        context_hash: contextHash,
        context_compile_action: "continue",
      },
      permission_manifest: readableContextEngineManifest(["sources"]),
    });
    await writeJson(root, contextViewRef, view);
    await writeJson(root, compileResultRef, {
      schema_version: "missionforge.context_compile_result.v1",
      result_id: "demo-flow-researcher-context-compile",
      view_ref: contextViewRef,
      context_hash: contextHash,
      action: "continue",
      epoch_ref: "kernel/demo-flow/steps/researcher/context/epoch.json",
      pressure_ref: "kernel/demo-flow/steps/researcher/context/pressure.json",
      cache_layout_ref: "kernel/demo-flow/steps/researcher/context/cache_layout.json",
      admitted_update_refs: ["sources/source_packet.json"],
      omitted_refs: ["secrets/raw-denied.txt"],
      demoted_refs: [],
      denied_source_refs: ["secrets/raw-denied.txt"],
      diagnostics_refs: [],
      metadata: {},
    });

    const text = await loadContextEngineProviderText(input, root);

    assert.equal(text.includes("[MissionForge ContextEngine compiled context]"), true);
    assert.equal(text.includes(`context_view_ref: ${contextViewRef}`), true);
    assert.equal(text.includes("source_refs=sources/source_packet.json"), true);
    assert.equal(text.includes("body_ref=sources/source_packet_projection.txt"), true);
    assert.equal(text.includes("omitted_ref_count: 1"), true);
    assert.equal(text.includes("secrets/raw-denied.txt"), false);
    assert.equal(text.includes("ARTIFACT_BODY_SENTINEL"), false);
  });
});

test("loadContextEngineProviderText renders bounded working-set projection text", async () => {
  await withWorkspace(async (root) => {
    const contextViewRef = "kernel/demo-flow/steps/researcher/context_projection.json";
    const compileResultRef = "kernel/demo-flow/steps/researcher/context/compile_result.json";
    const projectionRef = "context/projections/source_packet_entry1.md";
    const projectionText = "bounded working set fact\nsource body is not here\n";
    const view = withContextHash({
      ...minimalContextView(contextViewRef),
      semi_stable_context: [
        segment({
          segment_id: "src_002_working_set_entry1",
          kind: "artifact_preview",
          source_refs: ["sources/source_packet.json", projectionRef],
          source_hashes: { [projectionRef]: sha256(projectionText) },
          body_ref: projectionRef,
          cache_policy: "semi_stable",
          token_estimate: 8,
          metadata: {
            source_key: "working_set/000-entry1",
            source_kind: "working_set",
            entry_id: "entry1",
          },
        }),
      ],
    });
    const contextHash = view.context_hash;
    const input = sampleInput({
      context_engine: {
        schema_version: "missionforge.pi_agent_context_engine.v1",
        enabled: true,
        context_view_ref: contextViewRef,
        context_compile_result_ref: compileResultRef,
        context_hash: contextHash,
        context_compile_action: "continue",
      },
      permission_manifest: {
        ...readableContextEngineManifest(),
        readable_refs: ["contract", "context", "kernel", "sources"],
      },
    });
    await writeText(root, projectionRef, projectionText);
    await writeJson(root, contextViewRef, view);
    await writeJson(root, compileResultRef, {
      ...minimalCompileResult(contextViewRef, contextHash),
      working_set_ref: "context/working_set.json",
      admitted_update_refs: [projectionRef],
    });

    const text = await loadContextEngineProviderText(input, root);

    assert.equal(text.includes("working_set_projection:"), true);
    assert.equal(text.includes(`projection_ref: ${projectionRef}`), true);
    assert.equal(text.includes("bounded working set fact"), true);
    assert.equal(text.includes("FULL_SOURCE_BODY_SENTINEL"), false);
  });
});

test("loadContextEngineProviderText renders bounded tool-output projection text", async () => {
  await withWorkspace(async (root) => {
    const contextViewRef = "kernel/demo-flow/steps/reviewer/context_projection.json";
    const compileResultRef = "kernel/demo-flow/steps/reviewer/context/compile_result.json";
    const projectionRef = "attempts/demo-flow-001-researcher/context/tool_output_projections/tool-observation-000001.txt";
    const projectionText = [
      "[MissionForge tool output projection]",
      "observation_id: tool-observation-000001",
      "source_ref: sources/source_packet.json",
      "projection_note: full tool result body remains behind cited refs and current permissions.",
      "",
    ].join("\n");
    const view = withContextHash({
      ...minimalContextView(contextViewRef),
      volatile_tail: [
        segment({
          segment_id: "src_002_context_feed_tool-observation-000001",
          kind: "tool_observation",
          source_refs: [
            "attempts/demo-flow-001-researcher/context/tool_output_projections/tool-observation-000001.json",
            projectionRef,
          ],
          source_hashes: { [projectionRef]: sha256(projectionText) },
          body_ref: projectionRef,
          inline_policy: "preview",
          token_estimate: 10,
          metadata: {
            source_key: "context_feed/000-tool-observation-000001",
            source_kind: "tool_output_projection",
            tool_observation_id: "tool-observation-000001",
          },
        }),
      ],
    });
    const contextHash = view.context_hash;
    const input = sampleInput({
      context_engine: {
        schema_version: "missionforge.pi_agent_context_engine.v1",
        enabled: true,
        context_view_ref: contextViewRef,
        context_compile_result_ref: compileResultRef,
        context_hash: contextHash,
        context_compile_action: "continue",
      },
      permission_manifest: {
        ...readableContextEngineManifest(),
        readable_refs: ["contract", "attempts", "kernel"],
      },
    });
    await writeText(root, projectionRef, projectionText);
    await writeJson(root, contextViewRef, view);
    await writeJson(root, compileResultRef, {
      ...minimalCompileResult(contextViewRef, contextHash),
      admitted_update_refs: [projectionRef],
    });

    const text = await loadContextEngineProviderText(input, root);

    assert.equal(text.includes("tool_output_projection:"), true);
    assert.equal(text.includes(`projection_ref: ${projectionRef}`), true);
    assert.equal(text.includes("observation_id: tool-observation-000001"), true);
    assert.equal(text.includes("RAW_TOOL_BODY_SENTINEL"), false);
  });
});

test("loadContextEngineProviderText fails closed when working-set projection is denied", async () => {
  await withWorkspace(async (root) => {
    const contextViewRef = "kernel/demo-flow/steps/researcher/context_projection.json";
    const compileResultRef = "kernel/demo-flow/steps/researcher/context/compile_result.json";
    const projectionRef = "context/projections/source_packet_entry1.md";
    const view = withContextHash({
      ...minimalContextView(contextViewRef),
      semi_stable_context: [
        segment({
          kind: "artifact_preview",
          source_refs: ["sources/source_packet.json", projectionRef],
          body_ref: projectionRef,
          cache_policy: "semi_stable",
          metadata: { source_kind: "working_set" },
        }),
      ],
    });
    const contextHash = view.context_hash;
    const input = sampleInput({
      context_engine: {
        schema_version: "missionforge.pi_agent_context_engine.v1",
        enabled: true,
        context_view_ref: contextViewRef,
        context_compile_result_ref: compileResultRef,
        context_hash: contextHash,
        context_compile_action: "continue",
      },
      permission_manifest: {
        ...readableContextEngineManifest(),
        readable_refs: ["contract", "context", "kernel"],
        denied_refs: [projectionRef],
      },
    });
    await writeText(root, projectionRef, "bounded working set fact\n");
    await writeJson(root, contextViewRef, view);
    await writeJson(root, compileResultRef, minimalCompileResult(contextViewRef, contextHash));

    await assert.rejects(
      () => loadContextEngineProviderText(input, root),
      /permission denied/,
    );
  });
});

test("loadContextEngineProviderText fails closed when tool-output projection hash changes", async () => {
  await withWorkspace(async (root) => {
    const contextViewRef = "kernel/demo-flow/steps/reviewer/context_projection.json";
    const compileResultRef = "kernel/demo-flow/steps/reviewer/context/compile_result.json";
    const projectionRef = "attempts/demo-flow-001-researcher/context/tool_output_projections/tool-observation-000001.txt";
    const originalText = "original tool output projection\n";
    const view = withContextHash({
      ...minimalContextView(contextViewRef),
      volatile_tail: [
        segment({
          kind: "tool_observation",
          source_refs: [
            "attempts/demo-flow-001-researcher/context/tool_output_projections/tool-observation-000001.json",
            projectionRef,
          ],
          source_hashes: { [projectionRef]: sha256(originalText) },
          body_ref: projectionRef,
          inline_policy: "preview",
          metadata: { source_kind: "tool_output_projection" },
        }),
      ],
    });
    const contextHash = view.context_hash;
    const input = sampleInput({
      context_engine: {
        schema_version: "missionforge.pi_agent_context_engine.v1",
        enabled: true,
        context_view_ref: contextViewRef,
        context_compile_result_ref: compileResultRef,
        context_hash: contextHash,
        context_compile_action: "continue",
      },
      permission_manifest: {
        ...readableContextEngineManifest(),
        readable_refs: ["contract", "attempts", "kernel"],
      },
    });
    await writeText(root, projectionRef, "tampered tool output projection\n");
    await writeJson(root, contextViewRef, view);
    await writeJson(root, compileResultRef, minimalCompileResult(contextViewRef, contextHash));

    await assert.rejects(
      () => loadContextEngineProviderText(input, root),
      /tool_output_projection hash does not match/,
    );
  });
});

test("loadContextEngineProviderText fails closed on hash mismatch", async () => {
  await withWorkspace(async (root) => {
    const contextViewRef = "kernel/demo-flow/steps/researcher/context_projection.json";
    const compileResultRef = "kernel/demo-flow/steps/researcher/context/compile_result.json";
    const view = withContextHash(minimalContextView(contextViewRef));
    const input = sampleInput({
      context_engine: {
        schema_version: "missionforge.pi_agent_context_engine.v1",
        enabled: true,
        context_view_ref: contextViewRef,
        context_compile_result_ref: compileResultRef,
        context_hash: `sha256:${"b".repeat(64)}`,
      },
      permission_manifest: readableContextEngineManifest(),
    });
    await writeJson(root, contextViewRef, view);
    await writeJson(root, compileResultRef, minimalCompileResult(contextViewRef, view.context_hash));

    await assert.rejects(() => loadContextEngineProviderText(input, root), /context_hash does not match/);
  });
});

test("loadContextEngineProviderText fails closed when ContextView content hash is stale", async () => {
  await withWorkspace(async (root) => {
    const contextViewRef = "kernel/demo-flow/steps/researcher/context_projection.json";
    const compileResultRef = "kernel/demo-flow/steps/researcher/context/compile_result.json";
    const originalView = withContextHash(minimalContextView(contextViewRef));
    const tamperedView = {
      ...originalView,
      volatile_tail: [
        segment({
          segment_id: "tampered",
          kind: "artifact_ref",
          source_refs: ["sources/tampered.json"],
        }),
      ],
    };
    const input = sampleInput({
      context_engine: {
        schema_version: "missionforge.pi_agent_context_engine.v1",
        enabled: true,
        context_view_ref: contextViewRef,
        context_compile_result_ref: compileResultRef,
        context_hash: originalView.context_hash,
      },
      permission_manifest: readableContextEngineManifest(),
    });
    await writeJson(root, contextViewRef, tamperedView);
    await writeJson(root, compileResultRef, minimalCompileResult(contextViewRef, originalView.context_hash));

    await assert.rejects(
      () => loadContextEngineProviderText(input, root),
      /context_view hash does not match content/,
    );
  });
});

test("loadContextEngineProviderText fails closed when ContextEngine ref is not readable", async () => {
  await withWorkspace(async (root) => {
    const contextViewRef = "kernel/demo-flow/steps/researcher/context_projection.json";
    const compileResultRef = "kernel/demo-flow/steps/researcher/context/compile_result.json";
    const input = sampleInput({
      context_engine: {
        schema_version: "missionforge.pi_agent_context_engine.v1",
        enabled: true,
        context_view_ref: contextViewRef,
        context_compile_result_ref: compileResultRef,
        context_hash: `sha256:${"b".repeat(64)}`,
      },
      permission_manifest: {
        ...sampleInput().permission_manifest,
        readable_refs: ["contract"],
      },
    });

    await assert.rejects(() => loadContextEngineProviderText(input, root), /permission denied/);
  });
});

test("loadContextEngineProviderText fails closed when admitted source ref is not readable", async () => {
  await withWorkspace(async (root) => {
    const contextViewRef = "kernel/demo-flow/steps/researcher/context_projection.json";
    const compileResultRef = "kernel/demo-flow/steps/researcher/context/compile_result.json";
    const deniedRef = "sources/private_packet.json";
    const view = withContextHash({
      ...minimalContextView(contextViewRef),
      volatile_tail: [
        segment({
          segment_id: "private_source",
          kind: "artifact_ref",
          source_refs: [deniedRef],
        }),
      ],
    });
    const input = sampleInput({
      context_engine: {
        schema_version: "missionforge.pi_agent_context_engine.v1",
        enabled: true,
        context_view_ref: contextViewRef,
        context_compile_result_ref: compileResultRef,
        context_hash: view.context_hash,
      },
      permission_manifest: {
        ...readableContextEngineManifest(),
        readable_refs: ["contract", "kernel"],
      },
    });
    await writeJson(root, contextViewRef, view);
    await writeJson(root, compileResultRef, minimalCompileResult(contextViewRef, view.context_hash));

    await assert.rejects(
      () => loadContextEngineProviderText(input, root),
      /permission denied/,
    );
  });
});

test("loadContextEngineProviderText fails closed when working-set projection hash changes", async () => {
  await withWorkspace(async (root) => {
    const contextViewRef = "kernel/demo-flow/steps/researcher/context_projection.json";
    const compileResultRef = "kernel/demo-flow/steps/researcher/context/compile_result.json";
    const projectionRef = "context/projections/source_packet_entry1.md";
    const originalText = "bounded working set fact\n";
    const view = withContextHash({
      ...minimalContextView(contextViewRef),
      semi_stable_context: [
        segment({
          kind: "artifact_preview",
          source_refs: ["sources/source_packet.json", projectionRef],
          source_hashes: { [projectionRef]: sha256(originalText) },
          body_ref: projectionRef,
          cache_policy: "semi_stable",
          metadata: { source_kind: "working_set" },
        }),
      ],
    });
    const contextHash = view.context_hash;
    const input = sampleInput({
      context_engine: {
        schema_version: "missionforge.pi_agent_context_engine.v1",
        enabled: true,
        context_view_ref: contextViewRef,
        context_compile_result_ref: compileResultRef,
        context_hash: contextHash,
      },
      permission_manifest: {
        ...readableContextEngineManifest(),
        readable_refs: ["contract", "context", "kernel", "sources"],
      },
    });
    await writeText(root, projectionRef, "tampered working set fact\n");
    await writeJson(root, contextViewRef, view);
    await writeJson(root, compileResultRef, minimalCompileResult(contextViewRef, contextHash));

    await assert.rejects(
      () => loadContextEngineProviderText(input, root),
      /projection hash does not match/,
    );
  });
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

async function writeJson(root, ref, value) {
  const path = join(root, ref);
  await mkdir(dirname(path), { recursive: true });
  await writeFile(path, `${JSON.stringify(value, null, 2)}\n`, "utf-8");
}

async function writeText(root, ref, value) {
  const path = join(root, ref);
  await mkdir(dirname(path), { recursive: true });
  await writeFile(path, value, "utf-8");
}

function segment(overrides = {}) {
  return {
    schema_version: "missionforge.context_segment.v1",
    segment_id: "segment",
    kind: "artifact_ref",
    source_refs: [],
    source_hashes: {},
    cache_policy: "volatile",
    inline_policy: "ref_only",
    token_estimate: 0,
    priority: 0,
    role_scope: ["executor_piworker"],
    body_ref: null,
    metadata: {},
    ...overrides,
  };
}

function minimalContextView(viewRef) {
  return {
    schema_version: "missionforge.context_view.v1",
    view_id: "demo-flow-researcher-context",
    role: "executor_piworker",
    contract_ref: "contract/task_contract.json",
    contract_hash: `sha256:${"a".repeat(64)}`,
    permission_manifest_ref: "kernel/demo-flow/steps/researcher/permission_manifest.json",
    token_budget: 1000,
    stable_prefix: [],
    semi_stable_context: [],
    volatile_tail: [],
    omitted_segments: [],
    diagnostics_ref: viewRef,
  };
}

function withContextHash(view) {
  const { context_hash: _contextHash, ...content } = view;
  return { ...content, context_hash: stableJsonHash(content) };
}

function minimalCompileResult(viewRef, contextHash) {
  return {
    schema_version: "missionforge.context_compile_result.v1",
    result_id: "demo-flow-researcher-context-compile",
    view_ref: viewRef,
    context_hash: contextHash,
    action: "continue",
    epoch_ref: null,
    pressure_ref: null,
    working_set_ref: null,
    cache_layout_ref: null,
    admitted_update_refs: [],
    omitted_refs: [],
    demoted_refs: [],
    denied_source_refs: [],
    diagnostics_refs: [],
    metadata: {},
  };
}

function readableContextEngineManifest(extraReadableRefs = []) {
  return {
    ...sampleInput().permission_manifest,
    readable_refs: ["contract", "kernel", ...extraReadableRefs],
  };
}

function sha256(text) {
  return `sha256:${createHash("sha256").update(text).digest("hex")}`;
}

function stableJsonHash(value) {
  return `sha256:${createHash("sha256").update(stableJsonString(value)).digest("hex")}`;
}

function stableJsonString(value) {
  if (value === null) return "null";
  if (typeof value === "boolean") return value ? "true" : "false";
  if (typeof value === "string") return ensureAsciiJsonString(value);
  if (typeof value === "number") {
    if (!Number.isFinite(value)) throw new Error("stable_json value must not contain non-finite numbers");
    return JSON.stringify(value);
  }
  if (Array.isArray(value)) return `[${value.map((item) => stableJsonString(item)).join(",")}]`;
  if (typeof value === "object") {
    return `{${Object.keys(value)
      .sort()
      .map((key) => `${JSON.stringify(key)}:${stableJsonString(value[key])}`)
      .join(",")}}`;
  }
  throw new Error("stable_json value must be JSON-compatible");
}

function ensureAsciiJsonString(value) {
  return JSON.stringify(value).replace(/[^\x00-\x7F]/g, (char) =>
    `\\u${char.charCodeAt(0).toString(16).padStart(4, "0")}`,
  );
}
