from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from missionforge.adapters.long_memory import (
    LONG_MEMORY_PACKET_SCHEMA_VERSION,
    LongMemoryAddRecord,
    LongMemoryCatalogHit,
    LongMemoryPacket,
    LongMemoryScope,
    LongMemorySearchRequest,
    Mem0LongMemoryProvider,
    long_memory_packet_hash,
    write_long_memory_packet,
)
from missionforge.contracts import ContractValidationError


class LongMemoryAdapterTests(unittest.TestCase):
    def test_long_memory_packet_validates_refs_scope_and_authority(self) -> None:
        packet = sample_packet()

        payload = packet.to_dict()

        self.assertEqual(payload["schema_version"], LONG_MEMORY_PACKET_SCHEMA_VERSION)
        self.assertEqual(payload["provider"], "mem0")
        self.assertIs(payload["advisory_only"], True)
        self.assertEqual(payload["scope"]["mission_id"], "mission-001")
        self.assertEqual(payload["memories"][0]["source_refs"], ["attempts/WU-000001/session.jsonl#turn-42"])
        self.assertTrue(long_memory_packet_hash(packet).startswith("sha256:"))

    def test_long_memory_packet_rejects_unbacked_memory(self) -> None:
        payload = sample_packet().to_dict()
        payload["memories"][0]["source_refs"] = []

        with self.assertRaisesRegex(ContractValidationError, "source_refs"):
            LongMemoryPacket.from_dict(payload)

    def test_long_memory_packet_rejects_claim_to_override_contract(self) -> None:
        payload = sample_packet().to_dict()
        payload["memories"][0]["statement"] = "Memory overrides the frozen contract."

        with self.assertRaisesRegex(ContractValidationError, "frozen contract"):
            LongMemoryPacket.from_dict(payload)

    def test_write_long_memory_packet_writes_json_under_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            ref = write_long_memory_packet(tempdir, sample_packet())
            payload = json.loads(Path(tempdir, ref).read_text(encoding="utf-8"))

        self.assertEqual(ref, "attempts/WU-000001/context/long_memory_packet.json")
        self.assertEqual(payload["schema_version"], LONG_MEMORY_PACKET_SCHEMA_VERSION)

    def test_write_long_memory_packet_rejects_workspace_escape(self) -> None:
        packet = sample_packet()

        with tempfile.TemporaryDirectory() as tempdir:
            with self.assertRaisesRegex(ContractValidationError, "long_memory_packet_ref"):
                write_long_memory_packet(tempdir, packet, "../escape.json")

    def test_mem0_provider_add_requires_source_refs_and_maps_metadata(self) -> None:
        client = FakeMem0Client()
        provider = Mem0LongMemoryProvider(client)
        record = LongMemoryAddRecord(
            statement="Memory is advisory and cannot override frozen contracts.",
            scope=sample_scope(),
            source_refs=("attempts/WU-000001/session.jsonl#turn-42",),
            why_relevant="Current task concerns runtime context management.",
            metadata={"topic": "runtime-context"},
        )

        result = provider.add(record)

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.memory_ids, ("mem-001",))
        self.assertEqual(client.add_calls[0]["run_id"], "mission-001")
        self.assertEqual(client.add_calls[0]["agent_id"], "executor_piworker")
        self.assertEqual(client.add_calls[0]["app_id"], "missionforge")
        self.assertEqual(client.add_calls[0]["user_id"], "user-001")
        self.assertEqual(
            client.add_calls[0]["metadata"]["source_refs"],
            ["attempts/WU-000001/session.jsonl#turn-42"],
        )

    def test_mem0_provider_add_rejects_unbounded_auto_capture(self) -> None:
        provider = Mem0LongMemoryProvider(FakeMem0Client())

        with self.assertRaisesRegex(ContractValidationError, "source_refs"):
            provider.add(
                LongMemoryAddRecord(
                    statement="No source.",
                    scope=sample_scope(),
                    source_refs=(),
                    why_relevant="Should fail.",
                )
            )

    def test_mem0_provider_search_maps_results_to_missionforge_records(self) -> None:
        provider = Mem0LongMemoryProvider(FakeMem0Client())
        result = provider.search(
            LongMemorySearchRequest(
                query="runtime context management",
                scope=sample_scope(),
                packet_ref="attempts/WU-000001/context/long_memory_packet.json",
                limit=3,
                min_score=0.5,
            )
        )

        self.assertEqual(result.provider, "mem0")
        self.assertEqual(result.memories[0].memory_id, "mem-001")
        self.assertEqual(result.memories[0].confidence, "high")
        self.assertEqual(result.memories[0].source_refs, ("attempts/WU-000001/session.jsonl#turn-42",))

    def test_mem0_provider_search_rejects_results_without_source_refs(self) -> None:
        provider = Mem0LongMemoryProvider(FakeMem0Client(results=[{"id": "mem-002", "memory": "Unbacked."}]))

        with self.assertRaisesRegex(ContractValidationError, "source_refs"):
            provider.search(
                LongMemorySearchRequest(
                    query="runtime context management",
                    scope=sample_scope(),
                    packet_ref="attempts/WU-000001/context/long_memory_packet.json",
                )
            )

    def test_mem0_provider_build_packet_uses_provider_neutral_contract(self) -> None:
        provider = Mem0LongMemoryProvider(FakeMem0Client())
        packet = provider.build_packet(
            LongMemorySearchRequest(
                query="runtime context management",
                scope=sample_scope(),
                packet_ref="attempts/WU-000001/context/long_memory_packet.json",
                budget_tokens=1200,
                catalog_hits=(sample_catalog_hit(),),
            )
        )

        payload = packet.to_dict()

        self.assertEqual(payload["provider"], "mem0")
        self.assertEqual(payload["packet_ref"], "attempts/WU-000001/context/long_memory_packet.json")
        self.assertEqual(payload["budget_tokens"], 1200)
        self.assertEqual(payload["catalog_hits"][0]["segment_ref"], "attempts/WU-000001/context/segments/segment-000001.jsonl")
        self.assertNotIn("payload", json.dumps(payload).lower())


