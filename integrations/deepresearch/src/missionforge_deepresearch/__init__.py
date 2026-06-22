"""Thin academic DeepResearch integration for MissionForge."""

from .kernel_v2 import (
    DeepResearchKernelV2Result,
    KernelV2FixtureAdapter,
    build_deepresearch_kernel_v2_flow,
    run_deepresearch_kernel_v2,
)
from .product_contract import AcademicResearchRequest, ResearchIntensity, ResearchIntensityProfile, research_intensity_profile

__all__ = [
    "AcademicResearchRequest",
    "DeepResearchKernelV2Result",
    "KernelV2FixtureAdapter",
    "ResearchIntensity",
    "ResearchIntensityProfile",
    "build_deepresearch_kernel_v2_flow",
    "research_intensity_profile",
    "run_deepresearch_kernel_v2",
]
