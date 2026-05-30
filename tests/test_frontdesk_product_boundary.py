from __future__ import annotations

import ast
from pathlib import Path
import unittest

from missionforge.frontdesk import CompilerReadiness, InquirySlot, ProductInquiryProfile, SlotRequirement, SlotTargetMapping, SlotValueType
from missionforge.product_gate import ProductGateCheck


CORE_ROOT = Path("src/missionforge")
FRONTDESK_ROOT = CORE_ROOT / "frontdesk"
ADAPTER_ROOT = CORE_ROOT / "adapters"


class FrontDeskProductBoundaryTests(unittest.TestCase):
    def test_core_does_not_import_skillfoundry_integration(self) -> None:
        violations: list[str] = []
        for path in CORE_ROOT.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name.split(".", 1)[0] == "missionforge_skillfoundry":
                            violations.append(f"{path}: import {alias.name}")
                elif isinstance(node, ast.ImportFrom):
                    module = node.module or ""
                    if module.split(".", 1)[0] == "missionforge_skillfoundry":
                        violations.append(f"{path}: from {module} import ...")

        self.assertEqual(violations, [])

    def test_frontdesk_core_has_no_product_name_branches(self) -> None:
        violations = [
            str(path)
            for path in FRONTDESK_ROOT.rglob("*.py")
            if "skillfoundry" in path.read_text(encoding="utf-8").lower()
        ]

        self.assertEqual(violations, [])

    def test_adapters_have_no_product_specific_adapter_modules(self) -> None:
        forbidden = [ADAPTER_ROOT / "skillfoundry.py", ADAPTER_ROOT / "codexarium.py"]

        self.assertEqual([str(path) for path in forbidden if path.exists()], [])

    def test_product_profile_data_may_contain_skillfoundry(self) -> None:
        profile = ProductInquiryProfile(
            product_id="skillfoundry",
            version="v1",
            display_name="SkillFoundry",
            slots=[
                InquirySlot(
                    slot_id="goal",
                    question="What should the skill do?",
                    requirement=SlotRequirement.BLOCKING,
                    value_type=SlotValueType.FREE_TEXT,
                    maps_to=[SlotTargetMapping(target="skillfoundry.request.goal")],
                )
            ],
            compiler_readiness=CompilerReadiness(blocking_slot_ids=["goal"]),
        )

        self.assertEqual(ProductInquiryProfile.from_dict(profile.to_dict()).product_id, "skillfoundry")

    def test_product_check_ids_are_opaque_to_core(self) -> None:
        check = ProductGateCheck(check_id="SF-PROMPT-NO-RAW-CONTEXT", purpose="Opaque check id.")

        self.assertEqual(check.to_dict()["check_id"], "SF-PROMPT-NO-RAW-CONTEXT")


if __name__ == "__main__":
    unittest.main()
