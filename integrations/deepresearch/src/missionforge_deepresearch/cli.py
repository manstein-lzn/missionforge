"""CLI for the thin DeepResearch integration."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Sequence

from missionforge.adapters.pi_agent_runtime import PiAgentRuntimeConfig

from .judging import FixtureDeepResearchJudgeAdapter, run_deepresearch_academic_judged
from .product_contract import AcademicResearchRequest
from .quality_evaluation import (
    FixtureDirectBaselineAdapter,
    FixtureQualityEvaluatorAdapter,
    run_deepresearch_quality_evaluation,
)
from .runtime import run_deepresearch_academic_single_agent
from .source_collector import AcademicSourceCollectionConfig


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="missionforge-deepresearch")
    subparsers = parser.add_subparsers(dest="profile", required=True)
    academic = subparsers.add_parser("academic")
    academic_sub = academic.add_subparsers(dest="command", required=True)
    run_parser = academic_sub.add_parser("single-agent-run")
    _add_run_arguments(run_parser)
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
    args = parser.parse_args(argv)

    if args.profile == "academic" and args.command == "single-agent-run":
        request, source_config, piworker_config, piworker_env = _run_inputs(args)
        result = run_deepresearch_academic_single_agent(
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
        )
        print(json.dumps(result.to_dict(), sort_keys=True, ensure_ascii=False))
        return 0
    if args.profile == "academic" and args.command == "judged-run":
        request, source_config, piworker_config, piworker_env = _run_inputs(args)
        judge_adapter = (
            FixtureDeepResearchJudgeAdapter(args.fixture_judge_decision) if args.judge_mode == "fixture" else None
        )
        result = run_deepresearch_academic_judged(
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
        )
        print(json.dumps(result.to_dict(), sort_keys=True, ensure_ascii=False))
        return 0
    if args.profile == "academic" and args.command == "quality-eval":
        request, source_config, piworker_config, piworker_env = _run_inputs(args)
        direct_adapter = FixtureDirectBaselineAdapter() if args.direct_baseline_mode == "fixture" else None
        evaluator_mode = "piworker" if args.evaluator_mode == "fixture" else args.evaluator_mode
        evaluator_adapter = FixtureQualityEvaluatorAdapter() if args.evaluator_mode == "fixture" else None
        result = run_deepresearch_quality_evaluation(
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
        )
        print(json.dumps(result.to_dict(), sort_keys=True, ensure_ascii=False))
        return 0
    parser.error("unsupported command")
    return 2


def _add_run_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--topic", required=True)
    parser.add_argument("--request-id", default="deepresearch-phase1")
    parser.add_argument("--workspace", default=".")
    parser.add_argument("--audience", default="R&D team")
    parser.add_argument("--language", default="zh")
    parser.add_argument("--previous-run-ref", action="append", default=[])
    parser.add_argument("--source-mode", choices=["fixture", "live"], default="fixture")
    parser.add_argument("--researcher-mode", choices=["fixture", "piworker"], default="fixture")
    parser.add_argument("--search-intent-mode", choices=["none", "external", "piworker"], default="none")
    parser.add_argument("--search-query", action="append", default=[])
    parser.add_argument("--search-intent-ref", default=None)
    parser.add_argument("--live-extension-mode", action="store_true")
    parser.add_argument("--max-sources", type=int, default=24)
    parser.add_argument("--since-year", type=int, default=None)
    parser.add_argument("--source-timeout-seconds", type=float, default=20.0)
    parser.add_argument("--max-search-queries", type=int, default=6)
    parser.add_argument("--source-concurrency", type=int, default=8)
    parser.add_argument("--piworker-provider-config-source", choices=["env", "codex_current", "explicit"], default="env")
    parser.add_argument("--piworker-model", default=None)
    parser.add_argument("--piworker-base-url", default=None)
    parser.add_argument("--piworker-timeout-seconds", type=int, default=900)
    parser.add_argument("--piworker-max-turns", type=int, default=20)
    parser.add_argument("--piworker-reasoning", default="medium")


def _run_inputs(args: argparse.Namespace) -> tuple[AcademicResearchRequest, AcademicSourceCollectionConfig, PiAgentRuntimeConfig, dict[str, str]]:
    request = AcademicResearchRequest(
        request_id=args.request_id,
        topic=args.topic,
        audience=args.audience,
        language=args.language,
        previous_run_refs=list(args.previous_run_ref),
    )
    source_config = AcademicSourceCollectionConfig(
        max_records=args.max_sources,
        provider_timeout_seconds=args.source_timeout_seconds,
        since_year=args.since_year,
        max_search_queries=args.max_search_queries,
        max_concurrent_requests=args.source_concurrency,
    )
    piworker_metadata = {}
    if args.piworker_base_url:
        piworker_metadata["base_url"] = args.piworker_base_url
    piworker_env = dict(os.environ)
    piworker_env["MISSIONFORGE_PI_AGENT_MAX_TURNS"] = str(args.piworker_max_turns)
    piworker_env["MISSIONFORGE_PI_AGENT_REASONING"] = args.piworker_reasoning
    piworker_config = PiAgentRuntimeConfig(
        timeout_seconds=args.piworker_timeout_seconds,
        provider_mode="live",
        provider_config_source=args.piworker_provider_config_source,
        model=args.piworker_model,
        metadata=piworker_metadata,
        context_large_observation_bytes=16 * 1024,
    )
    return request, source_config, piworker_config, piworker_env


if __name__ == "__main__":
    raise SystemExit(main())
