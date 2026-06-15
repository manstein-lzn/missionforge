import assert from "node:assert/strict";
import { access, mkdir, mkdtemp, readFile, rm, symlink, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";

import { runMissionForgePiAgent } from "../dist/runtime.js";
import { createMissionForgeTools } from "../dist/tools.js";
import { ToolGateway } from "../dist/tool-gateway.js";
import { filterEnvByAllowlist, refIsUnder } from "../dist/permissions.js";
import { parseRuntimeInput } from "../dist/contract.js";
import { appendJsonLine, writeJsonFile } from "../dist/paths.js";
import { readJson, sampleInput, withWorkspace, writeInput } from "./helpers.mjs";

test("ref matching is segment-aware", () => {
  assert.equal(refIsUnder("outputs/report.md", "outputs"), true);
  assert.equal(refIsUnder("outputs-private/report.md", "outputs"), false);
});

test("file tools enforce read, write, and denied refs", async () => {
  await withWorkspace(async (root) => {
    await mkdir(join(root, "inputs/private"), { recursive: true });
    await mkdir(join(root, "outputs/private"), { recursive: true });
    await writeFile(join(root, "inputs/public.txt"), "public\n", "utf-8");
    await writeFile(join(root, "inputs/private/secret.txt"), "secret\n", "utf-8");

    const tools = await createMissionForgeTools({
      workspaceRoot: root,
      permissionManifest: samplePermissionManifest(),
      toolTimeoutSeconds: 30,
    });
    const read = tool(tools, "read");
    const write = tool(tools, "write");

    const readResult = await read.execute("read-1", { path: "inputs/public.txt" });
    assert.equal(readResult.content[0].text.includes("public"), true);

    await assert.rejects(
      () => read.execute("read-private", { path: "inputs/private/secret.txt" }),
      /permission denied.*denied/,
    );
    await assert.rejects(
      () => read.execute("read-outside", { path: "other/file.txt" }),
      /outside allowed roots/,
    );

    await write.execute("write-ok", { path: "outputs/result.txt", content: "ok\n" });
    assert.equal(await readFile(join(root, "outputs/result.txt"), "utf-8"), "ok\n");

    await assert.rejects(
      () => write.execute("write-private", { path: "outputs/private/result.txt", content: "no\n" }),
      /permission denied.*denied/,
    );
    await assert.rejects(
      () => write.execute("write-outside", { path: "other/result.txt", content: "no\n" }),
      /outside (allowed|writable) roots/,
    );
  });
});

test("sandbox profile narrows the effective tool boundary", async () => {
  await withWorkspace(async (root) => {
    await mkdir(join(root, "inputs"), { recursive: true });
    await mkdir(join(root, "outputs"), { recursive: true });
    await writeFile(join(root, "inputs/public.txt"), "public\n", "utf-8");
    await writeFile(join(root, "inputs/hidden.txt"), "hidden\n", "utf-8");

    const tools = await createMissionForgeTools({
      workspaceRoot: root,
      permissionManifest: samplePermissionManifest({
        readable_refs: ["inputs"],
        writable_refs: ["outputs"],
        denied_refs: [],
      }),
      sandboxProfile: {
        schema_version: "sandbox_profile.v1",
        profile_id: "narrow-profile",
        mode: "bubblewrap",
        workspace_root_ref: "attempts/WU-000001/workspace_view",
        readable_refs: ["inputs/public.txt"],
        writable_refs: ["outputs/result.txt"],
        denied_refs: [],
        network_enabled: false,
        env_allowlist: [],
        command_allowlist: [],
        resource_budget: {},
      },
      toolTimeoutSeconds: 30,
    });
    const read = tool(tools, "read");
    const write = tool(tools, "write");

    const readResult = await read.execute("read-public", { path: "inputs/public.txt" });
    assert.equal(readResult.content[0].text.includes("public"), true);
    await assert.rejects(
      () => read.execute("read-hidden", { path: "inputs/hidden.txt" }),
      /outside allowed roots/,
    );

    await write.execute("write-result", { path: "outputs/result.txt", content: "ok\n" });
    await assert.rejects(
      () => write.execute("write-other", { path: "outputs/other.txt", content: "no\n" }),
      /outside (allowed|writable) roots/,
    );
  });
});

test("bash tool is hidden when no command is allowed", async () => {
  await withWorkspace(async (root) => {
    const tools = await createMissionForgeTools({
      workspaceRoot: root,
      permissionManifest: samplePermissionManifest(),
      toolTimeoutSeconds: 30,
    });

    assert.equal(tools.some((candidate) => candidate.name === "bash"), false);
  });
});

test("bash requires explicit command permission and exposes only allowlisted env", async () => {
  await withWorkspace(async (root) => {
    const command = "printf '%s|%s' \"${VISIBLE_ENV:-}\" \"${SECRET_ENV:-}\"";
    const tools = await createMissionForgeTools({
      workspaceRoot: root,
      permissionManifest: {
        ...samplePermissionManifest({
          readable_refs: [],
          writable_refs: [],
          denied_refs: [],
          network_policy: "enabled",
        }),
        allowed_commands: [command],
        env_allowlist: ["PATH", "VISIBLE_ENV"],
      },
      toolTimeoutSeconds: 30,
    });
    const bash = tool(tools, "bash");
    const previousVisible = process.env.VISIBLE_ENV;
    const previousSecret = process.env.SECRET_ENV;
    process.env.VISIBLE_ENV = "visible";
    process.env.SECRET_ENV = "secret";
    try {
      await assert.rejects(
        () => bash.execute("bash-denied", { command: "echo denied" }),
        /allowed_commands/,
      );
      const result = await bash.execute("bash-allowed", { command });
      assert.equal(result.content[0].text.trim(), "visible|");
    } finally {
      restoreEnv("VISIBLE_ENV", previousVisible);
      restoreEnv("SECRET_ENV", previousSecret);
    }
  });
});

test("bash runs inside ref-scoped sandbox when command is explicitly allowed", async () => {
  await withWorkspace(async (root) => {
    await mkdir(join(root, "inputs/private"), { recursive: true });
    await mkdir(join(root, "outputs/private"), { recursive: true });
    await writeFile(join(root, "inputs/public.txt"), "public\n", "utf-8");
    await writeFile(join(root, "inputs/private/secret.txt"), "secret\n", "utf-8");
    const command = [
      "cat inputs/public.txt",
      "if [ -e inputs/private/secret.txt ]; then echo private-visible; else echo private-hidden; fi",
      "printf ok > outputs/result.txt",
      "if printf no > outputs/private/result.txt 2>/dev/null; then echo denied-write-succeeded; else echo denied-write-blocked; fi",
    ].join("; ");
    const tools = await createMissionForgeTools({
      workspaceRoot: root,
      permissionManifest: {
        ...samplePermissionManifest(),
        allowed_commands: [command],
        env_allowlist: ["PATH"],
      },
      toolTimeoutSeconds: 30,
      knownFileRefs: ["inputs/public.txt", "inputs/private/secret.txt", "outputs/result.txt"],
    });
    const bash = tool(tools, "bash");

    const result = await bash.execute("bash-sandboxed", { command });

    assert.equal(result.content[0].text.includes("public"), true);
    assert.equal(result.content[0].text.includes("private-hidden"), true);
    assert.equal(result.content[0].text.includes("denied-write-blocked"), true);
    assert.equal(await readFile(join(root, "outputs/result.txt"), "utf-8"), "ok");
    await assert.rejects(() => access(join(root, "outputs/private/result.txt")));
  });
});

test("sandboxed bash cannot read host paths outside the workspace view", async () => {
  const outside = await mkdtemp(join(tmpdir(), "mf-pi-agent-host-"));
  try {
    await withWorkspace(async (root) => {
      await mkdir(join(root, "outputs"), { recursive: true });
      await writeFile(join(outside, "secret.txt"), "outside secret\n", "utf-8");
      const command = `if cat ${JSON.stringify(join(outside, "secret.txt"))} 2>/dev/null; then echo host-visible; else echo host-hidden; fi`;
      const tools = await createMissionForgeTools({
        workspaceRoot: root,
        permissionManifest: {
          ...samplePermissionManifest({
            readable_refs: [],
            writable_refs: ["outputs"],
            denied_refs: [],
            network_policy: "enabled",
          }),
          allowed_commands: [command],
          env_allowlist: ["PATH"],
        },
        toolTimeoutSeconds: 30,
      });
      const bash = tool(tools, "bash");

      const result = await bash.execute("bash-host-hidden", { command });

      assert.equal(result.content[0].text.includes("host-hidden"), true);
      assert.equal(result.content[0].text.includes("outside secret"), false);
    });
  } finally {
    await rm(outside, { recursive: true, force: true });
  }
});

test("write tool can create a root-level file when that exact ref is writable", async () => {
  await withWorkspace(async (root) => {
    const tools = await createMissionForgeTools({
      workspaceRoot: root,
      permissionManifest: {
        ...samplePermissionManifest(),
        readable_refs: ["artifact.txt"],
        writable_refs: ["artifact.txt"],
        denied_refs: [],
      },
      toolTimeoutSeconds: 30,
    });
    const write = tool(tools, "write");

    await write.execute("write-root-file", { path: "artifact.txt", content: "root\n" });

    assert.equal(await readFile(join(root, "artifact.txt"), "utf-8"), "root\n");
  });
});

test("file tools reject symlink escapes before touching outside paths", async () => {
  const outside = await mkdtemp(join(tmpdir(), "mf-pi-agent-outside-"));
  try {
    await withWorkspace(async (root) => {
      await mkdir(join(root, "inputs"), { recursive: true });
      await mkdir(join(root, "outputs"), { recursive: true });
      await writeFile(join(outside, "secret.txt"), "outside secret\n", "utf-8");
      await symlink(outside, join(root, "inputs/link"), "dir");
      await symlink(outside, join(root, "outputs/link"), "dir");
      const tools = await createMissionForgeTools({
        workspaceRoot: root,
        permissionManifest: samplePermissionManifest({
          readable_refs: ["inputs"],
          writable_refs: ["outputs"],
          denied_refs: [],
        }),
        toolTimeoutSeconds: 30,
      });
      const read = tool(tools, "read");
      const write = tool(tools, "write");

      await assert.rejects(
        () => read.execute("read-symlink", { path: "inputs/link/secret.txt" }),
        /symlink/,
      );
      await assert.rejects(
        () => write.execute("write-symlink", { path: "outputs/link/result.txt", content: "no\n" }),
        /symlink/,
      );
      await assert.rejects(() => access(join(outside, "result.txt")));
    });
  } finally {
    await rm(outside, { recursive: true, force: true });
  }
});

test("runtime-owned writes reject symlink escapes before touching outside paths", async () => {
  const outside = await mkdtemp(join(tmpdir(), "mf-pi-agent-outside-"));
  try {
    await withWorkspace(async (root) => {
      await mkdir(join(root, "attempts/WU-000001"), { recursive: true });
      await symlink(outside, join(root, "attempts/WU-000001/link"), "dir");
      const escapedOutput = join(root, "attempts/WU-000001/link/output.json");
      const escapedEvents = join(root, "attempts/WU-000001/link/events.jsonl");

      await assert.rejects(
        () => writeJsonFile(escapedOutput, { ok: true }, { workspaceRoot: root }),
        /symlink/,
      );
      await assert.rejects(
        () => appendJsonLine(escapedEvents, { ok: true }, { workspaceRoot: root }),
        /symlink/,
      );
      await assert.rejects(() => access(join(outside, "output.json")));
      await assert.rejects(() => access(join(outside, "events.jsonl")));
    });
  } finally {
    await rm(outside, { recursive: true, force: true });
  }
});

test("env filtering keeps only allowlisted names", () => {
  assert.deepEqual(
    filterEnvByAllowlist(
      {
        PATH: "/bin",
        SECRET_ENV: "secret",
        VISIBLE_ENV: "visible",
      },
      ["PATH", "VISIBLE_ENV"],
    ),
    {
      PATH: "/bin",
      VISIBLE_ENV: "visible",
    },
  );
});

test("tool gateway records refs-first decisions without raw command or env values", async () => {
  await withWorkspace(async (root) => {
    await mkdir(join(root, "inputs"), { recursive: true });
    await writeFile(join(root, "inputs/public.txt"), "public\n", "utf-8");
    const decisions = [];
    const gateway = new ToolGateway({
      workspaceRoot: root,
      permissionManifest: {
        ...samplePermissionManifest({
          readable_refs: ["inputs"],
          writable_refs: ["outputs"],
          denied_refs: ["inputs/private"],
          allowed_commands: ["echo allowed-secret-text"],
          env_allowlist: ["VISIBLE_ENV"],
        }),
      },
      onDecision: (decision) => decisions.push(decision),
    });

    gateway.authorizeReadPath("read", join(root, "inputs/public.txt"));
    assert.throws(
      () => gateway.authorizeCommand("echo denied-secret-text"),
      /allowed_commands/,
    );
    gateway.filterEnv({
      VISIBLE_ENV: "visible-secret-value",
      SECRET_ENV: "hidden-secret-value",
    });

    const serialized = JSON.stringify(decisions);
    assert.equal(serialized.includes("inputs/public.txt"), true);
    assert.equal(serialized.includes("echo allowed-secret-text"), false);
    assert.equal(serialized.includes("echo denied-secret-text"), false);
    assert.equal(serialized.includes("visible-secret-value"), false);
    assert.equal(serialized.includes("hidden-secret-value"), false);
    assert.equal(decisions.some((decision) => decision.operation === "read_path" && decision.status === "allowed"), true);
    assert.equal(decisions.some((decision) => decision.operation === "bash_command" && decision.status === "denied"), true);
    assert.equal(decisions.some((decision) => decision.operation === "env" && decision.env_names.includes("VISIBLE_ENV")), true);
  });
});

test("unsupported hard policies fail before worker tools run and are reported in output", async () => {
  await withWorkspace(async (root) => {
    const input = sampleInput({
      permission_manifest: {
        ...sampleInput().permission_manifest,
        unsupported_hard_policies: ["process_network_namespace"],
      },
    });
    await writeInput(root, input);
    process.env.MISSIONFORGE_PI_AGENT_PROVIDER = "faux";
    try {
      await runMissionForgePiAgent(parseRuntimeInput(input), root);
    } finally {
      delete process.env.MISSIONFORGE_PI_AGENT_PROVIDER;
    }

    const output = await readJson(join(root, input.output_ref));
    assert.equal(output.status, "failed");
    assert.equal(output.produced_artifacts.length, 0);
    assert.equal(output.failures.join("\n").includes("unsupported hard permission policies"), true);
    await assert.rejects(() => access(join(root, input.call_spec.expected_outputs[0])));
  });
});

function samplePermissionManifest(overrides = {}) {
  return {
    manifest_id: "test-permissions",
    schema_version: "permission_manifest.v1",
    workspace_policy_ref: null,
    readable_refs: ["inputs"],
    writable_refs: ["outputs"],
    denied_refs: ["inputs/private", "outputs/private"],
    allowed_commands: [],
    network_policy: "disabled",
    env_allowlist: [],
    secret_ref: null,
    unsupported_hard_policies: [],
    ...overrides,
  };
}

function tool(tools, name) {
  const found = tools.find((candidate) => candidate.name === name);
  if (!found) throw new Error(`missing tool ${name}`);
  return found;
}

function restoreEnv(name, previous) {
  if (previous === undefined) {
    delete process.env[name];
  } else {
    process.env[name] = previous;
  }
}
