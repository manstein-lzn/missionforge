import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { requireRef } from "./contract.js";
import { assertNoSymlinkSegments, guardWorkspacePath } from "./permissions.js";
export function resolveWorkspaceRef(root, ref) {
    const safeRef = requireRef(ref, "workspace_ref");
    const rootPath = resolve(root);
    const path = resolve(rootPath, safeRef);
    if (path !== rootPath && !path.startsWith(`${rootPath}/`)) {
        throw new Error(`workspace ref escapes root: ${ref}`);
    }
    return path;
}
export async function readJsonFile(path) {
    return JSON.parse(await readFile(path, "utf-8"));
}
export async function writeJsonFile(path, value, options = {}) {
    const safePath = prepareWorkspaceWritePath(path, options.workspaceRoot);
    await mkdir(dirname(safePath), { recursive: true });
    await writeFile(safePath, `${JSON.stringify(value, null, 2)}\n`, "utf-8");
}
export async function appendJsonLine(path, value, options = {}) {
    const safePath = prepareWorkspaceWritePath(path, options.workspaceRoot);
    await mkdir(dirname(safePath), { recursive: true });
    await writeFile(safePath, `${JSON.stringify(value)}\n`, { encoding: "utf-8", flag: "a" });
}
export function prepareWorkspaceWritePath(path, workspaceRoot) {
    if (!workspaceRoot)
        return path;
    const safePath = guardWorkspacePath(workspaceRoot, path);
    assertNoSymlinkSegments(workspaceRoot, safePath, { allowMissingLeaf: true });
    return safePath;
}
export function prepareWorkspaceReadPath(path, workspaceRoot) {
    if (!workspaceRoot)
        return path;
    const safePath = guardWorkspacePath(workspaceRoot, path);
    assertNoSymlinkSegments(workspaceRoot, safePath, { allowMissingLeaf: false });
    return safePath;
}
