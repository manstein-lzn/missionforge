import assert from "node:assert/strict";
import { mkdir, writeFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import test from "node:test";

import {
  degradedLongMemoryDiagnostics,
  loadLongMemoryContext,
  parseLongMemoryPacket,
  renderLongMemoryPacket,
} from "../dist/long-memory.js";
import { sampleInput, withWorkspace } from "./helpers.mjs";

test("parseLongMemoryPacket accepts provider-neutral advisory packets", () => {
  const input = sampleInput({
    long_memory_packet_ref: "attempts/WU-000001/context/long_memory_packet.json",
  });
  const packet = parseLongMemoryPacket(
    sampleLongMemoryPacket(),
    input,
    "attempts/WU-000001/context/long_memory_packet.json",
  );
  const rendered = renderLongMemoryPacket(packet, "attempts/WU-000001/context/long_memory_packet.json");

  assert.equal(packet.schema_version, "missionforge.long_memory_packet.v1");
  assert.equal(packet.provider, "mem0");
  assert.equal(packet.advisory_only, true);
  assert.equal(packet.memories.length, 1);
  assert.equal(rendered.includes("advisory_only: true"), true);
  assert.equal(rendered.includes("source_refs: attempts/WU-000001/session.jsonl#turn-42"), true);
  assert.equal(rendered.includes("authority_note: memory is advisory retrieval context only"), true);
});

test("parseLongMemoryPacket rejects memory records without source refs", () => {
  const input = sampleInput({
    long_memory_packet_ref: "attempts/WU-000001/context/long_memory_packet.json",
  });
  const packet = sampleLongMemoryPacket({
    memories: [
      {
        memory_id: "mem-001",
        statement: "Memory needs evidence.",
        why_relevant: "Current work touches runtime memory.",
        source_refs: [],
        confidence: "high",
        status: "active",
      },
    ],
  });

  assert.throws(
    () => parseLongMemoryPacket(packet, input, "attempts/WU-000001/context/long_memory_packet.json"),
    /source_refs must not be empty/,
  );
});

test("parseLongMemoryPacket rejects mission and role scope mismatches", () => {
  const input = sampleInput({
    long_memory_packet_ref: "attempts/WU-000001/context/long_memory_packet.json",
  });

  assert.throws(
    () =>
      parseLongMemoryPacket(
        sampleLongMemoryPacket({ scope: { mission_id: "other-mission", role: "executor_piworker" } }),
        input,
        "attempts/WU-000001/context/long_memory_packet.json",
      ),
    /scope.mission_id must match/,
  );
  assert.throws(
    () =>
      parseLongMemoryPacket(
        sampleLongMemoryPacket({ scope: { mission_id: "mission-001", role: "judge_piworker" } }),
        input,
        "attempts/WU-000001/context/long_memory_packet.json",
      ),
    /scope.role must match/,
  );
});

test("loadLongMemoryContext rejects rendered packets over budget", async () => {
  await withWorkspace(async (root) => {
    const input = sampleInput({
      long_memory_packet_ref: "attempts/WU-000001/context/long_memory_packet.json",
    });
    const packet = sampleLongMemoryPacket({
      budget_tokens: 1,
      memories: [
        {
          memory_id: "mem-001",
          statement: "This packet is intentionally too long for its declared budget.",
          why_relevant: "Budget rejection should happen before provider context injection.",
          source_refs: ["attempts/WU-000001/session.jsonl#turn-42"],
          confidence: "high",
          status: "active",
        },
      ],
    });
    await writePacket(root, input.long_memory_packet_ref, packet);

    await assert.rejects(() => loadLongMemoryContext(input, root), /exceeds budget_tokens/);
  });
});

test("loadLongMemoryContext reports degraded mode without a packet ref", async () => {
  const context = await loadLongMemoryContext(sampleInput(), "/tmp");

  assert.equal(context.packet, null);
  assert.equal(context.message, null);
  assert.deepEqual(context.diagnostics, degradedLongMemoryDiagnostics("long_memory_packet_ref is not configured"));
});

test("loadLongMemoryContext renders a budgeted advisory user message", async () => {
  await withWorkspace(async (root) => {
    const input = sampleInput({
      long_memory_packet_ref: "attempts/WU-000001/context/long_memory_packet.json",
    });
    await writePacket(root, input.long_memory_packet_ref, sampleLongMemoryPacket());

    const context = await loadLongMemoryContext(input, root);

    assert.equal(context.packet.provider, "mem0");
    assert.equal(context.message.role, "user");
    assert.equal(context.message.content[0].text.includes("[MissionForge long-memory packet]"), true);
    assert.equal(context.diagnostics.provider_enabled, true);
    assert.equal(context.diagnostics.degraded, false);
    assert.equal(context.diagnostics.memory_count, 1);
    assert.equal(context.diagnostics.catalog_hit_count, 1);
    assert.equal(context.diagnostics.budget_tokens, 2000);
    assert.equal(context.diagnostics.estimated_tokens > 0, true);
  });
});

async function writePacket(root, ref, packet) {
  const path = join(root, ref);
  await mkdir(dirname(path), { recursive: true });
  await writeFile(path, `${JSON.stringify(packet, null, 2)}\n`, "utf-8");
}

function sampleLongMemoryPacket(overrides = {}) {
  return {
    schema_version: "missionforge.long_memory_packet.v1",
    provider: "mem0",
    packet_ref: "attempts/WU-000001/context/long_memory_packet.json",
    advisory_only: true,
    budget_tokens: 2000,
    scope: {
      project_id: "missionforge",
      mission_id: "mission-001",
      role: "executor_piworker",
    },
    memories: [
      {
        memory_id: "mem-001",
        statement: "Memory is advisory and cannot override frozen contracts.",
        why_relevant: "Current task concerns runtime context management.",
        source_refs: ["attempts/WU-000001/session.jsonl#turn-42"],
        confidence: "high",
        status: "active",
        created_at: "2026-06-13T00:00:00.000Z",
      },
    ],
    catalog_hits: [
      {
        segment_ref: "attempts/WU-000001/context/segments/segment-000001.jsonl",
        turn_range: [1, 8],
        topics: ["context management", "runtime"],
        artifact_refs: ["docs/CONTEXT_MANAGEMENT_UPGRADE_PLAN.md"],
        hash: `sha256:${"b".repeat(64)}`,
      },
    ],
    ...overrides,
  };
}
