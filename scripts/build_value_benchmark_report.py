#!/usr/bin/env python3
"""Build a sanitized MissionForge value benchmark report pack."""

from __future__ import annotations

import argparse
import json
import shlex
import shutil
from pathlib import Path
from typing import Any, Mapping

from missionforge.contracts import ContractValidationError, assert_refs_only_payload, require_mapping, validate_ref


ROOT = Path.cwd().resolve()
SCHEMA_MARKERS = [
    "raw_prompt",
    "raw_transcript",
    "provider_payload",
]
HARD_LEAK_MARKERS = [
    "raw_provider_payload",
    "OPENAI_API_KEY",
    "MISSIONFORGE_PI_AGENT_API_KEY",
]
LEAK_MARKERS = SCHEMA_MARKERS + HARD_LEAK_MARKERS
MAX_LEAK_SCAN_BYTES = 2_000_000
PRODUCT_GATE_PASS_STATUSES = {"passed", "product_grade"}
PRODUCT_GATE_FAIL_STATUSES = {"failed"}


def main() -> None:
    args = parse_args()
    run_ids = parse_csv(args.run_ids)
    if not run_ids:
        raise ContractValidationError("at least one run id is required")
    report_dir = report_dir_for(args.report_dir)
    if report_dir.exists():
        if not args.force:
            raise ContractValidationError(f"report dir already exists: {report_dir.relative_to(ROOT)}")
        shutil.rmtree(report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)
    pricing_table = read_json_ref(args.pricing_table)
    task_manifest = read_json_ref(args.task_manifest)
    run_records = [load_run_record(run_id) for run_id in run_ids]
    primary = select_primary_run(run_records, args.primary_run_id)
    primary_task_mode_summary = build_primary_task_mode_summary(primary)
    stability_summary = build_stability_summary(run_records, primary_run=primary)
    leakage = build_leakage_audit(run_records)
    failure_taxonomy = merge_failure_taxonomy(run_records)
    write_json(report_dir / "pricing_table.json", pricing_table)
    write_json(report_dir / "fixture_manifest.json", task_manifest)
    write_json(report_dir / "aggregate.json", primary["aggregate"])
    write_json(report_dir / "mode_comparisons.json", primary["mode_comparisons"])
    write_json(report_dir / "table_data.json", primary["table_data"])
    write_json(report_dir / "run_index.json", build_run_index(run_records))
    write_json(report_dir / "failure_taxonomy.json", failure_taxonomy)
    write_json(report_dir / "stage4_task_mode_summary.json", primary_task_mode_summary)
    write_json(report_dir / "stability_summary.json", stability_summary)
    write_json(report_dir / "leakage_audit.json", leakage)
    write_json(report_dir / "reviewer_packet_index.json", reviewer_packet_index(args))
    write_text(report_dir / "blind_review_summary.md", blind_review_summary(args))
    write_text(report_dir / "reproduction.md", reproduction(args=args, run_records=run_records, report_dir=report_dir))
    write_text(report_dir / "README.md", readme(report_dir=report_dir, run_records=run_records))
    write_text(
        report_dir / "final_report.md",
        final_report(
            report_dir=report_dir,
            run_records=run_records,
            primary=primary,
            primary_task_mode_summary=primary_task_mode_summary,
            task_manifest=task_manifest,
            pricing_table=pricing_table,
            stability_summary=stability_summary,
            leakage=leakage,
            failure_taxonomy=failure_taxonomy,
            blind_review_waived=args.waive_blind_review,
        ),
    )
    validate_publishable_report(report_dir)
    print(json.dumps({"event": "report_pack_built", "report_dir": str(report_dir.relative_to(ROOT))}, sort_keys=True))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report-dir", required=True)
    parser.add_argument("--run-ids", required=True)
    parser.add_argument("--primary-run-id", default="")
    parser.add_argument("--task-manifest", required=True)
    parser.add_argument("--pricing-table", required=True)
    parser.add_argument("--waive-blind-review", action="store_true")
    parser.add_argument("--blind-review-rationale", default="Deterministic hidden checks and ProductGate coverage are sufficient for this report.")
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def parse_csv(text: str) -> list[str]:
    return [item.strip() for item in text.split(",") if item.strip()]


def report_dir_for(ref: str) -> Path:
    safe = validate_ref(ref, "report_dir")
    path = (ROOT / safe).resolve()
    reports_root = (ROOT / "docs/reports").resolve()
    if reports_root not in path.parents and path != reports_root:
        raise ContractValidationError("report dir must be under docs/reports")
    return path


def read_json_ref(ref: str) -> dict[str, Any]:
    path = ROOT / validate_ref(ref, "json_ref")
    return require_mapping(json.loads(path.read_text(encoding="utf-8")), ref)


def read_json_path(path: Path) -> dict[str, Any]:
    return require_mapping(json.loads(path.read_text(encoding="utf-8")), str(path.relative_to(ROOT)))


