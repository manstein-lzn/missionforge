"""Seed-paper and seed-PDF artifact helpers for DeepResearch."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from hashlib import sha256
from pathlib import Path
import re
import shutil
from typing import Any, Mapping

import missionforge as mf


SEED_PAPERS_SCHEMA_VERSION = "missionforge_deepresearch.seed_papers.v1"
SEED_PDF_INDEX_SCHEMA_VERSION = "missionforge_deepresearch.seed_pdf_index.v1"
SEED_SOURCE_PACKET_SCHEMA_VERSION = "missionforge_deepresearch.seed_source_packet.v1"
SEED_CONTROL_SCHEMA_VERSION = "missionforge_deepresearch.seed_control.v1"

KERNEL_V2_SEED_NORMALIZER_BRIEF_REF = "manuals/seed_normalizer.md"
KERNEL_V2_SEED_PAPERS_REF = "inputs/seed_papers.json"
KERNEL_V2_SEED_PDF_INDEX_REF = "inputs/seed_pdf_index.json"
KERNEL_V2_SEED_SOURCE_PACKET_REF = "sources/seed_source_packet.json"
KERNEL_V2_SEED_GAPS_REF = "reports/seed_gaps.md"
KERNEL_V2_SEED_CONTROL_REF = "state/seed_control.json"


def has_seed_inputs(request: Any) -> bool:
    """Return true when a request has seed papers or seed PDFs."""

    return bool(getattr(request, "seed_papers", []) or getattr(request, "seed_pdf_refs", []))


def seed_papers_payload(request: Any) -> dict[str, Any]:
    """Return normalized seed-paper input payload from the frozen request."""

    return {
        "schema_version": SEED_PAPERS_SCHEMA_VERSION,
        "request_id": str(getattr(request, "request_id", "")),
        "seed_papers": [_seed_paper_dict(item) for item in getattr(request, "seed_papers", [])],
    }


def seed_pdf_index_payload(request: Any, *, root: Path, run_root: Path) -> dict[str, Any]:
    """Stage available seed PDFs into the run workspace and return an index."""

    entries = []
    for index, ref in enumerate(getattr(request, "seed_pdf_refs", []), start=1):
        original_ref = mf.validate_ref(ref, "seed_pdf_refs[]")
        source_path = _resolve_workspace_ref(root, original_ref)
        staging_prefix_ref = _seed_pdf_staging_prefix(index, original_ref)
        parser_output_prefix_ref = _seed_pdf_parser_output_prefix(index, original_ref)
        staged_pdf_ref = f"{staging_prefix_ref}/source.pdf"
        staged_path = _resolve_workspace_ref(run_root, staged_pdf_ref)
        diagnostics: list[str] = []
        available = False
        digest = ""
        byte_length = 0
        if source_path.is_file():
            staged_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source_path, staged_path)
            data = staged_path.read_bytes()
            available = True
            digest = "sha256:" + sha256(data).hexdigest()
            byte_length = len(data)
        else:
            run_root_source_path = _resolve_workspace_ref(run_root, original_ref)
            if run_root_source_path.is_file():
                data = run_root_source_path.read_bytes()
                available = True
                staged_pdf_ref = original_ref
                digest = "sha256:" + sha256(data).hexdigest()
                byte_length = len(data)
            else:
                diagnostics.append("seed_pdf_missing")
        entries.append(
            {
                "seed_pdf_id": f"PDF{index}",
                "original_ref": original_ref,
                "staged_pdf_ref": staged_pdf_ref,
                "parser_output_prefix_ref": parser_output_prefix_ref,
                "parse_result_ref": f"{parser_output_prefix_ref}/parse_result.json",
                "manifest_ref": f"{parser_output_prefix_ref}/manifest.json",
                "tei_ref": f"{parser_output_prefix_ref}/grobid.tei.xml",
                "diagnostics_ref": f"{parser_output_prefix_ref}/diagnostics.json",
                "metadata_ref": f"{parser_output_prefix_ref}/metadata.json",
                "sections_ref": f"{parser_output_prefix_ref}/sections.json",
                "references_ref": f"{parser_output_prefix_ref}/references.json",
                "provenance_ref": f"{parser_output_prefix_ref}/provenance.json",
                "available": available,
                "sha256": digest,
                "byte_length": byte_length,
                "diagnostics": diagnostics,
            }
        )
    return {
        "schema_version": SEED_PDF_INDEX_SCHEMA_VERSION,
        "request_id": str(getattr(request, "request_id", "")),
        "entries": entries,
    }


def _resolve_workspace_ref(root: Path, ref: str) -> Path:
    safe_ref = mf.validate_ref(ref, "seed_pdf_ref")
    root_path = root.resolve()
    candidate = (root_path / safe_ref).resolve(strict=False)
    try:
        candidate.relative_to(root_path)
    except ValueError:
        raise mf.ContractValidationError("seed_pdf_ref must stay under the workspace root") from None
    return candidate


def fixture_seed_source_packet(request_payload: Mapping[str, Any], seed_pdf_index: Mapping[str, Any]) -> dict[str, Any]:
    """Return a structural seed source packet for fixture runs."""

    records = []
    for index, seed in enumerate(request_payload.get("seed_papers", []), start=1):
        if not isinstance(seed, Mapping):
            continue
        kind = str(seed.get("kind") or "seed")
        value = str(seed.get("value") or "").strip()
        if not value:
            continue
        records.append(
            {
                "source_id": f"SEED{index}",
                "title": value if kind == "title" else f"Seed {kind}: {value}",
                "source_type": f"seed_{kind}",
                "locator": value,
                "evidence_note": "User-provided seed paper; fixture mode does not resolve live metadata.",
                "evidence_strength": "seed_metadata",
            }
        )
    pdf_offset = len(records)
    for index, entry in enumerate(seed_pdf_index.get("entries", []), start=1):
        if not isinstance(entry, Mapping):
            continue
        if entry.get("available") is not True:
            continue
        records.append(
            {
                "source_id": f"SEED{pdf_offset + index}",
                "title": f"Seed PDF {entry.get('seed_pdf_id') or index}",
                "source_type": "seed_pdf",
                "locator": str(entry.get("staged_pdf_ref") or entry.get("original_ref") or ""),
                "evidence_note": "User-provided seed PDF; parse diagnostics are tracked separately.",
                "evidence_strength": "pdf_seed",
                "parse_refs": _seed_pdf_parse_refs(entry),
            }
        )
    return {
        "schema_version": SEED_SOURCE_PACKET_SCHEMA_VERSION,
        "request_id": str(request_payload.get("request_id") or ""),
        "source_records": records,
    }


def no_seed_source_packet(request: Any) -> dict[str, Any]:
    """Return an explicit empty seed packet for requests without seed inputs."""

    return {
        "schema_version": SEED_SOURCE_PACKET_SCHEMA_VERSION,
        "request_id": str(getattr(request, "request_id", "")),
        "source_records": [],
    }


def fixture_seed_gaps(seed_pdf_index: Mapping[str, Any]) -> str:
    """Return a compact seed gap report for fixture runs."""

    lines = ["# Seed Input Gaps", ""]
    missing = [
        str(entry.get("original_ref"))
        for entry in seed_pdf_index.get("entries", [])
        if isinstance(entry, Mapping) and not entry.get("available")
    ]
    if missing:
        lines.append("Missing seed PDFs:")
        lines.extend(f"- {ref}" for ref in missing)
    else:
        lines.append("No fixture seed input gaps.")
    return "\n".join(lines) + "\n"


def no_seed_gaps() -> str:
    """Return a compact no-seed gap report."""

    return "# Seed Input Gaps\n\nNo seed inputs were provided.\n"


def fixture_seed_control() -> dict[str, Any]:
    """Return a seed-normalizer handoff decision."""

    return {
        "schema_version": SEED_CONTROL_SCHEMA_VERSION,
        "decision": "ready_for_source_mapping",
        "seed_source_packet_ref": KERNEL_V2_SEED_SOURCE_PACKET_REF,
        "seed_gaps_ref": KERNEL_V2_SEED_GAPS_REF,
    }


def no_seed_control() -> dict[str, Any]:
    """Return an explicit no-op seed control artifact for requests without seeds."""

    return {
        "schema_version": SEED_CONTROL_SCHEMA_VERSION,
        "decision": "not_applicable",
        "seed_source_packet_ref": KERNEL_V2_SEED_SOURCE_PACKET_REF,
        "seed_gaps_ref": KERNEL_V2_SEED_GAPS_REF,
    }


def _seed_pdf_parse_refs(entry: Mapping[str, Any]) -> dict[str, str]:
    fields = [
        "parse_result_ref",
        "manifest_ref",
        "tei_ref",
        "diagnostics_ref",
        "metadata_ref",
        "sections_ref",
        "references_ref",
        "provenance_ref",
    ]
    return {field: str(entry.get(field) or "") for field in fields}


def _seed_paper_dict(item: Any) -> dict[str, str]:
    if hasattr(item, "to_dict"):
        return dict(item.to_dict())
    if is_dataclass(item):
        return {key: str(value) for key, value in asdict(item).items()}
    if isinstance(item, Mapping):
        return {
            "kind": str(item.get("kind", "")),
            "value": str(item.get("value", "")),
            "note": str(item.get("note", "")),
        }
    return {"kind": "", "value": str(item), "note": ""}


def _seed_pdf_staging_prefix(index: int, ref: str) -> str:
    name = Path(ref).name or f"seed-{index}.pdf"
    stem = re.sub(r"[^A-Za-z0-9._-]+", "-", Path(name).stem).strip(".-") or f"seed-{index}"
    return f"inputs/seed_pdfs/{index:03d}-{stem}"


def _seed_pdf_parser_output_prefix(index: int, ref: str) -> str:
    name = Path(ref).name or f"seed-{index}.pdf"
    stem = re.sub(r"[^A-Za-z0-9._-]+", "-", Path(name).stem).strip(".-") or f"seed-{index}"
    return f"sources/seed_pdfs/{index:03d}-{stem}"
