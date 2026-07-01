"""CLI for the thin DeepResearch integration."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from typing import Any, Callable, Sequence

import missionforge as mf

from .frontdesk import (
    FRONTDESK_ASSISTANT_TURN_REF,
    FrontDeskFixtureAdapter,
    approve_frontdesk_requirements,
    run_deepresearch_frontdesk_turn,
)
from .kernel_v2 import KernelV2FixtureAdapter, run_deepresearch_kernel_v2
from .product_contract import AcademicResearchRequest, ResearchIntensity, SeedPaper, research_intensity_profile
from .tui import FrontDeskTuiConfig, run_frontdesk_tui


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="missionforge-deepresearch")
    subparsers = parser.add_subparsers(dest="profile", required=True)
    academic = subparsers.add_parser("academic")
    academic_sub = academic.add_subparsers(dest="command", required=True)
    kernel_v2_parser = academic_sub.add_parser("kernel-v2-run")
    _add_kernel_v2_arguments(kernel_v2_parser)
    frontdesk_step_parser = academic_sub.add_parser("frontdesk-step")
    _add_frontdesk_step_arguments(frontdesk_step_parser)
    frontdesk_run_parser = academic_sub.add_parser("frontdesk-run")
    _add_frontdesk_run_arguments(frontdesk_run_parser)
    frontdesk_tui_parser = academic_sub.add_parser("frontdesk-tui")
    _add_frontdesk_tui_arguments(frontdesk_tui_parser)
    args = parser.parse_args(argv)

    if args.profile == "academic" and args.command == "kernel-v2-run":
        request, piworker_config, piworker_env = _kernel_v2_inputs(args)
        adapter = (
            KernelV2FixtureAdapter()
            if args.kernel_v2_adapter_mode == "fixture"
            else mf.create_default_piworker_adapter(piworker_config, environ=piworker_env)
        )
        return _run_and_emit_result(
            args,
            lambda: run_deepresearch_kernel_v2(
                request,
                workspace=Path(args.workspace),
                adapter=adapter,
                live_extension_mode=args.live_extension_mode,
            ),
            progress_runner=lambda progress: run_deepresearch_kernel_v2(
                request,
                workspace=Path(args.workspace),
                adapter=adapter,
                live_extension_mode=args.live_extension_mode,
                event_sink=_kernel_v2_progress_event_sink(progress),
                runtime_progress_sink=_kernel_v2_runtime_progress_sink(progress),
            ),
        )
    if args.profile == "academic" and args.command == "frontdesk-step":
        piworker_config, piworker_env = _piworker_inputs(args, args.research_intensity)
        adapter = (
            FrontDeskFixtureAdapter()
            if args.frontdesk_adapter_mode == "fixture"
            else mf.create_default_piworker_adapter(piworker_config, environ=piworker_env)
        )
        result = run_deepresearch_frontdesk_turn(
            initial_input=args.initial_input,
            user_message=args.message,
            request_id=args.request_id,
            workspace=Path(args.workspace),
            adapter=adapter,
            audience=args.audience,
            language=args.language,
            research_intensity=args.research_intensity,
            live_extension_mode=args.live_extension_mode,
        )
        _emit_user_artifact_summary(args, result)
        print(json.dumps(result.to_dict(), sort_keys=True, ensure_ascii=False))
        return 0
    if args.profile == "academic" and args.command == "frontdesk-run":
        request = approve_frontdesk_requirements(
            request_id=args.request_id,
            workspace=Path(args.workspace),
        )
        piworker_config, piworker_env = _piworker_inputs(args, request.research_intensity)
        adapter = (
            KernelV2FixtureAdapter()
            if args.kernel_v2_adapter_mode == "fixture"
            else mf.create_default_piworker_adapter(piworker_config, environ=piworker_env)
        )
        return _run_and_emit_result(
            args,
            lambda: run_deepresearch_kernel_v2(
                request,
                workspace=Path(args.workspace),
                adapter=adapter,
                live_extension_mode=args.live_extension_mode,
            ),
            progress_runner=lambda progress: run_deepresearch_kernel_v2(
                request,
                workspace=Path(args.workspace),
                adapter=adapter,
                live_extension_mode=args.live_extension_mode,
                event_sink=_kernel_v2_progress_event_sink(progress),
                runtime_progress_sink=_kernel_v2_runtime_progress_sink(progress),
            ),
        )
    if args.profile == "academic" and args.command == "frontdesk-tui":
        frontdesk_config, frontdesk_env = _piworker_inputs(args, args.research_intensity)
        frontdesk_adapter = (
            FrontDeskFixtureAdapter()
            if args.frontdesk_adapter_mode == "fixture"
            else mf.create_default_piworker_adapter(frontdesk_config, environ=frontdesk_env)
        )

        def kernel_adapter_factory(research_intensity: ResearchIntensity | str):
            kernel_config, kernel_env = _piworker_inputs(args, research_intensity)
            return (
                KernelV2FixtureAdapter()
                if args.kernel_v2_adapter_mode == "fixture"
                else mf.create_default_piworker_adapter(kernel_config, environ=kernel_env)
            )

        return run_frontdesk_tui(
            config=FrontDeskTuiConfig(
                request_id=args.request_id,
                workspace=Path(args.workspace),
                audience=args.audience,
                language=args.language,
                research_intensity=args.research_intensity,
                live_extension_mode=args.live_extension_mode,
                stream_progress=args.stream_progress,
            ),
            frontdesk_adapter=frontdesk_adapter,
            kernel_adapter_factory=kernel_adapter_factory,
            input_stream=sys.stdin,
            output_stream=sys.stdout,
        )
    parser.error("unsupported command")
    return 2


def _add_kernel_v2_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--topic", required=True)
    parser.add_argument("--request-id", default="deepresearch-kernel-v2")
    parser.add_argument("--workspace", default=".")
    parser.add_argument("--audience", default="R&D team")
    parser.add_argument("--language", default="zh")
    parser.add_argument("--research-intensity", choices=[item.value for item in ResearchIntensity], default=ResearchIntensity.STANDARD.value)
    parser.add_argument("--previous-run-ref", action="append", default=[])
    parser.add_argument(
        "--seed-paper",
        action="append",
        default=[],
        metavar="KIND:VALUE",
        help="Optional seed paper, e.g. doi:10.1145/... or arxiv:2501.01234 or title:Paper Title.",
    )
    parser.add_argument("--seed-pdf-ref", action="append", default=[], help="Optional workspace PDF ref to use as a seed.")
    parser.add_argument("--sample-report-ref", default=None)
    parser.add_argument("--target-source-count", type=int, default=None)
    parser.add_argument("--live-extension-mode", action="store_true")
    parser.add_argument("--kernel-v2-adapter-mode", choices=["piworker", "fixture"], default="piworker")
    parser.add_argument("--piworker-provider-config-source", choices=["env", "codex_current", "explicit"], default="codex_current")
    parser.add_argument("--piworker-model", default=None)
    parser.add_argument("--piworker-base-url", default=None)
    parser.add_argument("--piworker-timeout-seconds", type=int, default=None)
    parser.add_argument("--piworker-max-turns", type=int, default=None)
    parser.add_argument("--piworker-reasoning", default=None)
    parser.add_argument(
        "--stream-progress",
        "--watch-progress",
        dest="stream_progress",
        action="store_true",
        help="Stream user-visible MissionForge progress events while the run executes.",
    )
    parser.add_argument("--progress-interval", type=float, default=0.5, help="Refresh interval for --stream-progress.")


def _add_common_runtime_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--request-id", default="deepresearch-kernel-v2")
    parser.add_argument("--workspace", default=".")
    parser.add_argument("--audience", default="R&D team")
    parser.add_argument("--language", default="zh")
    parser.add_argument("--research-intensity", choices=[item.value for item in ResearchIntensity], default=ResearchIntensity.STANDARD.value)
    parser.add_argument("--piworker-provider-config-source", choices=["env", "codex_current", "explicit"], default="codex_current")
    parser.add_argument("--piworker-model", default=None)
    parser.add_argument("--piworker-base-url", default=None)
    parser.add_argument("--piworker-timeout-seconds", type=int, default=None)
    parser.add_argument("--piworker-max-turns", type=int, default=None)
    parser.add_argument("--piworker-reasoning", default=None)
    parser.add_argument(
        "--stream-progress",
        "--watch-progress",
        dest="stream_progress",
        action="store_true",
        help="Stream user-visible MissionForge progress events while the run executes.",
    )
    parser.add_argument("--progress-interval", type=float, default=0.5, help="Refresh interval for --stream-progress.")


def _add_frontdesk_step_arguments(parser: argparse.ArgumentParser) -> None:
    _add_common_runtime_arguments(parser)
    parser.add_argument("--initial-input", default=None)
    parser.add_argument("--message", default=None)
    parser.add_argument("--live-extension-mode", action="store_true")
    parser.add_argument("--frontdesk-adapter-mode", choices=["piworker", "fixture"], default="piworker")


def _add_frontdesk_run_arguments(parser: argparse.ArgumentParser) -> None:
    _add_common_runtime_arguments(parser)
    parser.add_argument("--live-extension-mode", action="store_true")
    parser.add_argument("--kernel-v2-adapter-mode", choices=["piworker", "fixture"], default="piworker")


def _add_frontdesk_tui_arguments(parser: argparse.ArgumentParser) -> None:
    _add_common_runtime_arguments(parser)
    parser.set_defaults(live_extension_mode=True)
    parser.add_argument("--live-extension-mode", dest="live_extension_mode", action="store_true", default=True)
    parser.add_argument("--no-live-extension-mode", dest="live_extension_mode", action="store_false")
    parser.add_argument("--frontdesk-adapter-mode", choices=["piworker", "fixture"], default="piworker")
    parser.add_argument("--kernel-v2-adapter-mode", choices=["piworker", "fixture"], default="piworker")


def _run_and_emit_result(
    args: argparse.Namespace,
    runner: Callable[[], Any],
    *,
    progress_runner: Callable[[mf.ProgressStreamWriter], Any] | None = None,
) -> int:
    result = _run_with_optional_progress(args, runner, progress_runner=progress_runner)
    _emit_user_artifact_summary(args, result)
    print(json.dumps(result.to_dict(), sort_keys=True, ensure_ascii=False))
    return 0


def _emit_user_artifact_summary(args: argparse.Namespace, result: Any) -> None:
    workspace = Path(args.workspace).resolve()
    refs = [
        ("requirements", getattr(result, "requirements_ref", "")),
        ("frontdesk_control", getattr(result, "control_ref", "")),
        ("frontdesk_research_request", getattr(result, "research_request_ref", "")),
        ("final_report", getattr(result, "final_report_ref", "")),
        ("citation_projected_report", getattr(result, "citation_projected_report_ref", "")),
        ("report_html", getattr(result, "report_html_ref", "")),
        ("seed_papers", getattr(result, "seed_papers_ref", "")),
        ("seed_pdf_index", getattr(result, "seed_pdf_index_ref", "")),
        ("seed_source_packet", getattr(result, "seed_source_packet_ref", "")),
        ("seed_gaps", getattr(result, "seed_gaps_ref", "")),
        ("seed_control", getattr(result, "seed_control_ref", "")),
        ("search_plan", getattr(result, "search_plan_ref", "")),
        ("provider_hits", getattr(result, "provider_hits_ref", "")),
        ("source_packet", getattr(result, "source_packet_ref", "")),
        ("source_graph", getattr(result, "source_graph_ref", "")),
        ("coverage_report", getattr(result, "coverage_report_ref", "")),
        ("citation_registry", getattr(result, "citation_registry_ref", "")),
        ("claim_index", getattr(result, "claim_index_ref", "")),
        ("result_package", getattr(result, "result_ref", "") or getattr(result, "run_result_ref", "")),
        ("run_status", getattr(result, "run_status_ref", "")),
        ("judge_report", getattr(result, "judge_report_ref", "")),
        ("usage_summary", getattr(result, "usage_summary_ref", "")),
    ]
    lines = []
    missing_lines = []
    for label, ref in refs:
        if isinstance(ref, str) and ref:
            path = workspace / ref
            if path.exists():
                lines.append(f"  {label}: {path}")
            else:
                missing_lines.append(f"  {label}: {path}")
    if not lines and not missing_lines:
        return
    if lines:
        sys.stderr.write("输出文件：\n" + "\n".join(lines) + "\n")
    if missing_lines:
        sys.stderr.write("缺失输出：\n" + "\n".join(missing_lines) + "\n")
    usage_lines = _usage_summary_lines(workspace, getattr(result, "usage_summary_ref", ""))
    if usage_lines:
        sys.stderr.write("Token 用量：\n" + "\n".join(usage_lines) + "\n")
    frontdesk_lines = _frontdesk_message_lines(workspace, getattr(result, "control_ref", ""))
    if frontdesk_lines:
        sys.stderr.write("FrontDesk：\n" + "\n".join(frontdesk_lines) + "\n")
    failure_lines = _failure_summary_lines(workspace, result)
    if failure_lines:
        sys.stderr.write("失败原因：\n" + "\n".join(failure_lines) + "\n")


def _frontdesk_message_lines(workspace: Path, control_ref: Any) -> list[str]:
    if not isinstance(control_ref, str) or not control_ref:
        return []
    assistant_turn_ref = str(Path(control_ref).parent / Path(FRONTDESK_ASSISTANT_TURN_REF).name)
    try:
        assistant_turn = json.loads((workspace / assistant_turn_ref).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    lines = []
    message = assistant_turn.get("message")
    if isinstance(message, str) and message.strip():
        lines.append(f"  {message.strip()}")
    questions = assistant_turn.get("questions")
    if isinstance(questions, list) and questions:
        lines.append("  需要你补充：")
        for index, question in enumerate(questions, start=1):
            question_text = _frontdesk_question_text(question)
            if question_text:
                lines.append(f"    {index}. {question_text}")
    return lines


def _frontdesk_question_text(question: Any) -> str:
    if isinstance(question, dict):
        text = str(question.get("question") or "").strip()
        why = str(question.get("why") or "").strip()
        hint = str(question.get("answer_hint") or "").strip()
        parts = [text] if text else []
        if why:
            parts.append(f"为什么问：{why}")
        if hint:
            parts.append(f"回答示例：{hint}")
        choices = _frontdesk_choice_texts(question.get("choices"))
        if choices:
            parts.append("候选：" + "；".join(choices))
        return " ".join(parts)
    return str(question).strip()


def _frontdesk_choice_texts(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    choices: list[str] = []
    for index, choice in enumerate(value, start=1):
        if not isinstance(choice, dict):
            continue
        label = str(choice.get("label") or "").strip()
        description = str(choice.get("description") or "").strip()
        if not label:
            continue
        suffixes = []
        if choice.get("recommended") is True:
            suffixes.append("推荐")
        if choice.get("freeform") is True:
            suffixes.append("自定义")
        marker = f" ({', '.join(suffixes)})" if suffixes else ""
        detail = f": {description}" if description else ""
        choices.append(f"{index}. {label}{marker}{detail}")
    return choices


def _usage_summary_lines(workspace: Path, usage_summary_ref: Any) -> list[str]:
    if not isinstance(usage_summary_ref, str) or not usage_summary_ref:
        return []
    try:
        payload = json.loads((workspace / usage_summary_ref).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    totals = payload.get("totals")
    if not isinstance(totals, dict):
        return []
    lines = [
        f"  input_tokens: {_format_metric(totals.get('input_tokens'))}",
        f"  cached_input_tokens: {_format_metric(totals.get('cached_input_tokens'))}",
        f"  total_input_tokens: {_format_metric(totals.get('total_input_tokens'))}",
        f"  output_tokens: {_format_metric(totals.get('output_tokens'))}",
        f"  total_tokens: {_format_metric(totals.get('total_tokens'))}",
    ]
    provider_cost = totals.get("provider_reported_cost_usd")
    if isinstance(provider_cost, (int, float)) and provider_cost > 0:
        lines.append(f"  provider_reported_cost_usd: {provider_cost:.6f}")
    return lines


def _failure_summary_lines(workspace: Path, result: Any) -> list[str]:
    status = getattr(result, "status", "")
    if status in {"accepted", "completed", "draft_ready"}:
        return []
    run_workspace_ref = getattr(result, "run_workspace_ref", "")
    flow_result_ref = getattr(result, "flow_result_ref", "")
    if not isinstance(run_workspace_ref, str) or not run_workspace_ref:
        return []
    if not isinstance(flow_result_ref, str) or not flow_result_ref:
        return []
    try:
        flow_result = json.loads((workspace / flow_result_ref).read_text(encoding="utf-8"))
        step_refs = flow_result.get("step_record_refs")
        if not isinstance(step_refs, list) or not step_refs:
            return []
        last_ref = step_refs[-1]
        if not isinstance(last_ref, str):
            return []
        step_record = json.loads((workspace / run_workspace_ref / last_ref).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    metadata = step_record.get("metadata")
    if not isinstance(metadata, dict):
        return []
    summary = metadata.get("failure_summary")
    if not isinstance(summary, str) or not summary.strip():
        return []
    step_id = step_record.get("step_id")
    prefix = f"{step_id}: " if isinstance(step_id, str) and step_id else ""
    return [f"  {prefix}{summary.strip()}"]


def _format_metric(value: Any) -> str:
    if isinstance(value, bool):
        return "0"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return str(int(value)) if value.is_integer() else str(value)
    return "0"


def _run_with_optional_progress(
    args: argparse.Namespace,
    runner: Callable[[], Any],
    *,
    progress_runner: Callable[[mf.ProgressStreamWriter], Any] | None = None,
) -> Any:
    if not args.stream_progress:
        return runner()
    workspace = Path(args.workspace) / "runs" / args.request_id
    progress = mf.ProgressStreamWriter(workspace, stream_ref=mf.DEFAULT_PROGRESS_REF)

    def wrapped_runner() -> Any:
        progress.emit(
            stage="start",
            state="running",
            message=f"开始调研 request_id={args.request_id}",
            detail="正在准备研究合同、工具权限和工作区。",
            progress_hint="1/7",
        )
        result = progress_runner(progress) if progress_runner is not None else runner()
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

    return mf.stream_progress(
        wrapped_runner,
        workspace=workspace,
        stream_ref=mf.DEFAULT_PROGRESS_REF,
        interval_seconds=args.progress_interval,
    )


def _kernel_v2_progress_event_sink(progress: mf.ProgressStreamWriter) -> Callable[[mf.FlowLedgerEvent], None]:
    def emit(event: mf.FlowLedgerEvent) -> None:
        progress_event = _kernel_v2_progress_event(event)
        if progress_event is None:
            return
        progress.emit(**progress_event)

    return emit


def _kernel_v2_runtime_progress_sink(progress: mf.ProgressStreamWriter) -> mf.PiWorkerProgressSink:
    def emit(event: dict[str, Any]) -> None:
        state = event.get("state") if event.get("state") in {"pending", "running", "completed", "failed", "blocked"} else "running"
        progress.emit(
            stage=str(event.get("stage") or "piworker_runtime"),
            state=state,
            message=str(event.get("message") or "PiWorker runtime is running."),
            detail=str(event.get("detail") or ""),
            progress_hint=str(event.get("progress_hint") or "piworker"),
            refs=[ref for ref in event.get("refs", []) if isinstance(ref, str)],
        )

    return emit


def _kernel_v2_progress_event(event: mf.FlowLedgerEvent) -> dict[str, Any] | None:
    step_label = _kernel_v2_step_label(event.step_id)
    progress_hint = f"kernel {event.metadata.get('step_index')}" if event.metadata.get("step_index") else "kernel"
    if event.kind == mf.FlowLedgerEventKind.STEP_STARTED:
        return {
            "stage": f"kernel_{event.step_id or 'step'}",
            "state": "running",
            "message": f"{step_label} 正在执行。",
            "detail": "Kernel 已冻结 step 输入、输出 refs 和权限边界。",
            "progress_hint": progress_hint,
            "refs": event.refs,
        }
    if event.kind == mf.FlowLedgerEventKind.STEP_RECORDED:
        state = _progress_state_from_kernel_status(event.status)
        return {
            "stage": f"kernel_{event.step_id or 'step'}",
            "state": state,
            "message": f"{step_label} 已记录：status={event.status or 'unknown'}。",
            "detail": "Step record、PiWorker call result、metrics refs 已写入。",
            "progress_hint": progress_hint,
            "refs": event.refs,
        }
    if event.kind == mf.FlowLedgerEventKind.ROUTED:
        state = _progress_state_from_kernel_status(event.status)
        return {
            "stage": f"kernel_{event.step_id or 'route'}_route",
            "state": state,
            "message": f"{step_label} 路由到 {event.route_target or 'unknown'}。",
            "detail": f"decision={event.route_value or 'unknown'}；路由只读取 decision artifact。",
            "progress_hint": progress_hint,
            "refs": event.refs,
        }
    if event.kind == mf.FlowLedgerEventKind.INTERACTION_RECORDED:
        event_count = event.metadata.get("event_count") if isinstance(event.metadata, dict) else None
        detail = "用户插入已在安全点投影给后续 worker。"
        if isinstance(event_count, int):
            detail = f"本安全点包含 {event_count} 条待处理用户事件。"
        return {
            "stage": f"kernel_{event.step_id or 'flow'}_interaction",
            "state": event.status or "running",
            "message": f"{step_label} 已记录交互安全点。",
            "detail": detail,
            "progress_hint": progress_hint,
            "refs": event.refs,
        }
    if event.kind == mf.FlowLedgerEventKind.PROJECTIONS_RECORDED:
        return {
            "stage": "kernel_projections",
            "state": "completed",
            "message": "Kernel runtime projections 已完成。",
            "detail": "机械投影 artifacts 和 projection records 已写入。",
            "progress_hint": "kernel",
            "refs": event.refs,
        }
    return None


def _progress_state_from_kernel_status(status: str | None) -> str:
    if status in {"completed", "skipped", "accepted"}:
        return "completed"
    if status == "blocked":
        return "blocked"
    if status == "failed":
        return "failed"
    return "running"


def _kernel_v2_step_label(step_id: str | None) -> str:
    labels = {
        "seed_normalizer": "Kernel v2 seed normalizer",
        "source_mapper": "Kernel v2 source mapper",
        "researcher": "Kernel v2 researcher",
        "reviewer": "Kernel v2 reviewer",
        "judge": "Kernel v2 judge",
    }
    return labels.get(step_id or "", f"Kernel step {step_id or 'unknown'}")


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


def _kernel_v2_inputs(args: argparse.Namespace) -> tuple[AcademicResearchRequest, object, dict[str, str]]:
    request = AcademicResearchRequest(
        request_id=args.request_id,
        topic=args.topic,
        audience=args.audience,
        language=args.language,
        research_intensity=args.research_intensity,
        previous_run_refs=list(args.previous_run_ref),
        seed_papers=_seed_papers_from_args(args.seed_paper),
        seed_pdf_refs=list(args.seed_pdf_ref),
        sample_report_ref=args.sample_report_ref,
        target_source_count=args.target_source_count,
    )
    piworker_config, piworker_env = _piworker_inputs(args, request.research_intensity)
    return request, piworker_config, piworker_env


def _seed_papers_from_args(values: list[str]) -> list[SeedPaper]:
    result = []
    for value in values:
        if ":" not in value:
            raise mf.ContractValidationError("--seed-paper must use KIND:VALUE")
        kind, seed_value = value.split(":", 1)
        result.append(SeedPaper(kind=kind.strip(), value=seed_value.strip()))
    return result


def _piworker_inputs(args: argparse.Namespace, research_intensity: ResearchIntensity | str) -> tuple[object, dict[str, str]]:
    intensity_profile = research_intensity_profile(research_intensity)
    piworker_metadata = {}
    if args.piworker_base_url:
        piworker_metadata["base_url"] = args.piworker_base_url
    piworker_env = dict(os.environ)
    effective_timeout = args.piworker_timeout_seconds or intensity_profile.piworker_timeout_seconds
    effective_reasoning = args.piworker_reasoning or intensity_profile.piworker_reasoning
    if args.piworker_max_turns is not None:
        piworker_env["MISSIONFORGE_PI_AGENT_MAX_TURNS"] = str(args.piworker_max_turns)
    piworker_env["MISSIONFORGE_PI_AGENT_REASONING"] = effective_reasoning
    piworker_config = mf.create_piagent_runtime_config(
        timeout_seconds=effective_timeout,
        provider_mode="live",
        provider_config_source=args.piworker_provider_config_source,
        model=args.piworker_model,
        metadata=piworker_metadata,
        context_large_observation_bytes=16 * 1024,
    )
    return piworker_config, piworker_env


if __name__ == "__main__":
    raise SystemExit(main())
