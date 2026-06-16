"""Search-intent contract for the DeepResearch integration.

Search intent is semantic authoring. Python validates the shape and then the
collector executes the declared queries mechanically.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from missionforge.contracts import (
    ContractValidationError,
    require_mapping,
    require_non_empty_str,
    require_str_list,
    stable_json_hash,
    validate_ref,
)
from missionforge.piworker_call import PiWorkerCall, PiWorkerCallResult, PiWorkerCallResultStatus, PiWorkerCallRole
from missionforge.piworker_runtime import PiWorkerCallAdapter, run_piworker_call
from missionforge.runtime_results import ExecutionReport, WorkerAdapterResult, WorkerResult

from .product_contract import AcademicResearchRequest, research_intensity_profile
from .workspace import read_json_ref, write_json_ref, write_text_ref


SEARCH_INTENT_SCHEMA_VERSION = "missionforge_deepresearch.search_intent.v1"
SEARCH_INTENT_REF = "sources/search_intent.json"
SEARCH_INTENT_CONTRACT_REF = "sources/search_intent_contract.json"
SEARCH_INTENT_MANUAL_REF = "sources/search_intent_manual.md"
SEARCH_INTENT_SCHEMA_REF = "sources/search_intent_schema.json"
SEARCH_INTENT_CALL_REF = "attempts/search_intent/piworker_call.json"
SEARCH_INTENT_CALL_RESULT_REF = "attempts/search_intent/piworker_call_result.json"
SEARCH_INTENT_EXECUTION_REPORT_REF = "attempts/search_intent/execution_report.json"
SEARCH_INTENT_METRICS_REF = "attempts/search_intent/metrics.json"
SEARCH_INTENT_VALIDATION_REPORT_REF = "sources/search_intent_validation.json"
MAX_SEARCH_QUERIES = 12


@dataclass(frozen=True)
class AcademicSearchIntent:
    """LLM- or user-authored academic search query plan."""

    request_id: str
    topic: str
    language: str
    queries: list[str]
    created_by: str = "external"
    notes: list[str] = field(default_factory=list)
    schema_version: str = SEARCH_INTENT_SCHEMA_VERSION

    @classmethod
    def from_queries(
        cls,
        request: AcademicResearchRequest,
        queries: list[str],
        *,
        created_by: str = "external",
        notes: list[str] | None = None,
    ) -> "AcademicSearchIntent":
        request.validate()
        intent = cls(
            request_id=request.request_id,
            topic=request.topic,
            language=request.language,
            queries=_dedupe_query_texts(queries),
            created_by=created_by,
            notes=list(notes or []),
        )
        intent.validate_for_request(request)
        return intent

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "AcademicSearchIntent":
        data = require_mapping(payload, "academic_search_intent")
        unknown = sorted(set(data) - {"schema_version", "request_id", "topic", "language", "queries", "created_by", "notes"})
        if unknown:
            raise ContractValidationError(f"academic_search_intent contains unknown fields: {unknown}")
        intent = cls(
            schema_version=require_non_empty_str(
                data.get("schema_version", SEARCH_INTENT_SCHEMA_VERSION),
                "academic_search_intent.schema_version",
            ),
            request_id=require_non_empty_str(data.get("request_id"), "academic_search_intent.request_id"),
            topic=require_non_empty_str(data.get("topic"), "academic_search_intent.topic"),
            language=require_non_empty_str(data.get("language"), "academic_search_intent.language"),
            queries=_queries_from_payload(data.get("queries", [])),
            created_by=require_non_empty_str(data.get("created_by", "external"), "academic_search_intent.created_by"),
            notes=require_str_list(data.get("notes", []), "academic_search_intent.notes"),
        )
        intent.validate()
        return intent

    def validate(self) -> None:
        if self.schema_version != SEARCH_INTENT_SCHEMA_VERSION:
            raise ContractValidationError("academic_search_intent.schema_version is unsupported")
        require_non_empty_str(self.request_id, "academic_search_intent.request_id")
        validate_ref(f"runs/{self.request_id}", "academic_search_intent.request_id")
        if "/" in self.request_id:
            raise ContractValidationError("academic_search_intent.request_id must be one ref segment")
        require_non_empty_str(self.topic, "academic_search_intent.topic")
        require_non_empty_str(self.language, "academic_search_intent.language")
        require_non_empty_str(self.created_by, "academic_search_intent.created_by")
        if self.created_by not in {"external", "piworker"}:
            raise ContractValidationError("academic_search_intent.created_by must be external or piworker")
        queries = _dedupe_query_texts(self.queries)
        if len(queries) != len(self.queries):
            raise ContractValidationError("academic_search_intent.queries must not contain duplicates")
        if not queries:
            raise ContractValidationError("academic_search_intent.queries must contain at least one query")
        if len(queries) > MAX_SEARCH_QUERIES:
            raise ContractValidationError(f"academic_search_intent.queries must contain at most {MAX_SEARCH_QUERIES} queries")
        require_str_list(self.notes, "academic_search_intent.notes")

    def validate_for_request(self, request: AcademicResearchRequest) -> None:
        self.validate()
        request.validate()
        if self.request_id != request.request_id:
            raise ContractValidationError("academic_search_intent.request_id must match request.request_id")
        if self.topic != request.topic:
            raise ContractValidationError("academic_search_intent.topic must match request.topic")
        if self.language != request.language:
            raise ContractValidationError("academic_search_intent.language must match request.language")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "schema_version": self.schema_version,
            "request_id": self.request_id,
            "topic": self.topic,
            "language": self.language,
            "queries": list(self.queries),
            "created_by": self.created_by,
            "notes": list(self.notes),
        }


@dataclass(frozen=True)
class SearchIntentGenerationResult:
    """Search-intent artifact and PiWorker evidence refs."""

    search_intent: AcademicSearchIntent
    call_result: PiWorkerCallResult
    evidence_refs: list[str] = field(default_factory=list)


def generate_search_intent_with_piworker(
    request: AcademicResearchRequest,
    *,
    workspace: str | Path,
    adapter: PiWorkerCallAdapter,
) -> SearchIntentGenerationResult:
    """Ask a PiWorker to author search intent for a live academic collection."""

    request.validate()
    root = Path(workspace).resolve()
    root.mkdir(parents=True, exist_ok=True)
    contract_payload = _search_intent_contract_payload(request)
    write_json_ref(root, "product_contract/research_request.json", request.to_dict())
    write_json_ref(root, SEARCH_INTENT_CONTRACT_REF, contract_payload)
    write_json_ref(root, SEARCH_INTENT_SCHEMA_REF, search_intent_schema_payload())
    write_text_ref(root, SEARCH_INTENT_MANUAL_REF, _search_intent_manual_text())
    call = PiWorkerCall(
        call_id=f"deepresearch-{request.request_id}-search-intent",
        role=PiWorkerCallRole.FRONTDESK_AUTHOR,
        contract_id=f"deepresearch-{request.request_id}-search-intent-contract",
        contract_hash=stable_json_hash(contract_payload),
        contract_ref=SEARCH_INTENT_CONTRACT_REF,
        objective=(
            "Write a general academic search intent JSON artifact for the research topic. "
            "Do not collect sources and do not write the final report."
        ),
        visible_refs=[
            "product_contract/research_request.json",
            SEARCH_INTENT_CONTRACT_REF,
            SEARCH_INTENT_SCHEMA_REF,
            SEARCH_INTENT_MANUAL_REF,
        ],
        writable_refs=["sources", "attempts"],
        expected_output_refs=[SEARCH_INTENT_REF],
        source_packet_ref="product_contract/research_request.json",
        source_packet_hash=stable_json_hash(request.to_dict()),
        output_schema_ref=SEARCH_INTENT_SCHEMA_REF,
        validation_policy_ref=SEARCH_INTENT_CONTRACT_REF,
        runtime_budget={"max_turns": _search_intent_max_turns(request)},
        metadata={
            "phase": "deepresearch_search_intent",
            "artifact_ref": SEARCH_INTENT_REF,
            "research_intensity": request.research_intensity.value,
        },
    )
    write_json_ref(root, SEARCH_INTENT_CALL_REF, call.to_dict())
    call_result = run_piworker_call(
        call,
        workspace=root,
        adapter=adapter,
        result_id=f"{call.call_id}-result",
        metadata={"phase": "deepresearch_search_intent"},
        exit_criteria=[f"Write valid search intent JSON at {SEARCH_INTENT_REF}."],
        stop_conditions=["Stop if the requested topic cannot be turned into general academic search queries."],
    )
    write_json_ref(root, SEARCH_INTENT_CALL_RESULT_REF, call_result.to_dict())
    intent = _load_valid_search_intent(root, request)
    if call_result.status is not PiWorkerCallResultStatus.COMPLETED:
        write_json_ref(
            root,
            SEARCH_INTENT_VALIDATION_REPORT_REF,
            {
                "schema_version": "missionforge_deepresearch.search_intent_validation.v1",
                "status": "accepted_valid_artifact_after_runtime_failure",
                "request_id": request.request_id,
                "search_intent_ref": SEARCH_INTENT_REF,
                "call_result_ref": SEARCH_INTENT_CALL_RESULT_REF,
                "execution_report_ref": call_result.execution_report_ref,
                "call_status": call_result.status.value,
                "notes": [
                    "The PiWorker call did not report completed, but it wrote a valid search intent artifact.",
                    "MissionForge keeps the runtime failure evidence and proceeds with the validated artifact.",
                ],
            },
        )
    else:
        write_json_ref(
            root,
            SEARCH_INTENT_VALIDATION_REPORT_REF,
            {
                "schema_version": "missionforge_deepresearch.search_intent_validation.v1",
                "status": "accepted",
                "request_id": request.request_id,
                "search_intent_ref": SEARCH_INTENT_REF,
                "call_result_ref": SEARCH_INTENT_CALL_RESULT_REF,
                "execution_report_ref": call_result.execution_report_ref,
                "call_status": call_result.status.value,
                "notes": ["The PiWorker call completed and wrote a valid search intent artifact."],
            },
        )
    return SearchIntentGenerationResult(
        search_intent=intent,
        call_result=call_result,
        evidence_refs=[
            SEARCH_INTENT_CALL_REF,
            SEARCH_INTENT_CALL_RESULT_REF,
            call_result.execution_report_ref,
            SEARCH_INTENT_VALIDATION_REPORT_REF,
        ],
    )


class FixtureSearchIntentAdapter:
    """Offline adapter for tests and package shape checks only."""

    adapter_family = "fixture_deepresearch_search_intent"

    def run_call(
        self,
        call: PiWorkerCall,
        *,
        workspace: str | Path = ".",
        evidence_store: Any | None = None,
        call_spec: Any | None = None,
        exit_criteria: list[str] | None = None,
        stop_conditions: list[str] | None = None,
        extension_lock_ref: str | None = None,
    ) -> WorkerAdapterResult:
        call.validate()
        if call.role is not PiWorkerCallRole.FRONTDESK_AUTHOR:
            raise ContractValidationError("fixture search-intent adapter only supports frontdesk author calls")
        root = Path(workspace).resolve()
        request = AcademicResearchRequest.from_dict(read_json_ref(root, "product_contract/research_request.json", "research_request"))
        intent = AcademicSearchIntent.from_queries(
            request,
            [request.topic],
            created_by="piworker",
            notes=["Fixture adapter preserves the original topic only."],
        )
        write_json_ref(root, SEARCH_INTENT_REF, intent.to_dict())
        metrics = {"metric_ref": SEARCH_INTENT_METRICS_REF, "fixture": True, "query_count": len(intent.queries)}
        write_json_ref(root, SEARCH_INTENT_METRICS_REF, metrics)
        execution_report = ExecutionReport(
            report_id="deepresearch-fixture-search-intent-execution-report",
            call_id=call.call_id,
            status="completed",
            produced_artifacts=[SEARCH_INTENT_REF],
            changed_refs=[SEARCH_INTENT_REF, SEARCH_INTENT_EXECUTION_REPORT_REF, SEARCH_INTENT_METRICS_REF],
            evidence_refs=["product_contract/research_request.json"],
            worker_claims=["fixture search intent produced"],
            metrics=metrics,
        )
        write_json_ref(root, SEARCH_INTENT_EXECUTION_REPORT_REF, execution_report.to_dict())
        return WorkerAdapterResult(
            execution_report=execution_report,
            worker_result=WorkerResult(status="completed", execution_report_ref=SEARCH_INTENT_EXECUTION_REPORT_REF),
            event_evidence_refs=[],
            metrics=metrics,
        )


def search_intent_schema_payload() -> dict[str, Any]:
    return {
        "schema_version": "missionforge_deepresearch.search_intent_schema.v1",
        "expected_artifact_ref": SEARCH_INTENT_REF,
        "required_fields": ["schema_version", "request_id", "topic", "language", "queries", "created_by", "notes"],
        "rules": [
            "Write a JSON object only.",
            f"schema_version must be {SEARCH_INTENT_SCHEMA_VERSION}.",
            "request_id, topic, and language must exactly match product_contract/research_request.json.",
            f"queries must contain 1 to {MAX_SEARCH_QUERIES} general academic search strings.",
            "queries may be multilingual or translated when useful.",
            "created_by must be piworker.",
            "Do not include source results, summaries, citations, or final-report content.",
        ],
        "example_shape": {
            "schema_version": SEARCH_INTENT_SCHEMA_VERSION,
            "request_id": "<same as request>",
            "topic": "<same as request>",
            "language": "<same as request>",
            "queries": ["<academic search query>"],
            "created_by": "piworker",
            "notes": ["<brief note about search coverage>"],
        },
    }


def _search_intent_contract_payload(request: AcademicResearchRequest) -> dict[str, Any]:
    return {
        "schema_version": "missionforge_deepresearch.search_intent_contract.v1",
        "request_id": request.request_id,
        "topic": request.topic,
        "language": request.language,
        "objective": "Prepare the live academic collector's query plan.",
        "expected_output_ref": SEARCH_INTENT_REF,
        "manual_ref": SEARCH_INTENT_MANUAL_REF,
        "schema_ref": SEARCH_INTENT_SCHEMA_REF,
    }


def _search_intent_manual_text() -> str:
    return """# Academic Search Intent Manual

