import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname } from "node:path";
import type { AgentTool } from "@earendil-works/pi-agent-core";
import {
  createBashTool,
  createLocalBashOperations,
  createEditTool,
  createReadTool,
  createWriteTool,
} from "@earendil-works/pi-coding-agent";

import type { PermissionManifest } from "./contract.js";
import { resolveWorkspaceRef } from "./paths.js";
import { assertNoSymlinkSegments, guardWorkspacePath, ToolPermissionEnforcer } from "./permissions.js";

export interface MissionForgeToolOptions {
  workspaceRoot: string;
  permissionManifest: PermissionManifest;
  toolTimeoutSeconds: number;
}

export function createMissionForgeTools(options: MissionForgeToolOptions): AgentTool<any>[] {
  const cwd = options.workspaceRoot;
  const enforcer = new ToolPermissionEnforcer(cwd, options.permissionManifest);
  const tools: AgentTool<any>[] = [
    createReadTool(cwd, {
      operations: {
        readFile: (absolutePath) => readFile(enforcer.ensureReadPath(absolutePath)),
        access: async (absolutePath) => {
          await readFile(enforcer.ensureReadPath(absolutePath), { flag: "r" });
        },
      },
    }),
    createEditTool(cwd, {
      operations: {
        readFile: (absolutePath) => readFile(enforcer.ensureReadPath(absolutePath)),
        writeFile: (absolutePath, content) => writeFile(enforcer.ensureWritePath(absolutePath), content, "utf-8"),
        access: async (absolutePath) => {
          await readFile(enforcer.ensureReadPath(absolutePath), { flag: "r" });
        },
      },
    }),
    createWriteTool(cwd, {
      operations: {
        writeFile: (absolutePath, content) => writeFile(enforcer.ensureWritePath(absolutePath), content, "utf-8"),
        mkdir: async (dir) => {
          await mkdir(enforcer.ensureWriteContainerPath(dir), { recursive: true });
        },
      },
    }),
  ];
  if (options.permissionManifest.allowed_commands.length > 0) {
    const bashOps = createLocalBashOperations();
    tools.push(
      createBashTool(cwd, {
        operations: {
          exec: (command, execCwd, execOptions) => {
            const allowedCommand = enforcer.ensureCommand(command);
            return bashOps.exec(allowedCommand, guardPath(cwd, execCwd), {
              ...execOptions,
              env: enforcer.filterEnv(execOptions.env),
              timeout: execOptions.timeout ?? options.toolTimeoutSeconds,
            });
          },
        },
        spawnHook: (context) => ({
          ...context,
          cwd: guardPath(cwd, context.cwd),
          env: enforcer.filterEnv(context.env),
        }),
      }),
    );
  }
  return tools;
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
