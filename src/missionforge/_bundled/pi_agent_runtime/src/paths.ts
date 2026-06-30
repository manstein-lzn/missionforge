import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";

import { requireRef } from "./contract.js";
import { assertNoSymlinkSegments, guardWorkspacePath } from "./permissions.js";

export function resolveWorkspaceRef(root: string, ref: string): string {
  const safeRef = requireRef(ref, "workspace_ref");
  const rootPath = resolve(root);
  const path = resolve(rootPath, safeRef);
  if (path !== rootPath && !path.startsWith(`${rootPath}/`)) {
    throw new Error(`workspace ref escapes root: ${ref}`);
  }
  return path;
}

export async function readJsonFile(path: string): Promise<unknown> {
  return JSON.parse(await readFile(path, "utf-8"));
}

export async function writeJsonFile(
  path: string,
  value: unknown,
  options: { workspaceRoot?: string } = {},
): Promise<void> {
  const safePath = prepareWorkspaceWritePath(path, options.workspaceRoot);
  await mkdir(dirname(safePath), { recursive: true });
  await writeFile(safePath, `${JSON.stringify(value, null, 2)}\n`, "utf-8");
}

export async function appendJsonLine(
  path: string,
  value: unknown,
  options: { workspaceRoot?: string } = {},
): Promise<void> {
  const safePath = prepareWorkspaceWritePath(path, options.workspaceRoot);
  await mkdir(dirname(safePath), { recursive: true });
  await writeFile(safePath, `${JSON.stringify(value)}\n`, { encoding: "utf-8", flag: "a" });
}

export function prepareWorkspaceWritePath(path: string, workspaceRoot?: string): string {
  if (!workspaceRoot) return path;
  const safePath = guardWorkspacePath(workspaceRoot, path);
  assertNoSymlinkSegments(workspaceRoot, safePath, { allowMissingLeaf: true });
  return safePath;
}

export function prepareWorkspaceReadPath(path: string, workspaceRoot?: string): string {
  if (!workspaceRoot) return path;
  const safePath = guardWorkspacePath(workspaceRoot, path);
  assertNoSymlinkSegments(workspaceRoot, safePath, { allowMissingLeaf: false });
  return safePath;
}
