import { mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";

const DEFAULT_CONTRACT_HASH = `sha256:${"a".repeat(64)}`;

export async function withWorkspace(fn) {
  const root = await mkdtemp(join(tmpdir(), "mf-pi-agent-"));
  try {
    await fn(root);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
}

export function sampleInput(overrides = {}) {
  const callId = "WU-000001";
  const attempt = `attempts/${callId}`;
  const input = {
    schema_version: "missionforge.pi_agent_runtime_input.v1",
    call_id: callId,
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
    context_observations_ref: `${attempt}/context/tool_observations.jsonl`,
    context_projection_ref: `${attempt}/context/projection.json`,
    context_raw_dir_ref: `${attempt}/context/raw`,
    context_projection_config: {
      schema_version: "missionforge.pi_agent_context_projection_config.v1",
      large_observation_bytes: 8192,
    },
    piworker_call: {
      schema_version: "piworker_call.v1",
      call_id: callId,
      role: "executor_piworker",
      contract_id: "mission-001",
      contract_hash: DEFAULT_CONTRACT_HASH,
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
    call_spec: {
      call_id: callId,
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
      manifest_id: `${callId}-pi-runtime-permissions`,
      schema_version: "permission_manifest.v1",
      workspace_policy_ref: `${attempt}/runtime_workspace_policy.json`,
      readable_refs: [`${attempt}`],
      writable_refs: [`${attempt}`],
      denied_refs: [],
      allowed_commands: [],
      network_policy: "disabled",
      env_allowlist: [],
      secret_ref: null,
      unsupported_hard_policies: [],
    },
    capability_grant: null,
    sandbox_profile: null,
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
      summary_artifact_refs: [],
      resume_prompt: null,
    },
    ...overrides,
  };
  input.capability_grant = overrides.capability_grant ?? sampleCapabilityGrant(input);
  input.sandbox_profile = overrides.sandbox_profile ?? sampleSandboxProfile(input);
  return input;
}

function sampleCapabilityGrant(input) {
  const piworkerCall = input.piworker_call && typeof input.piworker_call === "object" ? input.piworker_call : {};
  const manifest = input.permission_manifest && typeof input.permission_manifest === "object" ? input.permission_manifest : {};
  return {
    schema_version: "runtime_capability_grant.v1",
    grant_id: `${input.call_id}-pi-runtime-grant`,
    role: piworkerCall.role ?? "executor_piworker",
    contract_hash: piworkerCall.contract_hash ?? DEFAULT_CONTRACT_HASH,
    workspace_policy_ref:
      manifest.workspace_policy_ref ?? `${input.attempt_dir_ref}/runtime_workspace_policy.json`,
    permission_manifest_ref: `${input.attempt_dir_ref}/runtime_permission_manifest.json`,
    workspace_view_ref: `${input.attempt_dir_ref}/workspace_view`,
    sandbox_profile_ref: `${input.attempt_dir_ref}/sandbox_profile.json`,
    issued_by: "missionforge.test",
    issued_at: "2026-06-13T00:00:00.000Z",
    expires_at: "2999-01-01T00:00:00.000Z",
    parent_grant_ref: null,
    revoked_at: null,
    metadata: {
      call_id: input.call_id,
      runtime: "missionforge.pi_agent_runtime",
      source_permission_manifest_ref: piworkerCall.permission_manifest_ref ?? null,
    },
  };
}

function sampleSandboxProfile(input) {
  const manifest = input.permission_manifest && typeof input.permission_manifest === "object" ? input.permission_manifest : {};
  return {
    schema_version: "sandbox_profile.v1",
    profile_id: `${input.call_id}-pi-runtime-sandbox`,
    mode: "bubblewrap",
    workspace_root_ref: `${input.attempt_dir_ref}/workspace_view`,
    readable_refs: [...(manifest.readable_refs ?? [])],
    writable_refs: [...(manifest.writable_refs ?? [])],
    denied_refs: [...(manifest.denied_refs ?? [])],
    network_enabled: manifest.network_policy === "enabled",
    env_allowlist: [...(manifest.env_allowlist ?? [])],
    command_allowlist: [...(manifest.allowed_commands ?? [])],
    resource_budget: {
      timeout_seconds: input.runtime.timeout_seconds,
    },
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
