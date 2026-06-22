import assert from "node:assert/strict";
import { mkdir, writeFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import test from "node:test";

import { parseRuntimeInput } from "../dist/contract.js";
import { buildRuntimeOutput } from "../dist/result-writer.js";
import { sampleInput, withWorkspace } from "./helpers.mjs";

test("runtime output includes changed exact allowed optional artifacts", async () => {
  await withWorkspace(async (root) => {
    const baseInput = sampleInput();
    const input = parseRuntimeInput(
      sampleInput({
        call_spec: {
          ...baseInput.call_spec,
          allowed_scope: [
            "frontdesk/decision_tree.json",
            "frontdesk/need_grilling_report.json",
            "frontdesk/core_need_brief.json",
            "frontdesk/unplanned",
          ],
          expected_outputs: ["frontdesk/decision_tree.json", "frontdesk/need_grilling_report.json"],
        },
        piworker_call: {
          ...baseInput.piworker_call,
          writable_refs: [
            "frontdesk/decision_tree.json",
            "frontdesk/need_grilling_report.json",
            "frontdesk/core_need_brief.json",
            "frontdesk/unplanned",
          ],
          expected_output_refs: ["frontdesk/decision_tree.json", "frontdesk/need_grilling_report.json"],
        },
      }),
    );
    await mkdir(join(root, "frontdesk"), { recursive: true });
    await writeFile(join(root, "frontdesk/decision_tree.json"), "{}\n", "utf-8");
    await writeFile(join(root, "frontdesk/need_grilling_report.json"), "{}\n", "utf-8");
    await writeFile(join(root, "frontdesk/core_need_brief.json"), "{}\n", "utf-8");
    await writeFile(join(root, "frontdesk/unplanned.json"), "{}\n", "utf-8");

    const output = await buildRuntimeOutput({
      input,
      workspaceRoot: root,
      changedRefs: ["frontdesk/core_need_brief.json", "frontdesk/unplanned.json"],
      commandsRun: [],
      testsRun: [],
      failures: [],
      durationMs: 10,
      metrics: {},
    });

    assert.deepEqual(output.produced_artifacts, ["frontdesk/core_need_brief.json"]);
    assert.equal(output.produced_artifacts.includes("frontdesk/unplanned.json"), false);
    assert.equal(output.failures.includes("expected output was not produced: frontdesk/decision_tree.json"), true);
    assert.equal(output.failures.includes("expected output was not produced: frontdesk/need_grilling_report.json"), true);
  });
});

test("runtime output does not count preexisting expected files as produced artifacts", async () => {
  await withWorkspace(async (root) => {
    const input = parseRuntimeInput(sampleInput());
    await mkdir(join(root, "attempts/WU-000001"), { recursive: true });
    await writeFile(join(root, input.call_spec.expected_outputs[0]), "preexisting placeholder\n", "utf-8");

    const output = await buildRuntimeOutput({
      input,
      workspaceRoot: root,
      changedRefs: [],
      commandsRun: [],
      testsRun: [],
      failures: [],
      durationMs: 10,
      metrics: {},
    });

    assert.equal(output.status, "failed");
    assert.deepEqual(output.produced_artifacts, []);
    assert.equal(output.failures.includes(`expected output was not produced: ${input.call_spec.expected_outputs[0]}`), true);
  });
});

test("runtime output keeps raw context artifacts behind observation index", async () => {
  await withWorkspace(async (root) => {
    const input = parseRuntimeInput(sampleInput());
    await mkdir(join(root, input.context_raw_dir_ref), { recursive: true });
    await writeFile(join(root, `${input.context_raw_dir_ref}/000001-bash-output.txt`), "raw output\n", "utf-8");

    const output = await buildRuntimeOutput({
      input,
      workspaceRoot: root,
      changedRefs: [`${input.context_raw_dir_ref}/000001-bash-output.txt`],
      commandsRun: [],
      testsRun: [],
      failures: [],
      durationMs: 10,
      metrics: {},
    });

    assert.equal(output.changed_refs.includes(`${input.context_raw_dir_ref}/000001-bash-output.txt`), false);
    assert.equal(output.changed_refs.includes(input.context_observations_ref), true);
    assert.equal(output.changed_refs.includes(input.context_projection_ref), true);
    assert.equal(output.verifier_evidence.includes(input.context_observations_ref), true);
    assert.equal(output.verifier_evidence.includes(input.context_projection_ref), true);
  });
});

test("runtime output can mark complete artifacts completed while retaining diagnostic failures", async () => {
  await withWorkspace(async (root) => {
    const input = parseRuntimeInput(sampleInput());
    await mkdir(dirname(join(root, input.call_spec.expected_outputs[0])), { recursive: true });
    await writeFile(join(root, input.call_spec.expected_outputs[0]), "artifact\n", "utf-8");

    const output = await buildRuntimeOutput({
      input,
      workspaceRoot: root,
      changedRefs: [input.call_spec.expected_outputs[0]],
      commandsRun: [],
      testsRun: [],
      failures: ["OpenAI API error (502): transient tail failure"],
      durationMs: 10,
      metrics: {},
      statusOverride: "completed",
    });

    assert.equal(output.status, "completed");
    assert.equal(output.verification_status, "failed");
    assert.equal(output.produced_artifacts.includes(input.call_spec.expected_outputs[0]), true);
    assert.equal(output.failures.includes("OpenAI API error (502): transient tail failure"), true);
    assert.deepEqual(output.new_unknowns, []);
  });
});