def load_run_record(run_id: str) -> dict[str, Any]:
    run_ref = validate_ref(f"benchmarks/runs/{run_id}", "run_id")
    run_root = ROOT / run_ref
    if not run_root.is_dir():
        raise ContractValidationError(f"benchmark run not found: {run_ref}")
    aggregate = read_json_path(run_root / "aggregate.json")
    mode_comparisons = read_json_path(run_root / "mode_comparisons.json")
    table_data = read_json_path(run_root / "table_data.json")
    multiseed = read_json_path(run_root / "multiseed_result.json")
    execution_summary = read_json_path(run_root / "execution_summary.json") if (run_root / "execution_summary.json").is_file() else {}
    return {
        "run_id": run_id,
        "run_ref": run_ref,
        "stage": execution_summary.get("stage", ""),
        "aggregate_ref": f"{run_ref}/aggregate.json",
        "mode_comparison_ref": f"{run_ref}/mode_comparisons.json",
        "table_data_ref": f"{run_ref}/table_data.json",
        "multiseed_result_ref": f"{run_ref}/multiseed_result.json",
        "execution_summary_ref": f"{run_ref}/execution_summary.json" if execution_summary else "",
        "aggregate": aggregate,
        "mode_comparisons": mode_comparisons,
        "table_data": table_data,
        "multiseed": multiseed,
        "execution_summary": execution_summary,
    }


def select_primary_run(run_records: list[dict[str, Any]], primary_run_id: str) -> dict[str, Any]:
    if primary_run_id:
        for record in run_records:
            if record["run_id"] == primary_run_id:
                return record
        raise ContractValidationError(f"primary run id not found: {primary_run_id}")
    return run_records[-1]


def build_run_index(run_records: list[dict[str, Any]]) -> dict[str, Any]:
    rows = []
    for record in run_records:
        summary = record["execution_summary"]
        aggregate = record["aggregate"]
        rows.append(
            {
                "run_id": record["run_id"],
                "stage": record.get("stage", ""),
                "run_ref": record["run_ref"],
                "task_ids": list(summary.get("task_ids", [])),
                "modes": list(summary.get("modes", [])),
                "seeds": list(summary.get("seeds", [])),
                "provider_mode": summary.get("provider_mode", ""),
                "provider_config_source": summary.get("provider_config_source", ""),
                "pricing_table_id": summary.get("pricing_table_id", ""),
                "trial_count": aggregate.get("trial_count", 0),
                "accepted_count": aggregate.get("accepted_count", 0),
                "comparable_trial_count": aggregate.get("comparable_trial_count", 0),
                "aggregate_ref": record["aggregate_ref"],
                "mode_comparison_ref": record["mode_comparison_ref"],
                "table_data_ref": record["table_data_ref"],
                "execution_summary_ref": record["execution_summary_ref"],
            }
        )
    payload = {"schema_version": "missionforge.value_benchmark_run_index.v1", "runs": rows}
    assert_refs_only_payload(payload, "run_index")
    return payload


def merge_failure_taxonomy(run_records: list[dict[str, Any]]) -> dict[str, Any]:
    counts: dict[str, int] = {}
    for record in run_records:
        for name, count in record["aggregate"].get("failure_taxonomy_counts", {}).items():
            counts[str(name)] = counts.get(str(name), 0) + int(count)
    return {
        "schema_version": "missionforge.value_benchmark_failure_taxonomy.v1",
        "failure_taxonomy_counts": dict(sorted(counts.items())),
    }


def build_stability_summary(run_records: list[dict[str, Any]], *, primary_run: Mapping[str, Any]) -> dict[str, Any]:
    stability_records = [record for record in run_records if record.get("stage") == "stage5_stability"]
    if not stability_records:
        return {
            "schema_version": "missionforge.value_benchmark_stability_summary.v1",
            "status": "not_available",
            "stage5_run_id": "",
            "primary_run_id": primary_run["run_id"],
            "task_ids": [],
            "modes": [],
            "seed_list": [],
            "mode_rows": [],
            "task_mode_rows": [],
            "failure_taxonomy_counts": {},
            "interpretation": "No Stage 5 stability run was included in this report pack.",
        }
    record = stability_records[-1]
    summaries = load_summary_rows(record)
    mode_rows = summarize_rows_by(summaries, keys=["mode"])
    task_mode_rows = summarize_rows_by(summaries, keys=["task_id", "mode"])
    stage4_full = _mode_summary(primary_run, "missionforge_full_product_flow")
    stage5_full = next((row for row in mode_rows if row.get("mode") == "missionforge_full_product_flow"), {})
    stage4_direct = _mode_summary(primary_run, "direct_piworker_chat")
    stage5_direct = next((row for row in mode_rows if row.get("mode") == "direct_piworker_chat"), {})
    return {
        "schema_version": "missionforge.value_benchmark_stability_summary.v1",
        "status": "available",
        "stage5_run_id": record["run_id"],
        "primary_run_id": primary_run["run_id"],
        "task_ids": sorted({str(row.get("task_id", "")) for row in summaries if row.get("task_id")}),
        "modes": sorted({str(row.get("mode", "")) for row in summaries if row.get("mode")}),
        "seed_list": sorted({int(row.get("seed", 0)) for row in summaries}),
        "mode_rows": mode_rows,
        "task_mode_rows": task_mode_rows,
        "failure_taxonomy_counts": record["aggregate"].get("failure_taxonomy_counts", {}),
        "interpretation": stability_interpretation(
            stage4_direct=stage4_direct,
            stage4_full=stage4_full,
            stage5_direct=stage5_direct,
            stage5_full=stage5_full,
        ),
    }


