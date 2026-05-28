"""Shared contract primitives for MissionForge."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import hashlib
import json
import math
from typing import Any, Mapping, TypeVar


class MissionForgeError(Exception):
    """Base error for MissionForge contract and runtime failures."""


class ContractValidationError(ValueError, MissionForgeError):
    """Raised when a MissionForge contract is malformed."""


class MissionValidationError(ContractValidationError):
    """Raised when Mission IR is malformed."""


class EvidenceTrustLevel(StrEnum):
    """Trust levels for evidence and observations."""

    UNTRUSTED_WORKER_CLAIM = "untrusted_worker_claim"
    LLM_INTERPRETATION = "llm_interpretation"
    ARTIFACT_REF = "artifact_ref"
    COMMAND_RESULT = "command_result"
    TEST_RESULT = "test_result"
    SCHEMA_VALIDATION = "schema_validation"
    VERIFIER_RESULT = "verifier_result"
    REVIEWER_DECISION = "reviewer_decision"
    HUMAN_ACCEPTANCE = "human_acceptance"


class ValidatorMode(StrEnum):
    """Execution mode for a validator."""

    EXECUTABLE = "executable"
    MANUAL = "manual"
    UNSUPPORTED = "unsupported"


class ValidatorSeverity(StrEnum):
    """Completion impact of a validator result."""

    BLOCKING = "blocking"
    ADVISORY = "advisory"


class VerificationStatus(StrEnum):
    """Canonical verification statuses."""

    COMPLETED_VERIFIED = "completed_verified"
    FAILED = "failed"
    REVIEW_REQUIRED = "review_required"
    HUMAN_ACCEPTANCE_REQUIRED = "human_acceptance_required"
    UNSUPPORTED_VERIFICATION_SPEC = "unsupported_verification_spec"
    MISSING_VERIFICATION_PLAN = "missing_verification_plan"
    EXECUTION_INCOMPLETE = "execution_incomplete"
    INVALID_CONTRACT = "invalid_contract"


class AdaptiveDecision(StrEnum):
    """Mission-generic adaptive decision vocabulary."""

    COMPLETE = "complete"
    CONTINUE = "continue"
    REPAIR = "repair"
    REDESIGN = "redesign"
    PIVOT = "pivot"
    REVIEW = "review"
    STOP = "stop"
    ESCALATE = "escalate"
    FAIL = "fail"


class ProposalValidationStatus(StrEnum):
    """Result of proposal boundary validation."""

    ACCEPTED = "accepted"
    REJECTED = "rejected"


E = TypeVar("E", bound=StrEnum)


def require_non_empty_str(value: Any, field_name: str) -> str:
    """Return a stripped string or fail closed."""

    if not isinstance(value, str) or not value.strip():
        raise ContractValidationError(f"{field_name} must be a non-empty string")
    return value.strip()


def require_str_list(value: Any, field_name: str) -> list[str]:
    """Return a list of non-empty strings."""

    if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
        raise ContractValidationError(f"{field_name} must be a list of non-empty strings")
    return [item.strip() for item in value]


def require_mapping(value: Any, field_name: str) -> dict[str, Any]:
    """Return a shallow dict copy from a mapping."""

    if not isinstance(value, Mapping):
        raise ContractValidationError(f"{field_name} must be a mapping")
    return dict(value)


def require_int_at_least(value: Any, field_name: str, minimum: int) -> int:
    """Return an integer greater than or equal to minimum."""

    if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
        raise ContractValidationError(f"{field_name} must be an integer >= {minimum}")
    return value


def require_enum(value: Any, enum_type: type[E], field_name: str) -> E:
    """Return an enum value from its wire string."""

    if isinstance(value, enum_type):
        return value
    if not isinstance(value, str):
        allowed = sorted(item.value for item in enum_type)
        raise ContractValidationError(f"{field_name} must be one of {allowed}")
    try:
        return enum_type(value)
    except ValueError as exc:
        allowed = sorted(item.value for item in enum_type)
        raise ContractValidationError(f"{field_name} must be one of {allowed}") from exc


def require_confidence(value: Any, field_name: str = "confidence") -> float:
    """Return a finite confidence value in [0, 1]."""

    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ContractValidationError(f"{field_name} must be a finite number in [0, 1]")
    result = float(value)
    if not math.isfinite(result) or result < 0.0 or result > 1.0:
        raise ContractValidationError(f"{field_name} must be a finite number in [0, 1]")
    return result


def validate_ref(value: Any, field_name: str = "ref") -> str:
    """Validate a repository/workspace-relative artifact or evidence ref."""

    ref = require_non_empty_str(value, field_name)
    if ref.startswith(("/", "~")) or "\\" in ref or "://" in ref:
        raise ContractValidationError(f"{field_name} must be a safe relative ref")
    if any(ord(char) < 32 or ord(char) == 127 for char in ref):
        raise ContractValidationError(f"{field_name} must not contain control characters")
    parts = ref.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise ContractValidationError(f"{field_name} must not contain empty, dot, or parent segments")
    if ":" in parts[0]:
        raise ContractValidationError(f"{field_name} must not contain a drive prefix")
    return ref


def ensure_json_value(value: Any, field_name: str = "value") -> Any:
    """Validate that a value is JSON-compatible and deterministic."""

    if value is None or isinstance(value, (bool, str)):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ContractValidationError(f"{field_name} must not contain NaN or infinity")
        return value
    if isinstance(value, list):
        return [ensure_json_value(item, f"{field_name}[]") for item in value]
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str) or not key:
                raise ContractValidationError(f"{field_name} keys must be non-empty strings")
            result[key] = ensure_json_value(item, f"{field_name}.{key}")
        return result
    raise ContractValidationError(f"{field_name} must be JSON-compatible")


def stable_json_dumps(value: Any) -> str:
    """Serialize JSON-compatible data in a stable form."""

    normalized = ensure_json_value(value)
    return json.dumps(normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def stable_json_hash(value: Any) -> str:
    """Return a stable sha256 hash for JSON-compatible data."""

    digest = hashlib.sha256(stable_json_dumps(value).encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


@dataclass(frozen=True)
class Ref:
    """A safe relative reference to a workspace artifact or evidence record."""

    value: str

    def __post_init__(self) -> None:
        validate_ref(self.value, "ref.value")

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "Ref":
        data = require_mapping(payload, "ref")
        return cls(value=validate_ref(data.get("value"), "ref.value"))

    def to_dict(self) -> dict[str, Any]:
        return {"value": validate_ref(self.value, "ref.value")}
