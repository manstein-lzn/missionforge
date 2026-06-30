import assert from "node:assert/strict";
import test from "node:test";

import { parseRuntimeInput } from "../dist/contract.js";
import { extensionLoadReportFromLock } from "../dist/extensions.js";
import { sampleInput } from "./helpers.mjs";

test("parseRuntimeInput accepts valid input", () => {
  const input = parseRuntimeInput(sampleInput());
  assert.equal(input.schema_version, "missionforge.pi_agent_runtime_input.v1");
  assert.equal(input.call_id, "WU-000001");
  assert.equal(input.piworker_call.call_id, "WU-000001");
  assert.deepEqual(input.piworker_call.expected_output_refs, ["attempts/WU-000001/artifact.txt"]);
  assert.equal(input.permission_manifest.schema_version, "permission_manifest.v1");
  assert.deepEqual(input.permission_manifest.writable_refs, ["attempts/WU-000001"]);
  assert.equal(input.capability_grant.schema_version, "runtime_capability_grant.v1");
  assert.equal(input.capability_grant.role, "executor_piworker");
  assert.equal(input.sandbox_profile.schema_version, "sandbox_profile.v1");
  assert.deepEqual(input.sandbox_profile.writable_refs, ["attempts/WU-000001"]);
  assert.equal(input.context_observations_ref, "attempts/WU-000001/context/tool_observations.jsonl");
  assert.equal(input.context_projection_ref, "attempts/WU-000001/context/projection.json");
  assert.equal(input.context_raw_dir_ref, "attempts/WU-000001/context/raw");
  assert.equal(input.long_memory_packet_ref, null);
  assert.deepEqual(input.context_projection_config, {
    schema_version: "missionforge.pi_agent_context_projection_config.v1",
    large_observation_bytes: 8192,
    soft_compact_ratio: 0.8,
    hard_compact_ratio: 0.9,
    cache_aware: true,
  });
  assert.deepEqual(input.context_engine, {
    schema_version: "missionforge.pi_agent_context_engine.v1",
    enabled: false,
    context_view_ref: null,
    context_compile_request_ref: null,
    context_compile_result_ref: null,
    context_baseline_ref: null,
    context_source_snapshot_ref: null,
    context_epoch_ref: null,
    context_cache_layout_ref: null,
    context_pressure_ref: null,
    context_turn_safe_point_ref: null,
    context_turn_boundary_ref: null,
    context_hash: null,
    context_compile_action: "",
  });
});

test("extensionLoadReportFromLock rejects lock entries outside manifest grants", () => {
  const grant = {
    grant_id: "web-search",
    package: "npm:pi-web-access",
    version_spec: "0.10.7",
    capability: "web",
    requires_network: true,
    requires_bash: false,
    required_env: ["SEARCH_API_KEY"],
    adapter_mode: "untrusted_pi_extension",
    config_ref: null,
    sandbox_profile_ref: null,
    integrity: null,
    metadata: {},
  };
  const input = parseRuntimeInput(
    sampleInput({
      extension_lock_ref: "attempts/WU-000001/extension_lock.json",
      permission_manifest: {
        ...sampleInput().permission_manifest,
        network_policy: "enabled",
        env_allowlist: ["SEARCH_API_KEY"],
        extension_grants: [grant],
      },
    }),
  );
  const entry = {
    grant_id: "web-search",
    package: "npm:pi-web-access",
    name: "pi-web-access",
    version: "0.10.7",
    capability: "web",
    install_path: ".missionforge/extensions/node_modules/pi-web-access",
    adapter_mode: "untrusted_pi_extension",
    requires_network: true,
    requires_bash: false,
    required_env: ["SEARCH_API_KEY"],
    resolved: null,
    integrity: null,
    package_hash: null,
    metadata: {},
  };
  const report = extensionLoadReportFromLock(input, {
    schema_version: "missionforge_extension_lock.v1",
    source_permission_manifest_ref: "attempts/WU-000001/runtime_permission_manifest.json",
    compiled_at: "2026-06-15T00:00:00.000Z",
    install_root_ref: ".missionforge/extensions",
    compiled_by: "missionforge.extensions",
    extensions: [
      entry,
      {
        ...entry,
        grant_id: "unauthorized-web-search",
      },
    ],
  });

  assert.deepEqual(
    report.rejected_extensions.map((record) => `${record.grant_id}:${record.reason}`),
    ["unauthorized-web-search:extra_lock_entry"],
  );
});

