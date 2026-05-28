"""Safe-point control requests."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from .contracts import ContractValidationError, require_mapping, require_non_empty_str, require_str_list


CONTROL_TYPES = {"halt"}


class ControlHalt(ContractValidationError):
    """Raised when an active halt request blocks dispatch."""


@dataclass(frozen=True)
class ControlRequest:
    """Explicit control intent checked at harness safe points."""

    control_id: str
    control_type: str
    reason: str
    active: bool = True
    evidence_refs: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ControlRequest":
        data = require_mapping(payload, "control_request")
        request = cls(
            control_id=require_non_empty_str(data.get("control_id"), "control_request.control_id"),
            control_type=require_non_empty_str(data.get("control_type"), "control_request.control_type"),
            reason=require_non_empty_str(data.get("reason"), "control_request.reason"),
            active=data.get("active", True),
            evidence_refs=require_str_list(data.get("evidence_refs", []), "control_request.evidence_refs"),
        )
        request.validate()
        return request

    def validate(self) -> None:
        require_non_empty_str(self.control_id, "control_request.control_id")
        if self.control_type not in CONTROL_TYPES:
            raise ContractValidationError(f"control_request.control_type must be one of {sorted(CONTROL_TYPES)}")
        require_non_empty_str(self.reason, "control_request.reason")
        if not isinstance(self.active, bool):
            raise ContractValidationError("control_request.active must be a boolean")
        require_str_list(self.evidence_refs, "control_request.evidence_refs")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "control_id": self.control_id,
            "control_type": self.control_type,
            "reason": self.reason,
            "active": self.active,
            "evidence_refs": list(self.evidence_refs),
        }


@dataclass
class ControlPoint:
    """In-memory safe-point control surface."""

    requests: list[ControlRequest] = field(default_factory=list)

    def add(self, request: ControlRequest) -> None:
        request.validate()
        self.requests.append(request)

    def assert_dispatch_allowed(self) -> None:
        for request in self.requests:
            if request.active and request.control_type == "halt":
                raise ControlHalt(f"dispatch halted: {request.reason}")
