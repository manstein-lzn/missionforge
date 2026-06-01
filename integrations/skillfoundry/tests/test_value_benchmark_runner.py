from __future__ import annotations

import importlib.util
from argparse import Namespace
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from missionforge.benchmark import BenchmarkBudget, BenchmarkMode, BenchmarkPricingTable, BenchmarkReadinessStatus, BenchmarkTask, ModelTokenPrice
from missionforge.contracts import ContractValidationError


def _load_runner():
    script_path = Path(__file__).resolve().parents[3] / "scripts" / "run_value_benchmark.py"
    spec = importlib.util.spec_from_file_location("run_value_benchmark", script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load run_value_benchmark.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ValueBenchmarkRunnerTests(unittest.TestCase):
    def test_runtime_only_fixture_rejects_path_like_run_id_before_writing(self) -> None:
        module = _load_runner()
        with TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            module.ROOT = root

            with self.assertRaises(ContractValidationError):
                module.prepare_runtime_only_fixtures(
                    run_id="../outside",
                    task_items=[],
                    modes=[BenchmarkMode.MISSIONFORGE_RUNTIME_ONLY],
                )

            self.assertFalse((root / "benchmarks").exists())

    def test_readiness_reports_missing_provider_as_unavailable(self) -> None:
        module = _load_runner()
        with TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            module.ROOT = root
            task = _task(root, task_id="task-a")

            report = module.build_value_benchmark_readiness(
                args=_args(provider_mode="live", provider_config_source="env", pricing_table="benchmarks/pricing/test-pricing.json"),
                task_items=[{"task_id": task.task_id, "task_ref": "", "runtime_request_ref": "benchmarks/tasks/task-a/request.json"}],
                tasks=[task],
                modes=[BenchmarkMode.MISSIONFORGE_FULL_PRODUCT_FLOW],
                pricing_table=_pricing_table(model="gpt-test"),
                model="gpt-test",
            )

            self.assertEqual(report.status, BenchmarkReadinessStatus.UNAVAILABLE)
            self.assertEqual(_check_status(report, "provider_config"), BenchmarkReadinessStatus.UNAVAILABLE)

    def test_readiness_reports_missing_hidden_acceptance_as_blocked(self) -> None:
        module = _load_runner()
        with TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            module.ROOT = root
            task = _task(root, task_id="task-a", write_hidden=False)

            report = module.build_value_benchmark_readiness(
                args=_args(provider_mode="faux", provider_config_source="explicit", pricing_table="benchmarks/pricing/test-pricing.json"),
                task_items=[{"task_id": task.task_id, "task_ref": "", "runtime_request_ref": "benchmarks/tasks/task-a/request.json"}],
                tasks=[task],
                modes=[BenchmarkMode.MISSIONFORGE_FULL_PRODUCT_FLOW],
                pricing_table=_pricing_table(model="missionforge-faux"),
                model="missionforge-faux",
            )

            self.assertEqual(report.status, BenchmarkReadinessStatus.BLOCKED)
            self.assertEqual(_check_status(report, "hidden_acceptance"), BenchmarkReadinessStatus.BLOCKED)

    def test_readiness_reports_missing_pricing_as_unavailable(self) -> None:
        module = _load_runner()
        with TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            module.ROOT = root
            task = _task(root, task_id="task-a")

            report = module.build_value_benchmark_readiness(
                args=_args(provider_mode="faux", provider_config_source="explicit", pricing_table="benchmarks/pricing/test-pricing.json"),
                task_items=[{"task_id": task.task_id, "task_ref": "", "runtime_request_ref": "benchmarks/tasks/task-a/request.json"}],
                tasks=[task],
                modes=[BenchmarkMode.MISSIONFORGE_FULL_PRODUCT_FLOW],
                pricing_table=_pricing_table(model="other-model"),
                model="missionforge-faux",
            )

            self.assertEqual(report.status, BenchmarkReadinessStatus.UNAVAILABLE)
            self.assertEqual(_check_status(report, "pricing_model"), BenchmarkReadinessStatus.UNAVAILABLE)

    def test_readiness_ready_offline_prerequisites(self) -> None:
        module = _load_runner()
        with TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            module.ROOT = root
            task = _task(root, task_id="task-a")

            report = module.build_value_benchmark_readiness(
                args=_args(provider_mode="faux", provider_config_source="explicit", pricing_table="benchmarks/pricing/test-pricing.json"),
                task_items=[{"task_id": task.task_id, "task_ref": "", "runtime_request_ref": "benchmarks/tasks/task-a/request.json"}],
                tasks=[task],
                modes=[BenchmarkMode.MISSIONFORGE_RUNTIME_ONLY, BenchmarkMode.MISSIONFORGE_FULL_PRODUCT_FLOW],
                pricing_table=_pricing_table(model="missionforge-faux"),
                model="missionforge-faux",
            )

            self.assertEqual(report.status, BenchmarkReadinessStatus.READY)
            self.assertEqual(report.ready_modes, [BenchmarkMode.MISSIONFORGE_RUNTIME_ONLY, BenchmarkMode.MISSIONFORGE_FULL_PRODUCT_FLOW])


def _args(*, provider_mode: str, provider_config_source: str, pricing_table: str) -> Namespace:
    return Namespace(
        run_id="s9-readiness",
        stage="stage9",
        provider_mode=provider_mode,
        provider_config_source=provider_config_source,
        pricing_table=pricing_table,
    )


def _task(root: Path, *, task_id: str, write_hidden: bool = True) -> BenchmarkTask:
    hidden_ref = f"benchmarks/tasks/{task_id}/acceptance/hidden_checks.json"
    if write_hidden:
        path = root / hidden_ref
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}\n", encoding="utf-8")
    return BenchmarkTask(
        task_id=task_id,
        task_family="skillfoundry",
        difficulty="simple",
        initial_user_text_ref=f"benchmarks/tasks/{task_id}/input.txt",
        budget=BenchmarkBudget(max_wall_minutes=5, max_total_tokens=1000, max_cost_usd=1.0, max_user_turns=1),
        expected_output_refs=["package/SKILL.md"],
        allowed_source_refs=[f"benchmarks/tasks/{task_id}/public.md"],
        acceptance_refs=[hidden_ref],
    )


def _pricing_table(*, model: str) -> BenchmarkPricingTable:
    return BenchmarkPricingTable(
        pricing_table_id="test-pricing",
        model_prices={
            model: ModelTokenPrice(
                model=model,
                input_per_1m_tokens_usd=1.0,
                output_per_1m_tokens_usd=1.0,
            )
        },
    )


def _check_status(report, check_id: str) -> BenchmarkReadinessStatus:
    for check in report.checks:
        if check.check_id == check_id:
            return check.status
    raise AssertionError(check_id)


if __name__ == "__main__":
    unittest.main()
