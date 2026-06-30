import { readdir, stat } from "node:fs/promises";
import { relative, resolve } from "node:path";

export type WorkspaceSnapshot = Map<string, string>;

export async function snapshotWorkspace(root: string): Promise<WorkspaceSnapshot> {
  const result: WorkspaceSnapshot = new Map();
  await walk(resolve(root), resolve(root), result);
  return result;
}

export async function changedRefs(root: string, before: WorkspaceSnapshot): Promise<string[]> {
  const after = await snapshotWorkspace(root);
  const changed: string[] = [];
  for (const [ref, signature] of after.entries()) {
    if (before.get(ref) !== signature) changed.push(ref);
  }
  return changed.sort();
}

async function walk(root: string, dir: string, result: WorkspaceSnapshot): Promise<void> {
  let entries;
  try {
    entries = await readdir(dir, { withFileTypes: true });
  } catch {
    return;
  }
  for (const entry of entries) {
    if (entry.name === ".git" || entry.name === "node_modules") continue;
    const path = resolve(dir, entry.name);
    if (entry.isDirectory()) {
      await walk(root, path, result);
      continue;
    }
    if (!entry.isFile()) continue;
    const info = await stat(path);
    result.set(relative(root, path), `${info.size}:${Math.floor(info.mtimeMs)}`);
  }
}
