import { spawn, spawnSync } from "node:child_process";
import { openSync, writeFileSync } from "node:fs";
import { access, mkdir, stat, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { tmpdir } from "node:os";
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
      const plan = await buildBubblewrapPlan({
        workspaceRoot,
        permissionManifest: options.permissionManifest,
        knownFileRefs,
        knownDirectoryRefs,
        command,
        sandboxCwd,
        env: sanitizeSandboxEnv(env ?? {}),
      });
      const stdio: Array<"ignore" | "pipe" | number> = ["ignore", "pipe", "pipe"];
      if (plan.seccompFd !== null) {
        stdio.push(plan.seccompFd);
      }
      return new Promise((resolvePromise, reject) => {
        const child = spawn(bwrapPath, plan.args, {
          cwd: workspaceRoot,
          detached: process.platform !== "win32",
          stdio,
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

interface BubblewrapPlan {
  args: string[];
  seccompFd: number | null;
}

async function buildBubblewrapPlan(options: BubblewrapArgsOptions): Promise<BubblewrapPlan> {
  const writableRoots = sortedRoots(options.permissionManifest.writable_refs);
  const readonlyRoots = readonlyMountRoots(options.permissionManifest, writableRoots);
  const deniedRoots = sortedRoots(options.permissionManifest.denied_refs);
  const seccompFd =
    options.permissionManifest.network_policy === "disabled" ? getNetworkBlockSeccompFd() : null;
  const args = [
    "--unshare-user-try",
    "--unshare-pid",
    "--unshare-uts",
    "--unshare-ipc",
    "--die-with-parent",
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
  if (seccompFd !== null) {
    args.push("--seccomp", "3");
  }

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
  return { args, seccompFd };
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

function getNetworkBlockSeccompFd(): number {
  if (networkBlockSeccompFd !== null) return networkBlockSeccompFd;
  const seccompPath = networkBlockSeccompPath ??= resolve(tmpdir(), "missionforge-bwrap-network-block.bpf");
  const script = String.raw`
import ctypes
import ctypes.util

libname = ctypes.util.find_library("seccomp")
if not libname:
    raise SystemExit("libseccomp not found")

lib = ctypes.CDLL(libname, use_errno=True)
lib.seccomp_init.argtypes = [ctypes.c_uint32]
lib.seccomp_init.restype = ctypes.c_void_p
lib.seccomp_rule_add.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_int, ctypes.c_uint]
lib.seccomp_rule_add.restype = ctypes.c_int
lib.seccomp_export_bpf.argtypes = [ctypes.c_void_p, ctypes.c_int]
lib.seccomp_export_bpf.restype = ctypes.c_int
lib.seccomp_release.argtypes = [ctypes.c_void_p]
lib.seccomp_release.restype = None
lib.seccomp_syscall_resolve_name.argtypes = [ctypes.c_char_p]
lib.seccomp_syscall_resolve_name.restype = ctypes.c_int

SCMP_ACT_ALLOW = 0x7fff0000
SCMP_ACT_ERRNO = 0x00050000
EPERM = 1

network_syscalls = [
    "socket",
    "socketpair",
    "connect",
    "bind",
    "listen",
    "accept",
    "accept4",
    "getsockname",
    "getpeername",
    "setsockopt",
    "getsockopt",
    "shutdown",
    "sendto",
    "recvfrom",
    "sendmsg",
    "recvmsg",
    "sendmmsg",
    "recvmmsg",
    "socketcall",
]

ctx = lib.seccomp_init(SCMP_ACT_ALLOW)
if not ctx:
    raise SystemExit("seccomp_init failed")

try:
    for name in network_syscalls:
        nr = lib.seccomp_syscall_resolve_name(name.encode("utf-8"))
        if nr < 0:
            continue
        rc = lib.seccomp_rule_add(ctx, SCMP_ACT_ERRNO | EPERM, nr, 0)
        if rc < 0:
            raise SystemExit(f"seccomp_rule_add failed for {name}: {rc}")
    rc = lib.seccomp_export_bpf(ctx, 1)
    if rc < 0:
        raise SystemExit(f"seccomp_export_bpf failed: {rc}")
finally:
    lib.seccomp_release(ctx)
`;
  const result = spawnSync("python3", ["-c", script], {
    cwd: process.cwd(),
    env: {
      ...process.env,
      PYTHONWARNINGS: "ignore",
    },
    encoding: "buffer",
    stdio: ["ignore", "pipe", "pipe"],
  });
  if (result.error) {
    throw result.error;
  }
  if (result.status !== 0) {
    const stderr = Buffer.isBuffer(result.stderr) ? result.stderr.toString("utf-8").trim() : String(result.stderr ?? "");
    throw new Error(`failed to build bubblewrap seccomp program: ${stderr || `exit ${result.status}`}`);
  }
  const program = Buffer.isBuffer(result.stdout) ? result.stdout : Buffer.from(result.stdout ?? []);
  if (program.length === 0) {
    throw new Error("bubblewrap seccomp program is empty");
  }
  writeFileSync(seccompPath, program);
  networkBlockSeccompFd = openSync(seccompPath, "r");
  return networkBlockSeccompFd;
}

let networkBlockSeccompFd: number | null = null;
let networkBlockSeccompPath: string | null = null;

function getNetworkBlockSeccompProgram(): Buffer {
  throw new Error("unreachable");
}
