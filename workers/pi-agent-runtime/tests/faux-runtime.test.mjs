import assert from "node:assert/strict";
import { access, readFile } from "node:fs/promises";
import { join } from "node:path";
import test from "node:test";

import { parseRuntimeInput } from "../dist/contract.js";
import { EvidenceRecorder } from "../dist/evidence-recorder.js";
import { runMissionForgePiAgent } from "../dist/runtime.js";
import { readJson, sampleInput, withWorkspace, writeInput } from "./helpers.mjs";

test("faux runtime writes expected artifact and output artifacts", async () => {
  await withWorkspace(async (root) => {
    const input = sampleInput({
      contract: {
        ...sampleInput().contract,
        expected_outputs: ["attempts/WU-000001/artifact.txt", "attempts/WU-000001/second.txt"],
      },
    });
    await writeInput(root, input);
    process.env.MISSIONFORGE_PI_AGENT_PROVIDER = "faux";
    await runMissionForgePiAgent(parseRuntimeInput(input), root);

    const output = await readJson(join(root, input.output_ref));
    assert.equal(output.status, "completed");
    assert.deepEqual(output.produced_artifacts, input.contract.expected_outputs);
    await access(join(root, input.contract.expected_outputs[0]));
    await access(join(root, input.contract.expected_outputs[1]));
    await access(join(root, input.events_ref));
    await access(join(root, input.session_ref));
    await access(join(root, input.metrics_ref));
    await access(join(root, input.savepoints_ref));
    const metrics = await readJson(join(root, input.metrics_ref));
    assert.equal(metrics.tool_call_count, 2);
    assert.equal(metrics.cache_read_tokens, 0);
    assert.equal(metrics.cache_write_tokens, 0);
    assert.equal(metrics.provider_reported_cost_usd, 0);
    assert.equal(metrics.tool_error_count, 0);
    assert.equal(metrics.command_count, 0);
    assert.equal(metrics.test_command_count, 0);
    assert.equal(metrics.command_failure_count, 0);
    assert.equal(metrics.tool_latency_ms_total >= 0, true);
    assert.equal(metrics.tool_latency_ms_by_name.write >= 0, true);
    assert.equal(Object.hasOwn(metrics, "time_to_first_tool_ms"), true);
    assert.equal(Object.hasOwn(metrics, "time_to_first_artifact_ms"), true);
    const savepoints = await readFile(join(root, input.savepoints_ref), "utf-8");
    assert.equal(savepoints.includes("missionforge.pi_agent_runtime_savepoint.v1"), true);
    assert.equal(savepoints.includes("after_completed_turn"), true);
  });
});

test("faux runtime does not serialize api keys", async () => {
  await withWorkspace(async (root) => {
    const input = sampleInput();
    await writeInput(root, input);
    process.env.MISSIONFORGE_PI_AGENT_PROVIDER = "faux";
    process.env.MISSIONFORGE_PI_AGENT_API_KEY = "secret-value-12345";
    await runMissionForgePiAgent(parseRuntimeInput(input), root);

    const outputData = await readJson(join(root, input.output_ref));
    const output = await readFile(join(root, input.output_ref), "utf-8");
    const events = await readFile(join(root, input.events_ref), "utf-8");
    const session = await readFile(join(root, input.session_ref), "utf-8");
    const metrics = await readFile(join(root, input.metrics_ref), "utf-8");
    const savepoints = await readFile(join(root, input.savepoints_ref), "utf-8");
    assert.equal(`${output}${events}${session}${metrics}${savepoints}`.includes("secret-value-12345"), false);
    assert.equal(`${events}${session}${savepoints}`.includes("pi-agent-runtime faux artifact"), false);
    assert.equal(`${output}${events}${session}`.includes("Completed WU-000001"), false);
    assert.deepEqual(outputData.worker_claims, ["assistant_final_text_present:length=20"]);
  });
});

test("faux runtime cancellation writes normalized non-success output", async () => {
  await withWorkspace(async (root) => {
    const input = sampleInput();
    await writeInput(root, input);
    process.env.MISSIONFORGE_PI_AGENT_PROVIDER = "faux";
    process.env.MISSIONFORGE_PI_AGENT_CANCEL_AFTER_TURNS = "1";
    try {
      await runMissionForgePiAgent(parseRuntimeInput(input), root);
    } finally {
      delete process.env.MISSIONFORGE_PI_AGENT_CANCEL_AFTER_TURNS;
    }

    const output = await readJson(join(root, input.output_ref));
    assert.equal(output.status, "cancelled");
    assert.equal(output.verification_status, "failed");
    assert.equal(output.recommended_next_steps.includes("Run was cancelled at a MissionForge safe point."), true);
    await access(join(root, input.savepoints_ref));
  });
});

test("faux runtime compaction writes a savepoint marker", async () => {
  await withWorkspace(async (root) => {
    const input = sampleInput();
    await writeInput(root, input);
    process.env.MISSIONFORGE_PI_AGENT_PROVIDER = "faux";
    process.env.MISSIONFORGE_PI_AGENT_COMPACT_AFTER_TURNS = "1";
    try {
      await runMissionForgePiAgent(parseRuntimeInput(input), root);
    } finally {
      delete process.env.MISSIONFORGE_PI_AGENT_COMPACT_AFTER_TURNS;
    }

    const savepoints = await readFile(join(root, input.savepoints_ref), "utf-8");
    const events = await readFile(join(root, input.events_ref), "utf-8");
    assert.equal(savepoints.includes('"compaction"'), true);
    assert.equal(savepoints.includes("after_completed_turn"), true);
    assert.equal(events.includes('"event_type":"compaction"'), true);
  });
});

test("evidence recorder summarizes unknown provider events instead of serializing payloads", async () => {
  await withWorkspace(async (root) => {
    const input = parseRuntimeInput(sampleInput());
    await writeInput(root, input);
    const recorder = new EvidenceRecorder(input, root);

    await recorder.record({
      type: "provider_payload",
      raw_prompt: "raw-provider-secret",
      nested: { transcript: "raw-transcript-secret" },
    });

    const events = await readFile(join(root, input.events_ref), "utf-8");
    assert.equal(events.includes("provider_payload"), true);
    assert.equal(events.includes("raw-provider-secret"), false);
    assert.equal(events.includes("raw-transcript-secret"), false);
  });
});
