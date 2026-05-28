"""Run-local controlled steering artifact store."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from .contracts import ContractValidationError, assert_refs_only_payload, ensure_json_value, require_mapping, validate_ref
from .review import ReviewPacket, ReviewerDecision
from .steering import (
    ContractAdjustmentRequest,
    DecisionLedgerEntry,
    ObservationSignal,
    RepairStrategyProposal,
    StateCorrection,
    SteeringContext,
    SteeringProposal,
)


def steering_root_ref(mission_run_id: str) -> str:
    return f"runs/{validate_ref(mission_run_id, 'mission_run_id')}/steering"


def steering_refs_for_iteration(mission_run_id: str, iteration: int) -> dict[str, str]:
    root = steering_root_ref(mission_run_id)
    return {
        "context": f"{root}/context_{iteration:06d}.json",
        "proposal": f"{root}/proposals/{iteration:06d}/steering_proposal.json",
        "observation_signal": f"{root}/proposals/{iteration:06d}/observation_signal.json",
        "contract_adjustment_request": f"{root}/proposals/{iteration:06d}/contract_adjustment_request.json",
        "repair_strategy": f"{root}/proposals/{iteration:06d}/repair_strategy.json",
        "state_correction": f"{root}/proposals/{iteration:06d}/state_correction.json",
        "review_packet": f"{root}/reviews/{iteration:06d}/review_packet.json",
        "reviewer_decision": f"{root}/reviews/{iteration:06d}/reviewer_decision.json",
        "decision_ledger": f"{root}/decision_ledger.jsonl",
    }


class SteeringArtifactStore:
    """Write and inspect refs-only controlled steering artifacts."""

    def __init__(self, workspace: str | Path = ".") -> None:
        self.workspace = Path(workspace)

    def write_context(self, context: SteeringContext) -> str:
        ref = steering_refs_for_iteration(context.mission_run_id, context.iteration)["context"]
        return self._write_json(ref, context.to_dict())

    def write_proposal(self, proposal: SteeringProposal) -> str:
        ref = steering_refs_for_iteration(proposal.mission_run_id, proposal.iteration)["proposal"]
        return self._write_json(ref, proposal.to_dict())

    def write_observation_signal(self, signal: ObservationSignal) -> str:
        ref = steering_refs_for_iteration(signal.mission_run_id, signal.iteration)["observation_signal"]
        return self._write_json(ref, signal.to_dict())

    def write_contract_adjustment_request(self, request: ContractAdjustmentRequest) -> str:
        ref = steering_refs_for_iteration(request.mission_run_id, request.iteration)["contract_adjustment_request"]
        return self._write_json(ref, request.to_dict())

    def write_repair_strategy(self, proposal: RepairStrategyProposal) -> str:
        ref = steering_refs_for_iteration(proposal.mission_run_id, proposal.iteration)["repair_strategy"]
        return self._write_json(ref, proposal.to_dict())

    def write_state_correction(self, *, mission_run_id: str, iteration: int, correction: StateCorrection) -> str:
        ref = steering_refs_for_iteration(mission_run_id, iteration)["state_correction"]
        return self._write_json(ref, correction.to_dict())

    def write_review_packet(self, packet: ReviewPacket) -> str:
        ref = steering_refs_for_iteration(packet.mission_run_id, packet.iteration)["review_packet"]
        return self._write_json(ref, packet.to_dict())

    def write_reviewer_decision(self, *, mission_run_id: str, iteration: int, decision: ReviewerDecision) -> str:
        ref = steering_refs_for_iteration(mission_run_id, iteration)["reviewer_decision"]
        return self._write_json(ref, decision.to_dict())

    def append_decision(self, *, mission_run_id: str, iteration: int, decision: DecisionLedgerEntry) -> str:
        ref = steering_refs_for_iteration(mission_run_id, iteration)["decision_ledger"]
        path = self._resolve(ref)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = assert_refs_only_payload(decision.to_dict(), "decision_ledger_entry")
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, sort_keys=True) + "\n")
        return ref

    def collect_refs(self, mission_run_id: str) -> list[str]:
        root_ref = steering_root_ref(mission_run_id)
        root = self._resolve(root_ref)
        if not root.exists():
            return []
        refs: list[str] = []
        for path in sorted(root.rglob("*")):
            if path.is_file():
                refs.append(path.relative_to(self.workspace.resolve()).as_posix())
        return refs

    def latest_refs(self, mission_run_id: str) -> dict[str, str]:
        refs = self.collect_refs(mission_run_id)
        latest: dict[str, str] = {}
        for ref in refs:
            if ref.endswith("/steering_proposal.json"):
                latest["latest_steering_proposal_ref"] = ref
            elif ref.endswith("/observation_signal.json"):
                latest["latest_observation_signal_ref"] = ref
            elif ref.endswith("/contract_adjustment_request.json"):
                latest["latest_contract_adjustment_request_ref"] = ref
            elif ref.endswith("/repair_strategy.json"):
                latest["latest_repair_strategy_ref"] = ref
            elif ref.endswith("/state_correction.json"):
                latest["latest_state_correction_ref"] = ref
            elif ref.endswith("/review_packet.json"):
                latest["latest_review_packet_ref"] = ref
            elif ref.endswith("decision_ledger.jsonl"):
                latest["decision_ledger_ref"] = ref
            elif "/context_" in ref and ref.endswith(".json"):
                latest["steering_context_ref"] = ref
        return latest

    def _write_json(self, ref: str, payload: Mapping[str, Any]) -> str:
        data = assert_refs_only_payload(
            ensure_json_value(require_mapping(payload, ref), ref),
            ref,
        )
        path = self._resolve(ref)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        return ref

    def _resolve(self, ref: str) -> Path:
        safe_ref = validate_ref(ref, "steering_store.ref")
        root = self.workspace.resolve()
        path = (root / safe_ref).resolve()
        if root not in path.parents and path != root:
            raise ContractValidationError("steering store ref escapes workspace")
        return path
