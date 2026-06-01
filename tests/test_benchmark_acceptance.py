from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from missionforge.benchmark import (
    AcceptanceCheck,
    AcceptanceCheckKind,
    AcceptancePack,
    AcceptanceVisibility,
    BenchmarkMode,
    BenchmarkStatus,
    BenchmarkSummary,
    apply_hidden_acceptance,
    evaluate_acceptance_pack,
    load_acceptance_pack,
)
from missionforge.contracts import ContractValidationError


class BenchmarkAcceptanceTests(unittest.TestCase):
    def test_hidden_pack_evaluates_without_embedding_expected_strings_in_result(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            trial_workspace = root / "benchmarks/runs/bench-001/trials/task-001/direct_piworker_chat/seed-1/workspace"
            (trial_workspace / "package").mkdir(parents=True)
            (trial_workspace / "package/SKILL.md").write_text(
                "# Skill\n\nThis is a reusable local method package.\n",
                encoding="utf-8",
            )
            pack = AcceptancePack(
                pack_id="hidden",
                task_id="task-001",
                visibility=AcceptanceVisibility.HIDDEN,
                checks=[
                    AcceptanceCheck(
                        check_id="contains-reusable",
                        kind=AcceptanceCheckKind.FILE_CONTAINS,
                        ref="package/SKILL.md",
                        expected_text="reusable",
                    ),
                    AcceptanceCheck(
                        check_id="no-raw-prompt",
                        kind=AcceptanceCheckKind.FILE_NOT_CONTAINS,
                        ref="package/SKILL.md",
                        forbidden_text="raw_prompt",
                    ),
                ],
            )

            result = evaluate_acceptance_pack(
                workspace=root,
                trial_workspace_ref="benchmarks/runs/bench-001/trials/task-001/direct_piworker_chat/seed-1/workspace",
                pack=pack,
                result_ref="benchmarks/runs/bench-001/trials/task-001/direct_piworker_chat/seed-1/hidden.json",
            )

            self.assertTrue(result.passed)
            payload = json.dumps(result.to_dict(), sort_keys=True)
            self.assertNotIn("reusable local method", payload)
            self.assertNotIn("raw_prompt", payload)

    def test_hidden_acceptance_failure_updates_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            trial_workspace_ref = "benchmarks/runs/bench-001/trials/task-001/direct_piworker_chat/seed-1/workspace"
            trial_workspace = root / trial_workspace_ref
            (trial_workspace / "package").mkdir(parents=True)
            (trial_workspace / "package/SKILL.md").write_text("raw_prompt leak\n", encoding="utf-8")
            pack = AcceptancePack(
                pack_id="hidden",
                task_id="task-001",
                visibility=AcceptanceVisibility.HIDDEN,
                checks=[
                    AcceptanceCheck(
                        check_id="no-raw-prompt",
                        kind=AcceptanceCheckKind.FILE_NOT_CONTAINS,
                        ref="package/SKILL.md",
                        forbidden_text="raw_prompt",
                    )
                ],
            )
            result = evaluate_acceptance_pack(workspace=root, trial_workspace_ref=trial_workspace_ref, pack=pack)
            summary = BenchmarkSummary(
                task_id="task-001",
                mode=BenchmarkMode.DIRECT_PIWORKER_CHAT,
                seed=1,
                accepted=True,
                status=BenchmarkStatus.ACCEPTED,
                artifact_refs=[f"{trial_workspace_ref}/package/SKILL.md"],
            )

            updated = apply_hidden_acceptance(summary, result)

            self.assertFalse(updated.accepted)
            self.assertFalse(updated.hidden_acceptance_passed)
            self.assertIn("hidden_acceptance_failed", updated.failure_taxonomy)

    def test_file_contains_any_is_case_insensitive_and_hides_expected_terms(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            trial_workspace_ref = "benchmarks/runs/bench-001/trials/task-001/direct_piworker_chat/seed-1/workspace"
            trial_workspace = root / trial_workspace_ref
            (trial_workspace / "package").mkdir(parents=True)
            (trial_workspace / "package/SKILL.md").write_text(
                "# Skill\n\n## Method Overview\n\nUse a staged engineering process.\n",
                encoding="utf-8",
            )
            pack = AcceptancePack(
                pack_id="hidden",
                task_id="task-001",
                visibility=AcceptanceVisibility.HIDDEN,
                checks=[
                    AcceptanceCheck(
                        check_id="has-process",
                        kind=AcceptanceCheckKind.FILE_CONTAINS_ANY,
                        ref="package/SKILL.md",
                        expected_terms=["workflow", "method"],
                    )
                ],
            )

            result = evaluate_acceptance_pack(workspace=root, trial_workspace_ref=trial_workspace_ref, pack=pack)

            self.assertTrue(result.passed)
            payload = json.dumps(result.to_dict(), sort_keys=True).lower()
            self.assertNotIn("workflow", payload)
            self.assertNotIn("method", payload)

    def test_loads_committed_complex_method_skill_fixture(self) -> None:
        root = Path(".")
        pack = load_acceptance_pack(
            root,
            "benchmarks/tasks/complex-method-skill-001/acceptance/hidden_checks.json",
        )
        user_statement = (
            root / "benchmarks/tasks/complex-method-skill-001/user_statement.txt"
        ).read_text(encoding="utf-8").lower()
        task_payload = json.loads(
            (root / "benchmarks/tasks/complex-method-skill-001/task.json").read_text(encoding="utf-8")
        )
        worker_visible_payload = json.dumps(
            {
                "task_id": task_payload["task_id"],
                "task_family": task_payload["task_family"],
                "initial_user_text_ref": task_payload["initial_user_text_ref"],
                "allowed_source_refs": task_payload["allowed_source_refs"],
                "expected_output_refs": task_payload["expected_output_refs"],
            },
            ensure_ascii=False,
            sort_keys=True,
        ).lower()

        self.assertEqual(pack.visibility, AcceptanceVisibility.HIDDEN)
        self.assertEqual(pack.task_id, "complex-method-skill-001")
        self.assertGreaterEqual(len(pack.checks), 3)
        self.assertNotIn("codexarium", user_statement)
        self.assertNotIn("source code", user_statement)
        self.assertNotIn("codexarium", worker_visible_payload)

    def test_rejects_unsafe_acceptance_refs(self) -> None:
        with self.assertRaises(ContractValidationError):
            AcceptanceCheck(
                check_id="bad-ref",
                kind=AcceptanceCheckKind.FILE_EXISTS,
                ref="../outside",
            ).validate()

    def test_acceptance_schema_rejects_non_string_optional_text_and_refs(self) -> None:
        with self.assertRaises(ContractValidationError):
            AcceptanceCheck.from_dict(
                {
                    "check_id": "bad-text",
                    "kind": "file_contains",
                    "ref": "package/SKILL.md",
                    "expected_text": ["reusable"],
                }
            )

        with self.assertRaises(ContractValidationError):
            AcceptancePack.from_dict(
                {
                    "schema_version": "missionforge.benchmark_acceptance_pack.v1",
                    "pack_id": "hidden",
                    "task_id": "task-001",
                    "visibility": "hidden",
                    "checks": [
                        {
                            "check_id": "exists",
                            "kind": "file_exists",
                            "ref": "package/SKILL.md",
                        }
                    ],
                    "rubric_ref": ["rubric.md"],
                }
            )

        with self.assertRaises(ContractValidationError):
            AcceptancePack.from_dict(
                {
                    "schema_version": "missionforge.benchmark_acceptance_pack.v1",
                    "pack_id": "hidden",
                    "task_id": "task-001",
                    "visibility": "hidden",
                    "checks": [
                        {
                            "check_id": "exists",
                            "kind": "file_exists",
                            "ref": "package/SKILL.md",
                        }
                    ],
                    "rubric_ref": None,
                }
            )


if __name__ == "__main__":
    unittest.main()
