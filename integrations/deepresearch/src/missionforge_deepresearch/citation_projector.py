"""Mechanical citation projection for DeepResearch reports."""

from __future__ import annotations

import re
from typing import Any, Mapping

import missionforge as mf


CITATION_REGISTRY_SCHEMA_VERSION = "missionforge_deepresearch.citation_registry.v1"
REPORT_CITATION_MAP_SCHEMA_VERSION = "missionforge_deepresearch.report_citation_map.v1"
CITATION_PROJECTION_VALIDATION_SCHEMA_VERSION = "missionforge_deepresearch.citation_projection_validation.v1"


SOURCE_CITATION_PATTERN = re.compile(r"\[(S\d+)\]")
PROJECTED_CITATION_PATTERN = re.compile(r"\[cite:\s*(\d+)\]\(#ref-\1\)")


def project_report_citations(
    *,
    markdown: str,
    canonical_sources_payload: Mapping[str, Any],
) -> dict[str, Any]:
    """Project source-id citations to numbered clickable citation anchors."""

    sources = canonical_sources_payload.get("sources", [])
    if not isinstance(sources, list):
        raise mf.ContractValidationError("canonical_sources.sources must be a list")
    source_lookup = {
        str(source.get("source_id")): source
        for source in sources
        if isinstance(source, Mapping) and isinstance(source.get("source_id"), str)
    }
    citation_order = _citation_order(markdown)
    entries = []
    citation_map = []
    failures: list[str] = []
    source_to_number: dict[str, int] = {}
    for source_id in citation_order:
        source = source_lookup.get(source_id)
        if source is None:
            failures.append(f"unknown_source_id:{source_id}")
            continue
        number = len(source_to_number) + 1
        source_to_number[source_id] = number
        reference_markdown, primary_url, access_status = _reference_entry(number, source)
        if not primary_url:
            failures.append(f"source_without_locator:{source_id}")
        entries.append(
            {
                "citation_number": number,
                "anchor": f"ref-{number}",
                "source_id": source_id,
                "reference_markdown": reference_markdown,
                "primary_url": primary_url,
                "access_status": access_status,
            }
        )
        citation_map.append(
            {
                "source_id": source_id,
                "citation_number": number,
                "anchor": f"ref-{number}",
            }
        )
    projected_markdown = _rewrite_citations(markdown, source_to_number, failures)
    projected_markdown = _replace_references_section(projected_markdown, entries)
    validation = _validate_projected_markdown(projected_markdown, entries, failures)
    return {
        "projected_markdown": projected_markdown,
        "citation_registry": {
            "schema_version": CITATION_REGISTRY_SCHEMA_VERSION,
            "entries": entries,
        },
        "report_citation_map": {
            "schema_version": REPORT_CITATION_MAP_SCHEMA_VERSION,
            "entries": citation_map,
        },
        "validation": validation,
    }


def _citation_order(markdown: str) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for segment in _non_fenced_segments(_report_body(markdown)):
        for match in SOURCE_CITATION_PATTERN.finditer(segment):
            source_id = match.group(1)
            if source_id not in seen:
                seen.add(source_id)
                result.append(source_id)
    return result


def _rewrite_citations(markdown: str, source_to_number: Mapping[str, int], failures: list[str]) -> str:
    def replace(match: re.Match[str]) -> str:
        source_id = match.group(1)
        number = source_to_number.get(source_id)
        if number is None:
            failures.append(f"unprojected_source_id:{source_id}")
            return match.group(0)
        return f"[cite: {number}](#ref-{number})"

    body, references = _split_reference_section(markdown)
    rewritten: list[str] = []
    in_fence = False
    for line in body.splitlines(keepends=True):
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            rewritten.append(line)
            continue
        rewritten.append(line if in_fence else SOURCE_CITATION_PATTERN.sub(replace, line))
    return "".join(rewritten) + references


