"""Proposal boundary validation and deterministic work-unit harness."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .contracts import AdaptiveDecision, ContractValidationError, ProposalValidationStatus, require_mapping, require_non_empty_str, validate_ref
from .control import ControlPoint
from .evidence_store import EvidenceLedger, InMemoryEvidenceStore
from .steering import DecisionLedgerEntry, ProposalProvider, ProposalValidationResult, SteeringContext, SteeringProposal
from .work_unit import ExecutionReport, WorkUnitContract, WorkerResult


AUTHORITY_EXPANSION_KEYS = {
    "authority_expansion",
    "budget",
    "capability_profiles",
    "contract_hash",
    "frozen_contract",
    "observability",
    "repair_policy",
    "verification",
}


@dataclass
class DeterministicProposalProvider:
    """List-backed proposal provider for offline tests."""

    proposals: list[SteeringProposal]
    index: int = 0

    def next_proposal(self, context: SteeringContext | None = None) -> SteeringProposal:
        if self.index >= len(self.proposals):
            raise ContractValidationError("no deterministic proposals remain")
        proposal = self.proposals[self.index]
        self.index += 1
        return proposal


@dataclass
class ProposalValidator:
    """Validate proposal boundaries before work-unit compilation."""

    available_refs: set[str] | None = None
    allowed_output_roots: list[str] | None = None

    def validate(self, proposal: SteeringProposal) -> ProposalValidationResult:
        reasons: list[str] = []
        try:
            proposal.validate()
        except ContractValidationError as exc:
            reasons.append(str(exc))
            return self._rejected(proposal.proposal_id, reasons)

        contract = require_mapping(proposal.proposed_contract, "steering_proposal.proposed_contract")
        if proposal.recommended_route == AdaptiveDecision.COMPLETE:
            reasons.append("proposal cannot close a mission")
        if any(key in contract for key in AUTHORITY_EXPANSION_KEYS):
            reasons.append("proposal cannot expand frozen contract authority")

        required_fields = ["next_objective", "allowed_scope", "visible_refs", "expected_outputs"]
        for field_name in required_fields:
            if field_name not in contract:
                reasons.append(f"proposed_contract.{field_name} is required")

        allowed_scope = _safe_ref_list(contract.get("allowed_scope", []), "proposed_contract.allowed_scope", reasons)
        visible_refs = _safe_ref_list(contract.get("visible_refs", []), "proposed_contract.visible_refs", reasons)
        expected_outputs = _safe_ref_list(
            contract.get("expected_outputs", []),
            "proposed_contract.expected_outputs",
            reasons,
        )

        if self.available_refs is None:
            reasons.append("proposal validator requires explicit available_refs")
        else:
            for ref in visible_refs:
                if ref not in self.available_refs:
                    reasons.append(f"missing visible ref: {ref}")
        if self.allowed_output_roots is None:
            reasons.append("proposal validator requires explicit allowed_output_roots")
        else:
            for scope in allowed_scope:
                if not any(_is_within(scope, root) for root in self.allowed_output_roots):
                    reasons.append(f"allowed scope outside frozen authority: {scope}")
        for output in expected_outputs:
            if not any(_is_within(output, scope) for scope in allowed_scope):
                reasons.append(f"expected output outside allowed scope: {output}")
        if not allowed_scope:
            reasons.append("proposed_contract.allowed_scope must not be empty")
        if not expected_outputs:
            reasons.append("proposed_contract.expected_outputs must not be empty")
        next_objective = contract.get("next_objective")
        if not isinstance(next_objective, str) or not next_objective.strip():
            reasons.append("proposed_contract.next_objective must be a non-empty string")
        if reasons:
            return self._rejected(proposal.proposal_id, reasons)
        return ProposalValidationResult(
            proposal_id=proposal.proposal_id,
            status=ProposalValidationStatus.ACCEPTED,
            accepted_contract_ref=_work_unit_ref(proposal),
        )

    def _rejected(self, proposal_id: str, reasons: list[str]) -> ProposalValidationResult:
        return ProposalValidationResult(
            proposal_id=proposal_id,
            status=ProposalValidationStatus.REJECTED,
            reasons=reasons,
        )

@dataclass
class WorkUnitCompiler:
    """Compile accepted steering proposals into work-unit contracts."""

    mission_id: str
    validator: ProposalValidator

    def compile(self, proposal: SteeringProposal) -> WorkUnitContract:
        validation = self.validator.validate(proposal)
        if validation.status != ProposalValidationStatus.ACCEPTED:
            raise ContractValidationError("; ".join(validation.reasons))
        contract = require_mapping(proposal.proposed_contract, "steering_proposal.proposed_contract")
        return WorkUnitContract(
            work_unit_id=_work_unit_id(proposal),
            mission_id=require_non_empty_str(self.mission_id, "work_unit.mission_id"),
            iteration=proposal.iteration,
            next_objective=require_non_empty_str(contract.get("next_objective"), "work_unit.next_objective"),
            allowed_scope=list(contract.get("allowed_scope", [])),
            visible_refs=list(contract.get("visible_refs", [])),
            expected_outputs=list(contract.get("expected_outputs", [])),
            exit_criteria=list(contract.get("exit_criteria", [])),
            stop_conditions=list(contract.get("stop_conditions", [])),
        )


@dataclass(frozen=True)
class HarnessDispatchResult:
    """Result of one harness dispatch."""

    validation: ProposalValidationResult
    work_unit: WorkUnitContract | None = None
    execution_report: ExecutionReport | None = None
    worker_result: WorkerResult | None = None


@dataclass
class WorkUnitHarness:
    """Validate, compile, and dispatch one deterministic work unit."""

    compiler: WorkUnitCompiler
    worker: Any
    evidence_store: EvidenceLedger = field(default_factory=InMemoryEvidenceStore)
    control_point: ControlPoint = field(default_factory=ControlPoint)
    decision_ledger: list[DecisionLedgerEntry] = field(default_factory=list)

    def evaluate(self, proposal: SteeringProposal) -> ProposalValidationResult:
        validation = self.compiler.validator.validate(proposal)
        self._record_decision(validation)
        return validation

    def dispatch(self, proposal: SteeringProposal, *, workspace: str = ".") -> HarnessDispatchResult:
        validation = self.evaluate(proposal)
        if validation.status != ProposalValidationStatus.ACCEPTED:
            return HarnessDispatchResult(validation=validation)
        self.control_point.assert_dispatch_allowed()
        work_unit = self.compiler.compile(proposal)
        run_result = self.worker.run(work_unit, workspace=workspace, evidence_store=self.evidence_store)
        return HarnessDispatchResult(
            validation=validation,
            work_unit=work_unit,
            execution_report=run_result.execution_report,
            worker_result=run_result.worker_result,
        )

    def _record_decision(self, validation: ProposalValidationResult) -> None:
        self.decision_ledger.append(
            DecisionLedgerEntry(
                entry_id=f"D-{len(self.decision_ledger) + 1:06d}",
                proposal_id=validation.proposal_id,
                status=validation.status,
                reasons=list(validation.reasons),
                accepted_contract_ref=validation.accepted_contract_ref,
            )
        )


def _safe_ref_list(value: Any, field_name: str, reasons: list[str]) -> list[str]:
    if not isinstance(value, list):
        reasons.append(f"{field_name} must be a list")
        return []
    result: list[str] = []
    for item in value:
        try:
            result.append(validate_ref(item, f"{field_name}[]"))
        except ContractValidationError as exc:
            reasons.append(str(exc))
    return result


def _is_within(ref: str, scope: str) -> bool:
    safe_ref = validate_ref(ref, "ref")
    safe_scope = validate_ref(scope, "scope")
    return safe_ref == safe_scope or safe_ref.startswith(f"{safe_scope}/")


def _work_unit_id(proposal: SteeringProposal) -> str:
    return f"WU-{proposal.iteration:06d}"


def _work_unit_ref(proposal: SteeringProposal) -> str:
    return f"work_units/{_work_unit_id(proposal)}.json"
