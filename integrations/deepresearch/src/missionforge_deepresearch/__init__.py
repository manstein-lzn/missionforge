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
from .product_contract import AcademicResearchRequest, DeepResearchRunResult, DeepResearchRunStatus
from .quality_evaluation import (
    DeepResearchQualityEvaluationResult,
    FixtureDirectBaselineAdapter,
    FixtureQualityEvaluatorAdapter,
    load_deepresearch_quality_evaluation_result,
    run_deepresearch_quality_evaluation,
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
    "DeepResearchTaskContractCompileResult",
    "DeepResearchQualityEvaluationResult",
    "DeepResearchFinalPackage",
    "DeepResearchJudgeReport",
    "DeepResearchJudgedRunResult",
    "FixtureAcademicResearcherAdapter",
    "FixtureDirectBaselineAdapter",
    "FixtureDeepResearchJudgeAdapter",
    "FixtureQualityEvaluatorAdapter",
    "compile_deepresearch_academic_task_contract",
    "judge_deepresearch_run",
    "load_deepresearch_final_package",
    "load_deepresearch_judged_run_result",
    "load_deepresearch_quality_evaluation_result",
    "load_deepresearch_run_result",
    "load_deepresearch_task_contract",
    "run_deepresearch_academic_judged",
    "run_deepresearch_quality_evaluation",
    "run_deepresearch_academic_single_agent",
]