test("parseRuntimeInput accepts ContextEngine refs", () => {
  const input = parseRuntimeInput(
    sampleInput({
      context_engine: {
        schema_version: "missionforge.pi_agent_context_engine.v1",
        enabled: true,
        context_view_ref: "kernel/demo/steps/researcher/context_projection.json",
        context_compile_result_ref: "kernel/demo/steps/researcher/context/compile_result.json",
        context_cache_layout_ref: "kernel/demo/steps/researcher/context/cache_layout.json",
        context_pressure_ref: "kernel/demo/steps/researcher/context/pressure.json",
        context_hash: `sha256:${"b".repeat(64)}`,
        context_compile_action: "continue",
      },
    }),
  );

  assert.equal(input.context_engine.enabled, true);
  assert.equal(input.context_engine.context_view_ref, "kernel/demo/steps/researcher/context_projection.json");
  assert.equal(input.context_engine.context_compile_result_ref, "kernel/demo/steps/researcher/context/compile_result.json");
  assert.equal(input.context_engine.context_cache_layout_ref, "kernel/demo/steps/researcher/context/cache_layout.json");
  assert.equal(input.context_engine.context_pressure_ref, "kernel/demo/steps/researcher/context/pressure.json");
});

test("parseRuntimeInput rejects enabled ContextEngine without required refs", () => {
  assert.throws(
    () =>
      parseRuntimeInput(
        sampleInput({
          context_engine: {
            schema_version: "missionforge.pi_agent_context_engine.v1",
            enabled: true,
            context_view_ref: "kernel/demo/steps/researcher/context_projection.json",
          },
        }),
      ),
    /enabled requires context_view_ref and context_compile_result_ref/,
  );
});

test("parseRuntimeInput fails closed without PiWorkerCall", () => {
  const payload = sampleInput({ piworker_call: null });
  assert.throws(() => parseRuntimeInput(payload), /piworker_call/);
});

test("parseRuntimeInput rejects PiWorkerCall authority mismatch", () => {
  const payload = sampleInput({
    piworker_call: {
      ...sampleInput().piworker_call,
      contract_id: "other-mission",
    },
  });
  assert.throws(() => parseRuntimeInput(payload), /contract_id must match mission_id/);
});

test("parseRuntimeInput rejects PiWorkerCall output outside writable refs", () => {
  const payload = sampleInput({
    piworker_call: {
      ...sampleInput().piworker_call,
      expected_output_refs: ["outside/artifact.txt"],
    },
  });
  assert.throws(() => parseRuntimeInput(payload), /inside writable_refs/);
});

test("parseRuntimeInput rejects escaping refs", () => {
  const payload = sampleInput({ output_ref: "../escape.json" });
  assert.throws(() => parseRuntimeInput(payload), /workspace-relative/);
});

test("parseRuntimeInput rejects context refs outside the attempt directory", () => {
  assert.throws(
    () => parseRuntimeInput(sampleInput({ context_observations_ref: "context/tool_observations.jsonl" })),
    /context_observations_ref must be inside attempt_dir_ref/,
  );
  assert.throws(
    () => parseRuntimeInput(sampleInput({ context_projection_ref: "context/projection.json" })),
    /context_projection_ref must be inside attempt_dir_ref/,
  );
  assert.throws(
    () => parseRuntimeInput(sampleInput({ context_raw_dir_ref: "context/raw" })),
    /context_raw_dir_ref must be inside attempt_dir_ref/,
  );
});

