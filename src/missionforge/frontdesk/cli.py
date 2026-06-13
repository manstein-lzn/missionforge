"""FrontDesk command helpers."""

from __future__ import annotations

from argparse import Namespace
from pathlib import Path
from typing import Any

from ..adapters.pi_agent_runtime import PiAgentRuntimeConfig
from ..contracts import ContractValidationError
from ..piworker_runtime import create_default_piworker_adapter
from .schema import ApprovalAuthority
from .generic_integration import GenericProductIntegration
from .service import FrontDesk
from .spec_grill_schema import PlanReviewDecision


def run_frontdesk_command(args: Namespace) -> tuple[dict[str, Any], list[str]]:
    """Execute one parsed FrontDesk CLI command and return refs-only data."""

    frontdesk = FrontDesk(workspace=Path(args.workspace), worker=_frontdesk_worker_from_args(args))
    action = args.frontdesk_command
    if action == "start":
        session = frontdesk.start(args.text, session_id=args.session_id)
        return {"session": session.to_dict()}, [session.session_ref]
    if action == "answer":
        session = frontdesk.answer(args.session, args.text)
        return {"session": session.to_dict()}, [session.session_ref, session.conversation_ref]
    if action == "inspect":
        result = frontdesk.inspect(args.session)
        return result.to_dict(), [result.refs["session_ref"]]
    if action == "scout":
        result = frontdesk.scout(args.session)
        return result.to_dict(), result.refs
    if action == "grill":
        result = frontdesk.grill(args.session)
        return result.to_dict(), result.refs
    if action == "cover-semantics":
        result = frontdesk.cover_semantics(args.session)
        return result.to_dict(), result.refs
    if action == "plan":
        result = frontdesk.plan_solution(args.session)
        return result.to_dict(), result.refs
    if action == "review-plan":
        review = frontdesk.review_plan(
            args.session,
            reviewed_by=args.reviewed_by,
            decision=PlanReviewDecision(args.decision),
            authority=ApprovalAuthority(args.authority),
            notes=[args.note] if args.note else None,
        )
        session = frontdesk.load_session(args.session)
        return {"plan_review": review.to_dict(), "session": session.to_dict()}, [session.session_ref, "frontdesk/plan_review.json"]
    if action == "map":
        result = frontdesk.map_mission(args.session)
        return result.to_dict(), result.refs
    if action == "draft":
        session = frontdesk.draft(args.session)
        return {"session": session.to_dict()}, [
            session.session_ref,
            "frontdesk/intent_bundle.json",
            session.semantic_lock_ref,
            session.mission_brief_ref,
            session.profile_recommendations_ref,
            session.mission_plan_ref,
            "frontdesk/semantic_coverage.json",
            "frontdesk/solution_plan.json",
            "frontdesk/plan_review.json",
            "frontdesk/mission_mapping_report.json",
        ]
    if action == "intent":
        bundle = frontdesk.build_intent_bundle(args.session)
        return {
            "intent_bundle_ref": bundle.intent_bundle_ref,
            "readiness": bundle.readiness.value,
            "product_id": bundle.product_context.product_id,
            "missing_product_slots": list(bundle.missing_blocking_slots),
        }, [bundle.intent_bundle_ref, *bundle.evidence_refs]
    if action == "compile-product":
        if args.integration_ref != "generic":
            raise ContractValidationError(
                "core FrontDesk CLI cannot import product integrations; use a product CLI entrypoint or --integration-ref generic"
            )
        result = frontdesk.compile_product(args.session, GenericProductIntegration())
        return {"product_compile_result": result.to_dict()}, [
            result.intent_bundle_ref,
            result.mission_ir_ref,
            *result.evidence_refs,
        ]
    if action == "audit":
        audit = frontdesk.audit(args.session)
        session = frontdesk.load_session(args.session)
        return {"audit": audit.to_dict(), "session": session.to_dict()}, [session.session_ref, session.mission_audit_ref]
    if action == "approve":
        approval = frontdesk.approve(args.session, approved_by=args.approved_by)
        session = frontdesk.load_session(args.session)
        return {"approval": approval.to_dict(), "session": session.to_dict()}, [
            session.session_ref,
            session.authoring_approval_ref,
        ]
    if action == "freeze":
        result = frontdesk.freeze(args.session)
        session = frontdesk.load_session(args.session)
        return {"compile_result": result.to_dict(), "session": session.to_dict()}, [
            session.session_ref,
            result.mission_ir_ref,
            result.frozen_contract_ref,
            result.freeze_manifest_ref,
        ]
    raise ContractValidationError(f"unsupported frontdesk command: {action}")


def _frontdesk_worker_from_args(args: Namespace):
    if not bool(getattr(args, "use_default_piworker", False)):
        return None
    return create_default_piworker_adapter(
        PiAgentRuntimeConfig(
            provider_mode=getattr(args, "piworker_provider_mode", "faux"),
            provider_config_source=getattr(args, "piworker_provider_config_source", "env"),
            model=getattr(args, "piworker_model", None) or None,
            timeout_seconds=int(getattr(args, "piworker_timeout_seconds", 300)),
        )
    )
