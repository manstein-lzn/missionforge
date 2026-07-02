"""Shared web-console types and response helpers."""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, Callable, Mapping

import missionforge as mf

from .product_contract import ResearchIntensity


WEB_POST_MAX_BYTES = 256 * 1024


@dataclass(frozen=True)
class WebConsoleResponse:
    """Pure response object used by the stdlib HTTP adapter."""

    status: int
    content_type: str
    body: str


@dataclass(frozen=True)
class WebFrontDeskConfig:
    """Server-owned FrontDesk execution settings for web messages."""

    adapter_factory: Callable[[], mf.PiWorkerCallAdapter]
    audience: str = "R&D team"
    language: str = "zh"
    research_intensity: ResearchIntensity | str = ResearchIntensity.STANDARD
    live_extension_mode: bool = False


def html_response(status: int, body: str) -> WebConsoleResponse:
    return WebConsoleResponse(status=status, content_type="text/html; charset=utf-8", body=body)


def json_response(status: int, payload: Mapping[str, Any]) -> WebConsoleResponse:
    return WebConsoleResponse(
        status=status,
        content_type="application/json; charset=utf-8",
        body=json.dumps(payload, sort_keys=True, ensure_ascii=False, indent=2) + "\n",
    )
