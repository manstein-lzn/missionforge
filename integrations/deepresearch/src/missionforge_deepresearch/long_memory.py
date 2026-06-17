"""Long-memory packet bridge for the DeepResearch integration."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Protocol

from missionforge.adapters.long_memory import (
    LongMemoryCatalogHit,
    LongMemoryPacket,
    LongMemoryProvider,
    LongMemoryScope,
    LongMemorySearchRequest,
    write_long_memory_packet,
)
from missionforge.contracts import ContractValidationError, validate_ref
from missionforge.piworker_call import PiWorkerCall

from .product_contract import AcademicResearchRequest


DEEPRESEARCH_LONG_MEMORY_PACKET_REF_TEMPLATE = "attempts/{call_id}/context/long_memory_packet.json"


class DeepResearchLongMemoryProvider(Protocol):
    def build_packet(self, request: LongMemorySearchRequest) -> LongMemoryPacket:
        ...


def prepare_researcher_long_memory_packet(
    provider: LongMemoryProvider | DeepResearchLongMemoryProvider | None,
    *,
    request: AcademicResearchRequest,
    call: PiWorkerCall,
    workspace: str | Path,
    project_id: str = "missionforge.deepresearch",
    user_id: str | None = None,
    budget_tokens: int = 2000,
    limit: int = 8,
    catalog_refs: list[str] | None = None,
) -> str | None:
    """Build and write an advisory long-memory packet for a researcher call."""

    if provider is None:
        return None
    request.validate()
    call.validate()
    if budget_tokens < 1:
        raise ContractValidationError("deepresearch long_memory budget_tokens must be >= 1")
    if limit < 1:
        raise ContractValidationError("deepresearch long_memory limit must be >= 1")
    packet_ref = DEEPRESEARCH_LONG_MEMORY_PACKET_REF_TEMPLATE.format(call_id=call.call_id)
    scope = LongMemoryScope(
        project_id=project_id,
        mission_id=call.contract_id,
        role=call.role.value,
        user_id=user_id,
    )
    search_request = LongMemorySearchRequest(
        query=_research_memory_query(request),
        scope=scope,
        packet_ref=packet_ref,
        budget_tokens=budget_tokens,
        limit=limit,
        catalog_hits=tuple(_catalog_hits(catalog_refs or [])),
    )
    packet = provider.build_packet(search_request)
    packet = _normalize_packet(packet, packet_ref=packet_ref, scope=scope, budget_tokens=budget_tokens)
    if not packet.memories and not packet.catalog_hits:
        return None
    return write_long_memory_packet(workspace, packet, packet_ref)


def _normalize_packet(
    packet: LongMemoryPacket,
    *,
    packet_ref: str,
    scope: LongMemoryScope,
    budget_tokens: int,
) -> LongMemoryPacket:
    normalized = replace(
        packet,
        packet_ref=packet_ref,
        scope=scope,
        budget_tokens=budget_tokens,
        advisory_only=True,
    )
    normalized.validate()
    return normalized


def _research_memory_query(request: AcademicResearchRequest) -> str:
    previous = ", ".join(request.previous_run_refs) if request.previous_run_refs else "none"
    return (
        f"DeepResearch topic: {request.topic}\n"
        f"Audience: {request.audience}\n"
        f"Language: {request.language}\n"
        f"Research intensity: {request.research_intensity.value}\n"
        f"Previous run refs: {previous}"
    )


def _catalog_hits(refs: list[str]) -> list[LongMemoryCatalogHit]:
    return [LongMemoryCatalogHit(segment_ref=validate_ref(ref, "deepresearch.long_memory.catalog_refs[]")) for ref in refs]
