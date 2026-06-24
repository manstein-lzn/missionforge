import assert from "node:assert/strict";
import { mkdir, writeFile } from "node:fs/promises";
import { join } from "node:path";
import test from "node:test";

import { CONTEXT_SNAPSHOT_SCHEMA_VERSION, buildContextSnapshot } from "../dist/context-snapshot.js";
import { createMissionForgeTools } from "../dist/tools.js";
import { withWorkspace } from "./helpers.mjs";

test("context_snapshot reports refs and projection state without raw bodies", async () => {
  await withWorkspace(async (root) => {
    const rawRef = "attempts/WU-000001/context/raw/000001-bash-output.txt";
    const sourceRef = "inputs/source.txt";
    const rawBody = "very large raw output body\n".repeat(500);
    await mkdir(join(root, "attempts/WU-000001/context/raw"), { recursive: true });
    await mkdir(join(root, "inputs"), { recursive: true });
    await writeFile(join(root, rawRef), rawBody, "utf-8");
    await writeFile(join(root, sourceRef), "alpha\nbeta\ngamma\n", "utf-8");

    const tools = await createMissionForgeTools({
      workspaceRoot: root,
      permissionManifest: permissionManifest({
        readable_refs: ["inputs", "attempts/WU-000001/context/raw"],
        writable_refs: ["outputs"],
        denied_refs: [],
        allowed_tools: ["read", "write", "edit", "context_snapshot"],
      }),
      toolTimeoutSeconds: 30,
      contextSnapshot: snapshotOptions({
        workspaceRoot: root,
        permissionManifest: permissionManifest({
          readable_refs: ["inputs", "attempts/WU-000001/context/raw"],
          writable_refs: ["outputs"],
          denied_refs: [],
          allowed_tools: ["read", "write", "edit", "context_snapshot"],
        }),
        observations: () => [
          observation({
            raw_ref: rawRef,
            source_ref: sourceRef,
            source_range: { offset: 2, limit: 1 },
            source_hash: `sha256:${"b".repeat(64)}`,
            source_bytes: 17,
          }),
        ],
        projectionDiagnostics: () => projectionDiagnostics({
          projected_observations: [{ observation_id: "tool-observation-000001" }],
        }),
      }),
    });
    const snapshotTool = tool(tools, "context_snapshot");

    const result = await snapshotTool.execute("snapshot-1", {});
    const text = result.content[0].text;
    const snapshot = JSON.parse(text);

    assert.equal(snapshot.schema_version, CONTEXT_SNAPSHOT_SCHEMA_VERSION);
    assert.equal(snapshot.observation_count, 1);
    assert.equal(snapshot.projection.projected_observation_count, 1);
    assert.equal(snapshot.projection.projected_observation_ids[0], "tool-observation-000001");
    assert.equal(snapshot.observations[0].projection_state, "projected_stub");
    assert.deepEqual(snapshot.observations[0].raw_ref.read_args, { path: rawRef });
    assert.deepEqual(snapshot.observations[0].source_ref.read_args, {
      path: sourceRef,
      offset: 2,
      limit: 1,
    });
    assert.equal(text.includes(rawBody.slice(0, 80)), false);
  });
});

test("context_snapshot marks refs unreadable without granting access", async () => {
  await withWorkspace(async (root) => {
    const rawRef = "attempts/WU-000001/context/raw/000001-bash-output.txt";
    const privateRef = "inputs/private/secret.txt";
    await mkdir(join(root, "inputs/private"), { recursive: true });
    await writeFile(join(root, privateRef), "classified-body-value\n", "utf-8");
    const snapshot = buildContextSnapshot(
      snapshotOptions({
        workspaceRoot: root,
        permissionManifest: permissionManifest({
          readable_refs: ["inputs"],
          writable_refs: ["outputs"],
          denied_refs: ["inputs/private"],
          allowed_tools: ["read", "write", "edit", "context_snapshot"],
        }),
        observations: () => [
          observation({
            raw_ref: rawRef,
            source_ref: privateRef,
          }),
        ],
      }),
    );

    assert.equal(snapshot.observations[0].raw_ref.readable, false);
    assert.equal(snapshot.observations[0].raw_ref.unreadable_reason, "ref_outside_allowed_roots");
    assert.equal(snapshot.observations[0].raw_ref.read_args, undefined);
    assert.equal(snapshot.observations[0].source_ref.readable, false);
    assert.equal(snapshot.observations[0].source_ref.unreadable_reason, "ref_denied");
    assert.equal(snapshot.observations[0].source_ref.read_args, undefined);
    assert.equal(JSON.stringify(snapshot).includes("classified-body-value"), false);
  });
});

