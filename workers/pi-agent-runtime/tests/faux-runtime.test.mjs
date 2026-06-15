import assert from "node:assert/strict";
import { access, mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import test from "node:test";

import { parseRuntimeInput } from "../dist/contract.js";
import { EvidenceRecorder } from "../dist/evidence-recorder.js";
import {
  buildCompletionRetryPrompt,
  promptForMissingExpectedOutputs,
  runMissionForgePiAgent,
} from "../dist/runtime.js";
import { readJson, sampleInput, withWorkspace, writeInput } from "./helpers.mjs";

test("faux runtime writes expected artifact and output artifacts", async () => {
  await withWorkspace(async (root) => {
    const input = sampleInput({
      call_spec: {
        ...sampleInput().call_spec,
        expected_outputs: ["attempts/WU-000001/artifact.txt", "attempts/WU-000001/second.txt"],
      },
    });
    await writeInput(root, input);
    process.env.MISSIONFORGE_PI_AGENT_PROVIDER = "faux";
    await runMissionForgePiAgent(parseRuntimeInput(input), root);

    const output = await readJson(join(root, input.output_ref));
    assert.equal(output.status, "completed");
    assert.deepEqual(output.produced_artifacts, input.call_spec.expected_outputs);
    await access(join(root, input.call_spec.expected_outputs[0]));
    await access(join(root, input.call_spec.expected_outputs[1]));
    await access(join(root, input.events_ref));
    await access(join(root, input.session_ref));
    await access(join(root, input.metrics_ref));
    await access(join(root, input.savepoints_ref));
    await access(join(root, output.context_observations_ref));
    await access(join(root, output.context_projection_ref));
    const projection = await readJson(join(root, output.context_projection_ref));
    assert.equal(projection.schema_version, "missionforge.pi_agent_context_projection.v1");
    assert.equal(projection.context_observations_ref, output.context_observations_ref);
    assert.equal(projection.projected_observations.length, 0);
    const metrics = await readJson(join(root, input.metrics_ref));
    assert.equal(metrics.tool_call_count, 2);
    assert.equal(metrics.cache_read_tokens > 0, true);
    assert.equal(metrics.cache_write_tokens > 0, true);
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
    assert.equal(eventsContainGatewayDecision(await readFile(join(root, input.events_ref), "utf-8"), "write"), true);
    assert.equal(eventsContainType(await readFile(join(root, input.events_ref), "utf-8"), "tool_observation"), true);
  });
});

test("runtime event log records gateway decisions without artifact bodies", async () => {
  await withWorkspace(async (root) => {
    const input = sampleInput();
    await writeInput(root, input);
    process.env.MISSIONFORGE_PI_AGENT_PROVIDER = "faux";
    await runMissionForgePiAgent(parseRuntimeInput(input), root);

    const events = await readFile(join(root, input.events_ref), "utf-8");
    assert.equal(events.includes('"event_type":"tool_gateway_decision"'), true);
    assert.equal(events.includes('"operation":"write_container"'), true);
    assert.equal(events.includes('"operation":"write_path"'), true);
    assert.equal(events.includes("pi-agent-runtime faux artifact"), false);
    assert.equal(gatewayDecisionPayloadHasKey(events, "content"), false);
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
    const observations = await readFile(join(root, outputData.context_observations_ref), "utf-8");
    const projection = await readFile(join(root, outputData.context_projection_ref), "utf-8");
    assert.equal(`${output}${events}${session}${metrics}${savepoints}${observations}${projection}`.includes("secret-value-12345"), false);
    assert.equal(`${events}${session}${savepoints}`.includes("pi-agent-runtime faux artifact"), false);
    assert.equal(projection.includes("pi-agent-runtime faux artifact"), false);
    assert.equal(`${output}${events}${session}`.includes("Completed WU-000001"), false);
    assert.deepEqual(outputData.worker_claims, ["assistant_final_text_present:length=20"]);
  });
});

function eventsContainGatewayDecision(events, toolName) {
  return events
    .trim()
    .split("\n")
    .filter(Boolean)
    .some((line) => {
      const event = JSON.parse(line);
      return event.event_type === "tool_gateway_decision" && event.payload.tool_name === toolName;
    });
}

function eventsContainType(events, eventType) {
  return events
    .trim()
    .split("\n")
    .filter(Boolean)
    .some((line) => {
      const event = JSON.parse(line);
      return event.event_type === eventType;
    });
}

function gatewayDecisionPayloadHasKey(events, key) {
  return events
    .trim()
    .split("\n")
    .filter(Boolean)
    .some((line) => {
      const event = JSON.parse(line);
      return event.event_type === "tool_gateway_decision" && Object.hasOwn(event.payload, key);
    });
}

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

test("missing expected output retry prompts once and stops after the artifact exists", async () => {
  await withWorkspace(async (root) => {
    const input = parseRuntimeInput(sampleInput());
    const prompts = [];

    const result = await promptForMissingExpectedOutputs({
      input,
      workspaceRoot: root,
      maxTurns: 4,
      maxRetries: 2,
      currentTurnCount: () => prompts.length,
      prompt: async (prompt) => {
        prompts.push(prompt);
        await mkdir(dirname(join(root, input.call_spec.expected_outputs[0])), { recursive: true });
        await writeFile(join(root, input.call_spec.expected_outputs[0]), "created by retry\n", "utf-8");
      },
    });

    assert.equal(result.retryCount, 1);
    assert.deepEqual(result.missingOutputs, []);
    assert.equal(prompts[0].includes(input.call_spec.expected_outputs[0]), true);
    assert.equal(prompts[0].includes("Do not answer in text instead of writing artifacts."), true);
  });
});

test("missing expected output retry respects exhausted turn budget", async () => {
  await withWorkspace(async (root) => {
    const input = parseRuntimeInput(sampleInput());
    const prompts = [];

    const result = await promptForMissingExpectedOutputs({
      input,
      workspaceRoot: root,
      maxTurns: 1,
      maxRetries: 2,
      currentTurnCount: () => 1,
      prompt: async (prompt) => {
        prompts.push(prompt);
      },
    });

    assert.equal(result.retryCount, 0);
    assert.deepEqual(result.missingOutputs, input.call_spec.expected_outputs);
    assert.deepEqual(prompts, []);
  });
});

test("judge retry prompt names JudgeReport without embedding artifact bodies", () => {
  const base = sampleInput();
  const input = parseRuntimeInput(
    sampleInput({
      piworker_call: {
        ...base.piworker_call,
        role: "judge_piworker",
        writable_refs: ["reports/judge_report.json"],
        expected_output_refs: ["reports/judge_report.json"],
      },
      call_spec: {
        ...base.call_spec,
        visible_refs: ["attempts/WU-000001/judge_node_spec.json", "packets/judge_packet.json"],
        allowed_scope: ["reports/judge_report.json"],
        expected_outputs: ["reports/judge_report.json"],
      },
      permission_manifest: {
        ...base.permission_manifest,
        readable_refs: ["attempts/WU-000001/judge_node_spec.json", "packets/judge_packet.json"],
        writable_refs: ["reports/judge_report.json"],
      },
    }),
  );

  const prompt = buildCompletionRetryPrompt(input, ["reports/judge_report.json"], 1);

  assert.equal(prompt.includes("judge_piworker"), true);
  assert.equal(prompt.includes("JudgeReport JSON object"), true);
  assert.equal(prompt.includes("reports/judge_report.json"), true);
  assert.equal(prompt.includes("raw_transcript"), false);
  assert.equal(prompt.includes("provider_payload"), false);
});
