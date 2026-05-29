"""FrontDesk command helpers."""

from __future__ import annotations

from argparse import Namespace
from pathlib import Path
from typing import Any

from ..contracts import ContractValidationError
from .service import FrontDesk


def run_frontdesk_command(args: Namespace) -> tuple[dict[str, Any], list[str]]:
    """Execute one parsed FrontDesk CLI command and return refs-only data."""

    frontdesk = FrontDesk(workspace=Path(args.workspace))
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
    if action == "draft":
        session = frontdesk.draft(args.session)
        return {"session": session.to_dict()}, [
            session.session_ref,
            session.semantic_lock_ref,
            session.mission_brief_ref,
            session.profile_recommendations_ref,
            session.mission_plan_ref,
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
    if action == "run":
        mission_result = frontdesk.run(args.session)
        session = frontdesk.load_session(args.session)
        return {
            "session": session.to_dict(),
            "mission_status": mission_result.status,
            "mission_id": mission_result.mission_id,
            "evidence_refs": list(mission_result.evidence_refs),
            "artifact_refs": list(mission_result.artifact_refs),
        }, [session.session_ref, *mission_result.evidence_refs, *mission_result.artifact_refs]
    raise ContractValidationError(f"unsupported frontdesk command: {action}")
