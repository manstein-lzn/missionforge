#!/usr/bin/env node

import { dirname, resolve } from "node:path";

import { parseDirectRuntimeInput } from "./direct-contract.js";
import { buildDirectFailureOutput, runDirectPiWorkerBenchmark, writeDirectOutput } from "./direct-runner.js";
import { readJsonFile, resolveWorkspaceRef } from "./paths.js";
import { redactText } from "./redaction.js";

async function main(argv: string[]): Promise<number> {
  const inputPath = argv[2];
  if (!inputPath) {
    console.error("usage: missionforge-pi-agent-direct-benchmark <direct_piworker_input.json>");
    return 2;
  }

  const absoluteInputPath = resolve(inputPath);
  let input: ReturnType<typeof parseDirectRuntimeInput> | undefined;
  let workspaceRoot = process.cwd();
  const started = Date.now();
  try {
    input = parseDirectRuntimeInput(await readJsonFile(absoluteInputPath));
    workspaceRoot = resolve(dirname(absoluteInputPath), relativeBackToRoot(input.input_ref));
    resolveWorkspaceRef(workspaceRoot, input.input_ref);
    await runDirectPiWorkerBenchmark(input, workspaceRoot);
    return 0;
  } catch (error) {
    const message = redactText(error instanceof Error ? error.message : String(error));
    console.error(message);
    if (input) {
      await writeDirectOutput(
        workspaceRoot,
        input,
        buildDirectFailureOutput(input, message, Date.now() - started),
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
