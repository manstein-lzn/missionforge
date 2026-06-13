import assert from "node:assert/strict";
import test from "node:test";

import { parseRuntimeInput } from "../dist/contract.js";
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
        resume_prompt: "Continue from the last completed turn.",
      },
    }),
  );

  assert.equal(input.resume.mode, "follow_up");
  assert.equal(input.resume.boundary, "after_completed_turn");
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
