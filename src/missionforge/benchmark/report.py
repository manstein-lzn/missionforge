"""Deterministic benchmark report rendering."""

from __future__ import annotations

from .contracts import BenchmarkAggregate


def build_aggregate_report(aggregate: BenchmarkAggregate) -> str:
    """Render a compact deterministic Markdown report from aggregate metrics."""

    aggregate.validate()
    lines = [
        f"# MissionForge Benchmark Report: {aggregate.benchmark_run_id}",
        "",
        "## Summary",
        "",
        f"- task_count: {aggregate.task_count}",
        f"- trial_count: {aggregate.trial_count}",
        f"- comparable_trial_count: {aggregate.comparable_trial_count}",
        f"- total_accepted_count: {aggregate.accepted_count}",
        "",
        "## Modes",
        "",
        "| mode | trials | comparable | non_comparable | comparable_accepted | total_accepted | success_rate | comparison_cost | total_cost | cost_per_acceptance | avg_time_ms | p95_time_ms | tokens | tools | repairs |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for mode, values in sorted(aggregate.mode_summaries.items()):
        lines.append(
            "| {mode} | {trial_count} | {comparable_trial_count} | {non_comparable_trial_count} | "
            "{comparable_accepted_count} | {total_accepted_count} | {success_rate:.6f} | "
            "{estimated_cost:.6f} | {total_cost:.6f} | {cost_per_acceptance:.6f} | "
            "{avg_time:.2f} | {p95_time:.2f} | {tokens} | {tools} | {repairs} |".format(
                mode=mode,
                trial_count=int(values.get("trial_count", 0)),
                comparable_trial_count=int(values.get("comparable_trial_count", 0)),
                non_comparable_trial_count=int(values.get("non_comparable_trial_count", 0)),
                comparable_accepted_count=int(values.get("comparable_accepted_count", 0)),
                total_accepted_count=int(values.get("accepted_count", 0)),
                success_rate=float(values.get("success_rate_within_budget", 0.0)),
                estimated_cost=float(values.get("estimated_cost_usd", 0.0)),
                total_cost=float(values.get("total_estimated_cost_usd", 0.0)),
                cost_per_acceptance=float(values.get("cost_per_accepted_deliverable_usd", 0.0)),
                avg_time=float(values.get("avg_time_to_accepted_deliverable_ms", 0.0)),
                p95_time=float(values.get("p95_time_to_accepted_deliverable_ms", 0.0)),
                tokens=int(values.get("total_tokens", 0)),
                tools=int(values.get("tool_call_count", 0)),
                repairs=int(values.get("repair_count", 0)),
            )
        )
    lines.extend(["", "## Winners", ""])
    if aggregate.mode_summaries:
        lines.append(f"- success_rate_within_budget: {_winner(aggregate.mode_summaries, 'success_rate_within_budget', higher=True)}")
        lines.append(
            f"- cost_per_accepted_deliverable_usd: {_winner(aggregate.mode_summaries, 'cost_per_accepted_deliverable_usd', higher=False)}"
        )
        lines.append(
            f"- avg_time_to_accepted_deliverable_ms: {_winner(aggregate.mode_summaries, 'avg_time_to_accepted_deliverable_ms', higher=False)}"
        )
    else:
        lines.append("- none: no mode summaries")
    lines.extend(["", "## Failure Taxonomy", ""])
    if aggregate.failure_taxonomy_counts:
        for name, count in sorted(aggregate.failure_taxonomy_counts.items()):
            lines.append(f"- {name}: {count}")
    else:
        lines.append("- none: 0")
    return "\n".join(lines) + "\n"


def _winner(mode_summaries: dict[str, dict[str, object]], metric: str, *, higher: bool) -> str:
    values = [
        (mode, float(summary.get(metric, 0.0)))
        for mode, summary in mode_summaries.items()
        if isinstance(summary.get(metric, 0.0), (int, float))
        and _eligible_for_metric_winner(summary, metric)
    ]
    if not values:
        return ""
    if not higher:
        non_zero = [(mode, value) for mode, value in values if value > 0]
        values = non_zero or values
    selected = max(values, key=lambda item: (item[1], item[0])) if higher else min(values, key=lambda item: (item[1], item[0]))
    return selected[0]


def _eligible_for_metric_winner(summary: dict[str, object], metric: str) -> bool:
    if metric in {
        "cost_per_accepted_deliverable_usd",
        "avg_time_to_accepted_deliverable_ms",
        "p50_time_to_accepted_deliverable_ms",
        "p95_time_to_accepted_deliverable_ms",
    }:
        count = summary.get("comparable_accepted_count", 0)
        return isinstance(count, int) and count > 0
    return True
