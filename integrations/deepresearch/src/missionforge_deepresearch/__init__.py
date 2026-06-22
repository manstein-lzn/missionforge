"""Thin academic DeepResearch integration for MissionForge."""

from .kernel_v2 import (
    DeepResearchKernelV2Result,
    KernelV2FixtureAdapter,
    build_deepresearch_kernel_v2_flow,
    deepresearch_kernel_v2_flow_run_id,
    run_deepresearch_kernel_v2,
)
from .frontdesk import (
    DeepResearchFrontDeskResult,
    FrontDeskFixtureAdapter,
    approve_frontdesk_requirements,
    run_deepresearch_frontdesk_turn,
)
from .product_contract import AcademicResearchRequest, ResearchIntensity, ResearchIntensityProfile, research_intensity_profile
from .tui import FrontDeskTuiConfig, run_frontdesk_tui

__all__ = [
    "AcademicResearchRequest",
    "DeepResearchFrontDeskResult",
    "DeepResearchKernelV2Result",
    "FrontDeskFixtureAdapter",
    "FrontDeskTuiConfig",
    "KernelV2FixtureAdapter",
    "ResearchIntensity",
    "ResearchIntensityProfile",
    "approve_frontdesk_requirements",
    "build_deepresearch_kernel_v2_flow",
    "deepresearch_kernel_v2_flow_run_id",
    "research_intensity_profile",
    "run_deepresearch_frontdesk_turn",
    "run_deepresearch_kernel_v2",
    "run_frontdesk_tui",
]
