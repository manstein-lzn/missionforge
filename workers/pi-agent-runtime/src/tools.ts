import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname } from "node:path";
import type { AgentTool } from "@earendil-works/pi-agent-core";
import {
  type BashOperations,
  createBashTool,
  createEditTool,
  createReadTool,
  createWriteTool,
  type EditOperations,
  type ReadOperations,
  type WriteOperations,
} from "@earendil-works/pi-coding-agent";

import type { PermissionManifest, SandboxProfile } from "./contract.js";
import { resolveWorkspaceRef } from "./paths.js";
import { assertNoSymlinkSegments, guardWorkspacePath, ToolPermissionEnforcer } from "./permissions.js";
import { createBubblewrapBashOperations } from "./sandbox.js";
import { ToolGateway, type ToolGatewayDecision } from "./tool-gateway.js";

export interface MissionForgeToolOptions {
  workspaceRoot: string;
  permissionManifest: PermissionManifest;
  sandboxProfile?: SandboxProfile;
  toolTimeoutSeconds: number;
  knownFileRefs?: string[];
  knownDirectoryRefs?: string[];
  onToolGatewayDecision?: (decision: ToolGatewayDecision) => void;
}

export function createMissionForgeTools(options: MissionForgeToolOptions): AgentTool<any>[] {
  const cwd = options.workspaceRoot;
  const effectiveManifest = permissionManifestFromSandboxProfile(
    options.permissionManifest,
    options.sandboxProfile,
  );
  const gateway = new ToolGateway({
    workspaceRoot: cwd,
    permissionManifest: effectiveManifest,
    onDecision: options.onToolGatewayDecision,
  });
  const tools: AgentTool<any>[] = [
    createReadTool(cwd, {
      operations: createGatewayReadOperations(gateway),
    }),
    createEditTool(cwd, {
      operations: createGatewayEditOperations(gateway),
    }),
    createWriteTool(cwd, {
      operations: createGatewayWriteOperations(gateway),
    }),
  ];
  if (effectiveManifest.allowed_commands.length > 0) {
    if (options.sandboxProfile && options.sandboxProfile.mode !== "bubblewrap") {
      throw new Error(`sandbox_profile.mode is not supported for bash: ${options.sandboxProfile.mode}`);
    }
    const bashOps = createBubblewrapBashOperations({
      workspaceRoot: cwd,
      permissionManifest: effectiveManifest,
      knownFileRefs: options.knownFileRefs,
      knownDirectoryRefs: options.knownDirectoryRefs,
    });
    tools.push(
      createBashTool(cwd, {
        operations: createGatewayBashOperations(gateway, bashOps, options.toolTimeoutSeconds),
        spawnHook: (context) => ({
          ...context,
          cwd: gateway.authorizeCwd(context.cwd),
          env: gateway.filterEnv(context.env),
        }),
      }),
    );
  }
  return tools;
}

export function permissionManifestFromSandboxProfile(
  permissionManifest: PermissionManifest,
  sandboxProfile?: SandboxProfile,
): PermissionManifest {
  if (!sandboxProfile) return permissionManifest;
  if (sandboxProfile.mode === "unsupported") {
    throw new Error("sandbox_profile.mode must be supported");
  }
  return {
    ...permissionManifest,
    readable_refs: [...sandboxProfile.readable_refs],
    writable_refs: [...sandboxProfile.writable_refs],
    denied_refs: [...sandboxProfile.denied_refs],
    allowed_commands: [...sandboxProfile.command_allowlist],
    network_policy: sandboxProfile.network_enabled ? "enabled" : "disabled",
    env_allowlist: [...sandboxProfile.env_allowlist],
  };
}

function createGatewayReadOperations(gateway: ToolGateway): ReadOperations {
  return {
    readFile: (absolutePath) => readFile(gateway.authorizeReadPath("read", absolutePath)),
    access: async (absolutePath) => {
      await readFile(gateway.authorizeReadPath("read", absolutePath), { flag: "r" });
    },
  };
}

function createGatewayEditOperations(gateway: ToolGateway): EditOperations {
  return {
    readFile: (absolutePath) => readFile(gateway.authorizeReadPath("edit", absolutePath)),
    writeFile: (absolutePath, content) =>
      writeFile(gateway.authorizeWritePath("edit", absolutePath), content, "utf-8"),
    access: async (absolutePath) => {
      await readFile(gateway.authorizeReadWritePath("edit", absolutePath), { flag: "r" });
    },
  };
}

function createGatewayWriteOperations(gateway: ToolGateway): WriteOperations {
  return {
    writeFile: (absolutePath, content) =>
      writeFile(gateway.authorizeWritePath("write", absolutePath), content, "utf-8"),
    mkdir: async (dir) => {
      await mkdir(gateway.authorizeWriteContainerPath("write", dir), { recursive: true });
    },
  };
}

function createGatewayBashOperations(
  gateway: ToolGateway,
  operations: BashOperations,
  toolTimeoutSeconds: number,
): BashOperations {
  return {
    exec: (command, execCwd, execOptions) => {
      const allowedCommand = gateway.authorizeCommand(command);
      return operations.exec(allowedCommand, gateway.authorizeCwd(execCwd), {
        ...execOptions,
        env: gateway.filterEnv(execOptions.env),
        timeout: execOptions.timeout ?? toolTimeoutSeconds,
      });
    },
  };
}

export function guardPath(workspaceRoot: string, path: string): string {
  return guardWorkspacePath(workspaceRoot, path);
}

export async function writeExpectedArtifact(
  workspaceRoot: string,
  ref: string,
  content: string,
  permissionManifest?: PermissionManifest,
): Promise<void> {
  if (permissionManifest) {
    new ToolPermissionEnforcer(workspaceRoot, permissionManifest).ensureWriteRef(ref);
  }
  const path = resolveWorkspaceRef(workspaceRoot, ref);
  assertNoSymlinkSegments(workspaceRoot, path, { allowMissingLeaf: true });
  await mkdir(dirname(path), { recursive: true });
  await writeFile(path, content, "utf-8");
}
