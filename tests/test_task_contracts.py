from __future__ import annotations

import unittest

from missionforge.contracts import ContractValidationError
from missionforge.task_contract import (
    ExtensionAdapterMode,
    ExtensionCapability,
    ExtensionGrant,
    PERMISSION_MANIFEST_SCHEMA_VERSION,
    TASK_CONTRACT_REVISION_SCHEMA_VERSION,
    TASK_CONTRACT_SCHEMA_VERSION,
    WORKSPACE_POLICY_SCHEMA_VERSION,
    PermissionManifest,
    ProgressStreamGrant,
    TaskContract,
    TaskContractRevision,
    WorkspacePolicy,
)


def required_output(output_id: str = "out-001") -> dict[str, object]:
    return {
        "output_id": output_id,
        "description": "Write the declared final artifact.",
        "artifact_refs": ["artifacts/final.md"],
    }


def hard_constraint(constraint_id: str = "hc-001") -> dict[str, object]:
    return {
        "constraint_id": constraint_id,
        "statement": "Stay inside the declared writable roots.",
        "source_refs": ["contract/permission_manifest.json"],
    }


def semantic_acceptance(criterion_id: str = "acc-001") -> dict[str, object]:
    return {
        "criterion_id": criterion_id,
        "statement": "The artifact satisfies the frozen task objective.",
        "evidence_refs": ["reports/execution_report.json"],
    }


def sample_contract_payload() -> dict[str, object]:
    return {
        "schema_version": TASK_CONTRACT_SCHEMA_VERSION,
        "contract_id": "contract-001",
        "product_id": "product.generic",
        "objective": "Produce the requested deliverable inside the declared workspace.",
        "background": "Compiled from a FrontDesk intent bundle by product integration.",
        "users_or_audience": ["operator"],
        "non_goals": ["Do not change unrelated files."],
        "assumptions": ["Inputs are available by ref."],
        "required_outputs": [required_output()],
        "hard_constraints": [hard_constraint()],
        "semantic_acceptance": [semantic_acceptance()],
        "risk_notes": ["Ask for explicit revision if the contract is wrong."],
        "source_refs": ["frontdesk/intent_bundle.json", "product/integration.json"],
        "workspace_policy_ref": "contract/workspace_policy.json",
        "permission_manifest_ref": "contract/permission_manifest.json",
        "judge_rubric_ref": "projections/judge_rubric.json",
        "revision_policy": {"mode": "explicit_revision_required", "policy_ref": "contract/revision_policy.json"},
        "created_by": "product.integration",
        "created_at": "2026-05-31T00:00:00Z",
    }


