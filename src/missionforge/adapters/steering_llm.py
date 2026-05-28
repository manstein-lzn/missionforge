"""Optional controlled steering LLM adapter.

This module is intentionally adapter-only. Core runtime code may accept an
object that implements the provider protocols, but it must not import this
module.
"""

from __future__ import annotations

import json
from typing import Any, Mapping

from ..contracts import ContractValidationError, EvidenceTrustLevel, assert_refs_only_payload, require_mapping
from ..review import ReviewPacket, ReviewerDecision
from ..steering import ObservationSignal, SteeringContext, SteeringProposal


class ControlledSteeringLLMAdapter:
    """Adapter that turns an injected LLM client into steering contracts."""

    def __init__(self, *, client: Any | None = None, enabled: bool = False, provider_id: str = "llm_adapter") -> None:
        self.client = client
        self.enabled = enabled
        self.provider_id = provider_id

    def next_proposal(self, context: SteeringContext | None = None) -> SteeringProposal:
        self._require_enabled()
        if context is None:
            raise ContractValidationError("LLM steering adapter requires SteeringContext")
        payload = self._call("propose", context.to_dict())
        data = self._normalize_mapping(payload, "steering_llm.proposal")
        data.setdefault("source", self.provider_id)
        data.setdefault("source_refs", [context.contract_ref, context.mission_run_ref])
        data.setdefault("trust_level", EvidenceTrustLevel.LLM_INTERPRETATION.value)
        proposal = SteeringProposal.from_dict(data)
        proposal.validate()
        return proposal

    def interpret_observation(self, context: SteeringContext) -> ObservationSignal:
        self._require_enabled()
        payload = self._call("interpret", context.to_dict())
        signal = ObservationSignal.from_dict(self._normalize_mapping(payload, "steering_llm.observation_signal"))
        signal.validate()
        return signal

    def review(self, packet: ReviewPacket) -> ReviewerDecision:
        self._require_enabled()
        payload = self._call("review", packet.to_dict())
        decision = ReviewerDecision.from_dict(self._normalize_mapping(payload, "steering_llm.reviewer_decision"))
        decision.validate()
        return decision

    def _require_enabled(self) -> None:
        if not self.enabled:
            raise ContractValidationError("LLM steering adapter is disabled")
        if self.client is None:
            raise ContractValidationError("LLM steering adapter requires an injected client")

    def _call(self, method_name: str, payload: Mapping[str, Any]) -> Mapping[str, Any] | str:
        assert_refs_only_payload(payload, f"steering_llm.{method_name}.input")
        method = getattr(self.client, method_name, None)
        if method is None:
            if callable(self.client):
                return self.client(method_name, payload)
            raise ContractValidationError(f"LLM steering client does not implement {method_name}")
        return method(payload)

    def _normalize_mapping(self, payload: Mapping[str, Any] | str, field_name: str) -> dict[str, Any]:
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except json.JSONDecodeError as exc:
                raise ContractValidationError(f"{field_name} must be JSON") from exc
        data = require_mapping(payload, field_name)
        assert_refs_only_payload(data, field_name)
        return data

