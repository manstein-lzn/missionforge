"""Interactive terminal FrontDesk for DeepResearch."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
try:  # Importing readline lets input() handle multibyte line editing on POSIX.
    import readline as _readline  # noqa: F401
except ImportError:  # pragma: no cover - Windows/plain runtime fallback.
    _readline = None  # type: ignore[assignment]
import sys
import threading
from typing import Any, Callable, TextIO

try:  # Rich is a presentation dependency; keep a plain fallback for source runs.
    from rich.console import Console
    from rich.markdown import Markdown
    from rich.panel import Panel
    from rich.table import Table
except ModuleNotFoundError:  # pragma: no cover - exercised by plain fallback tests.
    Console = None  # type: ignore[assignment]
    Markdown = None  # type: ignore[assignment]
    Panel = None  # type: ignore[assignment]
    Table = None  # type: ignore[assignment]

import missionforge as mf

from .frontdesk import (
    FRONTDESK_ASSISTANT_TURN_REF,
    FRONTDESK_CONTROL_REF,
    FRONTDESK_REQUIREMENTS_REF,
    approve_frontdesk_requirements,
    evaluate_frontdesk_resume_state,
    run_deepresearch_frontdesk_turn,
)
from .kernel_v2 import DeepResearchKernelV2Result, deepresearch_kernel_v2_flow_run_id, run_deepresearch_kernel_v2
from .product_contract import ResearchIntensity
from .project_lifecycle import PROJECT_LIFECYCLE_STATE_REF, PROJECT_RESUME_DIAGNOSTICS_REF
from .workspace import read_json_ref, read_text_ref


TUI_WIDTH = 88
PROJECT_PROGRESS_REFS = {
    "research_state": "state/research_state.json",
    "researcher_control": "state/researcher_control.json",
    "reviewer_observation": "reviews/reviewer_observation.json",
    "claim_support_review": "reviews/claim_support_review.json",
    "judge_report": "judge/judge_report.json",
    "acceptance_gate": "state/acceptance_gate.json",
    "revision_request": "revisions/revision_request.json",
    "run_status": "state/run_status.json",
    "seed_pdf_index": "inputs/seed_pdf_index.json",
    "seed_source_packet": "sources/seed_source_packet.json",
    "seed_gaps": "reports/seed_gaps.md",
    "seed_control": "state/seed_control.json",
    "search_plan": "sources/search_plan.json",
    "provider_hits": "sources/provider_hits.jsonl",
    "source_packet": "sources/source_packet.json",
    "coverage_report": "sources/coverage_report.json",
    "claim_index": "claims/claim_index.json",
    "usage_summary": "metrics/usage_summary.json",
}


@dataclass(frozen=True)
class FrontDeskTuiConfig:
    request_id: str
    workspace: Path
    audience: str = "R&D team"
    language: str = "zh"
    research_intensity: ResearchIntensity | str = ResearchIntensity.INTENSIVE
    live_extension_mode: bool = True
    stream_progress: bool = True


def run_frontdesk_tui(
    *,
    config: FrontDeskTuiConfig,
    frontdesk_adapter: mf.PiWorkerCallAdapter,
    kernel_adapter_factory: Callable[[ResearchIntensity | str], mf.PiWorkerCallAdapter],
    input_stream: TextIO = sys.stdin,
    output_stream: TextIO = sys.stdout,
    progress_runner: Callable[[Any], DeepResearchKernelV2Result] | None = None,
) -> int:
    """Run a simple chat-style FrontDesk session in the terminal."""

    _print_intro(output_stream, config)
    resume_ref = evaluate_frontdesk_resume_state(
        request_id=config.request_id,
        workspace=config.workspace,
        audience=config.audience,
        language=config.language,
        research_intensity=config.research_intensity,
        live_extension_mode=config.live_extension_mode,
    )
    if resume_ref:
        _print_resume_status(output_stream, config)
    initial_seen = _has_initial_input(config)
    last_status = _read_existing_status(config)
    if last_status == "ready_for_approval":
        _print_ready(output_stream, config)
    while True:
        prompt = "\n你> " if initial_seen else "\n请描述你的初始研究想法> "
        try:
            raw_message = _read_user_line(prompt, input_stream=input_stream, output_stream=output_stream)
        except KeyboardInterrupt:
            output_stream.write("\n已退出 FrontDesk。\n")
            return 130
        if raw_message is None:
            output_stream.write("\n已退出 FrontDesk。\n")
            return 0
        message = raw_message.strip()
        if not message:
            continue
        command = message.lower()
        if command in {"/quit", "/exit", "退出"}:
            output_stream.write("已退出 FrontDesk。\n")
            return 0
        if command in {"/help", "帮助"}:
            _print_help(output_stream)
            continue
        if command in {"/show", "查看"}:
            _print_requirements(output_stream, config)
            continue
        if command in {"/status", "状态"}:
            _print_status(output_stream, config)
            continue
        if command in {"/approve", "批准", "同意"}:
            if _read_existing_status(config) != "ready_for_approval":
                output_stream.write("FrontDesk 还没有标记 ready_for_approval，不能启动正式研究。\n")
                continue
            return _run_approved_research(
                config=config,
                kernel_adapter_factory=kernel_adapter_factory,
                input_stream=input_stream,
                output_stream=output_stream,
                progress_runner=progress_runner,
            )
        try:
            _section(output_stream, "FrontDesk 正在分析")
            result = run_deepresearch_frontdesk_turn(
                initial_input=message if not initial_seen else None,
                user_message=message if initial_seen else None,
                request_id=config.request_id,
                workspace=config.workspace,
                adapter=frontdesk_adapter,
                audience=config.audience,
                language=config.language,
                research_intensity=config.research_intensity,
                live_extension_mode=config.live_extension_mode,
                runtime_progress_sink=_tui_runtime_progress_sink(output_stream, "frontdesk")
                if config.stream_progress
                else None,
            )
        except mf.ContractValidationError as exc:
            output_stream.write(f"FrontDesk 调用失败：{exc}\n")
            continue
        initial_seen = True
        last_status = result.status
        _print_frontdesk_result(output_stream, config, result.status)


def _print_intro(output_stream: TextIO, config: FrontDeskTuiConfig) -> None:
    rich_console = _rich_console(output_stream)
    if rich_console is not None:
        grid = Table.grid(padding=(0, 1))
        grid.add_column(style="cyan", no_wrap=True)
        grid.add_column(style="white")
        grid.add_row("request_id", config.request_id)
        grid.add_row("workspace", str(config.workspace.resolve()))
        grid.add_row("intensity", ResearchIntensity(config.research_intensity).value)
        grid.add_row("live_tools", "enabled" if config.live_extension_mode else "disabled")
        rich_console.print(
            Panel(
                grid,
                title="[bold]MissionForge DeepResearch[/bold]",
                subtitle="FrontDesk requirements discovery",
                border_style="cyan",
            )
        )
        rich_console.print(
            "[bold cyan]命令：[/bold cyan]"
            "[green]/show[/green] 查看需求  "
            "[green]/status[/green] 项目推进  "
            "[green]/approve[/green] 批准并启动  "
            "[green]/quit[/green] 退出  "
            "[green]/help[/green] 命令帮助"
        )
        rich_console.print()
        return
    _box(
        output_stream,
        "MissionForge DeepResearch",
        [
            "FrontDesk 会把模糊想法压榨成可审批的调研需求文档。",
            f"request_id: {config.request_id}",
            f"workspace: {config.workspace.resolve()}",
            f"intensity: {ResearchIntensity(config.research_intensity).value}",
            f"live_tools: {'enabled' if config.live_extension_mode else 'disabled'}",
        ],
    )
    _command_bar(output_stream)


def _print_help(output_stream: TextIO) -> None:
    rich_console = _rich_console(output_stream)
    if rich_console is not None:
        table = Table(title="可用命令", box=None, show_header=True, header_style="bold cyan")
        table.add_column("命令", style="green", no_wrap=True)
        table.add_column("说明")
        for command, description in [
            ("/show", "查看当前 research_requirements.md"),
            ("/status", "查看项目推进看板、FrontDesk 状态和待回答问题"),
            ("/approve", "批准需求文档并启动 DeepResearch"),
            ("/quit", "退出会话"),
        ]:
            table.add_row(command, description)
        rich_console.print(table)
        return
    _section(output_stream, "可用命令")
    for command, description in [
        ("/show", "查看当前 research_requirements.md"),
        ("/status", "查看 FrontDesk 当前状态和待回答问题"),
        ("/approve", "批准需求文档并启动 DeepResearch"),
        ("/quit", "退出会话"),
    ]:
        output_stream.write(f"  {command:<10} {description}\n")
    output_stream.write("\n")


def _print_frontdesk_result(output_stream: TextIO, config: FrontDeskTuiConfig, status: str) -> None:
    _status_line(output_stream, "FrontDesk", status)
    _print_assistant_message(output_stream, config)
    _print_questions(output_stream, config)
    if status == "ready_for_approval":
        _print_ready(output_stream, config)
    else:
        _hint(output_stream, "直接回答上面的问题；输入 /show 可查看当前需求快照。")


def _print_ready(output_stream: TextIO, config: FrontDeskTuiConfig) -> None:
    requirements_path = _run_root(config) / FRONTDESK_REQUIREMENTS_REF
    _section(output_stream, "需求文档已可审批")
    output_stream.write(f"  requirements: {requirements_path}\n")
    _hint(output_stream, "输入 /approve 启动正式 DeepResearch；继续输入自然语言可修改需求。")


def _print_questions(output_stream: TextIO, config: FrontDeskTuiConfig) -> None:
    assistant_turn = _read_assistant_turn(config)
    questions = assistant_turn.get("questions") if isinstance(assistant_turn, dict) else None
    if not isinstance(questions, list) or not questions:
        return
    rich_console = _rich_console(output_stream)
    if rich_console is not None:
        table = Table(title="FrontDesk 需要你补充", box=None, show_header=False)
        table.add_column("index", style="cyan", no_wrap=True)
        table.add_column("question", overflow="fold")
        for index, question in enumerate(questions, start=1):
            table.add_row(str(index), _question_text(question))
        rich_console.print(table)
        rich_console.print()
        return
    _section(output_stream, "FrontDesk 需要你补充")
    for index, question in enumerate(questions, start=1):
        output_stream.write(f"  {index}. {_question_text(question)}\n")
    output_stream.write("\n")


def _print_assistant_message(output_stream: TextIO, config: FrontDeskTuiConfig) -> None:
    assistant_turn = _read_assistant_turn(config)
    message = assistant_turn.get("message") if isinstance(assistant_turn, dict) else ""
    if not isinstance(message, str) or not message.strip():
        return
    current_hypothesis = _string_value(assistant_turn, "current_hypothesis")
    user_unlock = _string_value(assistant_turn, "user_unlock")
    rich_console = _rich_console(output_stream)
    if rich_console is not None:
        body = Table.grid(padding=(0, 1))
        body.add_column(style="bold cyan", no_wrap=True)
        body.add_column()
        body.add_row("回复", message.strip())
        if current_hypothesis:
            body.add_row("当前假设", current_hypothesis)
        if user_unlock:
            body.add_row("你下一步会决定", user_unlock)
        rich_console.print(Panel(body, title="FrontDesk", border_style="cyan"))
        return
    _section(output_stream, "FrontDesk")
    output_stream.write(message.strip() + "\n")
    if current_hypothesis:
        output_stream.write(f"  当前假设: {current_hypothesis}\n")
    if user_unlock:
        output_stream.write(f"  你下一步会决定: {user_unlock}\n")


def _print_requirements(output_stream: TextIO, config: FrontDeskTuiConfig) -> None:
    try:
        text = read_text_ref(_run_root(config), FRONTDESK_REQUIREMENTS_REF)
    except mf.ContractValidationError as exc:
        _error(output_stream, f"无法读取需求文档：{exc}")
        return
    rich_console = _rich_console(output_stream)
    if rich_console is not None and Markdown is not None and Panel is not None:
        rich_console.print(
            Panel(
                Markdown(text.rstrip() or "_empty_"),
                title="research_requirements.md",
                border_style="blue",
            )
        )
        return
    _section(output_stream, "research_requirements.md")
    output_stream.write(text.rstrip() + "\n")
    _rule(output_stream)


def _print_status(output_stream: TextIO, config: FrontDeskTuiConfig) -> None:
    _status_line(output_stream, "FrontDesk", _read_existing_status(config) or "not_started")
    _print_assistant_message(output_stream, config)
    _print_questions(output_stream, config)
    _print_project_board(output_stream, config)


def _print_resume_status(output_stream: TextIO, config: FrontDeskTuiConfig) -> None:
    run_root = _run_root(config)
    lifecycle = _read_optional_json(run_root, PROJECT_LIFECYCLE_STATE_REF)
    diagnostics = _read_optional_json(run_root, PROJECT_RESUME_DIAGNOSTICS_REF)
    if not lifecycle and not diagnostics:
        return
    phase = _first_non_empty(_string_value(lifecycle, "phase"), "frontdesk")
    active_agent = _first_non_empty(_string_value(lifecycle, "active_agent"), "frontdesk")
    resume_status = _first_non_empty(_string_value(diagnostics, "status"), "missing_context")
    rich_console = _rich_console(output_stream)
    if rich_console is not None:
        body = Table.grid(padding=(0, 1))
        body.add_column(style="bold cyan", no_wrap=True)
        body.add_column()
        body.add_row("阶段", phase)
        body.add_row("当前 agent", active_agent)
        body.add_row("resume", f"[{_status_style(resume_status)}]{resume_status}[/]")
        rich_console.print(Panel(body, title="项目恢复状态", border_style=_phase_border_style(resume_status)))
        return
    _section(output_stream, "项目恢复状态")
    output_stream.write(f"  阶段: {phase}\n")
    output_stream.write(f"  当前 agent: {active_agent}\n")
    output_stream.write(f"  resume: {resume_status}\n")


def _run_approved_research(
    *,
    config: FrontDeskTuiConfig,
    kernel_adapter_factory: Callable[[ResearchIntensity | str], mf.PiWorkerCallAdapter],
    input_stream: TextIO,
    output_stream: TextIO,
    progress_runner: Callable[[Any], DeepResearchKernelV2Result] | None = None,
) -> int:
    try:
        request = approve_frontdesk_requirements(
            request_id=config.request_id,
            workspace=config.workspace,
        )
    except mf.ContractValidationError as exc:
        _error(output_stream, f"审批失败：{exc}")
        return 1
    _section(output_stream, "已批准需求文档")
    output_stream.write("  正在启动正式 DeepResearch...\n")
    adapter = kernel_adapter_factory(request.research_intensity)
    listener = _ResearchInputListener(
        config=config,
        input_stream=input_stream,
        output_stream=output_stream,
    )
    listener.start()
    try:
        result = (
            progress_runner(request)
            if progress_runner is not None
            else run_deepresearch_kernel_v2(
                request,
                workspace=config.workspace,
                adapter=adapter,
                live_extension_mode=config.live_extension_mode,
                event_sink=_tui_kernel_event_sink(output_stream) if config.stream_progress else None,
                runtime_progress_sink=_tui_runtime_progress_sink(output_stream, "research")
                if config.stream_progress
                else None,
            )
        )
    finally:
        listener.stop()
    _print_research_result(output_stream, config, result)
    return 0 if result.status == "accepted" else 1


def _print_research_result(output_stream: TextIO, config: FrontDeskTuiConfig, result: DeepResearchKernelV2Result) -> None:
    _status_line(output_stream, "DeepResearch", result.status)
    _print_project_board(output_stream, config)
    _section(output_stream, "输出文件")
    rich_console = _rich_console(output_stream)
    if rich_console is not None:
        table = Table(box=None, show_header=True, header_style="bold cyan")
        table.add_column("artifact", style="green", no_wrap=True)
        table.add_column("path", overflow="fold")
        for label, ref in [
            ("final_report", result.final_report_ref),
            ("citation_projected_report", result.citation_projected_report_ref),
            ("report_html", result.report_html_ref),
            ("seed_papers", result.seed_papers_ref),
            ("seed_pdf_index", result.seed_pdf_index_ref),
            ("seed_source_packet", result.seed_source_packet_ref),
            ("seed_gaps", result.seed_gaps_ref),
            ("seed_control", result.seed_control_ref),
            ("search_plan", result.search_plan_ref),
            ("provider_hits", result.provider_hits_ref),
            ("source_packet", result.source_packet_ref),
            ("source_graph", result.source_graph_ref),
            ("coverage_report", result.coverage_report_ref),
            ("citation_registry", result.citation_registry_ref),
            ("claim_support_review", result.claim_support_review_ref),
            ("acceptance_gate", result.acceptance_gate_ref),
            ("result_package", result.result_ref),
            ("judge_report", result.judge_report_ref),
            ("revision_request", result.revision_request_ref),
            ("usage_summary", result.usage_summary_ref),
        ]:
            path = config.workspace / ref
            if path.exists():
                table.add_row(label, str(path))
        rich_console.print(table)
        rich_console.print()
        return
    for label, ref in [
        ("final_report", result.final_report_ref),
        ("citation_projected_report", result.citation_projected_report_ref),
        ("report_html", result.report_html_ref),
        ("seed_papers", result.seed_papers_ref),
        ("seed_pdf_index", result.seed_pdf_index_ref),
        ("seed_source_packet", result.seed_source_packet_ref),
        ("seed_gaps", result.seed_gaps_ref),
        ("seed_control", result.seed_control_ref),
        ("search_plan", result.search_plan_ref),
        ("provider_hits", result.provider_hits_ref),
        ("source_packet", result.source_packet_ref),
        ("source_graph", result.source_graph_ref),
        ("coverage_report", result.coverage_report_ref),
        ("citation_registry", result.citation_registry_ref),
        ("claim_support_review", result.claim_support_review_ref),
        ("acceptance_gate", result.acceptance_gate_ref),
        ("result_package", result.result_ref),
        ("judge_report", result.judge_report_ref),
        ("revision_request", result.revision_request_ref),
        ("usage_summary", result.usage_summary_ref),
    ]:
        path = config.workspace / ref
        if path.exists():
            output_stream.write(f"  {label}: {path}\n")
    output_stream.write("\n")


def _tui_runtime_progress_sink(output_stream: TextIO, label: str):
    def emit(event: dict[str, Any]) -> None:
        message = str(event.get("message") or "").strip()
        detail = str(event.get("detail") or "").strip()
        if not message and not detail:
            return
        rich_console = _rich_console(output_stream)
        if rich_console is not None:
            rich_console.print(f"  [dim][{label}][/dim] {message}")
            if detail:
                rich_console.print(f"    [dim]{detail}[/dim]")
            return
        output_stream.write(f"  [{label}] {message}\n")
        if detail:
            output_stream.write(f"    {detail}\n")
        output_stream.flush()

    return emit


def _tui_kernel_event_sink(output_stream: TextIO):
    def emit(event: mf.FlowLedgerEvent) -> None:
        rich_console = _rich_console(output_stream)
        if event.kind == mf.FlowLedgerEventKind.STEP_STARTED:
            text = f"  [kernel] {event.step_id} started"
        elif event.kind == mf.FlowLedgerEventKind.STEP_RECORDED:
            text = f"  [kernel] {event.step_id} status={event.status}"
        elif event.kind == mf.FlowLedgerEventKind.ROUTED:
            text = f"  [kernel] {event.step_id} -> {event.route_target} ({event.route_value})"
        elif event.kind == mf.FlowLedgerEventKind.INTERACTION_RECORDED:
            count = event.metadata.get("event_count") if isinstance(event.metadata, dict) else None
            text = f"  [kernel] interaction safe point for {event.step_id or 'flow'}"
            if isinstance(count, int):
                text += f" events={count}"
        elif event.kind == mf.FlowLedgerEventKind.STOPPED:
            text = f"  [kernel] stopped status={event.status}"
        else:
            return
        if rich_console is not None:
            rich_console.print(f"[dim]{text}[/dim]")
            return
        output_stream.write(text + "\n")
        output_stream.flush()

    return emit


class _ResearchInputListener:
    """Collect user interventions while a DeepResearch run is active."""

    def __init__(self, *, config: FrontDeskTuiConfig, input_stream: TextIO, output_stream: TextIO) -> None:
        self.config = config
        self.input_stream = input_stream
        self.output_stream = output_stream
        self.run_id = deepresearch_kernel_v2_flow_run_id(config.request_id)
        self.control_port = mf.FileControlPort(mf.FileInteractionPort(_run_root(config)))
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, name=f"deepresearch-interaction-{self.config.request_id}", daemon=True)
        self._thread.start()
        _hint(
            self.output_stream,
            "研究运行中可以直接输入补充；/revise <内容>、/pause、/cancel、/resume、/checkpoint、/stop 会在下一安全点生效，不会打断当前 PiWorker 调用；/status 查看项目推进，/help 查看命令。",
        )

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=0.2)

    def _run(self) -> None:
        while not self._stop.is_set():
            raw = _read_user_line("", input_stream=self.input_stream, output_stream=self.output_stream)
            if raw is None:
                return
            message = raw.strip()
            if not message:
                continue
            if message.lower() in {"/quit", "/exit"}:
                self._record_event(
                    self.control_port.inject_message(
                        run_id=self.run_id,
                        text="用户请求退出交互界面；正式研究可在安全点继续或由外部终止。",
                    )
                )
                return
            if message.lower() == "/pause":
                self._record_event(self.control_port.pause(run_id=self.run_id))
                continue
            if message.lower() == "/cancel":
                self._record_event(self.control_port.cancel(run_id=self.run_id))
                continue
            if message.startswith("/revise "):
                revision = message.removeprefix("/revise ").strip()
                if revision:
                    self._record_event(self.control_port.request_revision(run_id=self.run_id, text=revision))
                continue
            if message.lower() == "/resume":
                self._record_event(self.control_port.resume(run_id=self.run_id))
                continue
            if message.lower() in {"/checkpoint", "/force-checkpoint"}:
                self._record_event(self.control_port.force_checkpoint(run_id=self.run_id))
                continue
            if message.lower() in {"/stop", "/stop-turn"}:
                self._record_event(self.control_port.stop_after_current_turn(run_id=self.run_id))
                continue
            if message.lower() in {"/help", "帮助"}:
                _print_runtime_help(self.output_stream)
                continue
            if message.lower() in {"/status", "状态"}:
                _print_project_board(self.output_stream, self.config)
                continue
            self._record_event(self.control_port.inject_message(run_id=self.run_id, text=message))

    def _record_event(self, event: mf.UserEvent) -> None:
        rich_console = _rich_console(self.output_stream)
        if rich_console is not None:
            rich_console.print(f"[dim]已记录用户插入：{event.kind.value} -> {event.event_id}[/dim]")
        else:
            self.output_stream.write(f"  [interaction] 已记录用户插入：{event.kind.value} -> {event.event_id}\n")
            self.output_stream.flush()


def _read_user_line(prompt: str, *, input_stream: TextIO, output_stream: TextIO) -> str | None:
    """Read one user-edited line, using readline for real terminals.

    `TextIO.readline()` keeps tests and scripted pipes simple, but on some
    terminals it leaves UTF-8 editing to the kernel line discipline. Python's
    `input()` path uses GNU readline when available, so Backspace operates on
    Chinese characters instead of bytes.
    """

    if _is_interactive_stdio(input_stream, output_stream):
        try:
            return input(prompt)
        except EOFError:
            return None
    output_stream.write(prompt)
    output_stream.flush()
    raw = input_stream.readline()
    if raw == "":
        return None
    return raw


def _is_interactive_stdio(input_stream: TextIO, output_stream: TextIO) -> bool:
    return input_stream is sys.stdin and output_stream is sys.stdout and _stream_isatty(input_stream)


def _stream_isatty(stream: TextIO) -> bool:
    isatty = getattr(stream, "isatty", None)
    return bool(isatty()) if callable(isatty) else False


def _print_runtime_help(output_stream: TextIO) -> None:
    rich_console = _rich_console(output_stream)
    if rich_console is not None:
        table = Table(title="研究运行中可用命令", box=None, show_header=True, header_style="bold cyan")
        table.add_column("命令", style="green", no_wrap=True)
        table.add_column("说明")
        for command, description in [
            ("/status", "查看项目推进看板"),
            ("/help", "查看这份帮助"),
            ("/pause", "在下一安全点暂停"),
            ("/cancel", "在下一安全点取消"),
            ("/resume", "记录恢复请求"),
            ("/checkpoint", "请求创建检查点"),
            ("/stop", "在当前回合结束后停止"),
            ("/revise <内容>", "请求修订合同"),
            ("自然语言", "作为补充意见写入下一安全点"),
        ]:
            table.add_row(command, description)
        rich_console.print(table)
        return
    _section(output_stream, "研究运行中可用命令")
    for command, description in [
        ("/status", "查看项目推进看板"),
        ("/help", "查看这份帮助"),
        ("/pause", "在下一安全点暂停"),
        ("/cancel", "在下一安全点取消"),
        ("/resume", "记录恢复请求"),
        ("/checkpoint", "请求创建检查点"),
        ("/stop", "在当前回合结束后停止"),
        ("/revise <内容>", "请求修订合同"),
        ("自然语言", "作为补充意见写入下一安全点"),
    ]:
        output_stream.write(f"  {command:<16} {description}\n")
    output_stream.write("\n")


def _print_project_board(output_stream: TextIO, config: FrontDeskTuiConfig) -> None:
    run_root = _run_root(config)
    if not _project_has_any_state(run_root):
        _hint(output_stream, "正式研究状态尚未写入；启动或等待下一个研究阶段后再查看项目推进。")
        return
    state = _read_project_json(run_root, "research_state")
    researcher_control = _read_project_json(run_root, "researcher_control")
    reviewer_observation = _read_project_json(run_root, "reviewer_observation")
    judge_report = _read_project_json(run_root, "judge_report")
    run_status = _read_project_json(run_root, "run_status")
    source_packet = _read_project_json(run_root, "source_packet")
    claim_index = _read_project_json(run_root, "claim_index")
    usage_summary = _read_project_json(run_root, "usage_summary")
    kernel_view = _kernel_run_view(run_root, run_status)

    phase = _first_non_empty(
        _string_value(state, "project_phase"),
        _string_value(run_status, "status"),
        _project_phase_from_decisions(researcher_control, reviewer_observation, judge_report),
        "running",
    )
    latest = _first_non_empty(
        _string_value(state, "latest_project_update"),
        _string_value(state, "current_synthesis"),
        _decision_summary(researcher_control, reviewer_observation, judge_report),
    )
    source_count = _source_count(source_packet, state)
    claim_count = _claim_count(claim_index)
    usage = _usage_totals(usage_summary)
    interaction_line = _interaction_status_line(run_status)
    rich_console = _rich_console(output_stream)
    if rich_console is not None:
        _print_rich_project_board(
            rich_console,
            phase=phase,
            latest=latest,
            source_count=source_count,
            claim_count=claim_count,
            usage=usage,
            interaction_line=interaction_line,
            kernel_view=kernel_view,
            state=state,
            researcher_control=researcher_control,
            reviewer_observation=reviewer_observation,
            judge_report=judge_report,
        )
        return

    _section(output_stream, "项目推进看板")
    output_stream.write(f"  阶段: {phase}\n")
    if latest:
        output_stream.write(f"  当前结论: {_one_line(latest, 110)}\n")
    if source_count or claim_count:
        output_stream.write(f"  证据规模: sources={source_count}, claims={claim_count}\n")
    if usage:
        output_stream.write(
            "  Token: "
            f"input={usage.get('input_tokens', 0)}, "
            f"cached={usage.get('cached_input_tokens', 0)}, "
            f"output={usage.get('output_tokens', 0)}, "
            f"total={usage.get('total_tokens', 0)}\n"
        )
    if interaction_line:
        output_stream.write(f"  交互: {interaction_line}\n")
    _print_kernel_view(output_stream, kernel_view)

    _print_milestones(output_stream, state)
    _print_coverage_map(output_stream, state)
    _print_feedback(output_stream, "Reviewer", reviewer_observation)
    _print_feedback(output_stream, "Judge", judge_report)
    _print_next_actions(output_stream, state, researcher_control, reviewer_observation, judge_report)


def _project_has_any_state(run_root: Path) -> bool:
    return any((run_root / ref).is_file() for ref in PROJECT_PROGRESS_REFS.values())


def _print_rich_project_board(
    rich_console: Any,
    *,
    phase: str,
    latest: str,
    source_count: int,
    claim_count: int,
    usage: dict[str, Any],
    interaction_line: str,
    kernel_view: mf.MissionRunView | None,
    state: dict[str, Any],
    researcher_control: dict[str, Any],
    reviewer_observation: dict[str, Any],
    judge_report: dict[str, Any],
) -> None:
    overview = Table.grid(padding=(0, 1))
    overview.add_column(style="bold cyan", no_wrap=True)
    overview.add_column()
    overview.add_row("阶段", phase)
    if latest:
        overview.add_row("当前结论", _one_line(latest, 120))
    overview.add_row("证据规模", f"sources={source_count}, claims={claim_count}")
    if usage:
        overview.add_row(
            "Token",
            "input={input_tokens}, cached={cached_input_tokens}, output={output_tokens}, total={total_tokens}".format(
                input_tokens=usage.get("input_tokens", 0),
                cached_input_tokens=usage.get("cached_input_tokens", 0),
                output_tokens=usage.get("output_tokens", 0),
                total_tokens=usage.get("total_tokens", 0),
            ),
        )
    if interaction_line:
        overview.add_row("交互", interaction_line)
    for label, value in _kernel_observer_rows(kernel_view):
        overview.add_row(label, value)
    rich_console.print(Panel(overview, title="项目推进看板", border_style=_phase_border_style(phase)))
    _print_rich_kernel_view(rich_console, kernel_view)
    _print_rich_milestones(rich_console, state)
    _print_rich_coverage_map(rich_console, state)
    _print_rich_feedback(rich_console, "Reviewer", reviewer_observation)
    _print_rich_feedback(rich_console, "Judge", judge_report)
    _print_rich_next_actions(rich_console, state, researcher_control, reviewer_observation, judge_report)


def _print_rich_milestones(rich_console: Any, state: dict[str, Any]) -> None:
    milestones = state.get("project_milestones")
    if not isinstance(milestones, list) or not milestones:
        return
    table = Table(title="里程碑", show_header=True, header_style="bold cyan")
    table.add_column("", width=3, no_wrap=True)
    table.add_column("事项", style="white")
    table.add_column("状态", no_wrap=True)
    table.add_column("说明", overflow="fold")
    for item in milestones[:8]:
        if not isinstance(item, dict):
            continue
        title = _first_non_empty(_string_value(item, "title"), _string_value(item, "id"), "untitled")
        status = _first_non_empty(_string_value(item, "status"), "unknown")
        notes = _one_line(_string_value(item, "notes"), 120)
        table.add_row(_status_mark(status), title, f"[{_status_style(status)}]{status}[/]", notes)
    rich_console.print(table)


def _print_rich_coverage_map(rich_console: Any, state: dict[str, Any]) -> None:
    coverage = state.get("coverage_map")
    if not isinstance(coverage, list) or not coverage:
        return
    table = Table(title="覆盖面", show_header=True, header_style="bold cyan")
    table.add_column("", width=3, no_wrap=True)
    table.add_column("维度", style="white")
    table.add_column("状态", no_wrap=True)
    table.add_column("置信度", no_wrap=True)
    table.add_column("缺口", overflow="fold")
    for item in coverage[:8]:
        if not isinstance(item, dict):
            continue
        dimension = _first_non_empty(_string_value(item, "dimension"), _string_value(item, "topic"), "unknown")
        status = _first_non_empty(_string_value(item, "status"), "unknown")
        confidence = _string_value(item, "confidence")
        gaps = _text_list(item.get("gaps"))
        gap_text = _one_line("; ".join(gaps[:2]), 120) if gaps else ""
        table.add_row(_status_mark(status), dimension, f"[{_status_style(status)}]{status}[/]", confidence, gap_text)
    rich_console.print(table)


def _print_rich_feedback(rich_console: Any, label: str, payload: dict[str, Any]) -> None:
    if not payload:
        return
    decision = _string_value(payload, "decision")
    summary = _first_non_empty(
        _string_value(payload, "summary"),
        _string_value(payload, "rationale"),
        _string_value(payload, "confidence_note"),
    )
    if not decision and not summary:
        return
    body = Table.grid(padding=(0, 1))
    body.add_column(style="bold cyan", no_wrap=True)
    body.add_column()
    if decision:
        body.add_row("decision", f"[{_status_style(decision)}]{decision}[/]")
    if summary:
        body.add_row("summary", _one_line(summary, 120))
    rich_console.print(Panel(body, title=label, border_style=_phase_border_style(decision)))


def _kernel_run_view(run_root: Path, run_status: dict[str, Any]) -> mf.MissionRunView | None:
    flow_result_ref = _string_value(run_status, "flow_result_ref")
    if not flow_result_ref:
        return None
    try:
        return mf.build_mission_run_view(run_root, flow_result_ref=flow_result_ref)
    except (mf.ContractValidationError, OSError, json.JSONDecodeError):
        return None


def _print_kernel_view(output_stream: TextIO, view: mf.MissionRunView | None) -> None:
    if view is None:
        return
    current = view.current_step_id or "<none>"
    latest = view.latest_event_kind or "<none>"
    latest_status = view.latest_event_status or "<none>"
    safe_point = view.last_safe_point_ref or "<none>"
    output_stream.write("  Kernel 状态:\n")
    output_stream.write(
        f"    status={view.status}, snapshot={view.snapshot_status or '<none>'}, "
        f"current={current}, latest={latest}:{latest_status}\n"
    )
    output_stream.write(
        f"    steps={len(view.step_record_refs)}, events={view.run_event_count}, "
        f"pending_user_events={view.pending_user_event_count}, safe_point={safe_point}\n"
    )
    output_stream.write(f"    flow_result={view.flow_result_ref}\n")
    for label, value in _kernel_observer_rows(view):
        output_stream.write(f"    {label}: {value}\n")
    for ref in view.observation_refs[:2]:
        output_stream.write(f"    observation={ref}\n")


def _print_rich_kernel_view(rich_console: Any, view: mf.MissionRunView | None) -> None:
    if view is None:
        return
    body = Table.grid(padding=(0, 1))
    body.add_column(style="bold cyan", no_wrap=True)
    body.add_column()
    body.add_row("status", f"[{_status_style(view.status)}]{view.status}[/]")
    body.add_row("snapshot", view.snapshot_status or "<none>")
    body.add_row("current", _first_non_empty(view.current_step_id, "<none>"))
    latest = view.latest_event_kind or "<none>"
    if view.latest_event_status:
        latest += f" status={view.latest_event_status}"
    body.add_row("latest", latest)
    body.add_row("steps/events", f"steps={len(view.step_record_refs)}, events={view.run_event_count}")
    if view.pending_user_event_count:
        body.add_row("pending_user_events", str(view.pending_user_event_count))
    if view.last_safe_point_ref:
        body.add_row("safe_point", view.last_safe_point_ref)
    body.add_row("flow_result", view.flow_result_ref)
    for label, value in _kernel_observer_rows(view):
        body.add_row(label, value)
    if view.observation_refs:
        body.add_row("observations", ", ".join(view.observation_refs[:2]))
    rich_console.print(Panel(body, title="Kernel 状态", border_style=_phase_border_style(view.status)))


def _print_rich_next_actions(
    rich_console: Any,
    state: dict[str, Any],
    researcher_control: dict[str, Any],
    reviewer_observation: dict[str, Any],
    judge_report: dict[str, Any],
) -> None:
    actions = _text_list(state.get("next_actions"))
    if not actions:
        actions = _text_list(researcher_control.get("next_actions"))
    if not actions:
        actions = _text_list(reviewer_observation.get("required_changes"))
    if not actions:
        actions = _text_list(judge_report.get("required_repairs"))
    if not actions:
        return
    table = Table(title="下一步", box=None, show_header=False)
    table.add_column("action", overflow="fold")
    for action in actions[:5]:
        table.add_row(_one_line(action, 130))
    rich_console.print(table)


def _read_project_json(run_root: Path, key: str) -> dict[str, Any]:
    ref = PROJECT_PROGRESS_REFS[key]
    try:
        payload = read_json_ref(run_root, ref, key)
    except (mf.ContractValidationError, OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _read_optional_json(run_root: Path, ref: str) -> dict[str, Any]:
    try:
        payload = read_json_ref(run_root, ref, ref)
    except (mf.ContractValidationError, OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _print_milestones(output_stream: TextIO, state: dict[str, Any]) -> None:
    milestones = state.get("project_milestones")
    if not isinstance(milestones, list) or not milestones:
        return
    output_stream.write("  里程碑:\n")
    for item in milestones[:8]:
        if not isinstance(item, dict):
            continue
        title = _first_non_empty(_string_value(item, "title"), _string_value(item, "id"), "untitled")
        status = _first_non_empty(_string_value(item, "status"), "unknown")
        notes = _one_line(_string_value(item, "notes"), 90)
        suffix = f" - {notes}" if notes else ""
        output_stream.write(f"    [{_status_mark(status)}] {title} ({status}){suffix}\n")


def _print_coverage_map(output_stream: TextIO, state: dict[str, Any]) -> None:
    coverage = state.get("coverage_map")
    if not isinstance(coverage, list) or not coverage:
        return
    output_stream.write("  覆盖面:\n")
    for item in coverage[:8]:
        if not isinstance(item, dict):
            continue
        dimension = _first_non_empty(_string_value(item, "dimension"), _string_value(item, "topic"), "unknown")
        status = _first_non_empty(_string_value(item, "status"), "unknown")
        confidence = _string_value(item, "confidence")
        gaps = _text_list(item.get("gaps"))
        detail_parts = []
        if confidence:
            detail_parts.append(f"confidence={confidence}")
        if gaps:
            detail_parts.append("gap=" + _one_line("; ".join(gaps[:2]), 80))
        detail = f" - {'; '.join(detail_parts)}" if detail_parts else ""
        output_stream.write(f"    [{_status_mark(status)}] {dimension}: {status}{detail}\n")


def _print_feedback(output_stream: TextIO, label: str, payload: dict[str, Any]) -> None:
    if not payload:
        return
    decision = _string_value(payload, "decision")
    summary = _first_non_empty(
        _string_value(payload, "summary"),
        _string_value(payload, "rationale"),
        _string_value(payload, "confidence_note"),
    )
    if not decision and not summary:
        return
    output_stream.write(f"  {label}:")
    if decision:
        output_stream.write(f" decision={decision}")
    if summary:
        output_stream.write(f" - {_one_line(summary, 100)}")
    output_stream.write("\n")


def _print_next_actions(
    output_stream: TextIO,
    state: dict[str, Any],
    researcher_control: dict[str, Any],
    reviewer_observation: dict[str, Any],
    judge_report: dict[str, Any],
) -> None:
    actions = _text_list(state.get("next_actions"))
    if not actions:
        actions = _text_list(researcher_control.get("next_actions"))
    if not actions:
        actions = _text_list(reviewer_observation.get("required_changes"))
    if not actions:
        actions = _text_list(judge_report.get("required_repairs"))
    if not actions:
        return
    output_stream.write("  下一步:\n")
    for action in actions[:5]:
        output_stream.write(f"    - {_one_line(action, 105)}\n")


def _project_phase_from_decisions(
    researcher_control: dict[str, Any],
    reviewer_observation: dict[str, Any],
    judge_report: dict[str, Any],
) -> str:
    judge_decision = _string_value(judge_report, "decision")
    if judge_decision:
        return f"judge:{judge_decision}"
    reviewer_decision = _string_value(reviewer_observation, "decision")
    if reviewer_decision:
        return f"review:{reviewer_decision}"
    researcher_decision = _string_value(researcher_control, "decision")
    if researcher_decision:
        return f"research:{researcher_decision}"
    return ""


def _decision_summary(
    researcher_control: dict[str, Any],
    reviewer_observation: dict[str, Any],
    judge_report: dict[str, Any],
) -> str:
    for payload in (judge_report, reviewer_observation, researcher_control):
        summary = _first_non_empty(
            _string_value(payload, "summary"),
            _string_value(payload, "rationale"),
            _string_value(payload, "status_summary"),
        )
        if summary:
            return summary
    return ""


def _source_count(source_packet: dict[str, Any], state: dict[str, Any]) -> int:
    records = source_packet.get("source_records")
    if isinstance(records, list):
        return len(records)
    value = state.get("source_count")
    return value if isinstance(value, int) and value >= 0 else 0


def _claim_count(claim_index: dict[str, Any]) -> int:
    claims = claim_index.get("claims")
    return len(claims) if isinstance(claims, list) else 0


def _usage_totals(usage_summary: dict[str, Any]) -> dict[str, Any]:
    totals = usage_summary.get("totals")
    return totals if isinstance(totals, dict) else {}


def _kernel_observer_rows(view: mf.MissionRunView | None) -> list[tuple[str, str]]:
    if view is None:
        return []
    rows: list[tuple[str, str]] = []
    usage = _optional_dict(view, "usage_totals")
    if usage:
        parts = []
        for key in ("input_tokens", "cached_input_tokens", "output_tokens", "total_tokens"):
            value = usage.get(key)
            if isinstance(value, int):
                parts.append(f"{key}={value}")
        if parts:
            rows.append(("usage_totals", ", ".join(parts)))
    context_pressure = _optional_context_pressure(view)
    if context_pressure:
        rows.append(("context_pressure", context_pressure))
    latest_event_age = _optional_event_age(view)
    if latest_event_age:
        rows.append(("latest_event_age", latest_event_age))
    tool_activity_refs = _optional_ref_list(view, "tool_activity_refs", "tool_activity_ref", "tool_refs")
    if tool_activity_refs:
        rows.append(("tool_activity_refs", ", ".join(tool_activity_refs[:3])))
    safe_point_details = _optional_safe_point_details(view)
    if safe_point_details:
        rows.append(("safe_point_details", safe_point_details))
    return rows


def _interaction_status_line(run_status: dict[str, Any]) -> str:
    reason = _string_value(run_status, "interaction_stop_reason")
    count = run_status.get("pending_user_event_count")
    snapshot_ref = _string_value(run_status, "last_interaction_snapshot_ref")
    parts = []
    if reason:
        parts.append(f"stop_reason={reason}")
    if isinstance(count, int) and count > 0:
        parts.append(f"safe_point_events={count}")
    if snapshot_ref:
        parts.append(f"snapshot={snapshot_ref}")
    return ", ".join(parts)


def _status_mark(status: str) -> str:
    normalized = status.lower()
    if normalized in {"done", "completed", "accepted", "covered", "ready_for_judge", "ready_for_review"}:
        return "*"
    if normalized in {"active", "running", "continue", "revise_report", "repair"}:
        return ">"
    if normalized in {"blocked", "failed", "rejected"}:
        return "!"
    if normalized in {"deferred", "partial", "weak", "gap"}:
        return "~"
    return " "


def _status_style(status: str) -> str:
    normalized = status.lower()
    if normalized in {"done", "completed", "accepted", "covered", "ready_for_judge", "ready_for_review"}:
        return "green"
    if normalized in {"active", "running", "continue", "revise_report", "repair"}:
        return "yellow"
    if normalized in {"blocked", "failed", "rejected"}:
        return "red"
    if normalized in {"deferred", "partial", "weak", "gap"}:
        return "magenta"
    return "white"


def _phase_border_style(phase: str) -> str:
    normalized = phase.lower()
    if "accepted" in normalized or "done" in normalized or "ready" in normalized:
        return "green"
    if "blocked" in normalized or "failed" in normalized or "rejected" in normalized:
        return "red"
    if "review" in normalized or "judge" in normalized:
        return "magenta"
    return "cyan"


def _rich_console(output_stream: TextIO) -> Any | None:
    if Console is None:
        return None
    return Console(file=output_stream, force_terminal=_force_rich_terminal(output_stream), width=TUI_WIDTH)


def _force_rich_terminal(output_stream: TextIO) -> bool | None:
    if output_stream is sys.stdout:
        return None
    return False


def _optional_dict(view: mf.MissionRunView, attr_name: str) -> dict[str, Any]:
    value = getattr(view, attr_name, None)
    return value if isinstance(value, dict) else {}


def _optional_context_pressure(view: mf.MissionRunView) -> str:
    value = getattr(view, "context_pressure", None)
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str) and value.strip():
        return value.strip()
    if isinstance(value, dict):
        parts = []
        percent = _first_non_empty(
            _string_value(value, "percent"),
            _string_value(value, "ratio"),
            _string_value(value, "pressure"),
        )
        if percent:
            parts.append(percent)
        for key in ("used_tokens", "limit_tokens", "available_tokens", "remaining_tokens"):
            if key in value and isinstance(value.get(key), int):
                parts.append(f"{key}={value[key]}")
        return ", ".join(parts)
    return ""


def _optional_event_age(view: mf.MissionRunView) -> str:
    for attr_name in ("latest_event_age_seconds", "latest_event_age_s", "latest_event_age"):
        value = getattr(view, attr_name, None)
        if isinstance(value, (int, float)) and value > 0:
            return f"{value:g}s"
        if isinstance(value, str) and value.strip():
            return value.strip()
    value = getattr(view, "latest_event_age", None)
    if isinstance(value, dict):
        seconds = value.get("seconds")
        if isinstance(seconds, (int, float)):
            return f"{seconds:g}s"
        age_ref = _string_value(value, "ref")
        if age_ref:
            return age_ref
    return ""


def _optional_ref_list(view: mf.MissionRunView, *attr_names: str) -> list[str]:
    for attr_name in attr_names:
        value = getattr(view, attr_name, None)
        if isinstance(value, list):
            refs = [str(item).strip() for item in value if str(item).strip()]
            if refs:
                return refs
        if isinstance(value, str) and value.strip():
            return [value.strip()]
    return []


def _optional_safe_point_details(view: mf.MissionRunView) -> str:
    details_ref = _first_non_empty(
        _string_value(_optional_dict(view, "last_safe_point"), "ref"),
        _string_value(_optional_dict(view, "last_safe_point_details"), "ref"),
        _string_value(_optional_dict(view, "safe_point_details"), "ref"),
        _string_value(_optional_dict(view, "safe_point"), "ref"),
        _string_value(_optional_dict(view, "last_safe_point_details"), "details_ref"),
    )
    parts = []
    if details_ref:
        parts.append(f"ref={details_ref}")
    for attr_name in ("last_safe_point_step_id", "last_safe_point_status", "last_safe_point_reason"):
        value = getattr(view, attr_name, None)
        if isinstance(value, str) and value.strip():
            parts.append(f"{attr_name.removeprefix('last_safe_point_')}={value.strip()}")
    for attr_name in ("last_safe_point_age_seconds", "last_safe_point_age_s"):
        value = getattr(view, attr_name, None)
        if isinstance(value, (int, float)) and value > 0:
            parts.append(f"age={value:g}s")
            break
    return ", ".join(parts)


def _text_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _string_value(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    return value.strip() if isinstance(value, str) else ""


def _first_non_empty(*values: str) -> str:
    for value in values:
        if value:
            return value
    return ""


def _one_line(text: str, limit: int) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return compact[: max(limit - 3, 0)].rstrip() + "..."


def _has_initial_input(config: FrontDeskTuiConfig) -> bool:
    return (_run_root(config) / "frontdesk/initial_input.md").is_file()


def _read_existing_status(config: FrontDeskTuiConfig) -> str:
    control = _read_control(config)
    decision = control.get("decision") if isinstance(control, dict) else ""
    return str(decision) if decision else ""


def _read_control(config: FrontDeskTuiConfig) -> dict[str, Any]:
    try:
        return read_json_ref(_run_root(config), FRONTDESK_CONTROL_REF, "frontdesk_control")
    except (mf.ContractValidationError, OSError, json.JSONDecodeError):
        return {}


def _read_assistant_turn(config: FrontDeskTuiConfig) -> dict[str, Any]:
    try:
        return read_json_ref(_run_root(config), FRONTDESK_ASSISTANT_TURN_REF, "frontdesk_assistant_turn")
    except (mf.ContractValidationError, OSError, json.JSONDecodeError):
        return {}


def _question_text(question: Any) -> str:
    if isinstance(question, dict):
        text = str(question.get("question") or "").strip()
        why = str(question.get("why") or "").strip()
        hint = str(question.get("answer_hint") or "").strip()
        parts = [text] if text else []
        if why:
            parts.append(f"为什么问：{why}")
        if hint:
            parts.append(f"回答示例：{hint}")
        choices = _choice_texts(question.get("choices"))
        if choices:
            parts.append("候选：" + "；".join(choices))
        return " ".join(parts)
    return str(question).strip()


def _choice_texts(value: Any) -> list[str]:
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


def _run_root(config: FrontDeskTuiConfig) -> Path:
    return config.workspace.resolve() / "runs" / config.request_id


def _box(output_stream: TextIO, title: str, lines: list[str]) -> None:
    border = "=" * TUI_WIDTH
    output_stream.write(f"\n{border}\n")
    output_stream.write(f"{title}\n")
    output_stream.write(f"{'-' * len(title)}\n")
    for line in lines:
        output_stream.write(f"{line}\n")
    output_stream.write(f"{border}\n\n")


def _command_bar(output_stream: TextIO) -> None:
    output_stream.write("命令：/show 查看需求 | /status 状态 | /approve 批准并启动 | /quit 退出\n\n")


def _section(output_stream: TextIO, title: str) -> None:
    output_stream.write(f"\n{title}\n")
    output_stream.write(f"{'-' * min(len(title), TUI_WIDTH)}\n")


def _rule(output_stream: TextIO) -> None:
    output_stream.write("-" * TUI_WIDTH + "\n\n")


def _status_line(output_stream: TextIO, subject: str, status: str) -> None:
    output_stream.write(f"\n[{subject}] status: {status}\n")


def _hint(output_stream: TextIO, text: str) -> None:
    output_stream.write(f"  next: {text}\n\n")


def _error(output_stream: TextIO, text: str) -> None:
    output_stream.write(f"\nERROR: {text}\n\n")
