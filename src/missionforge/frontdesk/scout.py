"""Workspace and profile scouting for FrontDesk spec-grill."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..profiles import ProfileRegistry
from .schema import SanitizedSourceSet
from .spec_grill_schema import (
    DomainLanguage,
    FactConfidence,
    ProfileCatalogSnapshot,
    SourceAdmissionReport,
    WorkspaceFact,
    WorkspaceFacts,
)
from .state import (
    DOMAIN_LANGUAGE_REF,
    PROFILE_CATALOG_SNAPSHOT_REF,
    SANITIZED_SOURCES_REF,
    SOURCE_ADMISSION_REPORT_REF,
    WORKSPACE_FACTS_REF,
    FrontDeskAuthoringSession,
)
from .workspace import FrontDeskWorkspace


@dataclass(frozen=True)
class ScoutResult:
    """Artifacts produced by the workspace/profile scout."""

    workspace_facts: WorkspaceFacts
    profile_catalog_snapshot: ProfileCatalogSnapshot
    domain_language: DomainLanguage
    source_admission_report: SourceAdmissionReport

    @property
    def refs(self) -> list[str]:
        return [
            WORKSPACE_FACTS_REF,
            PROFILE_CATALOG_SNAPSHOT_REF,
            DOMAIN_LANGUAGE_REF,
            SOURCE_ADMISSION_REPORT_REF,
        ]

    def to_dict(self) -> dict[str, Any]:
        return {
            "workspace_facts": self.workspace_facts.to_dict(),
            "profile_catalog_snapshot": self.profile_catalog_snapshot.to_dict(),
            "domain_language": self.domain_language.to_dict(),
            "source_admission_report": self.source_admission_report.to_dict(),
            "refs": list(self.refs),
        }


class WorkspaceScout:
    """Deterministic scout for available FrontDesk authoring facts."""

    def __init__(self, *, registry: ProfileRegistry | None = None) -> None:
        self.registry = registry or ProfileRegistry.builtins()

    def scout(
        self,
        *,
        session: FrontDeskAuthoringSession,
        workspace: FrontDeskWorkspace,
    ) -> ScoutResult:
        session.validate()
        profile_catalog = ProfileCatalogSnapshot(
            session_id=session.session_id,
            capability_profile_ids=self.registry.capability_profile_ids(),
            verification_profile_ids=self.registry.verification_profile_ids(),
        )
        domain_language = DomainLanguage(session_id=session.session_id)
        source_report = _source_admission(session, workspace)
        facts = WorkspaceFacts(
            session_id=session.session_id,
            facts=[
                WorkspaceFact(
                    fact_id="F-profile-capabilities",
                    summary="Available capability profiles were discovered from the active registry.",
                    source_refs=[],
                    confidence=FactConfidence.OBSERVED,
                    metadata={"profile_ids": profile_catalog.capability_profile_ids},
                ),
                WorkspaceFact(
                    fact_id="F-profile-verification",
                    summary="Available verification profiles were discovered from the active registry.",
                    source_refs=[],
                    confidence=FactConfidence.OBSERVED,
                    metadata={"profile_ids": profile_catalog.verification_profile_ids},
                ),
            ],
            questions_answered_by_workspace=[
                "Which capability profiles are available?",
                "Which verification profiles are available?",
            ],
            unsafe_or_excluded_refs=list(source_report.excluded_source_refs),
        )

        workspace.write_json(WORKSPACE_FACTS_REF, facts.to_dict())
        workspace.write_json(PROFILE_CATALOG_SNAPSHOT_REF, profile_catalog.to_dict())
        workspace.write_json(DOMAIN_LANGUAGE_REF, domain_language.to_dict())
        workspace.write_json(SOURCE_ADMISSION_REPORT_REF, source_report.to_dict())
        return ScoutResult(
            workspace_facts=facts,
            profile_catalog_snapshot=profile_catalog,
            domain_language=domain_language,
            source_admission_report=source_report,
        )


def _source_admission(session: FrontDeskAuthoringSession, workspace: FrontDeskWorkspace) -> SourceAdmissionReport:
    admitted_refs: list[str] = []
    excluded_refs = [session.conversation_ref]
    reasons = ["Raw conversation remains provenance only."]
    if workspace.exists(SANITIZED_SOURCES_REF):
        sources = SanitizedSourceSet.from_dict(workspace.read_json(SANITIZED_SOURCES_REF))
        admitted_refs.extend(sources.admitted_source_refs)
        excluded_refs.extend(ref for ref in sources.excluded_source_refs if ref not in excluded_refs)
        reasons.extend(sources.redaction_notes)
    return SourceAdmissionReport(
        session_id=session.session_id,
        admitted_source_refs=admitted_refs,
        excluded_source_refs=excluded_refs,
        reasons=reasons,
    )

def scout_frontdesk_session(
    *,
    session: FrontDeskAuthoringSession,
    workspace: FrontDeskWorkspace,
    registry: ProfileRegistry | None = None,
) -> ScoutResult:
    return WorkspaceScout(registry=registry).scout(session=session, workspace=workspace)


__all__ = ["ScoutResult", "WorkspaceScout", "scout_frontdesk_session"]
