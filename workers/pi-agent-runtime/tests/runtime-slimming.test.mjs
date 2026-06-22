import assert from "node:assert/strict";
import { readdir, readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { join } from "node:path";
import test from "node:test";

const runtimeRoot = fileURLToPath(new URL("..", import.meta.url));

test("package exposes only the main Pi agent runtime binary", async () => {
  const packageJson = JSON.parse(await readFile(new URL("../package.json", import.meta.url), "utf-8"));

  assert.deepEqual(packageJson.bin, {
    "missionforge-pi-agent-runtime": "./dist/main.js",
  });
});

test("source and test trees do not retain the retired auxiliary runtime", async () => {
  const disallowed = new Set([
    "direct-contract.ts",
    "direct-evidence-recorder.ts",
    "direct-main.ts",
    "direct-runner.ts",
    "direct-runner.test.mjs",
  ]);
  const sourceFiles = await readdir(join(runtimeRoot, "src"));
  const testFiles = await readdir(join(runtimeRoot, "tests"));

  for (const fileName of [...sourceFiles, ...testFiles]) {
    assert.equal(disallowed.has(fileName), false, `${fileName} should not be present`);
  }
});
