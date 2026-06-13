"""JSON workspace store backend."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .contracts import ContractValidationError, ensure_json_value, require_mapping, validate_ref
from .state import MissionRun, PiWorkerAttempt, load_mission_run, load_piworker_attempts, mission_run_refs_for_run_id


class JsonWorkspaceStore:
    """Default workspace-relative JSON/JSONL backend."""

    def __init__(self, workspace: str | Path = ".") -> None:
        self.workspace = Path(workspace)

    def write_mission_run(self, run: MissionRun) -> str:
        run.validate()
        ref = mission_run_refs_for_run_id(run.mission_run_id)["mission_run"]
        return self.write_json(ref, run.to_dict())

    def load_mission_run(self, mission_run_id: str | None = None) -> MissionRun:
        return load_mission_run(self.workspace, mission_run_id)

    def write_attempts(self, mission_run_id: str, attempts: list[PiWorkerAttempt]) -> str:
        ref = mission_run_refs_for_run_id(mission_run_id)["attempts"]
        return self.write_jsonl(ref, [attempt.to_dict() for attempt in attempts])

    def load_attempts(self, mission_run_id: str) -> list[PiWorkerAttempt]:
        return load_piworker_attempts(self.workspace, mission_run_id)

    def write_json(self, ref: str, payload: dict[str, Any]) -> str:
        data = ensure_json_value(require_mapping(payload, ref), ref)
        path = self._resolve(ref)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        return ref

    def read_json(self, ref: str) -> dict[str, Any]:
        return require_mapping(json.loads(self._resolve(ref).read_text(encoding="utf-8")), ref)

    def write_text(self, ref: str, text: str) -> str:
        if not isinstance(text, str):
            raise ContractValidationError("json store text payload must be a string")
        path = self._resolve(ref)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return ref

    def read_text(self, ref: str) -> str:
        return self._resolve(ref).read_text(encoding="utf-8")

    def write_jsonl(self, ref: str, payloads: list[dict[str, Any]], *, append: bool = False) -> str:
        path = self._resolve(ref)
        path.parent.mkdir(parents=True, exist_ok=True)
        mode = "a" if append else "w"
        with path.open(mode, encoding="utf-8") as handle:
            for payload in payloads:
                data = ensure_json_value(require_mapping(payload, f"{ref}[]"), f"{ref}[]")
                handle.write(json.dumps(data, sort_keys=True) + "\n")
        return ref

    def read_jsonl(self, ref: str) -> list[dict[str, Any]]:
        path = self._resolve(ref)
        if not path.is_file():
            return []
        records: list[dict[str, Any]] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                records.append(require_mapping(json.loads(line), f"{ref}[]"))
        return records

    def exists(self, ref: str) -> bool:
        return self._resolve(ref).is_file()

    def _resolve(self, ref: str) -> Path:
        safe_ref = validate_ref(ref, "json_store.ref")
        path = (self.workspace / safe_ref).resolve()
        workspace = self.workspace.resolve()
        if workspace not in path.parents and path != workspace:
            raise ContractValidationError("json store ref escapes workspace")
        return path


JsonRunStore = JsonWorkspaceStore
JsonArtifactStore = JsonWorkspaceStore
JsonEventLogStore = JsonWorkspaceStore
