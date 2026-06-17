import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { mkdir, mkdtemp, readFile, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";

import { ToolObservationRecorder } from "../dist/context-observations.js";
import { parseRuntimeInput } from "../dist/contract.js";
import { sampleInput, withWorkspace } from "./helpers.mjs";

test("large bash output writes raw ref and metadata-only observation", async () => {
  await withWorkspace(async (root) => {
    const input = parseRuntimeInput(sampleInput());
    const recorder = new ToolObservationRecorder({ input, workspaceRoot: root });
    const largeOutput = `${"line\n".repeat(3000)}final\n`;
    recorder.noteTurnStart();

    await recorder.recordAfterToolCall({
      toolCall: { id: "bash-call-1", name: "bash", arguments: { command: "generate output" } },
      args: { command: "generate output" },
      result: { content: [{ type: "text", text: largeOutput }], details: {} },
      isError: false,
      assistantMessage: { role: "assistant", content: [] },
      context: { messages: [], systemPrompt: "" },
    });

    const indexText = await readFile(join(root, input.context_observations_ref), "utf-8");
    const observation = JSON.parse(indexText.trim());
    assert.equal(observation.schema_version, "missionforge.pi_agent_tool_observation.v1");
    assert.equal(observation.tool_call_id, "bash-call-1");
    assert.equal(observation.tool_name, "bash");
    assert.equal(observation.inline_policy, "demote_after_turn");
    assert.equal(observation.content_hash, sha256(largeOutput));
    assert.equal(typeof observation.raw_ref, "string");
    assert.equal(indexText.includes(largeOutput.slice(0, 100)), false);

    const raw = await readFile(join(root, observation.raw_ref), "utf-8");
    assert.equal(raw, largeOutput);
  });
});

test("bash fullOutputPath is copied into MissionForge raw refs", async () => {
  await withWorkspace(async (root) => {
    const input = parseRuntimeInput(sampleInput());
    const recorder = new ToolObservationRecorder({ input, workspaceRoot: root });
    const tempDir = await mkdtemp(join(tmpdir(), "mf-pi-bash-test-"));
    const fullOutputPath = join(tempDir, "pi-bash-abcdef01.log");
    const fullOutput = "hidden full output\n".repeat(2000);
    await writeFile(fullOutputPath, fullOutput, "utf-8");
    recorder.noteTurnStart();

    await recorder.recordAfterToolCall({
      toolCall: { id: "bash-call-2", name: "bash", arguments: { command: "generate output" } },
      args: { command: "generate output" },
      result: {
        content: [{ type: "text", text: "truncated output\n[Full output available]" }],
        details: { fullOutputPath },
      },
      isError: false,
      assistantMessage: { role: "assistant", content: [] },
      context: { messages: [], systemPrompt: "" },
    });

    const observation = JSON.parse((await readFile(join(root, input.context_observations_ref), "utf-8")).trim());
    assert.equal(observation.content_hash, sha256(fullOutput));
    assert.equal(observation.content_bytes, Buffer.byteLength(fullOutput, "utf-8"));
    assert.equal(await readFile(join(root, observation.raw_ref), "utf-8"), fullOutput);
  });
});

test("read output records source ref range and hash", async () => {
  await withWorkspace(async (root) => {
    const sourceRef = "attempts/WU-000001/source.txt";
    const sourceText = "alpha\nbeta\ngamma\n";
    await mkdir(join(root, "attempts/WU-000001"), { recursive: true });
    await writeFile(join(root, sourceRef), sourceText, "utf-8");
    const input = parseRuntimeInput(sampleInput());
    const recorder = new ToolObservationRecorder({ input, workspaceRoot: root });
    recorder.noteTurnStart();

    await recorder.recordAfterToolCall({
      toolCall: { id: "read-call-1", name: "read", arguments: { path: sourceRef, offset: 2, limit: 1 } },
      args: { path: sourceRef, offset: 2, limit: 1 },
      result: { content: [{ type: "text", text: "beta" }], details: {} },
      isError: false,
      assistantMessage: { role: "assistant", content: [] },
      context: { messages: [], systemPrompt: "" },
    });

    const observation = JSON.parse((await readFile(join(root, input.context_observations_ref), "utf-8")).trim());
    assert.equal(observation.tool_name, "read");
    assert.equal(observation.source_ref, sourceRef);
    assert.deepEqual(observation.source_range, { offset: 2, limit: 1 });
    assert.equal(observation.source_hash, sha256(sourceText));
    assert.equal(observation.raw_ref, undefined);
  });
});

test("small bash output stays inline without raw ref", async () => {
  await withWorkspace(async (root) => {
    const input = parseRuntimeInput(sampleInput());
    const recorder = new ToolObservationRecorder({ input, workspaceRoot: root });
    recorder.noteTurnStart();

    await recorder.recordAfterToolCall({
      toolCall: { id: "bash-call-small", name: "bash", arguments: { command: "printf ok" } },
      args: { command: "printf ok" },
      result: { content: [{ type: "text", text: "ok\n" }], details: {} },
      isError: false,
      assistantMessage: { role: "assistant", content: [] },
      context: { messages: [], systemPrompt: "" },
    });

    const observation = JSON.parse((await readFile(join(root, input.context_observations_ref), "utf-8")).trim());
    assert.equal(observation.inline_policy, "keep");
    assert.equal(observation.raw_ref, undefined);
    assert.equal(observation.content_hash, sha256("ok\n"));
  });
});

test("context projection config controls large observation threshold", async () => {
  await withWorkspace(async (root) => {
    const input = parseRuntimeInput(
      sampleInput({
        context_projection_config: {
          schema_version: "missionforge.pi_agent_context_projection_config.v1",
          large_observation_bytes: 50000,
          soft_compact_ratio: 0.8,
          hard_compact_ratio: 0.9,
          cache_aware: true,
        },
      }),
    );
    const recorder = new ToolObservationRecorder({ input, workspaceRoot: root });
    const belowCustomThreshold = "configured threshold output\n".repeat(500);
    recorder.noteTurnStart();

    await recorder.recordAfterToolCall({
      toolCall: { id: "bash-config-threshold", name: "bash", arguments: { command: "generate output" } },
      args: { command: "generate output" },
      result: { content: [{ type: "text", text: belowCustomThreshold }], details: {} },
      isError: false,
      assistantMessage: { role: "assistant", content: [] },
      context: { messages: [], systemPrompt: "" },
    });

    const observation = JSON.parse((await readFile(join(root, input.context_observations_ref), "utf-8")).trim());
    assert.equal(observation.inline_policy, "keep");
    assert.equal(observation.raw_ref, undefined);
  });
});

test("large bash error output is captured and demoted", async () => {
  await withWorkspace(async (root) => {
    const input = parseRuntimeInput(sampleInput());
    const recorder = new ToolObservationRecorder({ input, workspaceRoot: root });
    const largeError = `${"error line\n".repeat(1200)}fatal\n`;
    recorder.noteTurnStart();

    await recorder.recordAfterToolCall({
      toolCall: { id: "bash-error-large", name: "bash", arguments: { command: "failing command" } },
      args: { command: "failing command" },
      result: { content: [{ type: "text", text: largeError }], details: {} },
      isError: true,
      assistantMessage: { role: "assistant", content: [] },
      context: { messages: [], systemPrompt: "" },
    });

    const observation = JSON.parse((await readFile(join(root, input.context_observations_ref), "utf-8")).trim());
    assert.equal(observation.status, "error");
    assert.equal(observation.inline_policy, "demote_after_turn");
    assert.equal(observation.content_hash, sha256(largeError));
    assert.equal(typeof observation.raw_ref, "string");
    assert.equal(await readFile(join(root, observation.raw_ref), "utf-8"), largeError);
  });
});

test("unauthorized read observation does not expose source or raw ref", async () => {
  await withWorkspace(async (root) => {
    await mkdir(join(root, "private"), { recursive: true });
    await writeFile(join(root, "private/secret.txt"), "secret\n", "utf-8");
    const input = parseRuntimeInput(sampleInput());
    const recorder = new ToolObservationRecorder({ input, workspaceRoot: root });
    recorder.noteTurnStart();

    await recorder.recordAfterToolCall({
      toolCall: { id: "read-denied", name: "read", arguments: { path: "private/secret.txt" } },
      args: { path: "private/secret.txt" },
      result: { content: [{ type: "text", text: "permission denied" }], details: {} },
      isError: true,
      assistantMessage: { role: "assistant", content: [] },
      context: { messages: [], systemPrompt: "" },
    });

    const observation = JSON.parse((await readFile(join(root, input.context_observations_ref), "utf-8")).trim());
    assert.equal(observation.status, "error");
    assert.equal(observation.inline_policy, "keep");
    assert.equal(observation.source_ref, undefined);
    assert.equal(observation.raw_ref, undefined);
  });
});

function sha256(text) {
  return `sha256:${createHash("sha256").update(text).digest("hex")}`;
}
