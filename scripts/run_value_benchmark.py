#!/usr/bin/env python3
"""Run MissionForge value benchmark matrices from committed fixtures."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Mapping

from missionforge.adapters.pi_agent_provider_config import (
    load_codex_current_provider,
    redact_provider_env,
    resolve_pi_agent_provider_environment,
)
from missionforge.adapters.pi_agent_runtime import PiAgentRuntimeAdapter, PiAgentRuntimeConfig
from missionforge.benchmark import (
    BenchmarkMode,
    BenchmarkPricingTable,
    BenchmarkReadinessCheck,
    BenchmarkReadinessReport,
    BenchmarkReadinessStatus,
    BenchmarkTask,
    DirectPiWorkerBenchmarkRunner,
    DirectPiWorkerConfig,
    FullProductFlowConfig,
    MissionForgeFullProductFlowBenchmarkRunner,
    MissionForgeRuntimeOnlyBenchmarkRunner,
    MultiSeedBenchmarkRunner,
    ProductGateOutcome,
    RuntimeOnlyConfig,
    build_readiness_report,
)
from missionforge.contracts import ContractValidationError, require_mapping, require_non_empty_str, validate_ref
from missionforge.json_store import JsonWorkspaceStore
from missionforge.runner import MissionResult
from missionforge_skillfoundry import (
    SkillFoundryFrontDeskIntegration,
    SkillFoundryMissionCompiler,
    SkillFoundryRequest,
    evaluate_product_grade,
    validate_skill_bundle,
)
from missionforge_skillfoundry.validators import BUNDLE_VALIDATION_REPORT_REF


ROOT = Path.cwd().resolve()
DEFAULT_MAX_TURNS = 16
DEFAULT_TOOL_TIMEOUT_SECONDS = 60
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
RUN_PUBLISHABLE_CANDIDATE_NAMES = {
    "aggregate.json",
    "manifest.json",
    "mode_comparisons.json",
    "multiseed_result.json",
    "report.md",
    "table_data.json",
}
MAX_LEAK_SCAN_BYTES = 2_000_000


class RuntimeOnlyModeRunner:
    def __init__(self, *, runner: MissionForgeRuntimeOnlyBenchmarkRunner, mission_refs: Mapping[str, str]) -> None:
        self.runner = runner
        self.mission_refs = dict(mission_refs)

    def run_trial(self, **kwargs: Any) -> Any:
        task = kwargs.get("task")
        if not isinstance(task, BenchmarkTask):
            raise ContractValidationError("runtime-only wrapper requires BenchmarkTask")
        mission_ref = self.mission_refs.get(task.task_id)
        if not mission_ref:
            raise ContractValidationError(f"runtime-only fixture missing for task: {task.task_id}")
        return self.runner.run_trial(mission_ir_ref=mission_ref, **kwargs)


class FullProductFlowModeRunner:
    def __init__(self, *, config: FullProductFlowConfig, pi_config: PiAgentRuntimeConfig) -> None:
        self.config = config
        self.pi_config = pi_config

    def run_trial(self, **kwargs: Any) -> Any:
        task = kwargs.get("task")
        if not isinstance(task, BenchmarkTask):
            raise ContractValidationError("full-flow wrapper requires BenchmarkTask")
        runner = MissionForgeFullProductFlowBenchmarkRunner(
            self.config,
            product_integration=SkillFoundryFrontDeskIntegration(bundle_id=task.task_id),
            product_gate=SkillFoundryProductGate(bundle_id=task.task_id),
            frontdesk_worker=PiAgentRuntimeAdapter(self.pi_config),
        )
        return runner.run_trial(**kwargs)


class LoggingModeRunner:
    def __init__(self, *, mode: BenchmarkMode, inner: Any) -> None:
        self.mode = mode
        self.inner = inner

    def run_trial(self, **kwargs: Any) -> Any:
        task = kwargs.get("task")
        seed = kwargs.get("seed")
        task_id = task.task_id if isinstance(task, BenchmarkTask) else ""
        print(json.dumps({"event": "trial_start", "mode": self.mode.value, "task_id": task_id, "seed": seed}), flush=True)
        record = self.inner.run_trial(**kwargs)
        print(
            json.dumps(
                {
                    "event": "trial_done",
                    "mode": self.mode.value,
                    "task_id": task_id,
                    "seed": seed,
                    "accepted": record.summary.accepted,
                    "status": record.summary.status.value,
                    "cost_source": record.summary.cost_source,
                    "estimated_cost_usd": record.summary.estimated_cost_usd,
                    "failure_taxonomy": record.summary.failure_taxonomy,
                },
                sort_keys=True,
            ),
            flush=True,
        )
        return record


class SkillFoundryProductGate:
    def __init__(self, *, bundle_id: str) -> None:
        self.bundle_id = bundle_id

    def run_product_gate(
        self,
        *,
        workspace: str | Path,
        task: BenchmarkTask,
        compile_result: Any,
        mission_result: MissionResult,
    ) -> ProductGateOutcome:
        validate_skill_bundle(
            workspace=workspace,
            bundle_id=self.bundle_id,
            matrix_ref=compile_result.product_gate_spec_ref,
            report_ref=BUNDLE_VALIDATION_REPORT_REF,
        )
        report = evaluate_product_grade(
            workspace=workspace,
            bundle_id=self.bundle_id,
            mission_result=mission_result,
            bundle_validation_report_ref=BUNDLE_VALIDATION_REPORT_REF,
        )
        return ProductGateOutcome(
            product_id="skillfoundry",
            status="product_grade" if report.product_grade else "failed",
            result_ref="qa/product_grade_report.json",
            evidence_refs=[BUNDLE_VALIDATION_REPORT_REF, "qa/product_grade_report.json"],
            artifact_refs=list(report.package_refs),
            diagnostic_refs=[report.repair_packet_ref] if report.repair_packet_ref else [],
            product_acceptance_coverage_passed=report.outcome_category != "coverage_miss",
            blocking_finding_count=sum(1 for finding in report.findings if finding.severity == "blocking"),
            outcome_category=report.outcome_category,
        )



def validate_benchmark_run_id(run_id: str) -> str:
    safe = validate_ref(run_id, "benchmark_run_id")
    if "/" in safe or safe in {".", ".."}:
        raise ContractValidationError("benchmark_run_id must be a safe id, not a path")
    return safe

def main() -> None:
    args = parse_args()
    validate_benchmark_run_id(args.run_id)
    store = JsonWorkspaceStore(ROOT)
    manifest = load_task_manifest(args.task_manifest)
    task_items = select_task_items(manifest, parse_csv(args.task_ids))
    modes = parse_modes(args.modes)
    seeds = parse_seeds(args.seeds)
    pricing_table = load_pricing_table(args.pricing_table)
    model, model_error = resolve_model_for_readiness(
        provider_mode=args.provider_mode,
        provider_config_source=args.provider_config_source,
        model=args.model,
    )
    tasks = [BenchmarkTask.from_dict(store.read_json(item["task_ref"])) for item in task_items]
    readiness = build_value_benchmark_readiness(
        args=args,
        task_items=task_items,
        tasks=tasks,
        modes=modes,
        pricing_table=pricing_table,
        model=model,
        model_error=model_error,
    )
    readiness_ref = write_readiness_report(args.run_id, readiness)
    if readiness.status != BenchmarkReadinessStatus.READY:
        summary_ref = write_execution_summary(
            args=args,
            manifest=manifest,
            tasks=tasks,
            modes=modes,
            seeds=seeds,
            pricing_table=pricing_table,
            provider_env={},
            result=None,
            runtime_mission_refs={},
            leak_hits=[],
            readiness_report_ref=readiness_ref,
            readiness_status=readiness.status.value,
        )
        print(
            json.dumps(
                {
                    "event": "benchmark_readiness_not_ready",
                    "run_id": args.run_id,
                    "readiness_status": readiness.status.value,
                    "readiness_report_ref": readiness_ref,
                    "execution_summary_ref": summary_ref,
                },
                sort_keys=True,
            ),
            flush=True,
        )
        return
    require_pricing_model(pricing_table=pricing_table, model=model, provider_mode=args.provider_mode)
    ensure_provider_available(
        provider_mode=args.provider_mode,
        provider_config_source=args.provider_config_source,
        model=model,
        metadata={"stage": args.stage, "run_id": args.run_id},
    )
    assert_hidden_checks_not_worker_visible(tasks)
    if args.dry_run:
        write_execution_summary(
            args=args,
            manifest=manifest,
            tasks=tasks,
            modes=modes,
            seeds=seeds,
            pricing_table=pricing_table,
            provider_env={},
            result=None,
            runtime_mission_refs={},
            leak_hits=[],
            readiness_report_ref=readiness_ref,
            readiness_status=readiness.status.value,
        )
        print(json.dumps({"event": "dry_run_ok", "run_id": args.run_id}), flush=True)
        return

    os.environ.setdefault("MISSIONFORGE_PI_AGENT_MAX_TURNS", str(args.max_turns))
    os.environ.setdefault("MISSIONFORGE_PI_AGENT_TOOL_TIMEOUT_SECONDS", str(args.tool_timeout_seconds))
    runtime_mission_refs = prepare_runtime_only_fixtures(
        run_id=args.run_id,
        task_items=task_items,
        modes=modes,
    )
    provider_metadata = {
        "stage": args.stage,
        "run_id": args.run_id,
        "pricing_table_id": pricing_table.pricing_table_id,
    }
    pi_config = PiAgentRuntimeConfig(
        timeout_seconds=args.timeout_seconds,
        provider_mode=args.provider_mode,
        provider_config_source=args.provider_config_source,
        model=model,
        metadata=provider_metadata,
    )
    direct_config = DirectPiWorkerConfig(
        timeout_seconds=args.timeout_seconds,
        provider_mode=args.provider_mode,
        provider_config_source=args.provider_config_source,
        model=model,
        pricing_table=pricing_table,
        metadata=provider_metadata,
    )
    mode_runners: dict[BenchmarkMode, Any] = {
        BenchmarkMode.DIRECT_PIWORKER_CHAT: LoggingModeRunner(
            mode=BenchmarkMode.DIRECT_PIWORKER_CHAT,
            inner=DirectPiWorkerBenchmarkRunner(direct_config),
        ),
        BenchmarkMode.MISSIONFORGE_RUNTIME_ONLY: LoggingModeRunner(
            mode=BenchmarkMode.MISSIONFORGE_RUNTIME_ONLY,
            inner=RuntimeOnlyModeRunner(
                runner=MissionForgeRuntimeOnlyBenchmarkRunner(
                    RuntimeOnlyConfig(
                        max_attempts=args.max_attempts,
                        pi_agent_config=pi_config,
                        product_gate_status="not_applicable",
                        pricing_table=pricing_table,
                        metadata=provider_metadata,
                    )
                ),
                mission_refs=runtime_mission_refs,
            ),
        ),
        BenchmarkMode.MISSIONFORGE_FULL_PRODUCT_FLOW: LoggingModeRunner(
            mode=BenchmarkMode.MISSIONFORGE_FULL_PRODUCT_FLOW,
            inner=FullProductFlowModeRunner(
                config=FullProductFlowConfig(
                    max_attempts=args.max_attempts,
                    pi_agent_config=pi_config,
                    pricing_table=pricing_table,
                    metadata=provider_metadata,
                ),
                pi_config=pi_config,
            ),
        ),
    }
    selected_runners = {mode: mode_runners[mode] for mode in modes}
    print(
        json.dumps(
            {
                "event": "benchmark_start",
                "run_id": args.run_id,
                "stage": args.stage,
                "task_ids": [task.task_id for task in tasks],
                "modes": [mode.value for mode in modes],
                "seeds": seeds,
                "model": model,
                "pricing_table_id": pricing_table.pricing_table_id,
            },
            sort_keys=True,
        ),
        flush=True,
    )
    result = MultiSeedBenchmarkRunner(workspace=ROOT, mode_runners=selected_runners).run(
        benchmark_run_id=args.run_id,
        tasks=tasks,
        modes=modes,
        seeds=seeds,
    )
    leak_hits = scan_run_for_leaks(run_id=args.run_id)
    provider_env = resolve_pi_agent_provider_environment(
        provider_mode=args.provider_mode,
        provider_config_source=args.provider_config_source,
        model=model,
        metadata=provider_metadata,
    ).redacted_env
    summary_ref = write_execution_summary(
        args=args,
        manifest=manifest,
        tasks=tasks,
        modes=modes,
        readiness_report_ref=readiness_ref,
        readiness_status=readiness.status.value,
        seeds=seeds,
        pricing_table=pricing_table,
        provider_env=provider_env,
        result=result,
        runtime_mission_refs=runtime_mission_refs,
        leak_hits=leak_hits,
    )
    print(json.dumps({"event": "benchmark_done", "run_id": args.run_id, "execution_summary_ref": summary_ref}), flush=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--stage", default="stage")
    parser.add_argument("--task-manifest", required=True)
    parser.add_argument("--task-ids", default="")
    parser.add_argument("--pricing-table", required=True)
    parser.add_argument("--modes", required=True)
    parser.add_argument("--seeds", required=True)
    parser.add_argument("--provider-mode", choices=["faux", "live"], default="live")
    parser.add_argument("--provider-config-source", choices=["env", "codex_current", "explicit"], default="codex_current")
    parser.add_argument("--model", default="")
    parser.add_argument("--timeout-seconds", type=int, default=900)
    parser.add_argument("--max-attempts", type=int, default=1)
    parser.add_argument("--max-turns", type=int, default=DEFAULT_MAX_TURNS)
    parser.add_argument("--tool-timeout-seconds", type=int, default=DEFAULT_TOOL_TIMEOUT_SECONDS)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def load_task_manifest(ref: str) -> dict[str, Any]:
    path = ROOT / validate_ref(ref, "value_benchmark.task_manifest")
    data = require_mapping(json.loads(path.read_text(encoding="utf-8")), "value_benchmark_manifest")
    tasks = data.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        raise ContractValidationError("value_benchmark_manifest.tasks must not be empty")
    return dict(data)


def select_task_items(manifest: Mapping[str, Any], task_ids: list[str]) -> list[dict[str, str]]:
    selected: list[dict[str, str]] = []
    wanted = set(task_ids)
    for item in manifest.get("tasks", []):
        data = require_mapping(item, "value_benchmark_manifest.tasks[]")
        task_id = require_non_empty_str(data.get("task_id"), "value_benchmark_manifest.task_id")
        if wanted and task_id not in wanted:
            continue
        selected.append(
            {
                "task_id": task_id,
                "task_ref": validate_ref(data.get("task_ref"), "value_benchmark_manifest.task_ref"),
                "runtime_request_ref": validate_ref(
                    data.get("runtime_request_ref"),
                    "value_benchmark_manifest.runtime_request_ref",
                )
                if data.get("runtime_request_ref")
                else "",
            }
        )
    if not selected:
        raise ContractValidationError("no benchmark tasks selected")
    return selected


def parse_modes(text: str) -> list[BenchmarkMode]:
    modes = [BenchmarkMode(item) for item in parse_csv(text)]
    if not modes:
        raise ContractValidationError("at least one mode is required")
    return modes


def parse_seeds(text: str) -> list[int]:
    seeds = [int(item) for item in parse_csv(text)]
    if not seeds:
        raise ContractValidationError("at least one seed is required")
    if any(seed < 0 for seed in seeds):
        raise ContractValidationError("seeds must be >= 0")
    return seeds


def parse_csv(text: str) -> list[str]:
    return [item.strip() for item in text.split(",") if item.strip()]


def load_pricing_table(ref: str) -> BenchmarkPricingTable:
    payload = json.loads((ROOT / validate_ref(ref, "value_benchmark.pricing_table")).read_text(encoding="utf-8"))
    return BenchmarkPricingTable.from_dict(require_mapping(payload, "benchmark_pricing_table"))
def resolve_model_for_readiness(*, provider_mode: str, provider_config_source: str, model: str) -> tuple[str, str]:
    try:
        return resolve_model(provider_mode=provider_mode, provider_config_source=provider_config_source, model=model), ""
    except Exception as exc:
        return "", f"model resolution unavailable: {type(exc).__name__}"


def build_value_benchmark_readiness(
    *,
    args: argparse.Namespace,
    task_items: list[dict[str, str]],
    tasks: list[BenchmarkTask],
    modes: list[BenchmarkMode],
    pricing_table: BenchmarkPricingTable,
    model: str,
    model_error: str = "",
) -> BenchmarkReadinessReport:
    checks = [
        _readiness_provider_check(args=args, model=model, model_error=model_error),
        _readiness_pricing_check(pricing_table=pricing_table, model=model, pricing_table_ref=args.pricing_table),
        _readiness_hidden_acceptance_check(tasks),
    ]
    if BenchmarkMode.MISSIONFORGE_RUNTIME_ONLY in modes:
        checks.append(_readiness_runtime_only_fixture_check(task_items))
    if BenchmarkMode.MISSIONFORGE_FULL_PRODUCT_FLOW in modes:
        checks.append(_readiness_full_product_flow_check())
    return build_readiness_report(benchmark_run_id=args.run_id, modes=modes, checks=checks)


def write_readiness_report(run_id: str, report: BenchmarkReadinessReport) -> str:
    ref = f"benchmarks/runs/{validate_benchmark_run_id(run_id)}/readiness/readiness_report.json"
    return JsonWorkspaceStore(ROOT).write_json(ref, report.to_dict())


def _readiness_provider_check(*, args: argparse.Namespace, model: str, model_error: str) -> BenchmarkReadinessCheck:
    if model_error:
        return BenchmarkReadinessCheck(
            check_id="provider_config",
            status=BenchmarkReadinessStatus.UNAVAILABLE,
            reason=model_error,
        )
    if args.provider_mode == "faux":
        return BenchmarkReadinessCheck(
            check_id="provider_config",
            status=BenchmarkReadinessStatus.READY,
            reason="faux provider mode is configured",
        )
    try:
        ensure_provider_available(
            provider_mode=args.provider_mode,
            provider_config_source=args.provider_config_source,
            model=model,
            metadata={"stage": args.stage, "run_id": args.run_id},
        )
    except Exception as exc:
        return BenchmarkReadinessCheck(
            check_id="provider_config",
            status=BenchmarkReadinessStatus.UNAVAILABLE,
            reason=f"provider config unavailable: {type(exc).__name__}",
        )
    return BenchmarkReadinessCheck(
        check_id="provider_config",
        status=BenchmarkReadinessStatus.READY,
        reason="provider configuration is available",
    )


def _readiness_pricing_check(*, pricing_table: BenchmarkPricingTable, model: str, pricing_table_ref: str) -> BenchmarkReadinessCheck:
    if not model:
        return BenchmarkReadinessCheck(
            check_id="pricing_model",
            status=BenchmarkReadinessStatus.UNAVAILABLE,
            reason="benchmark model is unavailable",
        )
    if pricing_table.price_for(model) is None:
        return BenchmarkReadinessCheck(
            check_id="pricing_model",
            status=BenchmarkReadinessStatus.UNAVAILABLE,
            reason=f"pricing table does not contain selected model {model}",
        )
    return BenchmarkReadinessCheck(
        check_id="pricing_model",
        status=BenchmarkReadinessStatus.READY,
        reason="pricing table contains selected model",
        evidence_refs=[validate_ref(pricing_table_ref, "pricing_model.evidence_ref")],
    )




def _readiness_hidden_acceptance_check(tasks: list[BenchmarkTask]) -> BenchmarkReadinessCheck:
    evidence_refs: list[str] = []
    missing: list[str] = []
    for task in tasks:
        hidden_refs = [ref for ref in task.acceptance_refs if ref.endswith("hidden_checks.json")]
        if not hidden_refs:
            missing.append(task.task_id)
            continue
        for ref in hidden_refs:
            if not (ROOT / ref).is_file():
                missing.append(task.task_id)
            else:
                evidence_refs.append(ref)
    if missing:
        return BenchmarkReadinessCheck(
            check_id="hidden_acceptance",
            status=BenchmarkReadinessStatus.BLOCKED,
            reason=f"hidden acceptance is missing for tasks: {', '.join(sorted(set(missing)))}",
            evidence_refs=sorted(set(evidence_refs)),
        )
    return BenchmarkReadinessCheck(
        check_id="hidden_acceptance",
        status=BenchmarkReadinessStatus.READY,
        reason="hidden acceptance packs are present and evaluator-only",
        evidence_refs=sorted(set(evidence_refs)),
    )


def _readiness_runtime_only_fixture_check(task_items: list[dict[str, str]]) -> BenchmarkReadinessCheck:
    missing = sorted(item["task_id"] for item in task_items if not item.get("runtime_request_ref"))
    evidence_refs = sorted(item["runtime_request_ref"] for item in task_items if item.get("runtime_request_ref"))
    if missing:
        return BenchmarkReadinessCheck(
            check_id="runtime_only_fixtures",
            status=BenchmarkReadinessStatus.BLOCKED,
            reason=f"runtime-only request refs are missing for tasks: {', '.join(missing)}",
            evidence_refs=evidence_refs,
        )
    return BenchmarkReadinessCheck(
        check_id="runtime_only_fixtures",
        status=BenchmarkReadinessStatus.READY,
        reason="runtime-only request refs are present",
        evidence_refs=evidence_refs,
    )


def _readiness_full_product_flow_check() -> BenchmarkReadinessCheck:
    return BenchmarkReadinessCheck(
        check_id="full_product_flow",
        status=BenchmarkReadinessStatus.READY,
        reason="SkillFoundry TaskContract integration and product gate are importable",
    )




def resolve_model(*, provider_mode: str, provider_config_source: str, model: str) -> str:
    if model:
        return model
    if provider_mode == "faux":
        return "missionforge-faux"
    if provider_config_source == "codex_current":
        return load_codex_current_provider()["model"]
    return os.environ.get("MISSIONFORGE_PI_AGENT_MODEL", "")


def require_pricing_model(*, pricing_table: BenchmarkPricingTable, model: str, provider_mode: str) -> None:
    if not model:
        raise ContractValidationError("benchmark model must be configured")
    if pricing_table.price_for(model) is None:
        raise ContractValidationError(f"pricing table {pricing_table.pricing_table_id} does not contain model {model}")
    if provider_mode == "live" and model == "missionforge-faux":
        raise ContractValidationError("live benchmark cannot use faux pricing model")


def ensure_provider_available(*, provider_mode: str, provider_config_source: str, model: str, metadata: Mapping[str, Any]) -> None:
    env = resolve_pi_agent_provider_environment(
        provider_mode=provider_mode,
        provider_config_source=provider_config_source,
        model=model,
        metadata=metadata,
    )
    env.require_no_empty_values()


def assert_hidden_checks_not_worker_visible(tasks: list[BenchmarkTask]) -> None:
    for task in tasks:
        hidden_refs = [ref for ref in task.acceptance_refs if ref.endswith("hidden_checks.json")]
        visible_refs = set(task.allowed_source_refs)
        leaked = sorted(ref for ref in hidden_refs if ref in visible_refs)
        if leaked:
            raise ContractValidationError(f"hidden acceptance refs are worker-visible for {task.task_id}: {leaked}")


def prepare_runtime_only_fixtures(
    *,
    run_id: str,
    task_items: list[dict[str, str]],
    modes: list[BenchmarkMode],
) -> dict[str, str]:
    safe_run_id = validate_benchmark_run_id(run_id)
    if BenchmarkMode.MISSIONFORGE_RUNTIME_ONLY not in modes:
        return {}
    mission_refs: dict[str, str] = {}
    for item in task_items:
        request_ref = item.get("runtime_request_ref", "")
        if not request_ref:
            raise ContractValidationError(f"runtime_request_ref is required for runtime-only mode: {item['task_id']}")
        request = SkillFoundryRequest.from_dict(
            require_mapping(json.loads((ROOT / request_ref).read_text(encoding="utf-8")), "skillfoundry_request")
        )
        fixture_ref = f"benchmarks/runs/{safe_run_id}/runtime_only_fixture/{item['task_id']}"
        fixture_root = ROOT / fixture_ref
        fixture_root.mkdir(parents=True, exist_ok=True)
        compiled = SkillFoundryMissionCompiler().compile_request(request, workspace=fixture_root)
        mission_refs[item["task_id"]] = f"{fixture_ref}/{compiled.mission_ir_ref}"
    return mission_refs


def scan_run_for_leaks(*, run_id: str) -> list[str]:
    root = ROOT / "benchmarks/runs" / run_id
    hits: list[str] = []
    if not root.exists():
        return hits
    for path in sorted(root.rglob("*")):
        if path.name not in RUN_PUBLISHABLE_CANDIDATE_NAMES:
            continue
        if not path.is_file() or path.stat().st_size > MAX_LEAK_SCAN_BYTES:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for marker in LEAK_MARKERS:
            if marker in text:
                hits.append(f"{path.relative_to(ROOT)}:{marker}")
    return hits


def write_execution_summary(
    *,
    args: argparse.Namespace,
    manifest: Mapping[str, Any],
    tasks: list[BenchmarkTask],
    modes: list[BenchmarkMode],
    seeds: list[int],
    pricing_table: BenchmarkPricingTable,
    provider_env: Mapping[str, str],
    result: Any | None,
    runtime_mission_refs: Mapping[str, str],
    leak_hits: list[str],
    readiness_report_ref: str,
    readiness_status: str,
) -> str:
    ref = f"benchmarks/runs/{args.run_id}/execution_summary.json"
    payload = {
        "schema_version": "missionforge.value_benchmark_execution_summary.v1",
        "run_id": args.run_id,
        "stage": args.stage,
        "task_manifest_ref": validate_ref(args.task_manifest, "execution_summary.task_manifest_ref"),
        "task_ids": [task.task_id for task in tasks],
        "modes": [mode.value for mode in modes],
        "seeds": list(seeds),
        "provider_mode": args.provider_mode,
        "provider_config_source": args.provider_config_source,
        "provider_env": dict(provider_env) if provider_env else {},
        "pricing_table_id": pricing_table.pricing_table_id,
        "runtime_mission_refs": dict(runtime_mission_refs),
        "manifest_metadata": dict(manifest.get("metadata", {})) if isinstance(manifest.get("metadata", {}), Mapping) else {},
        "result_refs": result.to_dict() if result is not None else {},
        "leak_hits": list(leak_hits),
        "readiness_report_ref": validate_ref(readiness_report_ref, "execution_summary.readiness_report_ref"),
        "readiness_status": readiness_status,
        "dry_run": bool(args.dry_run),
    }
    if args.provider_mode == "live":
        payload["provider_env"] = redact_provider_env(payload["provider_env"])
    return JsonWorkspaceStore(ROOT).write_json(ref, payload)


if __name__ == "__main__":
    main()
