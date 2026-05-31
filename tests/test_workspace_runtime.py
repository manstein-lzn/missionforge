from __future__ import annotations

from tempfile import TemporaryDirectory
import unittest

from missionforge import ContractValidationError, PermissionManifest, WorkspacePolicy
from missionforge.workspace_runtime import RunWorkspace


def sample_policy() -> WorkspacePolicy:
    return WorkspacePolicy.from_dict(
        {
            "policy_id": "workspace-001",
            "workspace_root_ref": "runs/run-001",
            "input_refs": ["inputs"],
            "artifact_root_refs": ["artifacts"],
            "scratch_root_refs": ["scratch"],
            "denied_refs": ["secrets"],
        }
    )


def sample_manifest() -> PermissionManifest:
    return PermissionManifest.from_dict(
        {
            "manifest_id": "perm-001",
            "readable_refs": ["inputs", "contract", "reports"],
            "writable_refs": ["artifacts", "reports"],
            "denied_refs": ["artifacts/secrets", "secrets"],
            "network_policy": "disabled",
        }
    )


class WorkspaceRuntimeTests(unittest.TestCase):
    def test_materialize_and_permission_aware_json_text_access(self) -> None:
        with TemporaryDirectory() as tmpdir:
            workspace = RunWorkspace(tmpdir, sample_policy(), sample_manifest())
            workspace.materialize()

            workspace.write_text("artifacts/final.txt", "ok")
            final_path = workspace.root_path / "runs/run-001/artifacts/final.txt"
            self.assertEqual(final_path.read_text(encoding="utf-8"), "ok")

            input_path = workspace.root_path / "runs/run-001/inputs/request.json"
            input_path.write_text('{"a": 1}', encoding="utf-8")
            self.assertEqual(workspace.read_json("inputs/request.json"), {"a": 1})

            workspace.write_json("reports/result.json", {"b": 2, "a": 1})
            self.assertEqual(workspace.read_text("reports/result.json"), '{\n  "a": 1,\n  "b": 2\n}\n')

    def test_denied_refs_override_read_and_write_roots(self) -> None:
        with TemporaryDirectory() as tmpdir:
            workspace = RunWorkspace(tmpdir, sample_policy(), sample_manifest())

            with self.assertRaises(ContractValidationError):
                workspace.write_text("artifacts/secrets/token.txt", "secret")
            with self.assertRaises(ContractValidationError):
                workspace.read_text("secrets/raw.txt")

    def test_workspace_policy_denied_refs_are_enforced_even_if_manifest_allows_root(self) -> None:
        policy = WorkspacePolicy.from_dict(
            {
                "policy_id": "workspace-001",
                "workspace_root_ref": "runs/run-001",
                "input_refs": ["inputs"],
                "artifact_root_refs": ["artifacts"],
                "denied_refs": ["inputs/private"],
            }
        )
        manifest = PermissionManifest.from_dict(
            {
                "manifest_id": "perm-001",
                "readable_refs": ["inputs"],
                "writable_refs": ["artifacts"],
            }
        )
        with TemporaryDirectory() as tmpdir:
            workspace = RunWorkspace(tmpdir, policy, manifest)

            with self.assertRaises(ContractValidationError):
                workspace.read_text("inputs/private/raw.txt")

    def test_rejects_path_escape_and_outside_permission_roots(self) -> None:
        with TemporaryDirectory() as tmpdir:
            workspace = RunWorkspace(tmpdir, sample_policy(), sample_manifest())

            with self.assertRaises(ContractValidationError):
                workspace.resolve_ref("../outside.txt")
            with self.assertRaises(ContractValidationError):
                workspace.write_text("scratch/tmp.txt", "not writable")
            with self.assertRaises(ContractValidationError):
                workspace.read_text("frontdesk/intent_bundle.json")

    def test_missing_permission_manifest_fails_closed(self) -> None:
        with TemporaryDirectory() as tmpdir:
            with self.assertRaises(ContractValidationError):
                RunWorkspace(tmpdir, sample_policy(), None)  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
