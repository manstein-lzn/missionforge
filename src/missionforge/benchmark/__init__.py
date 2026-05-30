"""MissionForge value benchmark contracts and offline harness."""

from .contracts import (
    BENCHMARK_AGGREGATE_SCHEMA_VERSION,
    BENCHMARK_BUDGET_SCHEMA_VERSION,
    BENCHMARK_SUMMARY_SCHEMA_VERSION,
    BENCHMARK_TASK_SCHEMA_VERSION,
    BENCHMARK_TRIAL_SCHEMA_VERSION,
    BenchmarkAggregate,
    BenchmarkBudget,
    BenchmarkMode,
    BenchmarkStatus,
    BenchmarkSummary,
    BenchmarkTask,
    BenchmarkTrial,
    OfflineTrialOutcome,
)
from .harness import OfflineBenchmarkHarness, OfflineTrialRecord
from .report import build_aggregate_report

__all__ = [
    "BENCHMARK_AGGREGATE_SCHEMA_VERSION",
    "BENCHMARK_BUDGET_SCHEMA_VERSION",
    "BENCHMARK_SUMMARY_SCHEMA_VERSION",
    "BENCHMARK_TASK_SCHEMA_VERSION",
    "BENCHMARK_TRIAL_SCHEMA_VERSION",
    "BenchmarkAggregate",
    "BenchmarkBudget",
    "BenchmarkMode",
    "BenchmarkStatus",
    "BenchmarkSummary",
    "BenchmarkTask",
    "BenchmarkTrial",
    "OfflineBenchmarkHarness",
    "OfflineTrialOutcome",
    "OfflineTrialRecord",
    "build_aggregate_report",
]
