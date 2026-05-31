import assert from "node:assert/strict";
import { access, mkdir, mkdtemp, readFile, rm, symlink, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import test from "node:test";

import { parseDirectRuntimeInput } from "../dist/direct-contract.js";
import { buildDirectSystemPrompt, buildDirectUserPrompt, runDirectPiWorkerBenchmark } from "../dist/direct-runner.js";
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
    assert.equal(publicArtifacts.includes("Completed direct benchmark task"), false);
    assert.deepEqual(output.worker_claims, ["assistant_final_text_present:length=41"]);
  });
});

test("direct prompt exposes public allowed source refs without MissionForge internals", () => {
  const input = sampleDirectInput({
    allowed_source_refs: ["benchmarks/tasks/task-001/public_contract.md"],
  });
  const parsed = parseDirectRuntimeInput(input);
  const userPrompt = buildDirectUserPrompt(parsed, "Build the package.", [
    {
      ref: "benchmarks/tasks/task-001/public_contract.md",
      content: "Manifest schema_version must be skillfoundry.bundle.v1.",
    },
  ]);

  assert.equal(userPrompt.includes("Public source refs to inspect before writing"), true);
  assert.equal(userPrompt.includes("benchmarks/tasks/task-001/public_contract.md"), true);
  assert.equal(userPrompt.includes("skillfoundry.bundle.v1"), true);
  assert.equal(userPrompt.includes("WorkUnitContract"), false);
  assert.equal(userPrompt.includes("MissionIR"), false);
  assert.equal(userPrompt.includes("FrontDesk"), false);
});

test("direct runner rejects workspace_ref symlink escape before tool setup", async () => {
  const outside = await mkdtemp(join(tmpdir(), "mf-direct-outside-"));
  try {
    await withWorkspace(async (root) => {
      const input = sampleDirectInput();
      await mkdir(join(root, dirname(input.workspace_ref)), { recursive: true });
      await symlink(outside, join(root, input.workspace_ref), "dir");

      process.env.MISSIONFORGE_PI_AGENT_PROVIDER = "faux";
      try {
        await assert.rejects(
          () => runDirectPiWorkerBenchmark(parseDirectRuntimeInput(input), root),
          /symlink/,
        );
      } finally {
        delete process.env.MISSIONFORGE_PI_AGENT_PROVIDER;
      }
      await assert.rejects(() => access(join(outside, "package/SKILL.md")));
    });
  } finally {
    await rm(outside, { recursive: true, force: true });
  }
});

test("direct runner rejects initial user text symlink without reading outside content", async () => {
  const outside = await mkdtemp(join(tmpdir(), "mf-direct-outside-"));
  try {
    await withWorkspace(async (root) => {
      const input = sampleDirectInput();
      await mkdir(join(root, "benchmarks/tasks/task-001"), { recursive: true });
      await mkdir(join(root, dirname(input.output_ref)), { recursive: true });
      await writeFile(join(outside, "secret.txt"), "direct-source-secret\n", "utf-8");
      await symlink(outside, join(root, "benchmarks/tasks/task-001/link"), "dir");
      const linkedInput = {
        ...input,
        initial_user_text_ref: "benchmarks/tasks/task-001/link/secret.txt",
      };

      process.env.MISSIONFORGE_PI_AGENT_PROVIDER = "faux";
      try {
        await runDirectPiWorkerBenchmark(parseDirectRuntimeInput(linkedInput), root);
      } finally {
        delete process.env.MISSIONFORGE_PI_AGENT_PROVIDER;
      }

      const output = await readJson(join(root, linkedInput.output_ref));
      const serialized = await serializedWorkspace(root);
      assert.equal(output.status, "failed");
      assert.equal(serialized.includes("symlink"), true);
      assert.equal(serialized.includes("direct-source-secret"), false);
      await assert.rejects(() => access(join(outside, "package/SKILL.md")));
    });
  } finally {
    await rm(outside, { recursive: true, force: true });
  }
});

test("direct runner rejects allowed source symlink without reading outside content", async () => {
  const outside = await mkdtemp(join(tmpdir(), "mf-direct-outside-"));
  try {
    await withWorkspace(async (root) => {
      const input = sampleDirectInput({
        allowed_source_refs: ["benchmarks/tasks/task-001/link/source.md"],
      });
      await mkdir(join(root, "benchmarks/tasks/task-001"), { recursive: true });
      await mkdir(join(root, dirname(input.output_ref)), { recursive: true });
      await writeFile(join(root, input.initial_user_text_ref), "Build the package.\n", "utf-8");
      await writeFile(join(outside, "source.md"), "allowed-source-secret\n", "utf-8");
      await symlink(outside, join(root, "benchmarks/tasks/task-001/link"), "dir");

      process.env.MISSIONFORGE_PI_AGENT_PROVIDER = "faux";
      try {
        await runDirectPiWorkerBenchmark(parseDirectRuntimeInput(input), root);
      } finally {
        delete process.env.MISSIONFORGE_PI_AGENT_PROVIDER;
      }

      const output = await readJson(join(root, input.output_ref));
      const serialized = await serializedWorkspace(root);
      assert.equal(output.status, "failed");
      assert.equal(serialized.includes("symlink"), true);
      assert.equal(serialized.includes("allowed-source-secret"), false);
      await assert.rejects(() => access(join(outside, "package/SKILL.md")));
    });
  } finally {
    await rm(outside, { recursive: true, force: true });
  }
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

async function serializedWorkspace(root) {
  const chunks = [];
  await collectFiles(root, chunks);
  return chunks.join("\n");
}

async function collectFiles(path, chunks) {
  const { readdir, stat } = await import("node:fs/promises");
  const entries = await readdir(path, { withFileTypes: true });
  for (const entry of entries) {
    const child = join(path, entry.name);
    if (entry.isDirectory()) {
      await collectFiles(child, chunks);
    } else if (entry.isFile()) {
      chunks.push(await readFile(child, "utf-8"));
    } else {
      try {
        const info = await stat(child);
        if (info.isFile()) chunks.push(await readFile(child, "utf-8"));
      } catch {
        continue;
      }
    }
  }
}
