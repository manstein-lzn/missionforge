from __future__ import annotations

import unittest

from missionforge import ContractValidationError, NetworkPolicy, PermissionManifest
from missionforge.permissions import PermissionEnforcer, PermissionOperation, ReadGate, WriteGate, ref_is_under


def sample_manifest() -> PermissionManifest:
    return PermissionManifest.from_dict(
        {
            "manifest_id": "perm-001",
            "readable_refs": ["inputs", "contract/task_contract.json"],
            "writable_refs": ["artifacts", "reports"],
            "denied_refs": ["artifacts/secrets", "inputs/private"],
            "allowed_tools": ["read", "write", "edit"],
            "allowed_commands": ["python3 -m unittest"],
            "network_policy": "disabled",
            "env_allowlist": ["PATH"],
            "unsupported_hard_policies": ["bash_subprocess_path_policy"],
        }
    )


class PermissionTests(unittest.TestCase):
    def test_ref_root_matching(self) -> None:
        self.assertTrue(ref_is_under("artifacts/final.md", "artifacts"))
        self.assertTrue(ref_is_under("contract/task_contract.json", "contract/task_contract.json"))
        self.assertFalse(ref_is_under("artifactss/final.md", "artifacts"))

    def test_read_write_permissions_and_denied_override(self) -> None:
        enforcer = PermissionEnforcer(sample_manifest())

        self.assertTrue(enforcer.check_read("inputs/request.json").allowed)
        self.assertTrue(enforcer.check_write("artifacts/final.md").allowed)
        self.assertFalse(enforcer.check_read("frontdesk/intent_bundle.json").allowed)
        self.assertFalse(enforcer.check_write("contract/task_contract.json").allowed)

        denied = enforcer.check_write("artifacts/secrets/token.txt")
        self.assertFalse(denied.allowed)
        self.assertEqual(denied.matched_ref, "artifacts/secrets")

    def test_ensure_methods_fail_closed(self) -> None:
        enforcer = PermissionEnforcer(sample_manifest())

        with self.assertRaises(ContractValidationError):
            enforcer.ensure_read("../outside.json")
        with self.assertRaises(ContractValidationError):
            enforcer.ensure_write("inputs/private/raw.txt")

    def test_command_network_and_unsupported_policy_reporting(self) -> None:
        enforcer = PermissionEnforcer(sample_manifest())

        self.assertTrue(enforcer.check_command("python3 -m unittest").allowed)
        self.assertFalse(enforcer.check_command("rm -rf .").allowed)
        self.assertFalse(enforcer.check_network(requested=True).allowed)
        self.assertTrue(enforcer.check_network(requested=False).allowed)

        unsupported = enforcer.check_supported_hard_policies(set())
        self.assertFalse(unsupported.allowed)
        self.assertEqual(unsupported.operation, PermissionOperation.HARD_POLICY)
        self.assertEqual(unsupported.unsupported_policy_names, ["bash_subprocess_path_policy"])

        supported = enforcer.check_supported_hard_policies({"bash_subprocess_path_policy"})
        self.assertTrue(supported.allowed)

    def test_tool_allowlist_requires_explicit_grant(self) -> None:
        enforcer = PermissionEnforcer(sample_manifest())

        self.assertTrue(enforcer.check_tool("read").allowed)
        self.assertTrue(enforcer.check_tool("write").allowed)
        self.assertFalse(enforcer.check_tool("bash").allowed)

    def test_read_and_write_gates_fail_closed_for_runtime_owned_refs(self) -> None:
        manifest = PermissionManifest.from_dict(
            {
                "manifest_id": "perm-runtime-owned",
                "readable_refs": ["inputs"],
                "writable_refs": ["artifacts", "reports"],
                "denied_refs": ["artifacts/secrets"],
                "allowed_tools": ["read", "write"],
            }
        )
        read_gate = ReadGate(manifest)
        write_gate = WriteGate(manifest)

        self.assertEqual(read_gate.authorize("inputs/request.json"), "inputs/request.json")
        self.assertEqual(write_gate.authorize("artifacts/final.md", writer_role="product"), "artifacts/final.md")
        with self.assertRaises(ContractValidationError):
            write_gate.authorize("kernel/demo-flow/flow_result.json", writer_role="executor_piworker")

    def test_network_policy_enabled_allows_requested_network(self) -> None:
        manifest = PermissionManifest.from_dict(
            {
                "manifest_id": "perm-002",
                "network_policy": NetworkPolicy.ENABLED.value,
            }
        )

        self.assertTrue(PermissionEnforcer(manifest).check_network(requested=True).allowed)

    def test_restricted_network_is_reported_as_unsupported(self) -> None:
        manifest = PermissionManifest.from_dict(
            {
                "manifest_id": "perm-003",
                "network_policy": NetworkPolicy.RESTRICTED.value,
            }
        )

        decision = PermissionEnforcer(manifest).check_network(requested=True)

        self.assertFalse(decision.allowed)
        self.assertEqual(decision.unsupported_policy_names, ["network_restricted_policy"])


if __name__ == "__main__":
    unittest.main()
