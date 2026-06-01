from __future__ import annotations

import importlib.util
import json
from argparse import Namespace
from pathlib import Path
import tempfile
import unittest

from missionforge.contracts import ContractValidationError


def _load_report_builder():
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "build_value_benchmark_report.py"
    spec = importlib.util.spec_from_file_location("build_value_benchmark_report", script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load build_value_benchmark_report.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ValueBenchmarkReportBuilderTests(unittest.TestCase):
    def test_internal_schema_markers_are_diagnostic_not_blocking(self) -> None:
        module = _load_report_builder()
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            _write_minimal_run(root, "run-a")
            internal_file = root / "benchmarks/runs/run-a/trials/task/mode/seed-1/workspace/frozen_contract.json"
            internal_file.parent.mkdir(parents=True, exist_ok=True)
            internal_file.write_text('{"raw_prompt": "", "provider_payload": {}}', encoding="utf-8")

            module.ROOT = root
            record = module.load_run_record("run-a")
            audit = module.build_leakage_audit([record])

        self.assertTrue(audit["passed"])
        self.assertEqual(audit["leak_hits"], [])
        self.assertEqual(audit["hard_leak_hits"], [])
        self.assertGreaterEqual(audit["internal_scanned_file_count"], 1)
        self.assertTrue(any(hit.endswith(":raw_prompt") for hit in audit["schema_marker_hits"]))
        self.assertTrue(any(hit.endswith(":provider_payload") for hit in audit["schema_marker_hits"]))

    def test_publishable_source_marker_is_blocking(self) -> None:
        module = _load_report_builder()
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            _write_minimal_run(root, "run-a", mode_comparison_note="provider_payload")

            module.ROOT = root
            record = module.load_run_record("run-a")
            audit = module.build_leakage_audit([record])

        self.assertFalse(audit["passed"])
        self.assertTrue(any(hit.endswith(":provider_payload") for hit in audit["hard_leak_hits"]))
        self.assertEqual(audit["leak_hits"], audit["hard_leak_hits"])

    def test_validate_publishable_report_allows_leakage_audit_marker_names(self) -> None:
        module = _load_report_builder()
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            module.ROOT = root
            report_dir = root / "docs/reports/value_benchmark_test"
            report_dir.mkdir(parents=True)
            _write_json(
                report_dir / "leakage_audit.json",
                {
                    "schema_version": "missionforge.value_benchmark_leakage_audit.v1",
                    "leak_markers": ["raw_prompt", "provider_payload", "MISSIONFORGE_PI_AGENT_API_KEY"],
                    "hard_leak_hits": [],
                    "schema_marker_hits": ["benchmarks/runs/run-a/internal.json:raw_prompt"],
                    "passed": True,
                },
            )
            (report_dir / "final_report.md").write_text("# Clean Report\n", encoding="utf-8")

            module.validate_publishable_report(report_dir)

    def test_validate_publishable_report_rejects_raw_field_json(self) -> None:
        module = _load_report_builder()
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            module.ROOT = root
            report_dir = root / "docs/reports/value_benchmark_test"
            report_dir.mkdir(parents=True)
            _write_json(report_dir / "bad.json", {"raw_prompt": "do not publish"})

            with self.assertRaises(ContractValidationError):
                module.validate_publishable_report(report_dir)

    def test_build_stability_summary_summarizes_stage5_rows(self) -> None:
        module = _load_report_builder()
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            module.ROOT = root
            refs = [
                "benchmarks/runs/stage5/trials/task-a/direct_piworker_chat/seed-1/summary.json",
                "benchmarks/runs/stage5/trials/task-a/direct_piworker_chat/seed-2/summary.json",
                "benchmarks/runs/stage5/trials/task-a/missionforge_full_product_flow/seed-1/summary.json",
                "benchmarks/runs/stage5/trials/task-a/missionforge_full_product_flow/seed-2/summary.json",
            ]
            _write_json(
                root / refs[0],
                _summary("task-a", "direct_piworker_chat", 1, accepted=True, cost=0.10, time_ms=100),
            )
            _write_json(
                root / refs[1],
                _summary("task-a", "direct_piworker_chat", 2, accepted=True, cost=0.20, time_ms=200),
            )
            _write_json(
                root / refs[2],
                _summary("task-a", "missionforge_full_product_flow", 1, accepted=True, cost=0.30, time_ms=300),
            )
            _write_json(
                root / refs[3],
                _summary(
                    "task-a",
                    "missionforge_full_product_flow",
                    2,
                    accepted=False,
                    cost=0.0,
                    time_ms=0,
                    failures=["product_gate_failed"],
                ),
            )
            primary = {
                "run_id": "stage4",
                "aggregate": {
                    "mode_summaries": {
                        "direct_piworker_chat": {"success_rate_within_budget": 1.0},
                        "missionforge_full_product_flow": {"success_rate_within_budget": 1.0},
                    }
                },
            }
            stage5 = {
                "run_id": "stage5",
                "stage": "stage5_stability",
                "aggregate": {
                    "summary_refs": refs,
                    "failure_taxonomy_counts": {"product_gate_failed": 1},
                },
            }

            summary = module.build_stability_summary([stage5], primary_run=primary)

        self.assertEqual(summary["status"], "available")
        self.assertEqual(summary["task_ids"], ["task-a"])
        full_row = next(row for row in summary["mode_rows"] if row["mode"] == "missionforge_full_product_flow")
        self.assertEqual(full_row["accepted_count"], 1)
        self.assertEqual(full_row["trial_count"], 2)
        self.assertEqual(full_row["success_rate"], 0.5)
        self.assertEqual(full_row["failure_taxonomy_counts"], {"product_gate_failed": 1})
        self.assertIn("weakened", summary["interpretation"])

    def test_stage5_claim_requires_direct_metric_advantage(self) -> None:
        module = _load_report_builder()
        primary = {
            "aggregate": {
                "task_count": 5,
                "mode_summaries": {},
            },
            "mode_comparisons": {
                "winner_by_cost_per_acceptance": "direct_piworker_chat",
                "winner_by_time_to_acceptance": "direct_piworker_chat",
            },
        }
        stability = {
            "status": "available",
            "interpretation": "fixture",
            "mode_rows": [
                {
                    "mode": "direct_piworker_chat",
                    "success_rate": 0.5,
                    "cost_per_accepted_deliverable_usd": 0.30,
                    "p95_time_to_accepted_deliverable_ms": 300.0,
                },
                {
                    "mode": "missionforge_full_product_flow",
                    "success_rate": 1.0,
                    "cost_per_accepted_deliverable_usd": 0.10,
                    "p95_time_to_accepted_deliverable_ms": 100.0,
                },
            ],
        }

        claims = module.claims_we_can_make(
            primary=primary,
            stability_summary=stability,
            leakage={"passed": True},
            blind_review_waived=False,
        )

        self.assertFalse(any("direct PiWorker chat had higher" in claim for claim in claims))

    def test_stage5_lower_cost_claim_requires_available_cost_data(self) -> None:
        module = _load_report_builder()
        primary = {
            "aggregate": {"task_count": 5, "mode_summaries": {}},
            "mode_comparisons": {
                "winner_by_cost_per_acceptance": "direct_piworker_chat",
                "winner_by_time_to_acceptance": "direct_piworker_chat",
            },
        }
        stability = {
            "status": "available",
            "interpretation": "fixture",
            "mode_rows": [
                {
                    "mode": "direct_piworker_chat",
                    "success_rate": 1.0,
                    "cost_source": "unavailable",
                    "estimated_cost_available_count": 0,
                    "cost_per_accepted_deliverable_usd": 0.0,
                    "p95_time_to_accepted_deliverable_ms": 50.0,
                },
                {
                    "mode": "missionforge_full_product_flow",
                    "success_rate": 0.5,
                    "cost_source": "pricing_table",
                    "estimated_cost_available_count": 1,
                    "cost_per_accepted_deliverable_usd": 0.10,
                    "p95_time_to_accepted_deliverable_ms": 100.0,
                },
            ],
        }

        claims = module.claims_we_can_make(
            primary=primary,
            stability_summary=stability,
            leakage={"passed": True},
            blind_review_waived=False,
        )

        self.assertFalse(any("lower projected cost" in claim for claim in claims))

    def test_readiness_unavailable_suppresses_winner_claims(self) -> None:
        module = _load_report_builder()
        primary = {
            "aggregate": {
                "task_count": 5,
                "mode_summaries": {
                    "direct_piworker_chat": {"success_rate_within_budget": 1.0},
                    "missionforge_full_product_flow": {"success_rate_within_budget": 0.0},
                },
            },
            "mode_comparisons": {
                "winner_by_cost_per_acceptance": "direct_piworker_chat",
                "winner_by_time_to_acceptance": "direct_piworker_chat",
            },
            "readiness_report": {
                "schema_version": "missionforge.benchmark_readiness_report.v1",
                "benchmark_run_id": "s9",
                "status": "unavailable",
                "modes": ["direct_piworker_chat", "missionforge_full_product_flow"],
                "ready_modes": [],
                "reason": "one or more benchmark prerequisites are unavailable",
                "checks": [],
            },
        }

        claims = module.claims_we_can_make(
            primary=primary,
            stability_summary={"status": "available", "interpretation": "direct wins", "mode_rows": []},
            leakage={"passed": True},
            blind_review_waived=False,
        )
        cannot = module.claims_we_cannot_make(primary=primary, leakage={"passed": True}, blind_review_waived=False)

        self.assertTrue(any("readiness status `unavailable`" in claim for claim in claims))
        self.assertFalse(any("In Stage 4" in claim for claim in claims))
        self.assertTrue(any("not product failures" in claim for claim in cannot))

    def test_load_run_record_includes_readiness_report_ref(self) -> None:
        module = _load_report_builder()
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            _write_minimal_run(root, "run-a")
            _write_json(
                root / "benchmarks/runs/run-a/readiness/readiness_report.json",
                {
                    "schema_version": "missionforge.benchmark_readiness_report.v1",
                    "benchmark_run_id": "run-a",
                    "status": "ready",
                    "modes": ["direct_piworker_chat"],
                    "ready_modes": ["direct_piworker_chat"],
                    "reason": "all selected benchmark prerequisites are ready",
                    "checks": [
                        {
                            "schema_version": "missionforge.benchmark_readiness_check.v1",
                            "check_id": "provider_config",
                            "status": "ready",
                            "reason": "faux provider mode is configured",
                            "evidence_refs": [],
                        }
                    ],
                },
            )
            module.ROOT = root

            record = module.load_run_record("run-a")

        self.assertEqual(record["readiness_report_ref"], "benchmarks/runs/run-a/readiness/readiness_report.json")
        self.assertEqual(record["readiness_report"]["status"], "ready")

    def test_readiness_only_skipped_run_is_reportable(self) -> None:
        module = _load_report_builder()
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            run_root = root / "benchmarks/runs/run-skipped"
            _write_json(
                run_root / "execution_summary.json",
                {
                    "schema_version": "missionforge.value_benchmark_execution_summary.v1",
                    "run_id": "run-skipped",
                    "stage": "s9",
                    "task_ids": ["task"],
                    "modes": ["missionforge_full_product_flow"],
                    "seeds": [1],
                    "provider_mode": "live",
                    "provider_config_source": "env",
                    "provider_env": {},
                    "pricing_table_id": "fixture-prices",
                    "readiness_report_ref": "benchmarks/runs/run-skipped/readiness/readiness_report.json",
                    "readiness_status": "unavailable",
                },
            )
            _write_json(
                run_root / "readiness/readiness_report.json",
                {
                    "schema_version": "missionforge.benchmark_readiness_report.v1",
                    "benchmark_run_id": "run-skipped",
                    "status": "unavailable",
                    "modes": ["missionforge_full_product_flow"],
                    "ready_modes": [],
                    "reason": "one or more benchmark prerequisites are unavailable",
                    "checks": [
                        {
                            "schema_version": "missionforge.benchmark_readiness_check.v1",
                            "check_id": "provider_config",
                            "status": "unavailable",
                            "reason": "provider config unavailable: missing env",
                            "evidence_refs": [],
                        }
                    ],
                },
            )
            module.ROOT = root

            record = module.load_run_record("run-skipped")
            claims = module.claims_we_can_make(
                primary=record,
                stability_summary={"status": "not_available"},
                leakage={"passed": True},
                blind_review_waived=False,
            )

        self.assertEqual(record["aggregate"]["trial_count"], 0)
        self.assertTrue(any("readiness status `unavailable`" in claim for claim in claims))

    def test_ready_run_missing_primary_artifacts_is_rejected(self) -> None:
        module = _load_report_builder()
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            run_root = root / "benchmarks/runs/run-ready-incomplete"
            _write_json(
                run_root / "aggregate.json",
                {
                    "schema_version": "missionforge.benchmark_aggregate.v1",
                    "benchmark_run_id": "run-ready-incomplete",
                    "task_count": 1,
                    "trial_count": 1,
                    "accepted_count": 1,
                    "comparable_trial_count": 1,
                    "mode_summaries": {},
                    "failure_taxonomy_counts": {},
                    "summary_refs": [],
                },
            )
            _write_json(
                run_root / "readiness/readiness_report.json",
                {
                    "schema_version": "missionforge.benchmark_readiness_report.v1",
                    "benchmark_run_id": "run-ready-incomplete",
                    "status": "ready",
                    "modes": ["direct_piworker_chat"],
                    "ready_modes": ["direct_piworker_chat"],
                    "reason": "all selected benchmark prerequisites are ready",
                    "checks": [
                        {
                            "schema_version": "missionforge.benchmark_readiness_check.v1",
                            "check_id": "provider_config",
                            "status": "ready",
                            "reason": "faux provider mode is configured",
                            "evidence_refs": [],
                        }
                    ],
                },
            )
            module.ROOT = root

            with self.assertRaisesRegex(ContractValidationError, "missing primary result artifacts"):
                module.load_run_record("run-ready-incomplete")

    def test_primary_task_mode_summary_includes_acceptance_and_gate_counts(self) -> None:
        module = _load_report_builder()
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            module.ROOT = root
            refs = [
                "benchmarks/runs/stage4/trials/task-a/missionforge_full_product_flow/seed-1/summary.json",
                "benchmarks/runs/stage4/trials/task-a/missionforge_full_product_flow/seed-2/summary.json",
            ]
            accepted = _summary("task-a", "missionforge_full_product_flow", 1, accepted=True, cost=0.10, time_ms=100)
            accepted["product_gate_status"] = "product_grade"
            accepted["hidden_acceptance_passed"] = True
            failed = _summary(
                "task-a",
                "missionforge_full_product_flow",
                2,
                accepted=False,
                cost=0.05,
                time_ms=0,
                failures=["product_gate_failed"],
            )
            failed["product_gate_status"] = "failed"
            failed["hidden_acceptance_passed"] = False
            _write_json(root / refs[0], accepted)
            _write_json(root / refs[1], failed)
            primary = {
                "run_id": "stage4",
                "stage": "stage4_initial_ab",
                "aggregate": {
                    "summary_refs": refs,
                    "failure_taxonomy_counts": {"product_gate_failed": 1},
                },
            }

            summary = module.build_primary_task_mode_summary(primary)

        row = summary["task_mode_rows"][0]
        self.assertEqual(row["accepted_count"], 1)
        self.assertEqual(row["hidden_acceptance_passed_count"], 1)
        self.assertEqual(row["hidden_acceptance_failed_count"], 1)
        self.assertEqual(row["product_gate_passed_count"], 1)
        self.assertEqual(row["product_gate_failed_count"], 1)
        self.assertEqual(row["failure_taxonomy_counts"], {"product_gate_failed": 1})

    def test_reproduction_includes_exact_task_ids_provider_and_report_flags(self) -> None:
        module = _load_report_builder()
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            module.ROOT = root
            _write_minimal_run(root, "run-a")
            record = module.load_run_record("run-a")
            args = Namespace(
                task_manifest="benchmarks/tasks/value_benchmark_manifest.json",
                pricing_table="benchmarks/pricing/pi-pricing-20260531.json",
                run_ids="run-a",
                primary_run_id="run-a",
                waive_blind_review=True,
                blind_review_rationale="Deterministic checks only",
            )

            text = module.reproduction(args=args, run_records=[record], report_dir=root / "docs/reports/report-a")

        self.assertIn("--task-ids task", text)
        self.assertIn("--provider-config-source explicit", text)
        self.assertIn("--timeout-seconds 900", text)
        self.assertIn("--max-turns 16", text)
        self.assertIn("--tool-timeout-seconds 60", text)
        self.assertIn("--primary-run-id run-a", text)
        self.assertIn("--blind-review-rationale 'Deterministic checks only'", text)

    def test_final_report_contains_required_completion_sections(self) -> None:
        module = _load_report_builder()
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            module.ROOT = root
            _write_minimal_run(root, "run-a")
            _write_task_manifest(root)
            record = module.load_run_record("run-a")
            task_manifest = module.read_json_ref("benchmarks/tasks/value_benchmark_manifest.json")
            pricing_table = {
                "schema_version": "missionforge.benchmark_pricing_table.v1",
                "pricing_table_id": "fixture-prices",
                "currency": "USD",
                "effective_date": "2026-05-31",
                "model_prices": {"missionforge-faux": {"model": "missionforge-faux"}},
            }

            text = module.final_report(
                report_dir=root / "docs/reports/report-a",
                run_records=[record],
                primary=record,
                primary_task_mode_summary=module.build_primary_task_mode_summary(record),
                task_manifest=task_manifest,
                pricing_table=pricing_table,
                stability_summary={"status": "not_available"},
                leakage={"passed": True, "scanned_file_count": 1, "hard_leak_hits": [], "schema_marker_hits": []},
                failure_taxonomy={"failure_taxonomy_counts": {}},
                blind_review_waived=True,
            )

        for heading in [
            "## Compared Modes",
            "## Fairness Controls",
            "## Task Inventory",
            "## Cost Method",
            "## Stage 4 Task/Mode Detail",
            "## Reproduction",
        ]:
            self.assertIn(heading, text)


def _write_minimal_run(root: Path, run_id: str, *, mode_comparison_note: str = "") -> None:
    run_root = root / "benchmarks/runs" / run_id
    run_root.mkdir(parents=True)
    _write_json(
        run_root / "aggregate.json",
        {
            "schema_version": "missionforge.benchmark_aggregate.v1",
            "benchmark_run_id": run_id,
            "task_count": 1,
            "trial_count": 1,
            "accepted_count": 1,
            "comparable_trial_count": 1,
            "mode_summaries": {},
            "failure_taxonomy_counts": {},
            "summary_refs": [],
        },
    )
    _write_json(
        run_root / "mode_comparisons.json",
        {
            "schema_version": "missionforge.benchmark_mode_comparison.v1",
            "benchmark_run_id": run_id,
            "baseline_mode": "direct_piworker_chat",
            "effect_size_rows": [],
            "winner_by_success_rate": "",
            "winner_by_cost_per_acceptance": "",
            "winner_by_time_to_acceptance": "",
            "note": mode_comparison_note,
        },
    )
    _write_json(
        run_root / "table_data.json",
        {
            "schema_version": "missionforge.benchmark_table_data.v1",
            "benchmark_run_id": run_id,
            "mode_rows": [],
            "task_rows": [],
        },
    )
    _write_json(
        run_root / "multiseed_result.json",
        {
            "schema_version": "missionforge.benchmark_multiseed_result.v1",
            "manifest_ref": f"benchmarks/runs/{run_id}/manifest.json",
            "aggregate_ref": f"benchmarks/runs/{run_id}/aggregate.json",
            "mode_comparison_ref": f"benchmarks/runs/{run_id}/mode_comparisons.json",
            "table_data_ref": f"benchmarks/runs/{run_id}/table_data.json",
            "report_ref": f"benchmarks/runs/{run_id}/report.md",
            "summary_refs": [],
            "hidden_acceptance_result_refs": [],
            "non_comparable_trial_refs": [],
        },
    )
    _write_json(
        run_root / "execution_summary.json",
        {
            "schema_version": "missionforge.value_benchmark_execution_summary.v1",
            "run_id": run_id,
            "stage": "test",
            "task_ids": ["task"],
            "modes": ["direct_piworker_chat"],
            "seeds": [1],
            "provider_mode": "faux",
            "provider_config_source": "explicit",
            "provider_env": {
                "MISSIONFORGE_PI_AGENT_MAX_TURNS": "16",
                "MISSIONFORGE_PI_AGENT_MODEL": "missionforge-faux",
                "MISSIONFORGE_PI_AGENT_TOOL_TIMEOUT_SECONDS": "60",
            },
            "pricing_table_id": "fixture-prices",
        },
    )


def _write_task_manifest(root: Path) -> None:
    _write_json(
        root / "benchmarks/tasks/value_benchmark_manifest.json",
        {
            "schema_version": "missionforge.value_benchmark_manifest.v1",
            "tasks": [
                {
                    "task_id": "task",
                    "task_ref": "benchmarks/tasks/task/task.json",
                    "hypothesis": "fixture hypothesis",
                }
            ],
        },
    )
    _write_json(
        root / "benchmarks/tasks/task/task.json",
        {
            "schema_version": "missionforge.benchmark_task.v1",
            "task_id": "task",
            "task_family": "fixture",
            "difficulty": "small",
            "budget": {
                "schema_version": "missionforge.benchmark_budget.v1",
                "max_wall_minutes": 1,
                "max_total_tokens": 100,
                "max_cost_usd": 0.01,
                "max_user_turns": 1,
            },
        },
    )


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def _summary(
    task_id: str,
    mode: str,
    seed: int,
    *,
    accepted: bool,
    cost: float,
    time_ms: int,
    failures: list[str] | None = None,
) -> dict:
    return {
        "schema_version": "missionforge.benchmark_summary.v1",
        "task_id": task_id,
        "mode": mode,
        "seed": seed,
        "accepted": accepted,
        "status": "accepted" if accepted else "failed",
        "comparable": True,
        "cost_source": "pricing_table" if accepted else "unavailable",
        "estimated_cost_usd": cost,
        "time_to_accepted_deliverable_ms": time_ms,
        "failure_taxonomy": list(failures or []),
    }
