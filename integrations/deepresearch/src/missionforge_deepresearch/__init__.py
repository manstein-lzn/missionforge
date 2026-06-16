"""Thin academic DeepResearch integration for MissionForge."""

from .compiler import (
    DeepResearchTaskContractCompileResult,
    compile_deepresearch_academic_task_contract,
    load_deepresearch_task_contract,
)
from .judging import (
    DeepResearchFinalPackage,
    DeepResearchJudgeReport,
    DeepResearchJudgedRunResult,
    FixtureDeepResearchJudgeAdapter,
    judge_deepresearch_run,
    load_deepresearch_final_package,
    load_deepresearch_judged_run_result,
    run_deepresearch_academic_judged,
)
from .minimal import (
    MinimalDeepResearchResult,
    MinimalDeepResearchLoopResult,
    MinimalFixtureResearcherAdapter,
    MinimalFixtureReviewerAdapter,
    run_deepresearch_minimal,
    run_deepresearch_minimal_loop,
)
from .product_contract import (
    AcademicResearchRequest,
    DeepResearchReviewedRunStatus,
    DeepResearchReviewedRunResult,
    DeepResearchRunResult,
    DeepResearchRunStatus,
    ResearchIntensity,
    ResearchIntensityProfile,
    research_intensity_profile,
)
from .runtime import (
    FixtureAcademicResearcherAdapter,
    load_deepresearch_run_result,
    run_deepresearch_academic_single_agent,
)

__all__ = [
    "AcademicResearchRequest",
    "DeepResearchRunResult",
    "DeepResearchRunStatus",
    "DeepResearchReviewedRunResult",
    "DeepResearchReviewedRunStatus",
    "DeepResearchTaskContractCompileResult",
    "ResearchIntensity",
    "ResearchIntensityProfile",
    "DeepResearchFinalPackage",
    "DeepResearchJudgeReport",
    "DeepResearchJudgedRunResult",
    "MinimalDeepResearchResult",
    "MinimalDeepResearchLoopResult",
    "FixtureAcademicResearcherAdapter",
    "FixtureDeepResearchJudgeAdapter",
    "MinimalFixtureResearcherAdapter",
    "MinimalFixtureReviewerAdapter",
    "compile_deepresearch_academic_task_contract",
    "judge_deepresearch_run",
    "load_deepresearch_final_package",
    "load_deepresearch_judged_run_result",
    "load_deepresearch_run_result",
    "load_deepresearch_task_contract",
    "run_deepresearch_academic_judged",
    "run_deepresearch_academic_single_agent",
    "run_deepresearch_minimal",
    "run_deepresearch_minimal_loop",
    "research_intensity_profile",
]