class TaskContractTests(unittest.TestCase):
    def test_task_contract_round_trip_and_stable_hash(self) -> None:
        contract = TaskContract.from_dict(sample_contract_payload())
        same_contract = TaskContract.from_dict(
            {
                "created_at": "2026-05-31T00:00:00Z",
                "created_by": "product.integration",
                "schema_version": TASK_CONTRACT_SCHEMA_VERSION,
                "contract_id": "contract-001",
                "product_id": "product.generic",
                "objective": "Produce the requested deliverable inside the declared workspace.",
                "background": "Compiled from a FrontDesk intent bundle by product integration.",
                "users_or_audience": ["operator"],
                "non_goals": ["Do not change unrelated files."],
                "assumptions": ["Inputs are available by ref."],
                "required_outputs": [required_output()],
                "hard_constraints": [hard_constraint()],
                "semantic_acceptance": [semantic_acceptance()],
                "risk_notes": ["Ask for explicit revision if the contract is wrong."],
                "source_refs": ["frontdesk/intent_bundle.json", "product/integration.json"],
                "workspace_policy_ref": "contract/workspace_policy.json",
                "permission_manifest_ref": "contract/permission_manifest.json",
                "judge_rubric_ref": "projections/judge_rubric.json",
                "revision_policy": {
                    "policy_ref": "contract/revision_policy.json",
                    "mode": "explicit_revision_required",
                },
            }
        )

        self.assertEqual(TaskContract.from_dict(contract.to_dict()), contract)
        self.assertEqual(contract.compute_hash(), same_contract.compute_hash())
        self.assertEqual(contract.to_dict()["contract_hash"], contract.compute_hash())
        self.assertTrue(contract.compute_hash().startswith("sha256:"))

    def test_task_contract_rejects_missing_required_ids(self) -> None:
        payload = sample_contract_payload()
        payload["required_outputs"] = [{"description": "Missing output id."}]

        with self.assertRaises(ContractValidationError):
            TaskContract.from_dict(payload)

    def test_task_contract_rejects_duplicate_ids(self) -> None:
        payload = sample_contract_payload()
        payload["semantic_acceptance"] = [
            semantic_acceptance("acc-001"),
            semantic_acceptance("acc-001"),
        ]

        with self.assertRaises(ContractValidationError):
            TaskContract.from_dict(payload)

    def test_task_contract_rejects_unsafe_refs_and_raw_payload_fields(self) -> None:
        payload = sample_contract_payload()
        payload["source_refs"] = ["../frontdesk/raw.json"]
        with self.assertRaises(ContractValidationError):
            TaskContract.from_dict(payload)

        payload = sample_contract_payload()
        payload["revision_policy"] = {"raw_transcript": "do not store raw chat here"}
        with self.assertRaises(ContractValidationError):
            TaskContract.from_dict(payload)

    def test_task_contract_detects_content_hash_drift(self) -> None:
        contract = TaskContract.from_dict(sample_contract_payload())
        contract.required_outputs[0].refs.append("artifacts/extra.md")

        with self.assertRaises(ContractValidationError):
            contract.to_dict()

    def test_task_contract_can_cite_product_integration_refs_without_importing_product_code(self) -> None:
        contract = TaskContract.from_dict(sample_contract_payload())

        self.assertEqual(contract.product_id, "product.generic")
        self.assertIn("product/integration.json", contract.source_refs)

    def test_workspace_policy_round_trip_and_ref_validation(self) -> None:
        policy = WorkspacePolicy.from_dict(
            {
                "schema_version": WORKSPACE_POLICY_SCHEMA_VERSION,
                "policy_id": "workspace-001",
                "readable_roots": ["inputs", "contract"],
                "writable_roots": ["artifacts"],
                "artifact_roots": ["artifacts"],
                "denied_paths": ["secrets"],
            }
        )

        self.assertEqual(WorkspacePolicy.from_dict(policy.to_dict()), policy)
        with self.assertRaises(ContractValidationError):
            WorkspacePolicy.from_dict(
                {
                    "schema_version": WORKSPACE_POLICY_SCHEMA_VERSION,
                    "policy_id": "workspace-001",
                    "readable_roots": ["/tmp/outside"],
                }
            )

    def test_permission_manifest_round_trip_and_ref_validation(self) -> None:
        manifest = PermissionManifest.from_dict(
            {
                "schema_version": PERMISSION_MANIFEST_SCHEMA_VERSION,
                "manifest_id": "perm-001",
                "workspace_policy_ref": "contract/workspace_policy.json",
                "readable_roots": ["inputs", "contract"],
                "writable_roots": ["artifacts"],
                "executable_commands": ["python3 -m pytest"],
                "network_policy": "disabled",
                "environment_allowlist": ["PATH"],
                "denied_paths": ["secrets"],
            }
        )

        self.assertEqual(PermissionManifest.from_dict(manifest.to_dict()), manifest)
        with self.assertRaises(ContractValidationError):
            PermissionManifest.from_dict(
                {
                    "schema_version": PERMISSION_MANIFEST_SCHEMA_VERSION,
                    "manifest_id": "perm-001",
                    "workspace_policy_ref": "../contract/workspace_policy.json",
                }
        )

    def test_task_contract_revision_requires_explicit_hash_change(self) -> None:
        contract = TaskContract.from_dict(sample_contract_payload())
        revised_payload = sample_contract_payload()
        revised_payload["semantic_acceptance"] = [
            semantic_acceptance("acc-001"),
            {
                "criterion_id": "acc-002",
                "statement": "The artifact cites evidence refs.",
                "evidence_refs": ["reports/execution_report.json"],
            },
        ]
        revised_contract = TaskContract.from_dict(revised_payload)

        revision = TaskContractRevision.from_dict(
            {
                "schema_version": TASK_CONTRACT_REVISION_SCHEMA_VERSION,
                "revision_id": "rev-001",
                "previous_contract_ref": "contract/task_contract.v1.json",
                "previous_contract_hash": contract.compute_hash(),
                "revised_contract_ref": "contract/task_contract.v2.json",
                "revised_contract_hash": revised_contract.compute_hash(),
                "reason": "Clarify evidence citation requirements.",
                "requested_by": "judge",
                "approved_by": "product.integration",
                "evidence_refs": ["revisions/rev-001.json"],
            }
        )

        self.assertEqual(TaskContractRevision.from_dict(revision.to_dict()), revision)

        with self.assertRaises(ContractValidationError):
            TaskContractRevision.from_dict(
                {
                    "schema_version": TASK_CONTRACT_REVISION_SCHEMA_VERSION,
                    "revision_id": "rev-002",
                    "previous_contract_ref": "contract/task_contract.v1.json",
                    "previous_contract_hash": contract.compute_hash(),
                    "revised_contract_ref": "contract/task_contract.v2.json",
                    "revised_contract_hash": contract.compute_hash(),
                    "reason": "No actual change.",
                    "requested_by": "judge",
                }
            )

        with self.assertRaises(ContractValidationError):
            TaskContractRevision.from_dict(
                {
                    "schema_version": TASK_CONTRACT_REVISION_SCHEMA_VERSION,
                    "revision_id": "rev-003",
                    "previous_contract_ref": "contract/task_contract.v1.json",
                    "previous_contract_hash": "old-hash",
                    "revised_contract_ref": "contract/task_contract.v2.json",
                    "revised_contract_hash": revised_contract.compute_hash(),
                    "reason": "Malformed old hash.",
                    "requested_by": "judge",
                }
            )

    def test_permission_manifest_extension_grants_are_declaration_only(self) -> None:
        manifest = PermissionManifest.from_dict(
            {
                "schema_version": PERMISSION_MANIFEST_SCHEMA_VERSION,
                "manifest_id": "perm-extensions",
                "readable_refs": ["inputs", "contract"],
                "writable_refs": ["artifacts"],
                "network_policy": "enabled",
                "env_allowlist": ["PATH", "SEARCH_API_KEY"],
                "extension_grants": [
                    {
                        "grant_id": "web-search",
                        "package": "npm:pi-web-access",
                        "version_spec": "0.10.7",
                        "capability": "web",
                        "config_ref": "policy/extensions/web.json",
                        "requires_network": True,
                        "requires_bash": False,
                        "required_env": ["SEARCH_API_KEY"],
                        "adapter_mode": "missionforge_provider",
                    }
                ],
            }
        )

        self.assertEqual(PermissionManifest.from_dict(manifest.to_dict()), manifest)
        self.assertEqual(manifest.extension_grants[0].capability, ExtensionCapability.WEB)
        self.assertEqual(manifest.extension_grants[0].adapter_mode, ExtensionAdapterMode.MISSIONFORGE_PROVIDER)

    def test_permission_manifest_defaults_extension_grants_for_old_payloads(self) -> None:
        manifest = PermissionManifest.from_dict(
            {
                "schema_version": PERMISSION_MANIFEST_SCHEMA_VERSION,
                "manifest_id": "perm-no-extensions",
            }
        )

        self.assertEqual(manifest.extension_grants, [])
        self.assertEqual(manifest.to_dict()["extension_grants"], [])

    def test_permission_manifest_declares_progress_streams(self) -> None:
        manifest = PermissionManifest.from_dict(
            {
                "schema_version": PERMISSION_MANIFEST_SCHEMA_VERSION,
                "manifest_id": "perm-progress",
                "writable_refs": ["progress/progress.jsonl"],
                "progress_streams": [
                    {
                        "stream_id": "user-progress",
                        "stream_ref": "progress/progress.jsonl",
                        "audience": "user",
                        "renderer": "plain",
                    }
                ],
            }
        )

        self.assertEqual(PermissionManifest.from_dict(manifest.to_dict()), manifest)
        self.assertEqual(
            manifest.progress_streams[0],
            ProgressStreamGrant(
                stream_id="user-progress",
                stream_ref="progress/progress.jsonl",
                audience="user",
                renderer="plain",
            ),
        )
        self.assertEqual(manifest.to_dict()["progress_streams"][0]["stream_ref"], "progress/progress.jsonl")

        with self.assertRaises(ContractValidationError):
            PermissionManifest.from_dict(
                {
                    "schema_version": PERMISSION_MANIFEST_SCHEMA_VERSION,
                    "manifest_id": "perm-progress-bad",
                    "progress_streams": [
                        {"stream_id": "user-progress", "stream_ref": "../progress.jsonl"},
                    ],
                }
            )

    def test_extension_grants_validate_ids_packages_capabilities_and_env(self) -> None:
        valid = {
            "grant_id": "code-search",
            "package": "npm:@example/pi-code-search",
            "version_spec": "1.2.3",
            "capability": "code_search",
            "required_env": ["PATH"],
        }
        self.assertEqual(ExtensionGrant.from_dict(valid).package, "npm:@example/pi-code-search")

        for bad in [
            {**valid, "package": "pip:tool"},
            {**valid, "capability": "academic_research"},
            {**valid, "required_env": ["BAD-NAME"]},
        ]:
            with self.subTest(bad=bad):
                with self.assertRaises(ContractValidationError):
                    ExtensionGrant.from_dict(bad)

        with self.assertRaises(ContractValidationError):
            PermissionManifest.from_dict(
                {
                    "manifest_id": "perm-dupes",
                    "extension_grants": [valid, valid],
                }
            )


if __name__ == "__main__":
    unittest.main()
