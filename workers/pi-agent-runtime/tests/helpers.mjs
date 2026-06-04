import { mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";

export async function withWorkspace(fn) {
  const root = await mkdtemp(join(tmpdir(), "mf-pi-agent-"));
  try {
    await fn(root);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
}

export function sampleInput(overrides = {}) {
  const workUnitId = "WU-000001";
  const attempt = `attempts/${workUnitId}`;
  return {
    schema_version: "missionforge.pi_agent_runtime_input.v1",
    work_unit_id: workUnitId,
    mission_id: "mission-001",
    iteration: 1,
    workspace_root: ".",
    attempt_dir_ref: attempt,
    input_ref: `${attempt}/pi_agent_input.json`,
    output_ref: `${attempt}/pi_agent_output.json`,
    session_ref: `${attempt}/pi_agent_session.jsonl`,
    events_ref: `${attempt}/pi_agent_events.jsonl`,
    metrics_ref: `${attempt}/pi_agent_metrics.json`,
    savepoints_ref: `${attempt}/pi_agent_savepoints.jsonl`,
    piworker_call: {
      schema_version: "piworker_call.v1",
      call_id: workUnitId,
      role: "executor_piworker",
      contract_id: "mission-001",
      contract_hash: `sha256:${"a".repeat(64)}`,
      contract_ref: "contract/task_contract.json",
      objective: "Produce a deterministic artifact.",
      visible_refs: [],
      writable_refs: [`${attempt}`],
      expected_output_refs: [`${attempt}/artifact.txt`],
      permission_manifest_ref: null,
      source_packet_ref: null,
      source_packet_hash: null,
      evidence_refs: [],
      output_schema_ref: "schemas/agent_execution_report.json",
      validation_policy_ref: "validation/piworker_executor_policy.json",
      runtime_budget: {},
      metadata: {},
    },
    contract: {
      work_unit_id: workUnitId,
      mission_id: "mission-001",
      iteration: 1,
      next_objective: "Produce a deterministic artifact.",
      allowed_scope: [`${attempt}`],
      visible_refs: [],
      expected_outputs: [`${attempt}/artifact.txt`],
      exit_criteria: ["Expected artifact exists."],
      stop_conditions: ["Timeout."],
    },
    permission_manifest: {
      manifest_id: `${workUnitId}-pi-runtime-permissions`,
      schema_version: "permission_manifest.v1",
      workspace_policy_ref: null,
      readable_refs: [`${attempt}`],
      writable_refs: [`${attempt}`],
      denied_refs: [],
      allowed_commands: [],
      network_policy: "disabled",
      env_allowlist: [],
      secret_ref: null,
      unsupported_hard_policies: [],
    },
    runtime: {
      runtime_name: "missionforge.pi_agent_runtime",
      timeout_seconds: 60,
      model: null,
      metadata: {},
    },
    repair: {
      mode: "none",
      verifier_failures: [],
      failed_constraints: [],
      previous_output_ref: null,
      repair_prompt: null,
    },
    resume: {
      mode: "none",
      boundary: null,
      savepoint_ref: null,
      session_ref: null,
      events_ref: null,
      resume_prompt: null,
    },
    ...overrides,
  };
}

export async function writeInput(root, input) {
  const path = join(root, input.input_ref);
  await mkdir(join(root, input.attempt_dir_ref), { recursive: true });
  await writeFile(path, `${JSON.stringify(input, null, 2)}\n`, "utf-8");
  return path;
}

export async function readJson(path) {
  return JSON.parse(await readFile(path, "utf-8"));
}
