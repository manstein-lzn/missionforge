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
        f"- accepted_count: {aggregate.accepted_count}",
        "",
        "## Modes",
        "",
        "| mode | trials | comparable | accepted | success_rate | estimated_cost | cost_per_acceptance | tokens | tools | repairs |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for mode, values in sorted(aggregate.mode_summaries.items()):
        lines.append(
            "| {mode} | {trial_count} | {comparable_trial_count} | {accepted_count} | {success_rate:.6f} | "
            "{estimated_cost:.6f} | {cost_per_acceptance:.6f} | {tokens} | {tools} | {repairs} |".format(
                mode=mode,
                trial_count=int(values.get("trial_count", 0)),
                comparable_trial_count=int(values.get("comparable_trial_count", 0)),
                accepted_count=int(values.get("accepted_count", 0)),
                success_rate=float(values.get("success_rate_within_budget", 0.0)),
                estimated_cost=float(values.get("estimated_cost_usd", 0.0)),
                cost_per_acceptance=float(values.get("cost_per_accepted_deliverable_usd", 0.0)),
                tokens=int(values.get("total_tokens", 0)),
                tools=int(values.get("tool_call_count", 0)),
                repairs=int(values.get("repair_count", 0)),
            )
        )
    lines.extend(["", "## Failure Taxonomy", ""])
    if aggregate.failure_taxonomy_counts:
        for name, count in sorted(aggregate.failure_taxonomy_counts.items()):
            lines.append(f"- {name}: {count}")
    else:
        lines.append("- none: 0")
    return "\n".join(lines) + "\n"
