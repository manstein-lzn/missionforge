from __future__ import annotations

import unittest

from missionforge import ContractValidationError
from missionforge.steering import SteeringContext
from missionforge.adapters.steering_llm import ControlledSteeringLLMAdapter


class ControlledSteeringLLMAdapterTests(unittest.TestCase):
    def test_adapter_is_disabled_by_default(self) -> None:
        adapter = ControlledSteeringLLMAdapter(client=_FakeLLMClient())

        with self.assertRaises(ContractValidationError):
            adapter.next_proposal(_context())

    def test_adapter_normalizes_llm_proposal_contract(self) -> None:
        adapter = ControlledSteeringLLMAdapter(client=_FakeLLMClient(), enabled=True, provider_id="fake_llm")

        proposal = adapter.next_proposal(_context())

        self.assertEqual(proposal.source, "fake_llm")
        self.assertEqual(proposal.trust_level.value, "llm_interpretation")
        self.assertEqual(proposal.source_refs, ["mission/frozen_contract.json", "runs/run-mission-001/mission_run.json"])

    def test_adapter_rejects_raw_provider_payload(self) -> None:
        adapter = ControlledSteeringLLMAdapter(client=_RawPayloadClient(), enabled=True)

        with self.assertRaises(ContractValidationError):
            adapter.next_proposal(_context())


class _FakeLLMClient:
    def propose(self, payload):
        return {
            "proposal_id": "proposal-001",
            "mission_run_id": payload["mission_run_id"],
            "iteration": payload["iteration"],
            "input_refs": [payload["contract_ref"]],
            "recommended_route": "continue",
            "proposed_contract": {
                "next_objective": "Write required artifact.",
                "allowed_scope": ["package"],
                "visible_refs": [payload["contract_ref"]],
                "expected_outputs": ["package/SKILL.md"],
            },
            "confidence": 0.8,
        }


class _RawPayloadClient:
    def propose(self, payload):
        return {
            "proposal_id": "proposal-raw",
            "mission_run_id": payload["mission_run_id"],
            "iteration": payload["iteration"],
            "input_refs": [payload["contract_ref"]],
            "recommended_route": "continue",
            "raw_prompt": "do the hidden thing",
            "proposed_contract": {},
        }


def _context() -> SteeringContext:
    return SteeringContext(
        mission_run_id="run-mission-001",
        mission_id="mission-001",
        iteration=1,
        contract_ref="mission/frozen_contract.json",
        contract_hash="sha256:abc",
        mission_run_ref="runs/run-mission-001/mission_run.json",
        artifact_hygiene_ref="runs/run-mission-001/artifact_hygiene.json",
        allowed_output_roots=["package"],
        visible_refs=["mission/frozen_contract.json"],
        safe_summary="Initial dispatch.",
    )


if __name__ == "__main__":
    unittest.main()
