"""Read-only operator CLI for MissionForge refs.

This adapter module is deliberately outside the package root. It observes
existing refs and renders safe status summaries; it does not execute,
schedule, accept, repair, or mutate runs.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time
from typing import Any, TextIO

from ..contracts import validate_ref
from ..operator_view import MissionRunView, build_mission_run_view, render_mission_run_view


def main(
    argv: list[str] | None = None,
    *,
    output_stream: TextIO | None = None,
    error_stream: TextIO | None = None,
) -> int:
    output = output_stream or sys.stdout
    errors = error_stream or sys.stderr
    parser = _parser()
    args = parser.parse_args(argv)
    if args.command in {"tui", "status"}:
        return _run_status_command(args, output_stream=output, error_stream=errors)
    parser.print_help(file=errors)
    return 2


def _run_status_command(args: argparse.Namespace, *, output_stream: TextIO, error_stream: TextIO) -> int:
    flow_result_ref = args.flow_result_ref or args.run_ref
    if not flow_result_ref:
        error_stream.write("missing required --flow-result-ref or --run-ref\n")
        return 2
    try:
        while True:
            view = build_mission_run_view(args.workspace, flow_result_ref=flow_result_ref)
            if args.json:
                payload = json.dumps(view.to_dict(), sort_keys=True)
                output_stream.write(payload + "\n")
            else:
                output_stream.write(render_mission_run_view(view))
            output_stream.flush()
            if not args.watch:
                return 0
            time.sleep(args.interval)
    except KeyboardInterrupt:
        return 130
    except Exception as exc:  # noqa: BLE001 - CLI boundary normalizes failures.
        error_stream.write(f"missionforge adapter error: {type(exc).__name__}: {exc}\n")
        return 1


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m missionforge.adapters.cli")
    subparsers = parser.add_subparsers(dest="command")
    for command in ("tui", "status"):
        sub = subparsers.add_parser(command, help="observe a Kernel run through refs-only records")
        sub.add_argument("--workspace", default=".", help="workspace root")
        sub.add_argument("--flow-result-ref", default="", help="Kernel flow_result.json ref")
        sub.add_argument("--run-ref", default="", help="alias for --flow-result-ref")
        sub.add_argument("--json", action="store_true", help="emit one JSON object")
        sub.add_argument("--watch", action="store_true", help="poll and render repeatedly")
        sub.add_argument("--interval", type=float, default=2.0, help="watch polling interval seconds")
    return parser


if __name__ == "__main__":
    raise SystemExit(main())
