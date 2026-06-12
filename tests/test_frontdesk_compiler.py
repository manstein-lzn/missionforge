from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from missionforge.ir import MissionIR
from missionforge.freeze import freeze_mission
from missionforge.frontdesk.compiler import approved_hash_for, compile_frontdesk_artifacts
from missionforge.frontdesk.schema import (
    ApprovalAuthority,
    AuthoringApproval,
    MissionBrief,
    MissionPlan,
    MissionSemanticLock,
    ProfileRecommendation,
    ProfileRecommendationKind,
    ProfileRecommendationSet,
    SanitizedSourceSet,
)


def sample_frontdesk_artifacts():
    session_id = "fd-compiler"
    semantic_lock = MissionSemanticLock(
        session_id=session_id,
        summary="Create package docs.",
        requirement_clauses=["Write a README under package/."],
        source_refs=["frontdesk/sanitized_sources.json"],
    )
    brief = MissionBrief(
        session_id=session_id,
        goal="Create a package README.",
        deliverable_type="documentation_change",
        success_signals=["package/README.md exists."],
    )
    profiles = ProfileRecommendationSet(
        session_id=session_id,
        recommendations=[
            ProfileRecommendation(
                profile_id="user_provided_evidence_only",
                kind=ProfileRecommendationKind.CAPABILITY,
                rationale="Only admitted source refs may be used.",
            ),
            ProfileRecommendation(
                profile_id="explicit_output_root",
                kind=ProfileRecommendationKind.CAPABILITY,
                rationale="Outputs are under package/.",
                requirements={"output_root": "package"},
            ),
            ProfileRecommendation(
                profile_id="generic_local_verification",
                kind=ProfileRecommendationKind.VERIFICATION,
                rationale="Local file checks are enough.",
            ),
        ],
    )
    plan = MissionPlan(
        session_id=session_id,
        expected_artifacts=["package/README.md"],
        validators=[
            {
                "validator_id": "V-readme-exists",
                "constraint_refs": [f"FD-{session_id}-C-authoring-contract"],
                "type": "file_exists",
                "inputs": {"path": "package/README.md"},
            }
        ],
    )
    approval = AuthoringApproval(
        session_id=session_id,
        approved_by="user",
        authority=ApprovalAuthority.USER,
        approved_ref="frontdesk/mission_plan.json",
        approved_hash=approved_hash_for(semantic_lock.to_dict(), brief.to_dict(), profiles.to_dict(), plan.to_dict()),
    )
    sources = SanitizedSourceSet(
        session_id=session_id,
        admitted_source_refs=["frontdesk/sanitized_sources.json"],
        excluded_source_refs=["frontdesk/conversation.jsonl"],
    )
    return semantic_lock, brief, profiles, plan, approval, sources


class FrontDeskCompilerTests(unittest.TestCase):
    def test_approved_artifacts_compile_to_valid_mission_ir(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            semantic_lock, brief, profiles, plan, approval, sources = sample_frontdesk_artifacts()
            result = compile_frontdesk_artifacts(
                semantic_lock=semantic_lock,
                mission_brief=brief,
                profile_recommendations=profiles,
                mission_plan=plan,
                approval=approval,
                sanitized_sources=sources,
                workspace=tempdir,
            )
            mission_payload = json.loads((Path(tempdir) / result.mission_ir_ref).read_text(encoding="utf-8"))
            mission = MissionIR.from_dict(mission_payload)

            self.assertEqual(mission.objective.summary, "Create a package README.")
            self.assertEqual(mission.outputs["required_artifacts"], ["package/README.md"])
            self.assertEqual(mission.inputs["excluded_source_refs"], ["frontdesk/conversation.jsonl"])
            self.assertTrue(result.contract_hash.startswith("sha256:"))

    def test_generated_mission_ir_freezes_deterministically(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            artifacts = sample_frontdesk_artifacts()
            first = compile_frontdesk_artifacts(
                semantic_lock=artifacts[0],
                mission_brief=artifacts[1],
                profile_recommendations=artifacts[2],
                mission_plan=artifacts[3],
                approval=artifacts[4],
                sanitized_sources=artifacts[5],
                workspace=tempdir,
            )
            second = compile_frontdesk_artifacts(
                semantic_lock=artifacts[0],
                mission_brief=artifacts[1],
                profile_recommendations=artifacts[2],
                mission_plan=artifacts[3],
                approval=artifacts[4],
                sanitized_sources=artifacts[5],
                workspace=tempdir,
            )
            mission = MissionIR.from_dict(json.loads((Path(tempdir) / first.mission_ir_ref).read_text(encoding="utf-8")))

            self.assertEqual(first.contract_hash, second.contract_hash)
            self.assertEqual(first.contract_hash, freeze_mission(mission).contract_hash)


if __name__ == "__main__":
    unittest.main()
