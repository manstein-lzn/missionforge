from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from missionforge.adapters.long_memory import LongMemoryPacket, LongMemoryRecord, LongMemoryScope, LongMemorySearchRequest
from missionforge_deepresearch import run_deepresearch_academic_single_agent

from .test_product_contract import sample_request


class LongMemoryIntegrationTests(unittest.TestCase):
    def test_single_agent_writes_researcher_long_memory_packet_ref(self) -> None:
        provider = FixtureDeepResearchLongMemoryProvider()

        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            result = run_deepresearch_academic_single_agent(
                sample_request(),
                workspace=root,
                long_memory_provider=provider,
            )
            run_root = root / result.run_workspace_ref
            packet_ref = "attempts/deepresearch-npu-compiler-survey-researcher/context/long_memory_packet.json"
            call_payload = json.loads((run_root / "attempts/researcher/piworker_call.json").read_text(encoding="utf-8"))
            packet_payload = json.loads((run_root / packet_ref).read_text(encoding="utf-8"))

        self.assertEqual(provider.captured_request.packet_ref, packet_ref)
        self.assertEqual(provider.captured_request.scope.project_id, "missionforge.deepresearch")
        self.assertEqual(provider.captured_request.scope.role, "executor_piworker")
        self.assertIn(packet_ref, call_payload["evidence_refs"])
        self.assertEqual(call_payload["metadata"]["context_packet_ref"], packet_ref)
        self.assertEqual(packet_payload["schema_version"], "missionforge.long_memory_packet.v1")
        self.assertTrue(packet_payload["advisory_only"])
        self.assertEqual(packet_payload["memories"][0]["source_refs"], ["runs/prior-research/packages/result.json"])
        self.assertIn(f"runs/npu-compiler-survey/{packet_ref}", result.evidence_refs)


class FixtureDeepResearchLongMemoryProvider:
    def __init__(self) -> None:
        self.captured_request: LongMemorySearchRequest | None = None

    def build_packet(self, request: LongMemorySearchRequest) -> LongMemoryPacket:
        request.validate()
        self.captured_request = request
        return LongMemoryPacket(
            provider="fixture",
            packet_ref=request.packet_ref,
            advisory_only=True,
            budget_tokens=request.budget_tokens,
            scope=request.scope,
            memories=(
                LongMemoryRecord(
                    memory_id="mem-deepresearch-001",
                    statement="Prior DeepResearch run identified the compiler autotuning baseline.",
                    why_relevant="Current topic asks for a related compiler survey.",
                    source_refs=("runs/prior-research/packages/result.json",),
                    confidence="high",
                    status="active",
                ),
            ),
        )


if __name__ == "__main__":
    unittest.main()
