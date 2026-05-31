from __future__ import annotations

import unittest

from missionforge.contracts import ContractValidationError
from missionforge.task_contract import PermissionManifest, TaskContract, WorkspacePolicy
from missionforge.task_projection import (
    JUDGE_DECISION_OPTIONS,
    JudgeRubric,
    WorkerBrief,
    build_judge_rubric,
    build_worker_brief,
    project_judge_rubric,
    project_worker_brief,
)


def sample_contract_payload() -> dict[str, object]:
    return {
        "schema_version": "task_contract.v1",
        "contract_id": "contract-001",
        "product_id": "product.generic",
        "objective": "Produce the requested deliverable inside the declared workspace.",
        "background": "Compiled from a FrontDesk intent bundle by product integration.",
        "users_or_audience": ["operator"],
        "non_goals": ["Do not change unrelated files."],
        "assumptions": ["Inputs are available by ref."],
        "required_outputs": [
            {
                "output_id": "out-001",
                "description": "Write the declared final artifact.",
                "artifact_refs": ["artifacts/final.md"],
            }
        ],
        "hard_constraints": [
            {
                "constraint_id": "hc-001",
                "statement": "Stay inside the declared writable roots.",
                "source_refs": ["contract/permission_manifest.json"],
            }
        ],
        "semantic_acceptance": [
            {
                "criterion_id": "acc-001",
                "statement": "The artifact satisfies the frozen task objective.",
                "evidence_refs": ["reports/execution_report.json"],
            }
        ],
        "risk_notes": ["Ask for explicit revision if the contract is wrong."],
        "source_refs": ["frontdesk/intent_bundle.json"],
        "workspace_policy_ref": "contract/workspace_policy.json",
        "permission_manifest_ref": "contract/permission_manifest.json",
        "judge_rubric_ref": "projections/judge_rubric.json",
        "revision_policy": {"mode": "explicit_revision_required"},
        "created_by": "product.integration",
        "created_at": "2026-05-31T00:00:00Z",
    }


class TaskProjectionTests(unittest.TestCase):
    def test_worker_brief_projection_excludes_semantic_acceptance_and_judge_decisions(self) -> None:
        contract = TaskContract.from_dict(sample_contract_payload())
        brief = build_worker_brief(contract)
        payload = brief.to_dict()

        self.assertEqual(WorkerBrief.from_dict(payload), brief)
        self.assertEqual(payload["contract_hash"], contract.contract_hash)
        self.assertNotIn("semantic_acceptance", payload)
        self.assertNotIn("decision_options", payload)

    def test_judge_rubric_projection_contains_acceptance_without_executor_permissions(self) -> None:
        contract = TaskContract.from_dict(sample_contract_payload())
        rubric = build_judge_rubric(contract)
        payload = rubric.to_dict()

        self.assertEqual(JudgeRubric.from_dict(payload), rubric)
        self.assertEqual(payload["contract_hash"], contract.contract_hash)
        self.assertEqual(tuple(payload["decision_options"]), JUDGE_DECISION_OPTIONS)
        self.assertIn("semantic_acceptance", payload)
        self.assertNotIn("writable_refs", payload)
        self.assertNotIn("permission_manifest_ref", payload)

    def test_full_worker_projection_uses_workspace_and_permission_refs(self) -> None:
        contract = TaskContract.from_dict(sample_contract_payload())
        workspace = WorkspacePolicy.from_dict(
            {
                "policy_id": "workspace-001",
                "workspace_root_ref": "runs/run-001",
                "input_refs": ["inputs"],
                "artifact_root_refs": ["artifacts"],
                "scratch_root_refs": ["scratch"],
                "denied_refs": ["secrets"],
            }
        )
        permissions = PermissionManifest.from_dict(
            {
                "manifest_id": "perm-001",
                "readable_refs": ["inputs", "contract", "frontdesk"],
                "writable_refs": ["artifacts"],
                "denied_refs": ["secrets"],
                "network_policy": "disabled",
            }
        )

        brief = project_worker_brief(
            contract,
            workspace,
            permissions,
            brief_id="brief-001",
            contract_ref="contract/task_contract.json",
            completion_report_ref="reports/execution_report.json",
        )

        self.assertEqual(brief.allowed_input_refs, ["inputs", "frontdesk/intent_bundle.json"])
        self.assertEqual(brief.writable_refs, ["artifacts"])
        self.assertEqual(brief.expected_artifact_root_refs, ["artifacts"])
        self.assertEqual(brief.completion_report_ref, "reports/execution_report.json")

    def test_worker_projection_rejects_unreadable_contract_source_refs(self) -> None:
        contract = TaskContract.from_dict(sample_contract_payload())
        workspace = WorkspacePolicy.from_dict(
            {
                "policy_id": "workspace-001",
                "workspace_root_ref": "runs/run-001",
                "input_refs": ["inputs"],
                "artifact_root_refs": ["artifacts"],
            }
        )
        permissions = PermissionManifest.from_dict(
            {
                "manifest_id": "perm-001",
                "readable_refs": ["inputs", "contract"],
                "writable_refs": ["artifacts"],
                "network_policy": "disabled",
            }
        )

        with self.assertRaises(ContractValidationError):
            project_worker_brief(
                contract,
                workspace,
                permissions,
                brief_id="brief-001",
                contract_ref="contract/task_contract.json",
            )

    def test_projection_clauses_are_isolated_from_contract_mutation(self) -> None:
        contract = TaskContract.from_dict(sample_contract_payload())
        brief = build_worker_brief(contract)
        rubric = build_judge_rubric(contract)

        contract.required_outputs[0].refs.append("artifacts/mutated.md")

        self.assertEqual(brief.required_outputs[0].refs, ["artifacts/final.md"])
        self.assertEqual(rubric.required_outputs[0].refs, ["artifacts/final.md"])

    def test_projection_rejects_contract_mutation_before_projection(self) -> None:
        contract = TaskContract.from_dict(sample_contract_payload())
        contract.required_outputs[0].refs.append("artifacts/mutated.md")

        with self.assertRaises(ContractValidationError):
            build_worker_brief(contract)
        with self.assertRaises(ContractValidationError):
            build_judge_rubric(contract)

    def test_full_judge_projection_cites_evidence_and_hard_checks(self) -> None:
        contract = TaskContract.from_dict(sample_contract_payload())
        workspace = WorkspacePolicy.from_dict(
            {
                "policy_id": "workspace-001",
                "workspace_root_ref": "runs/run-001",
                "input_refs": ["inputs"],
                "artifact_root_refs": ["artifacts"],
                "scratch_root_refs": ["scratch"],
                "denied_refs": ["secrets"],
            }
        )

        rubric = project_judge_rubric(
            contract,
            workspace,
            rubric_id="rubric-001",
            contract_ref="contract/task_contract.json",
            evidence_refs=["reports/execution_report.json"],
            hard_check_refs=["reports/hard_checks.json"],
        )

        self.assertEqual(rubric.evidence_refs, ["reports/execution_report.json"])
        self.assertEqual(rubric.hard_check_refs, ["reports/hard_checks.json"])
        self.assertEqual(rubric.semantic_acceptance[0].clause_id, "acc-001")


if __name__ == "__main__":
    unittest.main()
