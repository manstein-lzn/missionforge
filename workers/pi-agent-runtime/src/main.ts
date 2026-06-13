#!/usr/bin/env node

import { dirname, resolve } from "node:path";

import { parseRuntimeInput } from "./contract.js";
import { readJsonFile, resolveWorkspaceRef, writeJsonFile } from "./paths.js";
import { redactText } from "./redaction.js";
import { runMissionForgePiAgent } from "./runtime.js";

async function main(argv: string[]): Promise<number> {
  const inputPath = argv[2];
  if (!inputPath) {
    console.error("usage: missionforge-pi-agent-runtime <pi_agent_input.json>");
    return 2;
  }

  const absoluteInputPath = resolve(inputPath);
  let input: ReturnType<typeof parseRuntimeInput> | undefined;
  let workspaceRoot = process.cwd();
  try {
    input = parseRuntimeInput(await readJsonFile(absoluteInputPath));
    workspaceRoot = resolve(dirname(absoluteInputPath), relativeBackToRoot(input.input_ref));
    resolveWorkspaceRef(workspaceRoot, input.input_ref);
    await runMissionForgePiAgent(input, workspaceRoot);
    return 0;
  } catch (error) {
    const message = redactText(error instanceof Error ? error.message : String(error));
    console.error(message);
    if (input) {
      await writeJsonFile(
        resolveWorkspaceRef(workspaceRoot, input.output_ref),
        {
          schema_version: "missionforge.pi_agent_runtime_output.v1",
          call_id: input.call_id,
          status: "failed",
          produced_artifacts: [],
          changed_refs: [input.output_ref, input.savepoints_ref],
          commands_run: [],
          tests_run: [],
          failures: [message],
          worker_claims: [],
          verifier_evidence: [input.output_ref, input.savepoints_ref],
          new_unknowns: input.call_spec.expected_outputs,
          recommended_next_steps: ["Inspect pi-agent-runtime startup failure."],
          verification_status: "failed",
          input_ref: input.input_ref,
          output_ref: input.output_ref,
          session_ref: input.session_ref,
          events_ref: input.events_ref,
          metrics_ref: input.metrics_ref,
          savepoints_ref: input.savepoints_ref,
          duration_ms: 0,
          metrics: {},
        },
        { workspaceRoot },
      );
    }
    return 1;
  }
}

function relativeBackToRoot(inputRef: string): string {
  const depth = inputRef.split("/").length - 1;
  return depth <= 0 ? "." : Array(depth).fill("..").join("/");
}

main(process.argv).then((code) => {
  process.exitCode = code;
});
