import { spawn } from "node:child_process";
import { access, mkdir, stat, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import type { BashOperations } from "@earendil-works/pi-coding-agent";

import type { PermissionManifest } from "./contract.js";
import { resolveWorkspaceRef } from "./paths.js";
import {
  assertNoSymlinkSegments,
  guardWorkspacePath,
  refIsUnder,
} from "./permissions.js";

const SANDBOX_ROOT = "/workspace";

export interface BubblewrapSandboxOptions {
  workspaceRoot: string;
  permissionManifest: PermissionManifest;
  knownFileRefs?: string[];
  knownDirectoryRefs?: string[];
  bwrapPath?: string;
}

export function createBubblewrapBashOperations(options: BubblewrapSandboxOptions): BashOperations {
  const workspaceRoot = resolve(options.workspaceRoot);
  const bwrapPath = options.bwrapPath ?? process.env.MISSIONFORGE_BWRAP_PATH ?? "bwrap";
  const knownFileRefs = new Set(options.knownFileRefs ?? []);
  const knownDirectoryRefs = deriveDirectoryRoots([
    ...options.permissionManifest.readable_refs,
    ...options.permissionManifest.writable_refs,
    ...options.permissionManifest.denied_refs,
    ...(options.knownFileRefs ?? []),
    ...(options.knownDirectoryRefs ?? []),
  ]);
  for (const ref of options.knownDirectoryRefs ?? []) {
    knownDirectoryRefs.add(ref);
  }
  return {
    exec: async (command, cwd, { onData, signal, timeout, env }) => {
      await access(workspaceRoot);
      const sandboxCwd = sandboxPathForHostPath(workspaceRoot, cwd);
      const args = await buildBubblewrapArgs({
        workspaceRoot,
        permissionManifest: options.permissionManifest,
        knownFileRefs,
        knownDirectoryRefs,
        command,
        sandboxCwd,
        env: sanitizeSandboxEnv(env ?? {}),
      });

      return new Promise((resolvePromise, reject) => {
        const child = spawn(bwrapPath, args, {
          cwd: workspaceRoot,
          detached: process.platform !== "win32",
          stdio: ["ignore", "pipe", "pipe"],
          env: {
            PATH: "/bin:/usr/bin:/usr/local/bin",
            HOME: "/tmp",
            TMPDIR: "/tmp",
          },
        });
        let timedOut = false;
        let timeoutHandle: NodeJS.Timeout | undefined;
        if (timeout !== undefined && timeout > 0) {
          timeoutHandle = setTimeout(() => {
            timedOut = true;
            killProcessGroup(child.pid);
          }, timeout * 1000);
        }
        const onAbort = () => killProcessGroup(child.pid);
        if (signal) {
          if (signal.aborted) onAbort();
          else signal.addEventListener("abort", onAbort, { once: true });
        }
        child.stdout?.on("data", onData);
        child.stderr?.on("data", onData);
        child.on("error", (error) => {
          if (timeoutHandle) clearTimeout(timeoutHandle);
          signal?.removeEventListener("abort", onAbort);
          reject(error);
        });
        child.on("close", (code) => {
          if (timeoutHandle) clearTimeout(timeoutHandle);
          signal?.removeEventListener("abort", onAbort);
          if (signal?.aborted) {
            reject(new Error("aborted"));
          } else if (timedOut) {
            reject(new Error(`timeout:${timeout}`));
          } else {
            resolvePromise({ exitCode: code });
          }
        });
      });
    },
  };
}

interface BubblewrapArgsOptions {
  workspaceRoot: string;
  permissionManifest: PermissionManifest;
  knownFileRefs: Set<string>;
  knownDirectoryRefs: Set<string>;
  command: string;
  sandboxCwd: string;
  env: NodeJS.ProcessEnv;
}

async function buildBubblewrapArgs(options: BubblewrapArgsOptions): Promise<string[]> {
  const writableRoots = sortedRoots(options.permissionManifest.writable_refs);
  const readonlyRoots = readonlyMountRoots(options.permissionManifest, writableRoots);
  const deniedRoots = sortedRoots(options.permissionManifest.denied_refs);
  const args = [
    "--unshare-all",
    "--unshare-user-try",
    "--die-with-parent",
    ...(options.permissionManifest.network_policy === "enabled" ? ["--share-net"] : []),
    "--ro-bind",
    "/bin",
    "/bin",
    "--ro-bind",
    "/usr",
    "/usr",
    "--ro-bind-try",
    "/lib",
    "/lib",
    "--ro-bind-try",
    "/lib64",
    "/lib64",
    "--proc",
    "/proc",
    "--dev",
    "/dev",
    "--tmpfs",
    "/tmp",
    "--dir",
    SANDBOX_ROOT,
    "--chdir",
    options.sandboxCwd,
  ];

  for (const dirRef of collectMountDirs([
    ...readonlyRoots,
    ...writableRoots,
    ...deniedRoots,
  ], options.knownDirectoryRefs)) {
    args.push("--dir", sandboxRefPath(dirRef));
  }
  for (const ref of readonlyRoots) {
    await appendReadableMount(args, options.workspaceRoot, ref);
  }
  for (const ref of writableRoots) {
    await appendWritableMount(
      args,
      options.workspaceRoot,
      ref,
      options.knownFileRefs,
      options.knownDirectoryRefs,
    );
  }
  for (const ref of deniedRoots) {
    await appendDeniedMount(args, options.workspaceRoot, ref, options.knownDirectoryRefs);
  }
  for (const [name, value] of Object.entries(options.env)) {
    if (typeof value === "string") {
      args.push("--setenv", name, value);
    }
  }
  args.push("--", "/bin/bash", "-lc", options.command);
  return args;
}

function readonlyMountRoots(manifest: PermissionManifest, writableRoots: readonly string[]): string[] {
  return sortedRoots(manifest.readable_refs).filter(
    (readRef) => !writableRoots.some((writeRef) => refIsUnder(readRef, writeRef)),
  );
}

async function appendReadableMount(args: string[], workspaceRoot: string, ref: string): Promise<void> {
  const hostPath = safeExistingRefPath(workspaceRoot, ref, { allowMissingLeaf: false });
  await access(hostPath);
  args.push("--ro-bind", hostPath, sandboxRefPath(ref));
}

async function appendWritableMount(
  args: string[],
  workspaceRoot: string,
  ref: string,
  knownFileRefs: Set<string>,
  knownDirectoryRefs: Set<string>,
): Promise<void> {
  const hostPath = safeExistingRefPath(workspaceRoot, ref, { allowMissingLeaf: true });
  const asDirectory = isDirectoryMountRef(ref, knownFileRefs, knownDirectoryRefs);
  await ensureWritableHostPath(hostPath, asDirectory);
  args.push("--bind", hostPath, sandboxRefPath(ref));
}

async function appendDeniedMount(
  args: string[],
  workspaceRoot: string,
  ref: string,
  knownDirectoryRefs: Set<string>,
): Promise<void> {
  const hostPath = safeExistingRefPath(workspaceRoot, ref, { allowMissingLeaf: true });
  const target = sandboxRefPath(ref);
  const asDirectory = isDirectoryMountRef(ref, new Set(), knownDirectoryRefs);
  try {
    const info = await stat(hostPath);
    if (info.isDirectory() || asDirectory) {
      args.push("--tmpfs", target, "--remount-ro", target);
    } else {
      args.push("--ro-bind", "/dev/null", target);
    }
  } catch {
    args.push("--tmpfs", target, "--remount-ro", target);
  }
}

async function ensureWritableHostPath(path: string, asDirectory: boolean): Promise<void> {
  try {
    const info = await stat(path);
    if (info.isDirectory()) return;
    if (asDirectory) {
      throw new Error(`Writable ref is not a directory: ${path}`);
    }
    return;
  } catch {
    if (asDirectory) {
      await mkdir(path, { recursive: true });
      return;
    }
    await mkdir(dirname(path), { recursive: true });
    await writeFile(path, "", { encoding: "utf-8", flag: "a" });
  }
}

function safeExistingRefPath(
  workspaceRoot: string,
  ref: string,
  options: { allowMissingLeaf: boolean },
): string {
  const path = resolveWorkspaceRef(workspaceRoot, ref);
  assertNoSymlinkSegments(workspaceRoot, path, options);
  return path;
}

function sandboxPathForHostPath(workspaceRoot: string, path: string): string {
  const safePath = guardWorkspacePath(workspaceRoot, path);
  assertNoSymlinkSegments(workspaceRoot, safePath, { allowMissingLeaf: false });
  const relativePath = safePath === workspaceRoot ? "" : safePath.slice(workspaceRoot.length + 1);
  return relativePath ? `${SANDBOX_ROOT}/${relativePath}` : SANDBOX_ROOT;
}

function sandboxRefPath(ref: string): string {
  return `${SANDBOX_ROOT}/${ref}`;
}

function sanitizeSandboxEnv(env: NodeJS.ProcessEnv): NodeJS.ProcessEnv {
  const result: NodeJS.ProcessEnv = {
    PATH: "/bin:/usr/bin:/usr/local/bin",
    HOME: "/tmp",
    TMPDIR: "/tmp",
  };
  for (const [key, value] of Object.entries(env)) {
    if (typeof value === "string" && key !== "PATH" && key !== "HOME" && key !== "TMPDIR") {
      result[key] = value;
    }
  }
  return result;
}

function isDirectoryMountRef(
  ref: string,
  knownFileRefs: Set<string>,
  knownDirectoryRefs: Set<string>,
): boolean {
  if (knownFileRefs.has(ref)) return false;
  if (knownDirectoryRefs.has(ref)) return true;
  return !basename(ref).includes(".");
}

function deriveDirectoryRoots(refs: readonly string[]): Set<string> {
  const directories = new Set<string>();
  const normalized = [...new Set(refs)].filter((ref) => ref && !ref.endsWith("/"));
  for (const ref of normalized) {
    const parts = ref.split("/");
    for (let index = 1; index < parts.length; index += 1) {
      directories.add(parts.slice(0, index).join("/"));
    }
  }
  return directories;
}

function collectMountDirs(refs: readonly string[], knownDirectoryRefs: Set<string>): string[] {
  const dirs = new Set<string>([""]);
  for (const ref of refs) {
    const parts = ref.split("/");
    let current = "";
    for (let index = 0; index < parts.length - 1; index += 1) {
      current = current ? `${current}/${parts[index]}` : parts[index];
      dirs.add(current);
    }
    if (knownDirectoryRefs.has(ref)) {
      dirs.add(ref);
    }
  }
  return [...dirs].filter(Boolean);
}

function sortedRoots(refs: readonly string[]): string[] {
  return [...new Set(refs)].sort((left, right) => {
    const depth = left.split("/").length - right.split("/").length;
    if (depth !== 0) return depth;
    return left.localeCompare(right);
  });
}

function basename(ref: string): string {
  const parts = ref.split("/");
  return parts[parts.length - 1] ?? ref;
}

function killProcessGroup(pid: number | undefined): void {
  if (!pid) return;
  try {
    if (process.platform === "win32") {
      process.kill(pid, "SIGKILL");
    } else {
      process.kill(-pid, "SIGKILL");
    }
  } catch {
    try {
      process.kill(pid, "SIGKILL");
    } catch {
      // Process already exited.
    }
  }
}
