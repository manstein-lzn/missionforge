from __future__ import annotations

import unittest

from missionforge.benchmark import (
    BenchmarkMode,
    BenchmarkReadinessCheck,
    BenchmarkReadinessReport,
    BenchmarkReadinessStatus,
    build_readiness_report,
)
from missionforge.contracts import ContractValidationError


class BenchmarkReadinessTests(unittest.TestCase):
    def test_ready_report_requires_all_selected_modes_ready(self) -> None:
        report = build_readiness_report(
            benchmark_run_id="s9-ready",
            modes=[BenchmarkMode.DIRECT_PIWORKER_CHAT, BenchmarkMode.MISSIONFORGE_FULL_PRODUCT_FLOW],
            checks=[
                BenchmarkReadinessCheck(
                    check_id="provider_config",
                    status=BenchmarkReadinessStatus.READY,
                    reason="faux provider mode is configured",
                ),
                BenchmarkReadinessCheck(
                    check_id="hidden_acceptance",
                    status=BenchmarkReadinessStatus.READY,
                    reason="hidden acceptance packs are present",
                    evidence_refs=["benchmarks/tasks/task-a/acceptance/hidden_checks.json"],
                ),
            ],
        )

        self.assertEqual(report.status, BenchmarkReadinessStatus.READY)
        self.assertEqual(report.ready_modes, [BenchmarkMode.DIRECT_PIWORKER_CHAT, BenchmarkMode.MISSIONFORGE_FULL_PRODUCT_FLOW])
        self.assertEqual(BenchmarkReadinessReport.from_dict(report.to_dict()), report)

    def test_unavailable_report_has_no_ready_modes(self) -> None:
        report = build_readiness_report(
            benchmark_run_id="s9-unavailable",
            modes=[BenchmarkMode.MISSIONFORGE_FULL_PRODUCT_FLOW],
            checks=[
                BenchmarkReadinessCheck(
                    check_id="provider_config",
                    status=BenchmarkReadinessStatus.UNAVAILABLE,
                    reason="provider config unavailable: missing env",
                )
            ],
        )

        self.assertEqual(report.status, BenchmarkReadinessStatus.UNAVAILABLE)
        self.assertEqual(report.ready_modes, [])

    def test_readiness_rejects_raw_or_secret_shaped_fields(self) -> None:
        payload = {
            "schema_version": "missionforge.benchmark_readiness_check.v1",
            "check_id": "provider_config",
            "status": "ready",
            "reason": "ok",
            "evidence_refs": [],
            "raw_prompt": "leak",
        }

        with self.assertRaises(ContractValidationError):
            BenchmarkReadinessCheck.from_dict(payload)


if __name__ == "__main__":
    unittest.main()