test("context_snapshot keeps executor raw refs unreadable under a judge manifest", async () => {
  await withWorkspace(async (root) => {
    const executorRawRef = "attempts/WU-000001/context/raw/000001-bash-output.txt";
    const judgeVisibleRef = "artifacts/final.md";
    const snapshot = buildContextSnapshot(
      snapshotOptions({
        workspaceRoot: root,
        permissionManifest: permissionManifest({
          readable_refs: [
            "attempts/judge-packet-001/judge_node_spec.json",
            "contract/task_contract.json",
            "reports/execution_report.json",
            judgeVisibleRef,
          ],
          writable_refs: ["reports/judge_report.json"],
          denied_refs: [],
          allowed_tools: ["read", "write", "edit", "context_snapshot"],
        }),
        observations: () => [
          observation({
            raw_ref: executorRawRef,
            source_ref: judgeVisibleRef,
          }),
        ],
      }),
    );

    assert.equal(snapshot.observations[0].raw_ref.readable, false);
    assert.equal(snapshot.observations[0].raw_ref.read_args, undefined);
    assert.equal(snapshot.observations[0].source_ref.readable, true);
    assert.deepEqual(snapshot.observations[0].source_ref.read_args, { path: judgeVisibleRef });
    assert.equal(JSON.stringify(snapshot).includes("context/raw/000001-bash-output.txt"), true);
  });
});

function snapshotOptions(overrides = {}) {
  return {
    callId: "WU-000001",
    workspaceRoot: overrides.workspaceRoot,
    permissionManifest: overrides.permissionManifest ?? permissionManifest(),
    contextObservationsRef: "attempts/WU-000001/context/tool_observations.jsonl",
    contextProjectionRef: "attempts/WU-000001/context/projection.json",
    observations: () => [],
    currentTurnIndex: () => 3,
    projectionDiagnostics: () => projectionDiagnostics(),
    ...overrides,
  };
}

function projectionDiagnostics(overrides = {}) {
  return {
    schema_version: "missionforge.pi_agent_context_projection.v1",
    call_id: "WU-000001",
    created_at: "2026-06-13T00:00:00.000Z",
    context_observations_ref: "attempts/WU-000001/context/tool_observations.jsonl",
    projection_count: 1,
    latest_turn_index: 3,
    input_message_count: 1,
    projected_message_count: 1,
    context_projection_config: {
      schema_version: "missionforge.pi_agent_context_projection_config.v1",
      large_observation_bytes: 8192,
      soft_compact_ratio: 0.8,
      hard_compact_ratio: 0.9,
      cache_aware: true,
    },
    model_context_window: 128000,
    estimated_input_tokens: 0,
    pressure_ratio: 0,
    soft_compact_ratio: 0.8,
    hard_compact_ratio: 0.9,
    cache_read_tokens: 0,
    cache_write_tokens: 0,
    projection_strategy: "cache_aware_ref_projection",
    recommended_action: "continue",
    projected_observations: [],
    active_observations: [],
    warnings: [],
    ...overrides,
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
    ...overrides,
  };
}

function permissionManifest(overrides = {}) {
  return {
    manifest_id: "test-permissions",
    schema_version: "permission_manifest.v1",
    workspace_policy_ref: null,
    readable_refs: ["inputs"],
    writable_refs: ["outputs"],
    denied_refs: [],
    allowed_tools: ["read", "write", "edit", "context_snapshot"],
    allowed_commands: [],
    network_policy: "disabled",
    env_allowlist: [],
    secret_ref: null,
    unsupported_hard_policies: [],
    ...overrides,
  };
}

function tool(tools, name) {
  const found = tools.find((candidate) => candidate.name === name);
  if (!found) throw new Error(`missing tool ${name}`);
  return found;
}