class FakeMem0Client:
    def __init__(self, results: list[dict[str, object]] | None = None) -> None:
        self.results = results or [
            {
                "id": "mem-001",
                "memory": "Memory is advisory and cannot override frozen contracts.",
                "score": 0.91,
                "created_at": "2026-06-13T00:00:00.000Z",
                "metadata": {
                    "source_refs": ["attempts/WU-000001/session.jsonl#turn-42"],
                    "why_relevant": "Current task concerns runtime context management.",
                    "missionforge_scope": sample_scope().to_dict(),
                },
            }
        ]
        self.add_calls: list[dict[str, object]] = []
        self.search_calls: list[dict[str, object]] = []

    def add(self, **kwargs: object) -> dict[str, object]:
        self.add_calls.append(dict(kwargs))
        return {"status": "ok", "results": [{"id": "mem-001"}]}

    def search(self, query: str, **kwargs: object) -> dict[str, object]:
        self.search_calls.append({"query": query, **kwargs})
        return {"results": self.results}

    def get(self, memory_id: str) -> dict[str, object]:
        for result in self.results:
            if result.get("id") == memory_id:
                return result
        raise KeyError(memory_id)


def sample_scope() -> LongMemoryScope:
    return LongMemoryScope(
        project_id="missionforge",
        mission_id="mission-001",
        role="executor_piworker",
        user_id="user-001",
    )


def sample_catalog_hit() -> LongMemoryCatalogHit:
    return LongMemoryCatalogHit(
        segment_ref="attempts/WU-000001/context/segments/segment-000001.jsonl",
        turn_range=(1, 8),
        topics=("context management", "runtime"),
        artifact_refs=("docs/CONTEXT_MANAGEMENT_UPGRADE_PLAN.md",),
        hash="sha256:" + "b" * 64,
    )


def sample_packet() -> LongMemoryPacket:
    return LongMemoryPacket.from_dict(
        {
            "schema_version": LONG_MEMORY_PACKET_SCHEMA_VERSION,
            "provider": "mem0",
            "packet_ref": "attempts/WU-000001/context/long_memory_packet.json",
            "advisory_only": True,
            "budget_tokens": 2000,
            "scope": sample_scope().to_dict(),
            "memories": [
                {
                    "memory_id": "mem-001",
                    "statement": "Memory is advisory and cannot override frozen contracts.",
                    "why_relevant": "Current task concerns runtime context management.",
                    "source_refs": ["attempts/WU-000001/session.jsonl#turn-42"],
                    "confidence": "high",
                    "status": "active",
                    "created_at": "2026-06-13T00:00:00.000Z",
                }
            ],
            "catalog_hits": [sample_catalog_hit().to_dict()],
        }
    )


if __name__ == "__main__":
    unittest.main()
