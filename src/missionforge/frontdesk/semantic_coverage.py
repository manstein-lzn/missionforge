"""Semantic lock and coverage checks for FrontDesk spec-grill."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .schema import MissionBrief, MissionSemanticLock, SanitizedSourceSet
from .spec_grill_schema import (
    CoreNeedBrief,
    DomainLanguage,
    MissionSemanticCoverageReport,
    SemanticCoverageItem,
    SemanticCoverageItemStatus,
    SemanticCoverageStatus,
)
from .state import (
    CONVERSATION_REF,
    CORE_NEED_BRIEF_REF,
    DOMAIN_LANGUAGE_REF,
    MISSION_BRIEF_REF,
    SANITIZED_SOURCES_REF,
    SEMANTIC_COVERAGE_REF,
    SEMANTIC_LOCK_REF,
    FrontDeskAuthoringSession,
)
from .workspace import FrontDeskWorkspace


@dataclass(frozen=True)
class SemanticCoverageResult:
    """Artifacts produced by semantic coverage."""

    semantic_lock: MissionSemanticLock
    mission_brief: MissionBrief
    sanitized_sources: SanitizedSourceSet
    coverage_report: MissionSemanticCoverageReport

    @property
    def refs(self) -> list[str]:
        return [SANITIZED_SOURCES_REF, SEMANTIC_LOCK_REF, MISSION_BRIEF_REF, SEMANTIC_COVERAGE_REF]

    def to_dict(self) -> dict[str, Any]:
        return {
            "semantic_lock": self.semantic_lock.to_dict(),
            "mission_brief": self.mission_brief.to_dict(),
            "sanitized_sources": self.sanitized_sources.to_dict(),
            "semantic_coverage": self.coverage_report.to_dict(),
            "refs": list(self.refs),
        }


class SemanticCoverageChecker:
    """Build semantic authoring truth and verify signal coverage."""

    def cover(
        self,
        *,
        session: FrontDeskAuthoringSession,
        workspace: FrontDeskWorkspace,
    ) -> SemanticCoverageResult:
        session.validate()
        core_need = CoreNeedBrief.from_dict(workspace.read_json(CORE_NEED_BRIEF_REF))
        domain = _load_domain_language(workspace, session.session_id)
        semantic_lock = _semantic_lock(session.session_id, core_need, domain)
        mission_brief = MissionBrief(
            session_id=session.session_id,
            goal=core_need.desired_outcome,
            deliverable_type=core_need.deliverable_type,
            success_signals=list(core_need.success_signals),
            target_users=list(core_need.target_users),
            non_goals=list(core_need.non_goals),
            assumptions=list(core_need.assumptions),
            open_questions=[question.question for question in core_need.open_questions],
        )
        sanitized_sources = SanitizedSourceSet(
            session_id=session.session_id,
            admitted_source_refs=[SEMANTIC_LOCK_REF, MISSION_BRIEF_REF],
            excluded_source_refs=[CONVERSATION_REF],
            redaction_notes=["Raw conversation remains provenance only."],
        )
        coverage = _coverage_report(session.session_id, semantic_lock, mission_brief, core_need, domain)
        workspace.write_json(SANITIZED_SOURCES_REF, sanitized_sources.to_dict())
        workspace.write_json(SEMANTIC_LOCK_REF, semantic_lock.to_dict())
        workspace.write_json(MISSION_BRIEF_REF, mission_brief.to_dict())
        workspace.write_json(SEMANTIC_COVERAGE_REF, coverage.to_dict())
        return SemanticCoverageResult(
            semantic_lock=semantic_lock,
            mission_brief=mission_brief,
            sanitized_sources=sanitized_sources,
            coverage_report=coverage,
        )


def _load_domain_language(workspace: FrontDeskWorkspace, session_id: str) -> DomainLanguage:
    if workspace.exists(DOMAIN_LANGUAGE_REF):
        return DomainLanguage.from_dict(workspace.read_json(DOMAIN_LANGUAGE_REF))
    return DomainLanguage(session_id=session_id)


def _semantic_lock(session_id: str, core_need: CoreNeedBrief, domain: DomainLanguage) -> MissionSemanticLock:
    clauses = [
        core_need.core_pain,
        core_need.desired_outcome,
        *core_need.success_signals,
        *core_need.constraints,
        *domain.terms,
        *domain.implementation_terms,
        *domain.risk_terms,
    ]
    non_goals = list(core_need.non_goals)
    return MissionSemanticLock(
        session_id=session_id,
        summary=core_need.desired_outcome,
        requirement_clauses=_unique_non_empty(clauses),
        source_refs=[CORE_NEED_BRIEF_REF],
        assumptions=list(core_need.assumptions),
        non_goals=non_goals,
        risks=list(domain.risk_terms),
    )


def _coverage_report(
    session_id: str,
    semantic_lock: MissionSemanticLock,
    mission_brief: MissionBrief,
    core_need: CoreNeedBrief,
    domain: DomainLanguage,
) -> MissionSemanticCoverageReport:
    haystack = " ".join(
        [
            semantic_lock.summary,
            *semantic_lock.requirement_clauses,
            *semantic_lock.non_goals,
            *semantic_lock.risks,
            mission_brief.goal,
            *mission_brief.success_signals,
            *mission_brief.assumptions,
            *mission_brief.open_questions,
            *core_need.constraints,
        ]
    ).lower()
    signals = _unique_non_empty([*domain.terms, *domain.implementation_terms, *domain.risk_terms])
    items: list[SemanticCoverageItem] = []
    unmapped: list[str] = []
    for index, signal in enumerate(signals, start=1):
        covered = signal.lower() in haystack
        status = SemanticCoverageItemStatus.COVERED if covered else SemanticCoverageItemStatus.UNMAPPED
        if not covered:
            unmapped.append(signal)
        items.append(
            SemanticCoverageItem(
                signal_id=f"S-{index:03d}",
                source_signal=signal,
                status=status,
                source_refs=domain.source_refs or [CONVERSATION_REF],
                mapped_refs=[SEMANTIC_LOCK_REF, MISSION_BRIEF_REF] if covered else [],
                notes="Signal preserved in semantic artifacts." if covered else "Signal was not found in semantic artifacts.",
                blocking=True,
            )
        )
    status = SemanticCoverageStatus.FAILED if unmapped else SemanticCoverageStatus.PASSED
    return MissionSemanticCoverageReport(
        session_id=session_id,
        status=status,
        coverage_items=items,
        unmapped_signals=unmapped,
    )


def _unique_non_empty(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        normalized = value.strip()
        if normalized and normalized not in result:
            result.append(normalized)
    return result


def cover_frontdesk_semantics(
    *,
    session: FrontDeskAuthoringSession,
    workspace: FrontDeskWorkspace,
) -> SemanticCoverageResult:
    return SemanticCoverageChecker().cover(session=session, workspace=workspace)


__all__ = ["SemanticCoverageChecker", "SemanticCoverageResult", "cover_frontdesk_semantics"]
