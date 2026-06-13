import assert from "node:assert/strict";
import { mkdir, writeFile } from "node:fs/promises";
import { join } from "node:path";
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

    assert.deepEqual(output.produced_artifacts, [
      "frontdesk/decision_tree.json",
      "frontdesk/need_grilling_report.json",
      "frontdesk/core_need_brief.json",
    ]);
    assert.equal(output.produced_artifacts.includes("frontdesk/unplanned.json"), false);
  });
});