def _replace_references_section(markdown: str, entries: list[Mapping[str, Any]]) -> str:
    heading_match = re.search(r"(?m)^##\s+(参考文献|References)\s*$", markdown)
    reference_lines = ["## 参考文献", ""]
    reference_lines.extend(str(entry["reference_markdown"]) for entry in entries)
    reference_text = "\n".join(reference_lines).rstrip() + "\n"
    if not heading_match:
        return markdown.rstrip() + "\n\n" + reference_text
    return markdown[: heading_match.start()].rstrip() + "\n\n" + reference_text


def _reference_entry(number: int, source: Mapping[str, Any]) -> tuple[str, str, str]:
    title = _clean(source.get("title")) or f"Source {source.get('source_id', number)}"
    authors = ", ".join(_string_list(source.get("authors"))[:8])
    year = source.get("year")
    venue = _clean(source.get("venue"))
    primary_url, access_status = _primary_locator(source)
    parts = [f'<a id="ref-{number}"></a>[{number}] {title}.']
    if authors:
        parts.append(authors + ".")
    if venue or year:
        parts.append(", ".join([item for item in [venue, str(year) if year else ""] if item]) + ".")
    if primary_url:
        parts.append(primary_url)
    return " ".join(parts), primary_url, access_status


def _primary_locator(source: Mapping[str, Any]) -> tuple[str, str]:
    locators = source.get("locators")
    if isinstance(locators, list):
        for locator in locators:
            if not isinstance(locator, Mapping):
                continue
            url = _clean(locator.get("url"))
            if url:
                return url, _clean(locator.get("access_status")) or "unchecked"
    identifiers = source.get("identifiers")
    if isinstance(identifiers, Mapping):
        doi = _clean(identifiers.get("doi"))
        if doi:
            return f"https://doi.org/{doi}", "unchecked"
        arxiv = _clean(identifiers.get("arxiv"))
        if arxiv:
            return f"https://arxiv.org/abs/{arxiv}", "unchecked"
    return "", "inaccessible"


def _validate_projected_markdown(
    markdown: str,
    entries: list[Mapping[str, Any]],
    failures: list[str],
) -> dict[str, Any]:
    entry_numbers = [int(entry["citation_number"]) for entry in entries]
    if len(entry_numbers) != len(set(entry_numbers)):
        failures.append("duplicate_citation_number")
    projected_numbers = [int(match.group(1)) for match in PROJECTED_CITATION_PATTERN.finditer(markdown)]
    for number in projected_numbers:
        if number not in entry_numbers:
            failures.append(f"citation_without_reference:{number}")
    for number in entry_numbers:
        if f'<a id="ref-{number}"></a>' not in markdown:
            failures.append(f"missing_reference_anchor:{number}")
    if _contains_unprojected_source_citation(markdown):
        failures.append("unprojected_source_citation_present")
    unique_failures = []
    for failure in failures:
        if failure not in unique_failures:
            unique_failures.append(failure)
    return {
        "schema_version": CITATION_PROJECTION_VALIDATION_SCHEMA_VERSION,
        "status": "passed" if not unique_failures else "failed",
        "failure_codes": unique_failures,
    }


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [_clean(item) for item in value if _clean(item)]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", value).strip() if isinstance(value, str) else ""


def _report_body(markdown: str) -> str:
    body, _references = _split_reference_section(markdown)
    return body


def _split_reference_section(markdown: str) -> tuple[str, str]:
    heading_match = re.search(r"(?m)^##\s+(参考文献|References)\s*$", markdown)
    if not heading_match:
        return markdown, ""
    return markdown[: heading_match.start()], markdown[heading_match.start():]


def _non_fenced_segments(markdown: str) -> list[str]:
    segments: list[str] = []
    current: list[str] = []
    in_fence = False
    for line in markdown.splitlines(keepends=True):
        if line.lstrip().startswith("```"):
            if not in_fence and current:
                segments.append("".join(current))
                current = []
            in_fence = not in_fence
            continue
        if not in_fence:
            current.append(line)
    if current:
        segments.append("".join(current))
    return segments


def _contains_unprojected_source_citation(markdown: str) -> bool:
    return any(SOURCE_CITATION_PATTERN.search(segment) for segment in _non_fenced_segments(_report_body(markdown)))