def build_primary_task_mode_summary(primary_run: Mapping[str, Any]) -> dict[str, Any]:
    summaries = load_summary_rows(primary_run)
    return {
        "schema_version": "missionforge.value_benchmark_stage4_task_mode_summary.v1",
        "status": "available" if summaries else "not_available",
        "primary_run_id": primary_run["run_id"],
        "stage": primary_run.get("stage", ""),
        "task_ids": sorted({str(row.get("task_id", "")) for row in summaries if row.get("task_id")}),
        "modes": sorted({str(row.get("mode", "")) for row in summaries if row.get("mode")}),
        "seed_list": sorted({int(row.get("seed", 0)) for row in summaries}),
        "mode_rows": summarize_rows_by(summaries, keys=["mode"]),
        "task_mode_rows": summarize_rows_by(summaries, keys=["task_id", "mode"]),
        "failure_taxonomy_counts": primary_run["aggregate"].get("failure_taxonomy_counts", {}),
    }


def load_summary_rows(record: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for ref in record["aggregate"].get("summary_refs", []):
        rows.append(read_json_ref(validate_ref(ref, "benchmark_summary_ref")))
    return rows


def summarize_rows_by(rows: list[Mapping[str, Any]], *, keys: list[str]) -> list[dict[str, Any]]:
    buckets: dict[tuple[str, ...], list[Mapping[str, Any]]] = {}
    for row in rows:
        bucket_key = tuple(str(row.get(key, "")) for key in keys)
        buckets.setdefault(bucket_key, []).append(row)
    result: list[dict[str, Any]] = []
    for bucket_key, bucket_rows in sorted(buckets.items()):
        accepted_rows = [row for row in bucket_rows if bool(row.get("accepted", False))]
        comparable_count = sum(1 for row in bucket_rows if bool(row.get("comparable", True)))
        accepted_count = len(accepted_rows)
        cost_available_rows = [row for row in bucket_rows if str(row.get("cost_source", "")) != "unavailable"]
        available_costs = [float(row.get("estimated_cost_usd", 0.0)) for row in cost_available_rows]
        accepted_times = [int(row.get("time_to_accepted_deliverable_ms", 0)) for row in accepted_rows]
        failure_counts: dict[str, int] = {}
        product_gate_status_counts: dict[str, int] = {}
        for row in bucket_rows:
            gate_status = str(row.get("product_gate_status", "") or "not_applicable")
            product_gate_status_counts[gate_status] = product_gate_status_counts.get(gate_status, 0) + 1
            if bool(row.get("accepted", False)):
                continue
            for name in row.get("failure_taxonomy", []):
                failure_counts[str(name)] = failure_counts.get(str(name), 0) + 1
        output = {key: value for key, value in zip(keys, bucket_key)}
        output.update(
            {
                "trial_count": len(bucket_rows),
                "comparable_trial_count": comparable_count,
                "accepted_count": accepted_count,
                "success_rate": accepted_count / comparable_count if comparable_count else 0.0,
                "cost_source": _cost_source_for_rows(cost_available_rows),
                "estimated_cost_available_count": sum(
                    1 for row in bucket_rows if str(row.get("cost_source", "")) != "unavailable"
                ),
                "cost_per_accepted_deliverable_usd": sum(available_costs) / accepted_count if accepted_count else 0.0,
                "p50_cost_per_acceptance_usd": _percentile_float(available_costs, 0.50),
                "p95_cost_per_acceptance_usd": _percentile_float(available_costs, 0.95),
                "avg_time_to_accepted_deliverable_ms": sum(accepted_times) / accepted_count if accepted_count else 0.0,
                "p50_time_to_accepted_deliverable_ms": _percentile_int(accepted_times, 0.50),
                "p95_time_to_accepted_deliverable_ms": _percentile_int(accepted_times, 0.95),
                "hidden_acceptance_passed_count": sum(
                    1 for row in bucket_rows if bool(row.get("hidden_acceptance_passed", False))
                ),
                "hidden_acceptance_failed_count": sum(
                    1 for row in bucket_rows if not bool(row.get("hidden_acceptance_passed", False))
                ),
                "product_gate_passed_count": sum(
                    product_gate_status_counts.get(status, 0) for status in PRODUCT_GATE_PASS_STATUSES
                ),
                "product_gate_failed_count": sum(
                    product_gate_status_counts.get(status, 0) for status in PRODUCT_GATE_FAIL_STATUSES
                ),
                "product_gate_unsupported_count": product_gate_status_counts.get("unsupported", 0),
                "product_gate_not_applicable_count": product_gate_status_counts.get("not_applicable", 0),
                "product_gate_status_counts": dict(sorted(product_gate_status_counts.items())),
                "failure_taxonomy_counts": dict(sorted(failure_counts.items())),
            }
        )
        result.append(output)
    return result


def _cost_source_for_rows(rows: list[Mapping[str, Any]]) -> str:
    sources = {str(row.get("cost_source", "unavailable")) for row in rows}
    if not rows or not sources:
        return "unavailable"
    if len(sources) == 1:
        return next(iter(sources))
    return "mixed"


def _percentile_int(values: list[int], percentile: float) -> float:
    return float(_percentile(sorted(values), percentile))


def _percentile_float(values: list[float], percentile: float) -> float:
    return float(_percentile(sorted(values), percentile))


def _percentile(values: list[float] | list[int], percentile: float) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return float(values[0])
    index = int(round((len(values) - 1) * percentile))
    index = max(0, min(index, len(values) - 1))
    return float(values[index])


def _mode_summary(record: Mapping[str, Any], mode: str) -> Mapping[str, Any]:
    return require_mapping(record["aggregate"].get("mode_summaries", {}).get(mode, {}), f"{record['run_id']}.{mode}")


def stability_interpretation(
    *,
    stage4_direct: Mapping[str, Any],
    stage4_full: Mapping[str, Any],
    stage5_direct: Mapping[str, Any],
    stage5_full: Mapping[str, Any],
) -> str:
    stage4_delta = float(stage4_full.get("success_rate_within_budget", 0.0)) - float(
        stage4_direct.get("success_rate_within_budget", 0.0)
    )
    stage5_delta = float(stage5_full.get("success_rate", 0.0)) - float(stage5_direct.get("success_rate", 0.0))
    if stage5_delta < stage4_delta:
        return "Stage 5 weakened the full-product-flow signal relative to direct chat."
    if stage5_delta > stage4_delta:
        return "Stage 5 strengthened the full-product-flow signal relative to direct chat."
    return "Stage 5 preserved the Stage 4 success-rate signal."


def build_leakage_audit(run_records: list[dict[str, Any]]) -> dict[str, Any]:
    publishable_hits: list[str] = []
    internal_schema_hits: list[str] = []
    internal_marker_hits: list[str] = []
    publishable_scanned_files = 0
    internal_scanned_files = 0
    publishable_paths = publishable_source_paths(run_records)
    publishable_path_set = set(publishable_paths)
    for path in publishable_paths:
        text = read_scannable_text(path)
        if text is None:
            continue
        publishable_scanned_files += 1
        publishable_hits.extend(marker_hits(path, text, LEAK_MARKERS))
    for record in run_records:
        run_root = ROOT / record["run_ref"]
        for path in sorted(run_root.rglob("*")):
            if path in publishable_path_set:
                continue
            text = read_scannable_text(path)
            if text is None:
                continue
            internal_scanned_files += 1
            schema_hits = marker_hits(path, text, SCHEMA_MARKERS)
            all_hits = marker_hits(path, text, LEAK_MARKERS)
            internal_schema_hits.extend(schema_hits)
            internal_marker_hits.extend(all_hits)
    hard_hits = sorted(set(publishable_hits))
    return {
        "schema_version": "missionforge.value_benchmark_leakage_audit.v1",
        "audit_scope": "publishable report sources are blocking; internal run artifacts are diagnostic only",
        "scanned_file_count": publishable_scanned_files,
        "publishable_scanned_file_count": publishable_scanned_files,
        "internal_scanned_file_count": internal_scanned_files,
        "leak_markers": LEAK_MARKERS,
        "schema_markers": SCHEMA_MARKERS,
        "hard_leak_markers": HARD_LEAK_MARKERS,
        "publishable_blocking_markers": LEAK_MARKERS,
        "hard_leak_hits": hard_hits,
        "schema_marker_hits": sorted(set(internal_schema_hits)),
        "internal_marker_hits": sorted(set(internal_marker_hits)),
        "leak_hits": hard_hits,
        "passed": len(hard_hits) == 0,
    }


def publishable_source_paths(run_records: list[dict[str, Any]]) -> list[Path]:
    refs: list[str] = []
    for record in run_records:
        refs.extend(
            [
                record["aggregate_ref"],
                record["mode_comparison_ref"],
                record["table_data_ref"],
                record["multiseed_result_ref"],
            ]
        )
    paths: list[Path] = []
    seen: set[Path] = set()
    for ref in refs:
        if not ref:
            continue
        path = (ROOT / validate_ref(ref, "publishable_source_ref")).resolve()
        if path in seen:
            continue
        seen.add(path)
        paths.append(path)
    return paths


def read_scannable_text(path: Path) -> str | None:
    if not path.is_file() or path.stat().st_size > MAX_LEAK_SCAN_BYTES:
        return None
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return None


def marker_hits(path: Path, text: str, markers: list[str]) -> list[str]:
    return [f"{path.relative_to(ROOT)}:{marker}" for marker in markers if marker in text]


def reviewer_packet_index(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "schema_version": "missionforge.value_benchmark_reviewer_packet_index.v1",
        "blind_review_waived": bool(args.waive_blind_review),
        "waiver_rationale": args.blind_review_rationale if args.waive_blind_review else "",
        "reviewer_packets": [],
    }


def blind_review_summary(args: argparse.Namespace) -> str:
    if args.waive_blind_review:
        return "\n".join(
            [
                "# Blind Review Summary",
                "",
                "Status: waived for this report.",
                "",
                f"Rationale: {args.blind_review_rationale}",
                "",
                "Deterministic hidden checks and ProductGate evidence remain the acceptance authority.",
            ]
        ) + "\n"
    return "# Blind Review Summary\n\nStatus: pending reviewer packets.\n"


def reproduction(*, args: argparse.Namespace, run_records: list[dict[str, Any]], report_dir: Path) -> str:
    lines = [
        "# Reproduction",
        "",
        "Run artifacts under `benchmarks/runs/` are intentionally ignored by git.",
        "The sanitized report pack records refs, commands, and aggregate outputs.",
        "",
        "## Runs",
        "",
    ]
    for record in run_records:
        summary = record["execution_summary"]
        provider_env = require_mapping(summary.get("provider_env", {}), f"{record['run_id']}.provider_env")
        max_turns = provider_env.get("MISSIONFORGE_PI_AGENT_MAX_TURNS", "16")
        tool_timeout = provider_env.get("MISSIONFORGE_PI_AGENT_TOOL_TIMEOUT_SECONDS", "60")
        lines.extend(
            [
                f"### {record['run_id']}",
                "",
                "```bash",
                "env PYTHONPATH=src:integrations/skillfoundry/src:integrations/skillfoundry/tests \\",
                "python3 scripts/run_value_benchmark.py \\",
                f"  --run-id {record['run_id']} \\",
                f"  --stage {record.get('stage') or '<stage>'} \\",
                f"  --task-manifest {args.task_manifest} \\",
                f"  --task-ids {','.join(summary.get('task_ids', [])) or '<task-ids>'} \\",
                f"  --pricing-table {args.pricing_table} \\",
                f"  --modes {','.join(summary.get('modes', [])) or '<modes>'} \\",
                f"  --seeds {','.join(str(seed) for seed in summary.get('seeds', [])) or '<seeds>'} \\",
                f"  --provider-mode {summary.get('provider_mode', '<provider-mode>')} \\",
                f"  --provider-config-source {summary.get('provider_config_source', '<provider-config-source>')} \\",
                "  --timeout-seconds 900 \\",
                f"  --max-turns {max_turns} \\",
                f"  --tool-timeout-seconds {tool_timeout}",
                "```",
                "",
            ]
        )
    report_command_lines = [
        "env PYTHONPATH=src:integrations/skillfoundry/src:integrations/skillfoundry/tests \\",
        "python3 scripts/build_value_benchmark_report.py \\",
        f"  --report-dir {report_dir.relative_to(ROOT)} \\",
        f"  --run-ids {args.run_ids} \\",
        f"  --primary-run-id {args.primary_run_id or run_records[-1]['run_id']} \\",
        f"  --task-manifest {args.task_manifest} \\",
        f"  --pricing-table {args.pricing_table} \\",
    ]
    if args.waive_blind_review:
        report_command_lines.extend(
            [
                "  --waive-blind-review \\",
                f"  --blind-review-rationale {shlex.quote(args.blind_review_rationale)} \\",
            ]
        )
    report_command_lines.append("  --force")
    lines.extend(
        [
            "## Report Pack",
            "",
            "```bash",
            *report_command_lines,
            "```",
            "",
            "## Validation",
            "",
            "```bash",
            "env PYTHONPATH=src:integrations/skillfoundry/src:integrations/skillfoundry/tests python3 -m unittest discover -s tests -p 'test*.py'",
            "env PYTHONPATH=src:integrations/skillfoundry/src:integrations/skillfoundry/tests python3 -m unittest discover -s integrations/skillfoundry/tests -p 'test*.py'",
            "git diff --check",
            "```",
        ]
    )
    return "\n".join(lines) + "\n"


def readme(*, report_dir: Path, run_records: list[dict[str, Any]]) -> str:
    return "\n".join(
        [
            "# MissionForge Value Benchmark Report Pack",
            "",
            f"Report directory: `{report_dir.relative_to(ROOT)}`",
            "",
            "Included runs:",
            *[f"- `{record['run_id']}`" for record in run_records],
            "",
            "Start with `final_report.md`, then inspect `run_index.json`, `aggregate.json`, `table_data.json`, `stage4_task_mode_summary.json`, and `stability_summary.json`.",
        ]
    ) + "\n"


def final_report(
    *,
    report_dir: Path,
    run_records: list[dict[str, Any]],
    primary: dict[str, Any],
    primary_task_mode_summary: Mapping[str, Any],
    task_manifest: Mapping[str, Any],
    pricing_table: Mapping[str, Any],
    stability_summary: Mapping[str, Any],
    leakage: Mapping[str, Any],
    failure_taxonomy: Mapping[str, Any],
    blind_review_waived: bool,
) -> str:
    aggregate = primary["aggregate"]
    comparisons = primary["mode_comparisons"]
    primary_summary = require_mapping(primary.get("execution_summary", {}), "primary.execution_summary")
    provider_env = require_mapping(primary_summary.get("provider_env", {}), "primary.provider_env")
    lines = [
        "# MissionForge Value Benchmark Final Report",
        "",
        f"Report pack: `{report_dir.relative_to(ROOT)}`",
        f"Primary run: `{primary['run_id']}`",
        "",
        "## Executive Summary",
        "",
        f"- task_count: {aggregate.get('task_count', 0)}",
        f"- trial_count: {aggregate.get('trial_count', 0)}",
        f"- accepted_count: {aggregate.get('accepted_count', 0)}",
        f"- comparable_trial_count: {aggregate.get('comparable_trial_count', 0)}",
        f"- success result: {stage4_success_result(aggregate)}",
        f"- cost winner: `{comparisons.get('winner_by_cost_per_acceptance', '')}`",
        f"- time winner: `{comparisons.get('winner_by_time_to_acceptance', '')}`",
        f"- leakage audit passed: {bool(leakage.get('passed', False))}",
        "",
        "## Experiment Design",
        "",
        "- Worker: PiWorker only.",
        "- Baseline: direct PiWorker chat using the same live provider/model and pricing table.",
        "- MissionForge arms: runtime-only ablation and full FrontDesk + ProductIntegration + Runtime + ProductGate flow.",
        "- Acceptance: deterministic hidden checks and ProductGate evidence; worker self-report is not acceptance.",
        "- Cost method: provider-reported cost was unavailable in these runs, so cost comparisons use the committed pricing table projection.",
        "",
        "## Compared Modes",
        "",
        *compared_mode_lines(primary_summary),
        "",
        "## Fairness Controls",
        "",
        f"- provider_mode: `{primary_summary.get('provider_mode', '')}`",
        f"- provider_config_source: `{primary_summary.get('provider_config_source', '')}`",
        f"- model: `{provider_env.get('MISSIONFORGE_PI_AGENT_MODEL', '')}`",
        f"- pricing_table_id: `{primary_summary.get('pricing_table_id', pricing_table.get('pricing_table_id', ''))}`",
        f"- pricing_effective_date: `{pricing_table.get('effective_date', '')}`",
        f"- seeds: `{','.join(str(seed) for seed in primary_summary.get('seeds', []))}`",
        f"- run_ids: `{','.join(record['run_id'] for record in run_records)}`",
        f"- max_turns: `{provider_env.get('MISSIONFORGE_PI_AGENT_MAX_TURNS', '')}`",
        f"- tool_timeout_seconds: `{provider_env.get('MISSIONFORGE_PI_AGENT_TOOL_TIMEOUT_SECONDS', '')}`",
        "- run_timeout_seconds: `900`",
        "- hidden acceptance files were kept outside worker-visible prompts and workspaces; results are consumed only after worker execution.",
        "- all modes used the same task manifest, seed list for the same stage, pricing table, provider model, and deterministic hidden acceptance authority.",
        "",
        "## Task Inventory",
        "",
        "| task_id | family | difficulty | budget | hypothesis |",
        "| --- | --- | --- | --- | --- |",
        *task_inventory_lines(task_manifest),
        "",
        "## Cost Method",
        "",
        f"- pricing_table_id: `{pricing_table.get('pricing_table_id', '')}`",
        f"- currency: `{pricing_table.get('currency', '')}`",
        f"- effective_date: `{pricing_table.get('effective_date', '')}`",
        f"- model_prices: `{','.join(sorted(require_mapping(pricing_table.get('model_prices', {}), 'pricing.model_prices').keys()))}`",
        "- provider_reported_cost_usd was zero or unavailable in the live summaries, so the report uses pricing-table projection from input, output, and cache token counts.",
        "- cost_per_accepted_deliverable_usd includes available attempt cost divided by accepted deliverables; failed attempts with available projected cost are not hidden.",
        "",
        "## Included Runs",
        "",
        "| run_id | stage | tasks | trials | accepted | comparable |",
        "| --- | --- | ---: | ---: | ---: | ---: |",
        *run_index_lines(run_records),
        "",
        "## Stage 4 Multi-Task A/B Result",
        "",
        "## Mode Summary",
        "",
        "| mode | trials | comparable | accepted | success_rate | cost_source | cost_per_acceptance | avg_time_ms | p95_time_ms | tokens | repairs |",
        "| --- | ---: | ---: | ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for mode, values in sorted(aggregate.get("mode_summaries", {}).items()):
        lines.append(
            "| {mode} | {trial_count} | {comparable_trial_count} | {accepted_count} | "
            "{success_rate:.6f} | {cost_source} | {cost_per:.6f} | {avg_time:.2f} | "
            "{p95_time:.2f} | {tokens} | {repairs} |".format(
                mode=mode,
                trial_count=int(values.get("trial_count", 0)),
                comparable_trial_count=int(values.get("comparable_trial_count", 0)),
                accepted_count=int(values.get("accepted_count", 0)),
                success_rate=float(values.get("success_rate_within_budget", 0.0)),
                cost_source=str(values.get("cost_source", "unavailable")),
                cost_per=float(values.get("cost_per_accepted_deliverable_usd", 0.0)),
                avg_time=float(values.get("avg_time_to_accepted_deliverable_ms", 0.0)),
                p95_time=float(values.get("p95_time_to_accepted_deliverable_ms", 0.0)),
                tokens=int(values.get("total_tokens", 0)),
                repairs=int(values.get("repair_count", 0)),
            )
        )
    lines.extend(
        [
            "",
            "## Stage 4 Task/Mode Detail",
            "",
            *stage4_task_mode_report_lines(primary_task_mode_summary),
            "",
            "## Stage 5 Stability Result",
            "",
            *stability_report_lines(stability_summary),
            "",
            "## Claims We Can Make",
            "",
            *claims_we_can_make(
                primary=primary,
                stability_summary=stability_summary,
                leakage=leakage,
                blind_review_waived=blind_review_waived,
            ),
            "",
            "## Claims We Cannot Make Yet",
            "",
            *claims_we_cannot_make(primary=primary, leakage=leakage, blind_review_waived=blind_review_waived),
            "",
            "## Failure Taxonomy",
            "",
        ]
    )
    counts = failure_taxonomy.get("failure_taxonomy_counts", {})
    if counts:
        lines.extend([f"- {name}: {count}" for name, count in sorted(counts.items())])
    else:
        lines.append("- none: 0")
    lines.extend(
        [
            "",
            "## Leakage Audit",
            "",
            f"- scanned_file_count: {leakage.get('scanned_file_count', 0)}",
            f"- passed: {leakage.get('passed', False)}",
            f"- hard_leak_hits: {leakage.get('hard_leak_hits', leakage.get('leak_hits', []))}",
            f"- internal_schema_marker_hit_count: {len(leakage.get('schema_marker_hits', []))}",
            "",
            "## Evidence Files",
            "",
            "- `run_index.json`",
            "- `aggregate.json`",
            "- `mode_comparisons.json`",
            "- `table_data.json`",
            "- `stage4_task_mode_summary.json`",
            "- `stability_summary.json`",
            "- `failure_taxonomy.json`",
            "- `leakage_audit.json`",
            "- `blind_review_summary.md`",
            "- `reproduction.md`",
            "",
            "## Reproduction",
            "",
            "Exact run and report-pack commands are recorded in `reproduction.md`.",
        ]
    )
    return "\n".join(lines) + "\n"


def compared_mode_lines(primary_summary: Mapping[str, Any]) -> list[str]:
    descriptions = {
        "direct_piworker_chat": "direct PiWorker chat baseline with the same task text and acceptance checks applied after execution",
        "missionforge_runtime_only": "MissionForge runtime ablation without FrontDesk product discovery",
        "missionforge_full_product_flow": "FrontDesk plus ProductIntegration compile plus MissionForge runtime plus ProductGate closure",
    }
    return [f"- `{mode}`: {descriptions.get(str(mode), 'benchmark mode')}" for mode in primary_summary.get("modes", [])]


def task_inventory_lines(task_manifest: Mapping[str, Any]) -> list[str]:
    lines: list[str] = []
    for task in task_manifest.get("tasks", []):
        task_data = require_mapping(task, "task_manifest.tasks[]")
        task_ref = validate_ref(task_data.get("task_ref"), "task_ref")
        task_detail = read_json_ref(task_ref)
        budget = require_mapping(task_detail.get("budget", {}), f"{task_ref}.budget")
        budget_text = (
            f"{budget.get('max_wall_minutes', 0)}m/"
            f"{budget.get('max_total_tokens', 0)}tok/"
            f"${float(budget.get('max_cost_usd', 0.0)):.2f}/"
            f"{budget.get('max_user_turns', 0)}turns"
        )
        lines.append(
            "| {task_id} | {family} | {difficulty} | {budget} | {hypothesis} |".format(
                task_id=task_detail.get("task_id", task_data.get("task_id", "")),
                family=task_detail.get("task_family", ""),
                difficulty=task_detail.get("difficulty", ""),
                budget=budget_text,
                hypothesis=str(task_data.get("hypothesis", "")).replace("|", "/"),
            )
        )
    return lines


def run_index_lines(run_records: list[dict[str, Any]]) -> list[str]:
    lines: list[str] = []
    for record in run_records:
        aggregate = record["aggregate"]
        lines.append(
            "| {run_id} | {stage} | {task_count} | {trial_count} | {accepted_count} | {comparable_count} |".format(
                run_id=record["run_id"],
                stage=record.get("stage", ""),
                task_count=int(aggregate.get("task_count", 0)),
                trial_count=int(aggregate.get("trial_count", 0)),
                accepted_count=int(aggregate.get("accepted_count", 0)),
                comparable_count=int(aggregate.get("comparable_trial_count", 0)),
            )
        )
    return lines


def stage4_task_mode_report_lines(summary: Mapping[str, Any]) -> list[str]:
    if summary.get("status") != "available":
        return ["- Stage 4 task/mode summary is not available in this report pack."]
    lines = [
        "| task_id | mode | trials | accepted | success_rate | hidden_pass | hidden_fail | gate_pass | gate_fail | gate_unsupported | failures |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for row in summary.get("task_mode_rows", []):
        failures = ", ".join(f"{name}:{count}" for name, count in row.get("failure_taxonomy_counts", {}).items()) or "none"
        lines.append(
            "| {task_id} | {mode} | {trial_count} | {accepted_count} | {success_rate:.6f} | "
            "{hidden_pass} | {hidden_fail} | {gate_pass} | {gate_fail} | {gate_unsupported} | {failures} |".format(
                task_id=row.get("task_id", ""),
                mode=row.get("mode", ""),
                trial_count=int(row.get("trial_count", 0)),
                accepted_count=int(row.get("accepted_count", 0)),
                success_rate=float(row.get("success_rate", 0.0)),
                hidden_pass=int(row.get("hidden_acceptance_passed_count", 0)),
                hidden_fail=int(row.get("hidden_acceptance_failed_count", 0)),
                gate_pass=int(row.get("product_gate_passed_count", 0)),
                gate_fail=int(row.get("product_gate_failed_count", 0)),
                gate_unsupported=int(row.get("product_gate_unsupported_count", 0)),
                failures=failures,
            )
        )
    lines.extend(
        [
            "",
            "The same counts are available in `stage4_task_mode_summary.json` with ProductGate status breakdowns.",
        ]
    )
    return lines


def stability_report_lines(stability_summary: Mapping[str, Any]) -> list[str]:
    if stability_summary.get("status") != "available":
        return ["- Stage 5 stability summary is not available in this report pack."]
    lines = [
        f"- stage5_run_id: `{stability_summary.get('stage5_run_id', '')}`",
        f"- interpretation: {stability_summary.get('interpretation', '')}",
        "",
        "| mode | trials | comparable | accepted | success_rate | cost_source | cost_per_acceptance | p50_cost | p95_cost | avg_time_ms | p50_time_ms | p95_time_ms |",
        "| --- | ---: | ---: | ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in stability_summary.get("mode_rows", []):
        lines.append(
            "| {mode} | {trial_count} | {comparable_trial_count} | {accepted_count} | {success_rate:.6f} | "
            "{cost_source} | {cost_per:.6f} | {p50_cost:.6f} | {p95_cost:.6f} | {avg_time:.2f} | {p50_time:.2f} | {p95_time:.2f} |".format(
                mode=row.get("mode", ""),
                trial_count=int(row.get("trial_count", 0)),
                comparable_trial_count=int(row.get("comparable_trial_count", 0)),
                accepted_count=int(row.get("accepted_count", 0)),
                success_rate=float(row.get("success_rate", 0.0)),
                cost_source=str(row.get("cost_source", "unavailable")),
                cost_per=float(row.get("cost_per_accepted_deliverable_usd", 0.0)),
                p50_cost=float(row.get("p50_cost_per_acceptance_usd", 0.0)),
                p95_cost=float(row.get("p95_cost_per_acceptance_usd", 0.0)),
                avg_time=float(row.get("avg_time_to_accepted_deliverable_ms", 0.0)),
                p50_time=float(row.get("p50_time_to_accepted_deliverable_ms", 0.0)),
                p95_time=float(row.get("p95_time_to_accepted_deliverable_ms", 0.0)),
            )
        )
    lines.extend(
        [
            "",
            "Task and mode rows are available in `stability_summary.json`.",
        ]
    )
    return lines


def claims_we_can_make(
    *,
    primary: Mapping[str, Any],
    stability_summary: Mapping[str, Any],
    leakage: Mapping[str, Any],
    blind_review_waived: bool,
) -> list[str]:
    aggregate = primary["aggregate"]
    claims = [
        "- The benchmark produced refs-first comparable summaries for the primary run.",
        "- Direct PiWorker and MissionForge modes were evaluated by the same aggregate/report contracts.",
    ]
    comparisons = primary["mode_comparisons"]
    claims.append(
        f"- In Stage 4, {stage4_success_result(aggregate)}; cost winner was `{comparisons.get('winner_by_cost_per_acceptance', '')}` and time winner was `{comparisons.get('winner_by_time_to_acceptance', '')}`."
    )
    if stability_summary.get("status") == "available":
        claims.append(f"- Stage 5 stability result: {stability_summary.get('interpretation', '')}")
        direct_row = _stability_mode_row(stability_summary, "direct_piworker_chat")
        full_row = _stability_mode_row(stability_summary, "missionforge_full_product_flow")
        if direct_row and full_row:
            claims.append(
                "- In Stage 5, direct PiWorker chat had higher accepted-deliverable rate, lower projected cost per accepted deliverable, and lower p95 time than MissionForge full product flow."
            )
    if bool(leakage.get("passed", False)):
        claims.append("- The publishable report scan found no configured raw prompt/provider/secret leakage markers.")
    if all_costs_available(aggregate):
        claims.append("- Cost comparison uses available pricing-table or provider-reported cost sources.")
    if blind_review_waived:
        claims.append("- Blind review was explicitly waived; deterministic checks and ProductGate evidence are the authority.")
    return claims


def claims_we_cannot_make(*, primary: Mapping[str, Any], leakage: Mapping[str, Any], blind_review_waived: bool) -> list[str]:
    aggregate = primary["aggregate"]
    claims: list[str] = []
    if aggregate.get("task_count", 0) < 5:
        claims.append("- The primary run has fewer than five tasks, so broad task-family conclusions remain weak.")
    if not all_costs_available(aggregate):
        claims.append("- Some accepted comparable cost values are unavailable; cost winners must be treated as incomplete.")
    if not bool(leakage.get("passed", False)):
        claims.append("- Leakage audit did not pass, so public value claims are blocked.")
    if blind_review_waived:
        claims.append("- Human or independent-agent quality preference beyond deterministic checks was not measured.")
    comparisons = primary["mode_comparisons"]
    if (
        comparisons.get("winner_by_cost_per_acceptance") == "direct_piworker_chat"
        and comparisons.get("winner_by_time_to_acceptance") == "direct_piworker_chat"
    ):
        claims.append(
            "- This report does not support a claim that MissionForge full product flow is faster or cheaper than direct PiWorker chat on the measured tasks."
        )
    if not claims:
        claims.append("- No additional limitations were detected by the report builder; inspect run artifacts before external claims.")
    return claims


def _stability_mode_row(stability_summary: Mapping[str, Any], mode: str) -> Mapping[str, Any]:
    for row in stability_summary.get("mode_rows", []):
        if row.get("mode") == mode:
            return require_mapping(row, f"stability_summary.{mode}")
    return {}


def all_costs_available(aggregate: Mapping[str, Any]) -> bool:
    for values in aggregate.get("mode_summaries", {}).values():
        accepted = int(values.get("comparable_accepted_count", 0))
        if accepted > 0 and int(values.get("estimated_cost_available_count", 0)) <= 0:
            return False
    return True


def stage4_success_result(aggregate: Mapping[str, Any]) -> str:
    mode_summaries = require_mapping(aggregate.get("mode_summaries", {}), "aggregate.mode_summaries")
    scores = {
        mode: float(require_mapping(values, f"aggregate.mode_summaries.{mode}").get("success_rate_within_budget", 0.0))
        for mode, values in mode_summaries.items()
    }
    if not scores:
        return "success winner unavailable"
    best = max(scores.values())
    winners = sorted(mode for mode, score in scores.items() if score == best)
    if len(winners) == 1:
        return f"success winner was `{winners[0]}` at {best:.6f}"
    return f"success tied between {', '.join(f'`{winner}`' for winner in winners)} at {best:.6f}"


def validate_publishable_report(report_dir: Path) -> None:
    for path in sorted(report_dir.rglob("*")):
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        for marker in LEAK_MARKERS:
            if marker in text and path.name != "leakage_audit.json":
                raise ContractValidationError(f"publishable report contains leak marker {marker}: {path}")
        if path.suffix == ".json":
            assert_refs_only_payload(require_mapping(json.loads(text), str(path.relative_to(ROOT))), str(path.relative_to(ROOT)))


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
