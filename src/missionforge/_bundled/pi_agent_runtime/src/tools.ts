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

import type { ExtensionLock, PermissionManifest, SandboxProfile } from "./contract.js";
import { createContextSnapshotTool, type ContextSnapshotToolOptions } from "./context-snapshot.js";
import { resolveWorkspaceRef } from "./paths.js";
import { assertNoSymlinkSegments, guardWorkspacePath, ToolPermissionEnforcer } from "./permissions.js";
import { createBubblewrapBashOperations } from "./sandbox.js";
import { ToolGateway, type ToolGatewayDecision } from "./tool-gateway.js";

const RESERVED_TOOL_NAMES = new Set(["read", "write", "edit", "bash", "context_snapshot"]);

export interface MissionForgeToolOptions {
  workspaceRoot: string;
  permissionManifest: PermissionManifest;
  sandboxProfile?: SandboxProfile;
  toolTimeoutSeconds: number;
  knownFileRefs?: string[];
  knownDirectoryRefs?: string[];
  contextSnapshot?: ContextSnapshotToolOptions;
  extensionLock?: ExtensionLock | null;
  extensionTools?: AgentTool<any>[];
  callId?: string;
  onToolGatewayDecision?: (decision: ToolGatewayDecision) => void;
}

export async function createMissionForgeTools(options: MissionForgeToolOptions): Promise<AgentTool<any>[]> {
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
  const toolsByName = new Map<string, AgentTool<any>>();
  const coreTools = [
    ["read", createReadTool(cwd, { operations: createGatewayReadOperations(gateway) })],
    ["edit", createEditTool(cwd, { operations: createGatewayEditOperations(gateway) })],
    ["write", createWriteTool(cwd, { operations: createGatewayWriteOperations(gateway) })],
  ] as const;
  for (const [toolName, tool] of coreTools) {
    if (canUseTool(effectiveManifest.allowed_tools, toolName)) {
      toolsByName.set(toolName, tool);
    }
  }
  if (options.contextSnapshot && canUseTool(effectiveManifest.allowed_tools, "context_snapshot")) {
    toolsByName.set("context_snapshot", createContextSnapshotTool({
      ...options.contextSnapshot,
      permissionManifest: effectiveManifest,
    }));
  }
  if (effectiveManifest.allowed_commands.length > 0 && canUseTool(effectiveManifest.allowed_tools, "bash")) {
    if (options.sandboxProfile && options.sandboxProfile.mode !== "bubblewrap") {
      throw new Error(
        `bash requires sandbox_profile.mode=bubblewrap; got ${options.sandboxProfile.mode}`,
      );
    }
    const bashOps = createBubblewrapBashOperations({
      workspaceRoot: cwd,
      permissionManifest: effectiveManifest,
      knownFileRefs: options.knownFileRefs,
      knownDirectoryRefs: options.knownDirectoryRefs,
    });
    toolsByName.set(
      "bash",
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
  for (const tool of options.extensionTools ?? []) {
    if (!canUseTool(effectiveManifest.allowed_tools, tool.name)) continue;
    if (RESERVED_TOOL_NAMES.has(tool.name)) {
      throw new Error(`extension tool name conflicts with MissionForge core tool: ${tool.name}`);
    }
    toolsByName.set(tool.name, createGatewayExtensionTool(tool, gateway));
  }
  return [...toolsByName.values()];
}

export function permissionManifestFromSandboxProfile(
  permissionManifest: PermissionManifest,
  sandboxProfile?: SandboxProfile,
): PermissionManifest {
  if (!sandboxProfile) return permissionManifest;
  if (sandboxProfile.mode === "unsupported") {
    throw new Error("sandbox_profile.mode must be supported");
  }
  const profileAllowedTools = sandboxProfile.allowed_tools as readonly string[] | undefined;
  const manifestAllowedTools = permissionManifest.allowed_tools as readonly string[] | undefined;
  const allowedTools = profileAllowedTools === undefined
    ? manifestAllowedTools === undefined
      ? ["read", "write", "edit"]
      : [...manifestAllowedTools]
    : [...profileAllowedTools];
  return {
    ...permissionManifest,
    readable_refs: [...sandboxProfile.readable_refs],
    writable_refs: [...sandboxProfile.writable_refs],
    denied_refs: [...sandboxProfile.denied_refs],
    allowed_tools: allowedTools,
    allowed_commands: [...sandboxProfile.command_allowlist],
    network_policy: sandboxProfile.network_enabled ? "enabled" : "disabled",
    env_allowlist: [...sandboxProfile.env_allowlist],
    extension_grants: [...(permissionManifest.extension_grants ?? [])],
  };
}

function canUseTool(allowedTools: readonly string[] | undefined, toolName: string): boolean {
  const effectiveAllowedTools = allowedTools === undefined ? ["read", "write", "edit"] : allowedTools;
  if (effectiveAllowedTools.includes(toolName)) return true;
  if (toolName === "read_text" || toolName === "read_json") return effectiveAllowedTools.includes("read");
  if (toolName === "write_text" || toolName === "write_json") return effectiveAllowedTools.includes("write");
  return false;
}

function createGatewayExtensionTool(tool: AgentTool<any>, gateway: ToolGateway): AgentTool<any> {
  return {
    ...tool,
    execute: async (toolCallId, params, signal, onUpdate) => {
      gateway.authorizeTool(tool.name);
      return tool.execute.call(tool, toolCallId, params, signal, onUpdate);
    },
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
