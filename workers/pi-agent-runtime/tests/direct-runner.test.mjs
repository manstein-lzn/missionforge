import assert from "node:assert/strict";
import { access, mkdir, readFile, writeFile } from "node:fs/promises";
import { join } from "node:path";
import test from "node:test";

import { parseDirectRuntimeInput } from "../dist/direct-contract.js";
import { buildDirectSystemPrompt, runDirectPiWorkerBenchmark } from "../dist/direct-runner.js";
import { readJson, withWorkspace } from "./helpers.mjs";

test("direct faux runner writes comparable safe artifacts without WorkUnit prompt semantics", async () => {
  await withWorkspace(async (root) => {
    const input = sampleDirectInput();
    await mkdir(join(root, "benchmarks/tasks/task-001"), { recursive: true });
    await mkdir(join(root, "benchmarks/runs/bench-001/trials/task-001/direct_piworker_chat/seed-1"), {
      recursive: true,
    });
    await writeFile(
      join(root, input.initial_user_text_ref),
      "Please solve this private direct baseline task. raw-user-secret-phrase\n",
      "utf-8",
    );
    await writeFile(join(root, input.input_ref), `${JSON.stringify(input, null, 2)}\n`, "utf-8");

    process.env.MISSIONFORGE_PI_AGENT_PROVIDER = "faux";
    process.env.MISSIONFORGE_PI_AGENT_API_KEY = "secret-value-12345";
    try {
      const parsed = parseDirectRuntimeInput(input);
      const systemPrompt = buildDirectSystemPrompt(parsed);
      for (const forbidden of ["Work unit", "WorkUnitContract", "MissionIR", "FrontDesk", "ProductGate", "verifier"]) {
        assert.equal(systemPrompt.includes(forbidden), false);
      }
      await runDirectPiWorkerBenchmark(parsed, root);
    } finally {
      delete process.env.MISSIONFORGE_PI_AGENT_PROVIDER;
      delete process.env.MISSIONFORGE_PI_AGENT_API_KEY;
    }

    const output = await readJson(join(root, input.output_ref));
    assert.equal(output.schema_version, "missionforge.pi_agent_direct_output.v1");
    assert.equal(output.status, "completed");
    assert.deepEqual(output.produced_artifacts, input.expected_output_refs);
    assert.equal(output.changed_refs.includes("package/SKILL.md"), true);
    await access(join(root, input.workspace_ref, input.expected_output_refs[0]));

    const metrics = await readJson(join(root, input.metrics_ref));
    assert.equal(metrics.schema_version, "missionforge.pi_agent_direct_metrics.v1");
    assert.equal(metrics.tool_call_count, 1);
    assert.equal(typeof metrics.total_tokens, "number");
    assert.equal(metrics.cache_read_tokens, 0);
    assert.equal(metrics.provider_reported_cost_usd, 0);
    assert.equal(metrics.tool_latency_ms_by_name.write >= 0, true);
    assert.equal(Object.hasOwn(metrics, "time_to_first_tool_ms"), true);
    assert.equal(Object.hasOwn(metrics, "time_to_first_artifact_ms"), true);

    const events = await readFile(join(root, input.events_ref), "utf-8");
    const session = await readFile(join(root, input.session_ref), "utf-8");
    const outputText = await readFile(join(root, input.output_ref), "utf-8");
    const metricsText = await readFile(join(root, input.metrics_ref), "utf-8");
    const publicArtifacts = `${events}${session}${outputText}${metricsText}`;
    assert.equal(publicArtifacts.includes("secret-value-12345"), false);
    assert.equal(publicArtifacts.includes("raw-user-secret-phrase"), false);
    assert.equal(publicArtifacts.includes("Please solve this private direct baseline task"), false);
  });
});

function sampleDirectInput(overrides = {}) {
  const root = "benchmarks/runs/bench-001/trials/task-001/direct_piworker_chat/seed-1";
  return {
    schema_version: "missionforge.pi_agent_direct_input.v1",
    benchmark_run_id: "bench-001",
    task_id: "task-001",
    seed: 1,
    workspace_root: ".",
    workspace_ref: `${root}/workspace`,
    input_ref: `${root}/direct_piworker_input.json`,
    output_ref: `${root}/direct_piworker_output.json`,
    session_ref: `${root}/direct_piworker_session.jsonl`,
    events_ref: `${root}/direct_piworker_events.jsonl`,
    metrics_ref: `${root}/direct_piworker_metrics.json`,
    initial_user_text_ref: "benchmarks/tasks/task-001/user_statement.txt",
    allowed_source_refs: [],
    expected_output_refs: ["package/SKILL.md"],
    runtime: {
      runtime_name: "missionforge.pi_agent_direct_benchmark",
      timeout_seconds: 60,
      model: null,
      metadata: {},
    },
    ...overrides,
  };
}
