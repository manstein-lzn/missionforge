from __future__ import annotations

from pathlib import Path
import unittest

from missionforge import (
    CapabilityGrant,
    ContractValidationError,
    HostSandboxRunner,
    NetworkPolicy,
    PermissionManifest,
    SandboxMode,
    ToolGateway,
    ToolGatewayRequest,
    WorkspacePolicy,
    create_capability_grant,
    create_sandbox_profile_from_workspace,
)


def sample_workspace_policy() -> WorkspacePolicy:
    return WorkspacePolicy.from_dict(
        {
            "policy_id": "workspace-001",
            "workspace_root_ref": "runs/run-001",
            "input_refs": ["inputs"],
            "artifact_root_refs": ["artifacts"],
            "denied_refs": ["secrets"],
        }
    )


def sample_manifest() -> PermissionManifest:
    return PermissionManifest.from_dict(
        {
            "manifest_id": "perm-001",
            "workspace_policy_ref": "policy/workspace_policy.json",
            "readable_refs": ["inputs", "contract"],
            "writable_refs": ["artifacts"],
            "denied_refs": ["inputs/private", "artifacts/secrets"],
            "allowed_commands": ["python3 -m unittest"],
            "network_policy": "disabled",
            "env_allowlist": ["PATH"],
        }
    )


def sample_grant(**overrides: object) -> CapabilityGrant:
    payload = {
        "grant_id": "grant-001",
        "role": "executor_piworker",
        "contract_hash": "sha256:" + "a" * 64,
        "workspace_policy_ref": "policy/workspace_policy.json",
        "permission_manifest_ref": "policy/permission_manifest.json",
        "workspace_view_ref": "runs/run-001",
        "sandbox_profile_ref": "policy/sandbox_profile.json",
        "issued_by": "missionforge.runtime",
        "issued_at": "2026-06-13T00:00:00Z",
        "expires_at": "2026-06-14T00:00:00Z",
    }
    payload.update(overrides)
    return CapabilityGrant.from_dict(payload)


class RuntimeControlTests(unittest.TestCase):
    def test_capability_grant_round_trip_and_activity(self) -> None:
        grant = sample_grant()

        self.assertTrue(grant.is_active(now="2026-06-13T00:30:00Z"))
        self.assertFalse(grant.is_active(now="2026-06-14T00:00:00Z"))

        restored = CapabilityGrant.from_dict(grant.to_dict())
        self.assertEqual(restored.grant_hash, grant.grant_hash)

    def test_revoked_grant_is_inactive(self) -> None:
        grant = sample_grant(revoked_at="2026-06-13T00:20:00Z")

        self.assertFalse(grant.is_active(now="2026-06-13T00:30:00Z"))

    def test_sandbox_profile_compiles_from_workspace_and_permissions(self) -> None:
        profile = create_sandbox_profile_from_workspace(
            "executor-sandbox",
            workspace_policy=sample_workspace_policy(),
            permission_manifest=sample_manifest(),
            mode=SandboxMode.BUBBLEWRAP,
        )

        self.assertEqual(profile.workspace_root_ref, "runs/run-001")
        self.assertEqual(profile.readable_refs, ["inputs", "contract"])
        self.assertEqual(profile.writable_refs, ["artifacts"])
        self.assertIn("secrets", profile.denied_refs)
        self.assertFalse(profile.network_enabled)

    def test_gateway_allows_authorized_read_and_rejects_denied_ref(self) -> None:
        gateway = ToolGateway(HostSandboxRunner())
        profile = create_sandbox_profile_from_workspace(
            "executor-sandbox",
            workspace_policy=sample_workspace_policy(),
            permission_manifest=sample_manifest(),
        )

        allowed = gateway.dispatch(
            ToolGatewayRequest(
                request_id="req-001",
                grant=sample_grant(),
                tool_name="read",
                input_refs=["inputs/request.json"],
            ),
            workspace=Path("."),
            sandbox_profile=profile,
        )
        denied = gateway.dispatch(
            ToolGatewayRequest(
                request_id="req-002",
                grant=sample_grant(),
                tool_name="read",
                input_refs=["inputs/private/raw.txt"],
            ),
            workspace=Path("."),
            sandbox_profile=profile,
        )

        self.assertTrue(allowed.allowed)
        self.assertEqual(denied.decision, "read_denied")

    def test_gateway_rejects_expired_grant_and_unlisted_command(self) -> None:
        gateway = ToolGateway(HostSandboxRunner())
        profile = create_sandbox_profile_from_workspace(
            "executor-sandbox",
            workspace_policy=sample_workspace_policy(),
            permission_manifest=sample_manifest(),
        )

        expired = gateway.dispatch(
            ToolGatewayRequest(
                request_id="req-expired",
                grant=sample_grant(expires_at="2026-06-12T00:00:00Z"),
                tool_name="bash",
                args={"command": "python3 -m unittest"},
            ),
            workspace=Path("."),
            sandbox_profile=profile,
        )
        denied = gateway.dispatch(
            ToolGatewayRequest(
                request_id="req-command",
                grant=create_capability_grant(
                    grant_id="grant-002",
                    role="executor_piworker",
                    contract_hash="sha256:" + "a" * 64,
                    workspace_policy_ref="policy/workspace_policy.json",
                    permission_manifest_ref="policy/permission_manifest.json",
                    workspace_view_ref="runs/run-001",
                    sandbox_profile_ref="policy/sandbox_profile.json",
                    issued_by="missionforge.runtime",
                    issued_at="2026-06-13T00:00:00Z",
                    expires_at="2027-06-13T00:00:00Z",
                ),
                tool_name="bash",
                args={"command": "rm -rf ."},
            ),
            workspace=Path("."),
            sandbox_profile=profile,
        )

        self.assertEqual(expired.decision, "grant_inactive")
        self.assertEqual(denied.decision, "command_denied")

    def test_gateway_requires_grant_workspace_to_match_profile(self) -> None:
        gateway = ToolGateway(HostSandboxRunner())
        profile = create_sandbox_profile_from_workspace(
            "executor-sandbox",
            workspace_policy=sample_workspace_policy(),
            permission_manifest=sample_manifest(),
        )

        with self.assertRaises(ContractValidationError):
            gateway.dispatch(
                ToolGatewayRequest(
                    request_id="req-001",
                    grant=sample_grant(workspace_view_ref="runs/other"),
                    tool_name="read",
                    input_refs=["inputs/request.json"],
                ),
                workspace=Path("."),
                sandbox_profile=profile,
            )

    def test_enabled_network_manifest_can_authorize_network_request(self) -> None:
        manifest = PermissionManifest.from_dict(
            {
                "manifest_id": "perm-002",
                "readable_refs": ["inputs"],
                "writable_refs": ["artifacts"],
                "allowed_commands": ["python3 fetch.py"],
                "network_policy": NetworkPolicy.ENABLED.value,
            }
        )
        profile = create_sandbox_profile_from_workspace(
            "network-sandbox",
            workspace_policy=sample_workspace_policy(),
            permission_manifest=manifest,
        )

        result = ToolGateway(HostSandboxRunner()).dispatch(
            ToolGatewayRequest(
                request_id="req-network",
                grant=sample_grant(),
                tool_name="bash",
                args={"command": "python3 fetch.py", "network": True},
            ),
            workspace=Path("."),
            sandbox_profile=profile,
        )

        self.assertTrue(result.allowed)


if __name__ == "__main__":
    unittest.main()