You are preparing the query plan for a live academic deep research collector.

Write only `sources/search_intent.json`.

Create a small set of high-recall academic search queries for the user's topic.
Use expert judgment. Translate or normalize terms when useful, split broad
topics into complementary queries, and avoid overfitting to one provider.

Do not collect sources, cite papers, summarize the field, or write the final
report. The collector will execute your queries mechanically.
"""


def _search_intent_max_turns(request: AcademicResearchRequest) -> int:
    return research_intensity_profile(request.research_intensity).search_intent_max_turns


def _load_valid_search_intent(root: Path, request: AcademicResearchRequest) -> AcademicSearchIntent:
    try:
        intent = AcademicSearchIntent.from_dict(read_json_ref(root, SEARCH_INTENT_REF, "academic_search_intent"))
        intent.validate_for_request(request)
        return intent
    except Exception as exc:
        raise ContractValidationError("search-intent PiWorker did not produce a valid search intent artifact") from exc


def _queries_from_payload(value: Any) -> list[str]:
    if isinstance(value, list) and all(isinstance(item, Mapping) for item in value):
        texts: list[str] = []
        for index, item in enumerate(value):
            texts.append(require_non_empty_str(item.get("query"), f"academic_search_intent.queries[{index}].query"))
        return _dedupe_query_texts(texts)
    return _dedupe_query_texts(require_str_list(value, "academic_search_intent.queries"))


def _dedupe_query_texts(queries: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for query in queries:
        text = require_non_empty_str(query, "academic_search_intent.queries[]")
        if len(text) > 240:
            raise ContractValidationError("academic_search_intent.queries[] must be at most 240 characters")
        key = text.casefold()
        if key not in seen:
            result.append(text)
            seen.add(key)
    return result
