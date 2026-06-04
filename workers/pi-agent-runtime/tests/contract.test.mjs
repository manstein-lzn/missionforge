import assert from "node:assert/strict";
import test from "node:test";

import { parseRuntimeInput } from "../dist/contract.js";
import { sampleInput } from "./helpers.mjs";

test("parseRuntimeInput accepts valid input", () => {
  const input = parseRuntimeInput(sampleInput());
  assert.equal(input.schema_version, "missionforge.pi_agent_runtime_input.v1");
  assert.equal(input.work_unit_id, "WU-000001");
  assert.equal(input.piworker_call.call_id, "WU-000001");
  assert.deepEqual(input.piworker_call.expected_output_refs, ["attempts/WU-000001/artifact.txt"]);
  assert.equal(input.permission_manifest.schema_version, "permission_manifest.v1");
  assert.deepEqual(input.permission_manifest.writable_refs, ["attempts/WU-000001"]);
});

test("parseRuntimeInput accepts legacy input without PiWorkerCall", () => {
  const payload = sampleInput({ piworker_call: null });
  const input = parseRuntimeInput(payload);
  assert.equal(input.piworker_call, null);
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
