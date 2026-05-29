"""Compile approved FrontDesk artifacts into MissionIR."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from ..contracts import ContractValidationError, require_mapping, require_non_empty_str, stable_json_hash, validate_ref
from ..freeze import freeze_mission
from ..ir import CapabilityProfileRef, MissionConstraint, MissionIR, MissionObjective
from ..profiles import ProfileRegistry
from .schema import (
    AuthoringApproval,
    FrontDeskFreezeManifest,
    MissionBrief,
    MissionPlan,
    MissionSemanticLock,
    ProfileRecommendationKind,
    ProfileRecommendationSet,
    SanitizedSourceSet,
)
from .state import AUTHORING_APPROVAL_REF, DRAFT_MISSION_REF, FREEZE_MANIFEST_REF
from .workspace import FrontDeskWorkspace


@dataclass(frozen=True)
class FrontDeskCompileResult:
    """Refs-only result of compiling FrontDesk artifacts."""

    session_id: str
    mission_ir_ref: str
    frozen_contract_ref: str
    contract_hash: str
    approval_ref: str
    freeze_manifest_ref: str
    profile_ids: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    next_action: str = "run"

    def validate(self) -> None:
        require_non_empty_str(self.session_id, "frontdesk_compile_result.session_id")
        validate_ref(self.mission_ir_ref, "frontdesk_compile_result.mission_ir_ref")
        validate_ref(self.frozen_contract_ref, "frontdesk_compile_result.frozen_contract_ref")
        if not require_non_empty_str(self.contract_hash, "frontdesk_compile_result.contract_hash").startswith("sha256:"):
            raise ContractValidationError("frontdesk_compile_result.contract_hash must be a sha256 hash")
        validate_ref(self.approval_ref, "frontdesk_compile_result.approval_ref")
        validate_ref(self.freeze_manifest_ref, "frontdesk_compile_result.freeze_manifest_ref")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "session_id": self.session_id,
            "mission_ir_ref": self.mission_ir_ref,
            "frozen_contract_ref": self.frozen_contract_ref,
            "contract_hash": self.contract_hash,
            "approval_ref": self.approval_ref,
            "freeze_manifest_ref": self.freeze_manifest_ref,
            "profile_ids": list(self.profile_ids),
            "warnings": list(self.warnings),
            "next_action": self.next_action,
        }


class FrontDeskMissionCompiler:
    """Deterministic compiler for approved FrontDesk authoring artifacts."""

    def compile(
        self,
        *,
        semantic_lock: MissionSemanticLock,
        mission_brief: MissionBrief,
        profile_recommendations: ProfileRecommendationSet,
        mission_plan: MissionPlan,
        approval: AuthoringApproval,
        sanitized_sources: SanitizedSourceSet | None = None,
        workspace: str | Path = ".",
        registry: ProfileRegistry | None = None,
    ) -> FrontDeskCompileResult:
        for item in (semantic_lock, mission_brief, profile_recommendations, mission_plan, approval):
            item.validate()
        if sanitized_sources is not None:
            sanitized_sources.validate()
        _require_same_session(
            semantic_lock.session_id,
            mission_brief.session_id,
            profile_recommendations.session_id,
            mission_plan.session_id,
            approval.session_id,
            sanitized_sources.session_id if sanitized_sources else semantic_lock.session_id,
        )
        active_registry = registry or ProfileRegistry.builtins()
        mission = build_mission_ir(
            semantic_lock=semantic_lock,
            mission_brief=mission_brief,
            profile_recommendations=profile_recommendations,
            mission_plan=mission_plan,
            approval=approval,
            sanitized_sources=sanitized_sources,
        )
        # This is the deterministic profile and validator-language gate.
        frozen = freeze_mission(mission, registry=active_registry)

        mission_ir_ref = f"missions/{semantic_lock.session_id}.mission.json"
        frozen_contract_ref = f"missions/{semantic_lock.session_id}.frozen_contract.json"
        profile_ids = [profile.profile_id for profile in mission.capability_profiles]
        profile_ids.extend(
            _verification_profile_id(item)
            for item in mission.verification.get("verification_profiles", [])
            if isinstance(item, Mapping)
        )
        manifest = FrontDeskFreezeManifest(
            session_id=semantic_lock.session_id,
            mission_ir_ref=mission_ir_ref,
            frozen_contract_ref=frozen_contract_ref,
            contract_hash=frozen.contract_hash,
            approval_ref=AUTHORING_APPROVAL_REF,
            source_refs=list(mission.inputs.get("admitted_source_refs", [])),
            profile_ids=profile_ids,
        )
        workspace_io = FrontDeskWorkspace(workspace)
        workspace_io.write_json(DRAFT_MISSION_REF, mission.to_dict())
        workspace_io.write_json(mission_ir_ref, mission.to_dict())
        workspace_io.write_json(frozen_contract_ref, frozen.to_dict())
        workspace_io.write_json(FREEZE_MANIFEST_REF, manifest.to_dict())

        result = FrontDeskCompileResult(
            session_id=semantic_lock.session_id,
            mission_ir_ref=mission_ir_ref,
            frozen_contract_ref=frozen_contract_ref,
            contract_hash=frozen.contract_hash,
            approval_ref=AUTHORING_APPROVAL_REF,
            freeze_manifest_ref=FREEZE_MANIFEST_REF,
            profile_ids=profile_ids,
        )
        result.validate()
        return result


def build_mission_ir(
    *,
    semantic_lock: MissionSemanticLock,
    mission_brief: MissionBrief,
    profile_recommendations: ProfileRecommendationSet,
    mission_plan: MissionPlan,
    approval: AuthoringApproval,
    sanitized_sources: SanitizedSourceSet | None = None,
) -> MissionIR:
    """Build a MissionIR object from validated FrontDesk contracts."""

    source_refs = sanitized_sources.admitted_source_refs if sanitized_sources else semantic_lock.source_refs
    excluded_refs = sanitized_sources.excluded_source_refs if sanitized_sources else []
    constraints = [
        MissionConstraint.from_dict(require_mapping(item, "mission_plan.constraints[]"))
        for item in mission_plan.constraints
    ]
    if not constraints:
        constraints.append(
            MissionConstraint(
                constraint_id=f"FD-{semantic_lock.session_id}-C-authoring-contract",
                kind="frontdesk_authoring_contract",
                statement="Satisfy the approved FrontDesk mission plan using only admitted source refs.",
                priority="must",
                source_refs=[approval.approved_ref, *source_refs],
                evidence_obligations=list(mission_plan.expected_artifacts),
                repair_hints=["Regenerate outputs from the approved FrontDesk mission contract."],
            )
        )
    for index, note in enumerate(mission_plan.risk_notes, start=1):
        constraints.append(
            MissionConstraint(
                constraint_id=f"FD-{semantic_lock.session_id}-C-risk-{index:03d}",
                kind="risk_note",
                statement=note,
                priority="should",
                source_refs=[approval.approved_ref],
                evidence_obligations=[],
                repair_hints=["Respect the FrontDesk risk note or request mission revision."],
            )
        )

    mission = MissionIR(
        mission_id=f"frontdesk-{semantic_lock.session_id}",
        objective=MissionObjective(
            summary=mission_brief.goal,
            deliverable_type=mission_brief.deliverable_type,
            success_signals=list(mission_brief.success_signals),
        ),
        inputs={
            "frontdesk_semantic_lock_ref": "frontdesk/semantic_lock.json",
            "frontdesk_mission_brief_ref": "frontdesk/mission_brief.json",
            "frontdesk_profile_recommendations_ref": "frontdesk/profile_recommendations.json",
            "frontdesk_mission_plan_ref": "frontdesk/mission_plan.json",
            "frontdesk_approval_ref": approval.approved_ref,
            "admitted_source_refs": list(source_refs),
            "excluded_source_refs": list(excluded_refs),
            "semantic_hash": semantic_lock.semantic_hash,
        },
        outputs={
            "required_artifacts": list(mission_plan.expected_artifacts),
        },
        constraints=constraints,
        capability_profiles=[
            CapabilityProfileRef(profile_id=item.profile_id, requirements=dict(item.requirements))
            for item in profile_recommendations.selected_capability_profiles
        ],
        verification={
            "required_evidence": list(mission_plan.expected_artifacts),
            "verification_profiles": [
                {"profile_id": item.profile_id}
                for item in profile_recommendations.selected_verification_profiles
            ]
            or [{"profile_id": "generic_local_verification"}],
            "validators": list(mission_plan.validators),
            "manual_gates": list(mission_plan.manual_gates),
        },
        repair_policy={"rules": []},
        budget={},
        observability={
            "frontdesk_approval_ref": approval.approved_ref,
            "frontdesk_approved_hash": approval.approved_hash,
            "frontdesk_compiler": "missionforge.frontdesk",
        },
    )
    mission.validate()
    return mission


def compile_frontdesk_artifacts(
    *,
    semantic_lock: MissionSemanticLock,
    mission_brief: MissionBrief,
    profile_recommendations: ProfileRecommendationSet,
    mission_plan: MissionPlan,
    approval: AuthoringApproval,
    sanitized_sources: SanitizedSourceSet | None = None,
    workspace: str | Path = ".",
    registry: ProfileRegistry | None = None,
) -> FrontDeskCompileResult:
    return FrontDeskMissionCompiler().compile(
        semantic_lock=semantic_lock,
        mission_brief=mission_brief,
        profile_recommendations=profile_recommendations,
        mission_plan=mission_plan,
        approval=approval,
        sanitized_sources=sanitized_sources,
        workspace=workspace,
        registry=registry,
    )


def approved_hash_for(*payloads: dict[str, Any]) -> str:
    return stable_json_hash({"approved_payloads": list(payloads)})


def _require_same_session(*session_ids: str) -> None:
    first = session_ids[0]
    for session_id in session_ids:
        if session_id != first:
            raise ContractValidationError("FrontDesk artifact session_id values do not match")


def _verification_profile_id(value: Mapping[str, Any]) -> str:
    return require_non_empty_str(value.get("profile_id"), "verification_profile.profile_id")