test("parseRuntimeInput accepts long memory packet refs inside the attempt directory", () => {
  const input = parseRuntimeInput(
    sampleInput({
      long_memory_packet_ref: "attempts/WU-000001/context/long_memory_packet.json",
    }),
  );

  assert.equal(input.long_memory_packet_ref, "attempts/WU-000001/context/long_memory_packet.json");
});

test("parseRuntimeInput rejects long memory packet refs outside the attempt directory", () => {
  assert.throws(
    () =>
      parseRuntimeInput(
        sampleInput({
          long_memory_packet_ref: "context/long_memory_packet.json",
        }),
      ),
    /long_memory_packet_ref must be inside attempt_dir_ref/,
  );
});

test("parseRuntimeInput validates context projection config", () => {
  assert.throws(
    () =>
      parseRuntimeInput(
        sampleInput({
            context_projection_config: {
              schema_version: "missionforge.pi_agent_context_projection_config.v1",
              large_observation_bytes: 0,
            },
          }),
      ),
    /large_observation_bytes must be at least 1/,
  );
});

test("parseRuntimeInput validates compact ratios", () => {
  assert.throws(
    () =>
      parseRuntimeInput(
        sampleInput({
          context_projection_config: {
            schema_version: "missionforge.pi_agent_context_projection_config.v1",
            large_observation_bytes: 8192,
            soft_compact_ratio: 0.9,
            hard_compact_ratio: 0.8,
            cache_aware: true,
          },
        }),
      ),
    /hard_compact_ratio must be greater than soft_compact_ratio/,
  );
});

test("parseRuntimeInput fails closed without permission manifest", () => {
  const payload = sampleInput();
  delete payload.permission_manifest;
  assert.throws(() => parseRuntimeInput(payload), /permission_manifest/);
});

test("parseRuntimeInput fails closed without runtime authority envelope", () => {
  const missingGrant = sampleInput();
  delete missingGrant.capability_grant;
  assert.throws(() => parseRuntimeInput(missingGrant), /capability_grant/);

  const missingProfile = sampleInput();
  delete missingProfile.sandbox_profile;
  assert.throws(() => parseRuntimeInput(missingProfile), /sandbox_profile/);
});

test("parseRuntimeInput rejects runtime authority mismatches", () => {
  const base = sampleInput();
  assert.throws(
    () =>
      parseRuntimeInput(
        sampleInput({
          capability_grant: {
            ...base.capability_grant,
            role: "judge_piworker",
          },
        }),
      ),
    /role must match/,
  );
  assert.throws(
    () =>
      parseRuntimeInput(
        sampleInput({
          capability_grant: {
            ...base.capability_grant,
            contract_hash: `sha256:${"b".repeat(64)}`,
          },
        }),
      ),
    /contract_hash must match/,
  );
  assert.throws(
    () =>
      parseRuntimeInput(
        sampleInput({
          sandbox_profile: {
            ...base.sandbox_profile,
            workspace_root_ref: "attempts/WU-000001/other_view",
          },
        }),
      ),
    /workspace_view_ref must match/,
  );
});

test("parseRuntimeInput rejects inactive grants and unsupported sandbox profiles", () => {
  const base = sampleInput();
  assert.throws(
    () =>
      parseRuntimeInput(
        sampleInput({
          capability_grant: {
            ...base.capability_grant,
            expires_at: "2000-01-01T00:00:00.000Z",
          },
        }),
      ),
    /must be active/,
  );
  assert.throws(
    () =>
      parseRuntimeInput(
        sampleInput({
          capability_grant: {
            ...base.capability_grant,
            revoked_at: "2026-06-13T00:01:00.000Z",
          },
        }),
      ),
    /must not be revoked/,
  );
  assert.throws(
    () =>
      parseRuntimeInput(
        sampleInput({
          sandbox_profile: {
            ...base.sandbox_profile,
            mode: "unsupported",
          },
        }),
      ),
    /sandbox_profile.mode must be supported/,
  );
});

