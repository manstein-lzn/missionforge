import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, relative, resolve } from "node:path";
import type { AgentTool } from "@earendil-works/pi-agent-core";
import {
  createBashTool,
  createLocalBashOperations,
  createEditTool,
  createFindTool,
  createGrepTool,
  createLsTool,
  createReadTool,
  createWriteTool,
} from "@earendil-works/pi-coding-agent";

import { resolveWorkspaceRef } from "./paths.js";

export interface MissionForgeToolOptions {
  workspaceRoot: string;
  toolTimeoutSeconds: number;
}

export function createMissionForgeTools(options: MissionForgeToolOptions): AgentTool<any>[] {
  const cwd = options.workspaceRoot;
  const bashOps = createLocalBashOperations();
  return [
    createReadTool(cwd, {
      operations: {
        readFile: (absolutePath) => readFile(guardPath(cwd, absolutePath)),
        access: async (absolutePath) => {
          await readFile(guardPath(cwd, absolutePath), { flag: "r" });
        },
      },
    }),
    createBashTool(cwd, {
      operations: {
        exec: (command, execCwd, execOptions) =>
          bashOps.exec(command, execCwd, {
            ...execOptions,
            timeout: execOptions.timeout ?? options.toolTimeoutSeconds,
          }),
      },
      spawnHook: (context) => ({
        ...context,
        cwd: guardPath(cwd, context.cwd),
      }),
    }),
    createEditTool(cwd, {
      operations: {
        readFile: (absolutePath) => readFile(guardPath(cwd, absolutePath)),
        writeFile: (absolutePath, content) => writeFile(guardPath(cwd, absolutePath), content, "utf-8"),
        access: async (absolutePath) => {
          await readFile(guardPath(cwd, absolutePath), { flag: "r" });
        },
      },
    }),
    createWriteTool(cwd, {
      operations: {
        writeFile: (absolutePath, content) => writeFile(guardPath(cwd, absolutePath), content, "utf-8"),
        mkdir: async (dir) => {
          await mkdir(guardPath(cwd, dir), { recursive: true });
        },
      },
    }),
    createGrepTool(cwd),
    createFindTool(cwd),
    createLsTool(cwd),
  ];
}

export function guardPath(workspaceRoot: string, path: string): string {
  const root = resolve(workspaceRoot);
  const resolved = resolve(path);
  const rel = relative(root, resolved);
  if (rel === "" || (!rel.startsWith("..") && !rel.includes(".."))) return resolved;
  throw new Error(`Path escapes MissionForge workspace: ${path}`);
}

export async function writeExpectedArtifact(
  workspaceRoot: string,
  ref: string,
  content: string,
): Promise<void> {
  const path = resolveWorkspaceRef(workspaceRoot, ref);
  await mkdir(dirname(path), { recursive: true });
  await writeFile(path, content, "utf-8");
}
