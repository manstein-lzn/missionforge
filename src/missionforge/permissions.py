"""Permission checks for workspace-bound PiWorker execution."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from .contracts import ContractValidationError, require_non_empty_str, require_str_list, validate_ref
from .task_contract import NetworkPolicy, PermissionManifest


class PermissionOperation(StrEnum):
    """Operations checked by the permission layer."""

    READ = "read"
    WRITE = "write"
    COMMAND = "command"
    NETWORK = "network"
    HARD_POLICY = "hard_policy"


@dataclass(frozen=True)
class PermissionDecision:
    """Refs-only permission decision."""

    allowed: bool
    operation: PermissionOperation
    reason: str
    ref: str | None = None
    matched_ref: str | None = None
    command: str | None = None
    unsupported_policy_names: list[str] = field(default_factory=list)

    def validate(self) -> None:
        if not isinstance(self.allowed, bool):
            raise ContractValidationError("permission_decision.allowed must be a bool")
        if not isinstance(self.operation, PermissionOperation):
            raise ContractValidationError("permission_decision.operation must be a PermissionOperation")
        require_non_empty_str(self.reason, "permission_decision.reason")
        if self.ref is not None:
            validate_ref(self.ref, "permission_decision.ref")
        if self.matched_ref is not None:
            validate_ref(self.matched_ref, "permission_decision.matched_ref")
        if self.command is not None:
            require_non_empty_str(self.command, "permission_decision.command")
        require_str_list(self.unsupported_policy_names, "permission_decision.unsupported_policy_names")

    def to_dict(self) -> dict[str, object]:
        self.validate()
        return {
            "allowed": self.allowed,
            "operation": self.operation.value,
            "reason": self.reason,
            "ref": self.ref,
            "matched_ref": self.matched_ref,
            "command": self.command,
            "unsupported_policy_names": list(self.unsupported_policy_names),
        }


class PermissionEnforcer:
    """Hard ref and policy checks for a PermissionManifest."""

    def __init__(self, manifest: PermissionManifest) -> None:
        manifest.validate()
        self.manifest = manifest

    def check_read(self, ref: str) -> PermissionDecision:
        return self._check_ref(PermissionOperation.READ, ref, self.manifest.readable_refs)

    def check_write(self, ref: str) -> PermissionDecision:
        return self._check_ref(PermissionOperation.WRITE, ref, self.manifest.writable_refs)

    def ensure_read(self, ref: str) -> str:
        return self._ensure_allowed(self.check_read(ref))

    def ensure_write(self, ref: str) -> str:
        return self._ensure_allowed(self.check_write(ref))

    def check_command(self, command: str) -> PermissionDecision:
        normalized = require_non_empty_str(command, "permission.command")
        if normalized in self.manifest.allowed_commands:
            return PermissionDecision(
                allowed=True,
                operation=PermissionOperation.COMMAND,
                command=normalized,
                reason="command explicitly allowed",
            )
        return PermissionDecision(
            allowed=False,
            operation=PermissionOperation.COMMAND,
            command=normalized,
            reason="command is not in allowed_commands",
        )

    def check_network(self, *, requested: bool) -> PermissionDecision:
        if not requested:
            return PermissionDecision(
                allowed=True,
                operation=PermissionOperation.NETWORK,
                reason="network not requested",
            )
        if self.manifest.network_policy is NetworkPolicy.DISABLED:
            return PermissionDecision(
                allowed=False,
                operation=PermissionOperation.NETWORK,
                reason="network is disabled",
            )
        if self.manifest.network_policy is NetworkPolicy.RESTRICTED:
            return PermissionDecision(
                allowed=False,
                operation=PermissionOperation.NETWORK,
                reason="restricted network policy is not hard-enforced yet",
                unsupported_policy_names=["network_restricted_policy"],
            )
        return PermissionDecision(
            allowed=True,
            operation=PermissionOperation.NETWORK,
            reason=f"network policy is {self.manifest.network_policy.value}",
        )

    def check_supported_hard_policies(self, supported_policy_names: set[str]) -> PermissionDecision:
        unsupported = [
            name for name in self.manifest.unsupported_hard_policies
            if name not in supported_policy_names
        ]
        if unsupported:
            return PermissionDecision(
                allowed=False,
                operation=PermissionOperation.HARD_POLICY,
                reason="unsupported hard policies are declared",
                unsupported_policy_names=unsupported,
            )
        return PermissionDecision(
            allowed=True,
            operation=PermissionOperation.HARD_POLICY,
            reason="all declared hard policies are supported",
        )

    def _check_ref(self, operation: PermissionOperation, ref: str, allowed_roots: list[str]) -> PermissionDecision:
        safe_ref = validate_ref(ref, "permission.ref")
        denied_match = first_matching_root(safe_ref, self.manifest.denied_refs)
        if denied_match is not None:
            return PermissionDecision(
                allowed=False,
                operation=operation,
                ref=safe_ref,
                matched_ref=denied_match,
                reason="ref is denied",
            )
        allowed_match = first_matching_root(safe_ref, allowed_roots)
        if allowed_match is not None:
            return PermissionDecision(
                allowed=True,
                operation=operation,
                ref=safe_ref,
                matched_ref=allowed_match,
                reason="ref is allowed",
            )
        return PermissionDecision(
            allowed=False,
            operation=operation,
            ref=safe_ref,
            reason="ref is outside allowed roots",
        )

    def _ensure_allowed(self, decision: PermissionDecision) -> str:
        decision.validate()
        if not decision.allowed:
            target = decision.ref or decision.command or decision.operation.value
            raise ContractValidationError(f"permission denied for {target}: {decision.reason}")
        if decision.ref is None:
            raise ContractValidationError("permission decision has no ref")
        return decision.ref


def first_matching_root(ref: str, root_refs: list[str]) -> str | None:
    safe_ref = validate_ref(ref, "permission.ref")
    for root_ref in root_refs:
        safe_root = validate_ref(root_ref, "permission.root_ref")
        if ref_is_under(safe_ref, safe_root):
            return safe_root
    return None


def ref_is_under(ref: str, root_ref: str) -> bool:
    safe_ref = validate_ref(ref, "permission.ref")
    safe_root = validate_ref(root_ref, "permission.root_ref")
    return safe_ref == safe_root or safe_ref.startswith(f"{safe_root}/")