test("parseRuntimeInput rejects sandbox profile and permission manifest drift", () => {
  const base = sampleInput();
  assert.throws(
    () =>
      parseRuntimeInput(
        sampleInput({
          sandbox_profile: {
            ...base.sandbox_profile,
            readable_refs: ["other"],
          },
        }),
      ),
    /readable_refs must match/,
  );
  assert.throws(
    () =>
      parseRuntimeInput(
        sampleInput({
          sandbox_profile: {
            ...base.sandbox_profile,
            command_allowlist: ["python3 -m unittest"],
          },
        }),
      ),
    /command_allowlist must match/,
  );
  assert.throws(
    () =>
      parseRuntimeInput(
        sampleInput({
          sandbox_profile: {
            ...base.sandbox_profile,
            network_enabled: true,
          },
        }),
      ),
    /network_enabled must match/,
  );
});

test("parseRuntimeInput defaults missing repair to none", () => {
  const payload = sampleInput();
  delete payload.repair;
  const input = parseRuntimeInput(payload);
  assert.equal(input.repair.mode, "none");
  assert.deepEqual(input.repair.verifier_failures, []);
});

test("parseRuntimeInput validates follow-up repair envelope", () => {
  const input = parseRuntimeInput(
    sampleInput({
      repair: {
        mode: "follow_up",
        verifier_failures: ["expected artifact was missing"],
        failed_constraints: ["C-artifact"],
        previous_output_ref: "attempts/WU-000001/pi_agent_output.json",
        repair_prompt: "Create the missing artifact.",
      },
    }),
  );

  assert.equal(input.repair.mode, "follow_up");
  assert.equal(input.repair.previous_output_ref, "attempts/WU-000001/pi_agent_output.json");
});

test("parseRuntimeInput rejects invalid repair refs", () => {
  assert.throws(
    () =>
      parseRuntimeInput(
        sampleInput({
          repair: {
            mode: "follow_up",
            verifier_failures: ["missing"],
            failed_constraints: [],
            previous_output_ref: "../escape.json",
            repair_prompt: "fix",
          },
        }),
      ),
    /workspace-relative/,
  );
});

test("parseRuntimeInput validates completed-turn resume envelope", () => {
  const input = parseRuntimeInput(
    sampleInput({
      resume: {
        mode: "follow_up",
        boundary: "after_completed_turn",
        savepoint_ref: "attempts/WU-000001/pi_agent_savepoints.jsonl#turn=1",
        session_ref: "attempts/WU-000001/pi_agent_session.jsonl",
        events_ref: "attempts/WU-000001/pi_agent_events.jsonl",
        checkpoint_refs: ["attempts/WU-000001/context/context_pressure_checkpoint.json"],
        summary_artifact_refs: ["attempts/WU-000001/context/summary.json"],
        resume_prompt: "Continue from the last completed turn.",
      },
    }),
  );

  assert.equal(input.resume.mode, "follow_up");
  assert.equal(input.resume.boundary, "after_completed_turn");
  assert.deepEqual(input.resume.checkpoint_refs, ["attempts/WU-000001/context/context_pressure_checkpoint.json"]);
  assert.deepEqual(input.resume.summary_artifact_refs, ["attempts/WU-000001/context/summary.json"]);
});

test("parseRuntimeInput rejects unsupported resume boundary", () => {
  assert.throws(
    () =>
      parseRuntimeInput(
        sampleInput({
          resume: {
            mode: "follow_up",
            boundary: "mid_tool_call",
            savepoint_ref: "attempts/WU-000001/pi_agent_savepoints.jsonl#turn=1",
            session_ref: "attempts/WU-000001/pi_agent_session.jsonl",
            events_ref: "attempts/WU-000001/pi_agent_events.jsonl",
            resume_prompt: "Continue.",
          },
        }),
      ),
    /resume.boundary/,
  );
});
