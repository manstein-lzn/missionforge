"""CLI for the thin DeepResearch integration."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Callable, Sequence

from missionforge.adapters.long_memory import Mem0LongMemoryProvider
from missionforge.adapters.pi_agent_runtime import PiAgentRuntimeConfig
from missionforge.progress_stream import DEFAULT_PROGRESS_REF, ProgressStreamWriter, stream_progress

from .experimental import (
    FixtureDirectBaselineAdapter,
    FixturePeerReviewerAdapter,
    FixtureQualityEvaluatorAdapter,
    run_deepresearch_academic_reviewed,
    run_deepresearch_academic_reviewed_judged,
    run_deepresearch_quality_evaluation,
    run_deepresearch_tool_healthcheck,
)
from .judging import FixtureDeepResearchJudgeAdapter, run_deepresearch_academic_judged
from .minimal import run_deepresearch_minimal, run_deepresearch_minimal_loop
from .product_contract import AcademicResearchRequest, ResearchIntensity, research_intensity_profile
from .runtime import run_deepresearch_academic_single_agent
from .search_intent import AcademicSearchIntent
from .source_collector import AcademicSourceCollectionConfig


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="missionforge-deepresearch")
    subparsers = parser.add_subparsers(dest="profile", required=True)
    academic = subparsers.add_parser("academic")
    academic_sub = academic.add_subparsers(dest="command", required=True)
    minimal_parser = academic_sub.add_parser("minimal-run")
    _add_run_arguments(minimal_parser)
    minimal_loop_parser = academic_sub.add_parser("minimal-loop-run")
    _add_run_arguments(minimal_loop_parser)
    minimal_loop_parser.add_argument("--reviewer-mode", choices=["fixture", "piworker"], default="piworker")
    minimal_loop_parser.add_argument("--review-rounds", type=int, default=None, help="Maximum reviewer-guided rounds.")
    run_parser = academic_sub.add_parser("single-agent-run")
    _add_run_arguments(run_parser)
    reviewed_parser = academic_sub.add_parser("reviewed-run")
    _add_run_arguments(reviewed_parser)
    reviewed_parser.add_argument("--reviewer-mode", choices=["fixture", "piworker"], default="piworker")
    reviewed_parser.add_argument("--review-rounds", type=int, default=None, help="Maximum reviewer-guided rounds.")
    reviewed_judged_parser = academic_sub.add_parser("reviewed-judged-run")
    _add_run_arguments(reviewed_judged_parser)
    reviewed_judged_parser.add_argument("--reviewer-mode", choices=["fixture", "piworker"], default="piworker")
    reviewed_judged_parser.add_argument("--review-rounds", type=int, default=None, help="Maximum reviewer-guided rounds.")
    reviewed_judged_parser.add_argument("--judge-mode", choices=["fixture", "piworker"], default="piworker")
    reviewed_judged_parser.add_argument(
        "--fixture-judge-decision",
        choices=["accepted", "repair", "revision_required", "rejected"],
        default="accepted",
    )
    judged_parser = academic_sub.add_parser("judged-run")
    _add_run_arguments(judged_parser)
    judged_parser.add_argument("--judge-mode", choices=["fixture", "piworker"], default="piworker")
    judged_parser.add_argument(
        "--fixture-judge-decision",
        choices=["accepted", "repair", "revision_required", "rejected"],
        default="accepted",
    )
    eval_parser = academic_sub.add_parser("quality-eval")
    _add_run_arguments(eval_parser)
    eval_parser.add_argument("--direct-baseline-mode", choices=["fixture", "piworker"], default="piworker")
    eval_parser.add_argument("--evaluator-mode", choices=["heuristic", "piworker", "fixture"], default="heuristic")
    health_parser = academic_sub.add_parser("tool-healthcheck")
    _add_healthcheck_arguments(health_parser)
    args = parser.parse_args(argv)

    if args.profile == "academic" and args.command == "minimal-run":
        request, _source_config, piworker_config, piworker_env = _run_inputs(args)
        return _run_and_emit_result(
            args,
            lambda: run_deepresearch_minimal(
                request,
                workspace=Path(args.workspace),
                researcher_mode=args.researcher_mode,
                piworker_config=piworker_config,
                piworker_environ=piworker_env,
                live_extension_mode=args.live_extension_mode,
            ),
        )
    if args.profile == "academic" and args.command == "minimal-loop-run":
        request, _source_config, piworker_config, piworker_env = _run_inputs(args)
        return _run_and_emit_result(
            args,
            lambda: run_deepresearch_minimal_loop(
                request,
                workspace=Path(args.workspace),
                researcher_mode=args.researcher_mode,
                reviewer_mode=args.reviewer_mode,
                piworker_config=piworker_config,
                piworker_environ=piworker_env,
                live_extension_mode=args.live_extension_mode,
                review_rounds=args.review_rounds,
            ),
        )
    if args.profile == "academic" and args.command == "single-agent-run":
        request, source_config, piworker_config, piworker_env = _run_inputs(args)
        long_memory_provider = _long_memory_provider(args)
        return _run_and_emit_result(
            args,
            lambda: run_deepresearch_academic_single_agent(
                request,
                workspace=Path(args.workspace),
                source_mode=args.source_mode,
                researcher_mode=args.researcher_mode,
                search_intent_mode=args.search_intent_mode,
                search_queries=list(args.search_query),
                search_intent_ref=args.search_intent_ref,
                source_config=source_config,
                piworker_config=piworker_config,
                piworker_environ=piworker_env,
                live_extension_mode=args.live_extension_mode,
                long_memory_provider=long_memory_provider,
                long_memory_budget_tokens=args.long_memory_budget_tokens,
                long_memory_limit=args.long_memory_limit,
            ),
        )
    if args.profile == "academic" and args.command == "reviewed-run":
        request, source_config, piworker_config, piworker_env = _run_inputs(args)
        reviewer_adapter = FixturePeerReviewerAdapter() if args.reviewer_mode == "fixture" else None
        return _run_and_emit_result(
            args,
            lambda: run_deepresearch_academic_reviewed(
                request,
                workspace=Path(args.workspace),
                source_mode=args.source_mode,
                researcher_mode=args.researcher_mode,
                reviewer_mode=args.reviewer_mode,
                search_intent_mode=args.search_intent_mode,
                search_queries=list(args.search_query),
                search_intent_ref=args.search_intent_ref,
                source_config=source_config,
                piworker_config=piworker_config,
                piworker_environ=piworker_env,
                live_extension_mode=args.live_extension_mode,
                reviewer_adapter=reviewer_adapter,
                review_rounds=args.review_rounds,
            ),
        )
    if args.profile == "academic" and args.command == "reviewed-judged-run":
        request, source_config, piworker_config, piworker_env = _run_inputs(args)
        reviewer_adapter = FixturePeerReviewerAdapter() if args.reviewer_mode == "fixture" else None
        judge_adapter = (
            FixtureDeepResearchJudgeAdapter(args.fixture_judge_decision) if args.judge_mode == "fixture" else None
        )
        return _run_and_emit_result(
            args,
            lambda: run_deepresearch_academic_reviewed_judged(
                request,
                workspace=Path(args.workspace),
                source_mode=args.source_mode,
                researcher_mode=args.researcher_mode,
                reviewer_mode=args.reviewer_mode,
                search_intent_mode=args.search_intent_mode,
                search_queries=list(args.search_query),
                search_intent_ref=args.search_intent_ref,
                source_config=source_config,
                piworker_config=piworker_config,
                piworker_environ=piworker_env,
                live_extension_mode=args.live_extension_mode,
                reviewer_adapter=reviewer_adapter,
                judge_adapter=judge_adapter,
                review_rounds=args.review_rounds,
            ),
        )
    if args.profile == "academic" and args.command == "judged-run":
        request, source_config, piworker_config, piworker_env = _run_inputs(args)
        judge_adapter = (
            FixtureDeepResearchJudgeAdapter(args.fixture_judge_decision) if args.judge_mode == "fixture" else None
        )
        return _run_and_emit_result(
            args,
            lambda: run_deepresearch_academic_judged(
                request,
                workspace=Path(args.workspace),
                source_mode=args.source_mode,
                researcher_mode=args.researcher_mode,
                search_intent_mode=args.search_intent_mode,
                search_queries=list(args.search_query),
                search_intent_ref=args.search_intent_ref,
                source_config=source_config,
                piworker_config=piworker_config,
                piworker_environ=piworker_env,
                live_extension_mode=args.live_extension_mode,
                judge_adapter=judge_adapter,
            ),
        )
    if args.profile == "academic" and args.command == "quality-eval":
        request, source_config, piworker_config, piworker_env = _run_inputs(args)
        direct_adapter = FixtureDirectBaselineAdapter() if args.direct_baseline_mode == "fixture" else None
        evaluator_mode = "piworker" if args.evaluator_mode == "fixture" else args.evaluator_mode
        evaluator_adapter = FixtureQualityEvaluatorAdapter() if args.evaluator_mode == "fixture" else None
        return _run_and_emit_result(
            args,
            lambda: run_deepresearch_quality_evaluation(
                request,
                workspace=Path(args.workspace),
                source_mode=args.source_mode,
                researcher_mode=args.researcher_mode,
                search_intent_mode=args.search_intent_mode,
                search_queries=list(args.search_query),
                search_intent_ref=args.search_intent_ref,
                source_config=source_config,
                piworker_config=piworker_config,
                piworker_environ=piworker_env,
                live_extension_mode=args.live_extension_mode,
                direct_adapter=direct_adapter,
                evaluator_mode=evaluator_mode,
                evaluator_adapter=evaluator_adapter,
            ),
        )
    if args.profile == "academic" and args.command == "tool-healthcheck":
        request = AcademicResearchRequest(
            request_id=args.request_id,
            topic=args.topic,
            audience=args.audience,
            language=args.language,
            research_intensity=args.research_intensity,
        )
        providers = tuple(args.academic_provider) if args.academic_provider else ("semantic_scholar", "crossref", "openalex", "arxiv")
        intensity_profile = research_intensity_profile(request.research_intensity)
        source_config = AcademicSourceCollectionConfig(
            max_records=args.max_sources or intensity_profile.max_sources,
            provider_timeout_seconds=args.source_timeout_seconds,
            since_year=args.since_year,
            providers=providers,
            max_search_queries=args.max_search_queries or intensity_profile.max_search_queries,
            max_concurrent_requests=args.source_concurrency,
        )
        search_intent = (
            AcademicSearchIntent.from_queries(
                request,
                list(args.search_query),
                created_by="external",
                notes=["CLI supplied explicit healthcheck search queries."],
            )
            if args.search_query
            else None
        )
        result = run_deepresearch_tool_healthcheck(
            request,
            workspace=Path(args.workspace),
            source_config=source_config,
            academic_providers=providers,
            github_query=args.github_query,
            search_intent=search_intent,
        )
        print(json.dumps(result, sort_keys=True, ensure_ascii=False))
        return 0
    parser.error("unsupported command")
    return 2


def _add_run_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--topic", required=True)
    parser.add_argument("--request-id", default="deepresearch-phase1")
    parser.add_argument("--workspace", default=".")
    parser.add_argument("--audience", default="R&D team")
    parser.add_argument("--language", default="zh")
    parser.add_argument("--research-intensity", choices=[item.value for item in ResearchIntensity], default=ResearchIntensity.STANDARD.value)
    parser.add_argument("--previous-run-ref", action="append", default=[])
    parser.add_argument("--source-mode", choices=["fixture", "live"], default="fixture")
    parser.add_argument("--researcher-mode", choices=["fixture", "piworker"], default="fixture")
    parser.add_argument("--search-intent-mode", choices=["none", "external", "piworker"], default="none")
    parser.add_argument("--search-query", action="append", default=[])
    parser.add_argument("--search-intent-ref", default=None)
    parser.add_argument("--live-extension-mode", action="store_true")
    parser.add_argument("--max-sources", type=int, default=None)
    parser.add_argument("--since-year", type=int, default=None)
    parser.add_argument("--source-timeout-seconds", type=float, default=20.0)
    parser.add_argument("--max-search-queries", type=int, default=None)
    parser.add_argument("--source-concurrency", type=int, default=8)
    parser.add_argument("--piworker-provider-config-source", choices=["env", "codex_current", "explicit"], default="env")
    parser.add_argument("--piworker-model", default=None)
    parser.add_argument("--piworker-base-url", default=None)
    parser.add_argument("--piworker-timeout-seconds", type=int, default=None)
    parser.add_argument("--piworker-max-turns", type=int, default=None)
    parser.add_argument("--piworker-reasoning", default=None)
    parser.add_argument("--long-memory-provider", choices=["none", "mem0"], default="none")
    parser.add_argument("--long-memory-budget-tokens", type=int, default=2000)
    parser.add_argument("--long-memory-limit", type=int, default=8)
    parser.add_argument(
        "--stream-progress",
        "--watch-progress",
        dest="stream_progress",
        action="store_true",
        help="Stream user-visible MissionForge progress events while the run executes.",
    )
    parser.add_argument("--progress-interval", type=float, default=0.5, help="Refresh interval for --stream-progress.")


def _add_healthcheck_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--topic", required=True)
    parser.add_argument("--request-id", default="deepresearch-tool-healthcheck")
    parser.add_argument("--workspace", default=".")
    parser.add_argument("--audience", default="R&D team")
    parser.add_argument("--language", default="zh")
    parser.add_argument("--research-intensity", choices=[item.value for item in ResearchIntensity], default=ResearchIntensity.STANDARD.value)
    parser.add_argument(
        "--academic-provider",
        action="append",
        choices=["semantic_scholar", "crossref", "openalex", "arxiv"],
        default=[],
    )
    parser.add_argument("--search-query", action="append", default=[])
    parser.add_argument("--github-query", default=None)
    parser.add_argument("--max-sources", type=int, default=None)
    parser.add_argument("--since-year", type=int, default=None)
    parser.add_argument("--source-timeout-seconds", type=float, default=20.0)
    parser.add_argument("--max-search-queries", type=int, default=None)
    parser.add_argument("--source-concurrency", type=int, default=4)


def _run_and_emit_result(args: argparse.Namespace, runner: Callable[[], Any]) -> int:
    result = _run_with_optional_progress(args, runner)
    print(json.dumps(result.to_dict(), sort_keys=True, ensure_ascii=False))
    return 0


def _run_with_optional_progress(args: argparse.Namespace, runner: Callable[[], Any]) -> Any:
    if not args.stream_progress:
        return runner()
    workspace = Path(args.workspace) / "runs" / args.request_id
    progress = ProgressStreamWriter(workspace, stream_ref=DEFAULT_PROGRESS_REF)

    def wrapped_runner() -> Any:
        progress.emit(
            stage="start",
            state="running",
            message=f"开始调研：{args.topic}",
            detail="正在准备研究合同、工具权限和工作区。",
            progress_hint="1/7",
        )
        result = runner()
        state, message, detail = _progress_completion(result)
        progress.emit(
            stage="complete",
            state=state,
            message=message,
            detail=detail,
            progress_hint="7/7",
            refs=_progress_result_refs(result),
        )
        return result

    return stream_progress(
        wrapped_runner,
        workspace=workspace,
        stream_ref=DEFAULT_PROGRESS_REF,
        interval_seconds=args.progress_interval,
    )


def _progress_completion(result: Any) -> tuple[str, str, str]:
    status = str(getattr(result, "status", "") or "")
    if status in {"draft_ready", "accepted", "comparison_ready"}:
        return (
            "completed",
            "调研流程完成。",
            "最终报告、证据索引和运行结果已写入工作区。",
        )
    if status in {"blocked", "repair", "revision_required"}:
        return (
            "blocked",
            "调研流程需要后续处理。",
            f"运行结果为 {status}；请检查 run result、review/judge 报告和相关 refs。",
        )
    return (
        "failed",
        "调研流程未完成。",
        f"运行结果为 {status or 'unknown'}；请检查 run result、结构化检查和 PiWorker execution report refs。",
    )


def _progress_result_refs(result: Any) -> list[str]:
    refs = []
    for field_name in (
        "run_result_ref",
        "result_ref",
        "reviewed_run_result_ref",
        "judged_run_result_ref",
        "final_run_result_ref",
        "final_package_ref",
        "evaluation_result_ref",
    ):
        value = getattr(result, field_name, "")
        if isinstance(value, str) and value and value not in refs:
            refs.append(value)
    return refs


def _run_inputs(args: argparse.Namespace) -> tuple[AcademicResearchRequest, AcademicSourceCollectionConfig, PiAgentRuntimeConfig, dict[str, str]]:
    request = AcademicResearchRequest(
        request_id=args.request_id,
        topic=args.topic,
        audience=args.audience,
        language=args.language,
        research_intensity=args.research_intensity,
        previous_run_refs=list(args.previous_run_ref),
    )
    intensity_profile = research_intensity_profile(request.research_intensity)
    source_config = AcademicSourceCollectionConfig(
        max_records=args.max_sources or intensity_profile.max_sources,
        provider_timeout_seconds=args.source_timeout_seconds,
        since_year=args.since_year,
        max_search_queries=args.max_search_queries or intensity_profile.max_search_queries,
        max_concurrent_requests=args.source_concurrency,
    )
    piworker_metadata = {}
    if args.piworker_base_url:
        piworker_metadata["base_url"] = args.piworker_base_url
    piworker_env = dict(os.environ)
    effective_max_turns = args.piworker_max_turns or intensity_profile.researcher_max_turns
    effective_timeout = args.piworker_timeout_seconds or intensity_profile.piworker_timeout_seconds
    effective_reasoning = args.piworker_reasoning or intensity_profile.piworker_reasoning
    piworker_env["MISSIONFORGE_PI_AGENT_MAX_TURNS"] = str(effective_max_turns)
    piworker_env["MISSIONFORGE_PI_AGENT_REASONING"] = effective_reasoning
    piworker_config = PiAgentRuntimeConfig(
        timeout_seconds=effective_timeout,
        provider_mode="live",
        provider_config_source=args.piworker_provider_config_source,
        model=args.piworker_model,
        metadata=piworker_metadata,
        context_large_observation_bytes=16 * 1024,
    )
    return request, source_config, piworker_config, piworker_env


def _long_memory_provider(args: argparse.Namespace) -> Any | None:
    if args.long_memory_provider == "none":
        return None
    if args.long_memory_provider == "mem0":
        return Mem0LongMemoryProvider.from_environment()
    raise ValueError(f"unsupported long memory provider: {args.long_memory_provider}")


if __name__ == "__main__":
    raise SystemExit(main())
