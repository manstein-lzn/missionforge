#!/usr/bin/env python3
"""Build a sanitized MissionForge value benchmark report pack."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any, Mapping

from missionforge.contracts import ContractValidationError, assert_refs_only_payload, require_mapping, validate_ref


ROOT = Path.cwd().resolve()
LEAK_MARKERS = [
    "raw_prompt",
    "raw_transcript",
    "raw_provider_payload",
    "provider_payload",
    "OPENAI_API_KEY",
    "MISSIONFORGE_PI_AGENT_API_KEY",
]


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
    leakage = build_leakage_audit(run_records)
    failure_taxonomy = merge_failure_taxonomy(run_records)
    write_json(report_dir / "pricing_table.json", pricing_table)
    write_json(report_dir / "fixture_manifest.json", task_manifest)
    write_json(report_dir / "aggregate.json", primary["aggregate"])
    write_json(report_dir / "mode_comparisons.json", primary["mode_comparisons"])
    write_json(report_dir / "table_data.json", primary["table_data"])
    write_json(report_dir / "run_index.json", build_run_index(run_records))
    write_json(report_dir / "failure_taxonomy.json", failure_taxonomy)
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


def build_leakage_audit(run_records: list[dict[str, Any]]) -> dict[str, Any]:
    hits: list[str] = []
    scanned_files = 0
    for record in run_records:
        run_root = ROOT / record["run_ref"]
        for path in sorted(run_root.rglob("*")):
            if not path.is_file() or path.stat().st_size > 2_000_000:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            scanned_files += 1
            for marker in LEAK_MARKERS:
                if marker in text:
                    hits.append(f"{path.relative_to(ROOT)}:{marker}")
    return {
        "schema_version": "missionforge.value_benchmark_leakage_audit.v1",
        "scanned_file_count": scanned_files,
        "leak_markers": LEAK_MARKERS,
        "leak_hits": sorted(set(hits)),
        "passed": len(hits) == 0,
    }


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
                f"  --pricing-table {args.pricing_table} \\",
                f"  --modes {','.join(summary.get('modes', [])) or '<modes>'} \\",
                f"  --seeds {','.join(str(seed) for seed in summary.get('seeds', [])) or '<seeds>'} \\",
                f"  --provider-mode {summary.get('provider_mode', '<provider-mode>')}",
                "```",
                "",
            ]
        )
    lines.extend(
        [
            "## Report Pack",
            "",
            "```bash",
            "env PYTHONPATH=src:integrations/skillfoundry/src:integrations/skillfoundry/tests \\",
            "python3 scripts/build_value_benchmark_report.py \\",
            f"  --report-dir {report_dir.relative_to(ROOT)} \\",
            f"  --run-ids {args.run_ids} \\",
            f"  --task-manifest {args.task_manifest} \\",
            f"  --pricing-table {args.pricing_table} \\",
            "  --waive-blind-review \\",
            "  --force",
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
            "Start with `final_report.md`, then inspect `run_index.json`, `aggregate.json`, and `table_data.json`.",
        ]
    ) + "\n"


def final_report(
    *,
    report_dir: Path,
    run_records: list[dict[str, Any]],
    primary: dict[str, Any],
    leakage: Mapping[str, Any],
    failure_taxonomy: Mapping[str, Any],
    blind_review_waived: bool,
) -> str:
    aggregate = primary["aggregate"]
    comparisons = primary["mode_comparisons"]
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
        f"- success winner: `{comparisons.get('winner_by_success_rate', '')}`",
        f"- cost winner: `{comparisons.get('winner_by_cost_per_acceptance', '')}`",
        f"- time winner: `{comparisons.get('winner_by_time_to_acceptance', '')}`",
        f"- leakage audit passed: {bool(leakage.get('passed', False))}",
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
            "## Claims We Can Make",
            "",
            *claims_we_can_make(primary=primary, leakage=leakage, blind_review_waived=blind_review_waived),
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
            f"- leak_hits: {leakage.get('leak_hits', [])}",
            "",
            "## Evidence Files",
            "",
            "- `run_index.json`",
            "- `aggregate.json`",
            "- `mode_comparisons.json`",
            "- `table_data.json`",
            "- `failure_taxonomy.json`",
            "- `leakage_audit.json`",
            "- `blind_review_summary.md`",
            "- `reproduction.md`",
        ]
    )
    return "\n".join(lines) + "\n"


def claims_we_can_make(*, primary: Mapping[str, Any], leakage: Mapping[str, Any], blind_review_waived: bool) -> list[str]:
    aggregate = primary["aggregate"]
    claims = [
        "- The benchmark produced refs-first comparable summaries for the primary run.",
        "- Direct PiWorker and MissionForge modes were evaluated by the same aggregate/report contracts.",
    ]
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
    if not claims:
        claims.append("- No additional limitations were detected by the report builder; inspect run artifacts before external claims.")
    return claims


def all_costs_available(aggregate: Mapping[str, Any]) -> bool:
    for values in aggregate.get("mode_summaries", {}).values():
        accepted = int(values.get("comparable_accepted_count", 0))
        if accepted > 0 and int(values.get("estimated_cost_available_count", 0)) <= 0:
            return False
    return True


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
