"""DeepResearch FrontDesk request-discovery layer.

FrontDesk is intentionally an integration-level PiWorker node. It elicits and
freezes a research requirements document before the existing kernel-v2 research
flow starts. MissionForge code owns refs and boundaries; PiWorker owns the
semantic grilling.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Mapping

import missionforge as mf

from .product_contract import AcademicResearchRequest, ResearchIntensity
from .project_lifecycle import (
    evaluate_project_context_packages,
    write_frontdesk_lifecycle_state,
    write_project_manifest,
)
from .workspace import read_json_ref, read_text_ref, resolve_workspace_ref, write_json_ref, write_text_ref


FRONTDESK_RESULT_REF = "frontdesk/frontdesk_result.json"
FRONTDESK_CONTRACT_REF = "frontdesk/frontdesk_contract.json"
FRONTDESK_WORKSPACE_POLICY_REF = "frontdesk/workspace_policy.json"
FRONTDESK_PERMISSION_MANIFEST_REF = "frontdesk/permission_manifest.json"
FRONTDESK_INITIAL_INPUT_REF = "frontdesk/initial_input.md"
FRONTDESK_DIALOGUE_REF = "frontdesk/dialogue.jsonl"
FRONTDESK_BRIEF_REF = "frontdesk/frontdesk_brief.md"
FRONTDESK_ASSISTANT_TURN_REF = "frontdesk/assistant_turn.json"
FRONTDESK_SESSION_STATE_REF = "frontdesk/session_state.json"
FRONTDESK_REQUIREMENTS_REF = "frontdesk/research_requirements.md"
FRONTDESK_CONTROL_REF = "frontdesk/frontdesk_control.json"
FRONTDESK_APPROVAL_REF = "frontdesk/approval.json"
FRONTDESK_RESEARCH_REQUEST_REF = "frontdesk/research_request.json"
FRONTDESK_RESEARCH_PROJECTION_REF = "frontdesk/research_projection.json"


@dataclass(frozen=True)
class DeepResearchFrontDeskResult:
    """Refs-first result for one DeepResearch FrontDesk turn."""

    request_id: str
    status: str
    run_workspace_ref: str
    result_ref: str
    requirements_ref: str
    control_ref: str
    dialogue_ref: str
    assistant_turn_ref: str
    session_state_ref: str
    research_request_ref: str
    evidence_refs: list[str]
    metric_refs: list[str]
    contract_hash: str
    schema_version: str = "missionforge_deepresearch.frontdesk_result.v1"

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "schema_version": self.schema_version,
            "request_id": self.request_id,
            "status": self.status,
            "run_workspace_ref": self.run_workspace_ref,
            "result_ref": self.result_ref,
            "requirements_ref": self.requirements_ref,
            "control_ref": self.control_ref,
            "dialogue_ref": self.dialogue_ref,
            "assistant_turn_ref": self.assistant_turn_ref,
            "session_state_ref": self.session_state_ref,
            "research_request_ref": self.research_request_ref,
            "evidence_refs": list(self.evidence_refs),
            "metric_refs": list(self.metric_refs),
            "contract_hash": self.contract_hash,
        }

    def validate(self) -> None:
        if self.schema_version != "missionforge_deepresearch.frontdesk_result.v1":
            raise mf.ContractValidationError("deepresearch_frontdesk_result.schema_version is unsupported")
        for field_name in (
            "run_workspace_ref",
            "result_ref",
            "requirements_ref",
            "control_ref",
            "dialogue_ref",
            "assistant_turn_ref",
            "session_state_ref",
        ):
            mf.validate_ref(getattr(self, field_name), f"deepresearch_frontdesk_result.{field_name}")
        if self.research_request_ref:
            mf.validate_ref(self.research_request_ref, "deepresearch_frontdesk_result.research_request_ref")
        for ref in [*self.evidence_refs, *self.metric_refs]:
            mf.validate_ref(ref, "deepresearch_frontdesk_result.refs[]")
        if not self.contract_hash.startswith("sha256:"):
            raise mf.ContractValidationError("deepresearch_frontdesk_result.contract_hash must be sha256")


def run_deepresearch_frontdesk_turn(
    *,
    initial_input: str | None = None,
    user_message: str | None = None,
    request_id: str = "deepresearch-frontdesk",
    workspace: str | Path = ".",
    adapter: mf.PiWorkerCallAdapter | None = None,
    audience: str = "R&D team",
    language: str = "zh",
    research_intensity: ResearchIntensity | str = ResearchIntensity.STANDARD,
    live_extension_mode: bool = False,
    extension_installer: mf.ExtensionInstaller | None = None,
    runtime_progress_sink: mf.PiWorkerProgressSink | None = None,
) -> DeepResearchFrontDeskResult:
    """Run one FrontDesk turn and persist the current requirements document."""

    if adapter is None:
        raise mf.ContractValidationError("deepresearch_frontdesk requires an explicit PiWorker adapter")
    root = Path(workspace).resolve()
    run_ref = f"runs/{request_id}"
    run_root = root / run_ref
    run_root.mkdir(parents=True, exist_ok=True)
    write_project_manifest(run_root, request_id=request_id)
    if initial_input is not None and not (run_root / FRONTDESK_INITIAL_INPUT_REF).exists():
        write_text_ref(run_root, FRONTDESK_INITIAL_INPUT_REF, initial_input.strip() + "\n")
    if not (run_root / FRONTDESK_INITIAL_INPUT_REF).exists():
        raise mf.ContractValidationError("deepresearch_frontdesk requires initial_input for a new session")
    _append_dialogue(run_root, "user", user_message or initial_input or "")
    contract = _frontdesk_contract(
        request_id=request_id,
        audience=audience,
        language=language,
        research_intensity=research_intensity,
        live_extension_mode=live_extension_mode,
    )
    contract_hash = mf.stable_json_hash(contract)
    _write_frontdesk_workspace(run_root, contract=contract)
    flow_result = mf.run_flow(
        _frontdesk_flow(live_extension_mode=live_extension_mode),
        context=_frontdesk_flow_context(
            request_id=request_id,
            contract=contract,
            contract_hash=contract_hash,
        ),
        workspace=run_root,
        adapter=adapter,
        extension_lock_mode="install" if live_extension_mode else "verify-installed",
        extension_installer=extension_installer,
        max_steps=1,
        resume=True,
        runtime_progress_sink=runtime_progress_sink,
    )
    if not flow_result.step_results:
        raise mf.ContractValidationError("deepresearch_frontdesk flow did not produce a step result")
    step_result = flow_result.step_results[-1]
    call_result = step_result.call_result
    _write_frontdesk_compat_runtime_refs(run_root, step_result)
    status = _frontdesk_status(run_root, call_result.status.value)
    research_request_ref = ""
    if status == "ready_for_approval":
        research_request_ref = _write_research_request_projection(
            run_root,
            request_id=request_id,
            audience=audience,
            language=language,
            research_intensity=research_intensity,
        )
    result = DeepResearchFrontDeskResult(
        request_id=request_id,
        status=status,
        run_workspace_ref=run_ref,
        result_ref=_outer_ref(run_ref, FRONTDESK_RESULT_REF),
        requirements_ref=_outer_ref(run_ref, FRONTDESK_REQUIREMENTS_REF),
        control_ref=_outer_ref(run_ref, FRONTDESK_CONTROL_REF),
        dialogue_ref=_outer_ref(run_ref, FRONTDESK_DIALOGUE_REF),
        assistant_turn_ref=_outer_ref(run_ref, FRONTDESK_ASSISTANT_TURN_REF),
        session_state_ref=_outer_ref(run_ref, FRONTDESK_SESSION_STATE_REF),
        research_request_ref=_outer_ref(run_ref, research_request_ref) if research_request_ref else "",
        evidence_refs=_dedupe_refs(
            [
                _outer_ref(run_ref, FRONTDESK_INITIAL_INPUT_REF),
                _outer_ref(run_ref, FRONTDESK_DIALOGUE_REF),
                _outer_ref(run_ref, FRONTDESK_ASSISTANT_TURN_REF),
                _outer_ref(run_ref, FRONTDESK_SESSION_STATE_REF),
                _outer_ref(run_ref, FRONTDESK_REQUIREMENTS_REF),
                _outer_ref(run_ref, FRONTDESK_CONTROL_REF),
                _outer_ref(run_ref, flow_result.flow_result_ref),
                _outer_ref(run_ref, step_result.step_record_ref),
                _outer_ref(run_ref, step_result.piworker_call_result_ref),
                _outer_ref(run_ref, step_result.step_record.metadata.get("context_package_ref", ""))
                if isinstance(step_result.step_record.metadata.get("context_package_ref"), str)
                else "",
                _outer_ref(run_ref, step_result.step_record.extension_lock_ref)
                if step_result.step_record.extension_lock_ref
                else "",
            ]
        ),
        metric_refs=[_outer_ref(run_ref, ref) for ref in call_result.metric_refs],
        contract_hash=contract_hash,
    )
    write_json_ref(root, result.result_ref, result.to_dict())
    write_frontdesk_lifecycle_state(
        run_root,
        request_id=request_id,
        status=status,
        result_ref=FRONTDESK_RESULT_REF,
        flow_result=flow_result,
        contract_ref=FRONTDESK_CONTRACT_REF,
        requirements_ref=FRONTDESK_REQUIREMENTS_REF,
        control_ref=FRONTDESK_CONTROL_REF,
        assistant_turn_ref=FRONTDESK_ASSISTANT_TURN_REF,
        session_state_ref=FRONTDESK_SESSION_STATE_REF,
        research_request_ref=research_request_ref,
    )
    return result


def approve_frontdesk_requirements(
    *,
    request_id: str,
    workspace: str | Path = ".",
) -> AcademicResearchRequest:
    """Approve the current requirements document and return the frozen research request."""

    root = Path(workspace).resolve()
    run_ref = f"runs/{request_id}"
    run_root = root / run_ref
    control = read_json_ref(run_root, FRONTDESK_CONTROL_REF, "frontdesk_control")
    if control.get("decision") != "ready_for_approval":
        raise mf.ContractValidationError("frontdesk requirements are not ready for approval")
    projection = read_json_ref(run_root, FRONTDESK_RESEARCH_PROJECTION_REF, "frontdesk_research_projection")
    requirements = read_text_ref(run_root, FRONTDESK_REQUIREMENTS_REF)
    if projection.get("requirements_hash") != _text_hash(requirements):
        raise mf.ContractValidationError("frontdesk requirements changed after research request projection")
    request_payload = read_json_ref(run_root, FRONTDESK_RESEARCH_REQUEST_REF, "frontdesk_research_request")
    request = AcademicResearchRequest.from_dict(request_payload)
    write_json_ref(
        run_root,
        FRONTDESK_APPROVAL_REF,
        {
            "schema_version": "missionforge_deepresearch.frontdesk_approval.v1",
            "decision": "approved",
            "requirements_ref": FRONTDESK_REQUIREMENTS_REF,
            "research_request_ref": FRONTDESK_RESEARCH_REQUEST_REF,
            "research_projection_ref": FRONTDESK_RESEARCH_PROJECTION_REF,
            "requirements_hash": projection["requirements_hash"],
        },
    )
    return request


class FrontDeskFixtureAdapter:
    """Fixture adapter for testing the FrontDesk shell without a live PiWorker."""

    adapter_family = "fixture_deepresearch_frontdesk"

    def run_call(self, call: mf.PiWorkerCall, *, workspace: str | Path = ".", **_kwargs: Any) -> mf.WorkerAdapterResult:
        root = Path(workspace)
        dialogue = _read_dialogue(root)
        if len([item for item in dialogue if item.get("role") == "user"]) <= 1:
            decision = "needs_user_answer"
            turn = _fixture_assistant_turn(decision)
            state = _fixture_session_state(decision)
        else:
            decision = "ready_for_approval"
            turn = _fixture_assistant_turn(decision)
            state = _fixture_session_state(decision)
        initial = read_text_ref(root, FRONTDESK_INITIAL_INPUT_REF).strip()
        write_text_ref(
            root,
            FRONTDESK_REQUIREMENTS_REF,
            _fixture_requirements(initial, decision=decision),
        )
        write_json_ref(root, FRONTDESK_ASSISTANT_TURN_REF, turn)
        write_json_ref(root, FRONTDESK_SESSION_STATE_REF, state)
        write_json_ref(
            root,
            FRONTDESK_CONTROL_REF,
            {
                "schema_version": "missionforge_deepresearch.frontdesk_control.v1",
                "decision": decision,
                "requirements_ref": FRONTDESK_REQUIREMENTS_REF,
                "assistant_turn_ref": FRONTDESK_ASSISTANT_TURN_REF,
                "session_state_ref": FRONTDESK_SESSION_STATE_REF,
                "research_request_ref": FRONTDESK_RESEARCH_REQUEST_REF if decision == "ready_for_approval" else "",
            },
        )
        report_ref = f"attempts/{call.call_id}/execution_report.json"
        metrics_ref = f"attempts/{call.call_id}/metrics.json"
        write_json_ref(root, metrics_ref, {"fixture": True, "step_id": "frontdesk"})
        report = mf.ExecutionReport(
            report_id=f"{call.call_id}-execution-report",
            call_id=call.call_id,
            status="completed",
            produced_artifacts=[
                FRONTDESK_ASSISTANT_TURN_REF,
                FRONTDESK_SESSION_STATE_REF,
                FRONTDESK_REQUIREMENTS_REF,
                FRONTDESK_CONTROL_REF,
            ],
            changed_refs=[
                FRONTDESK_ASSISTANT_TURN_REF,
                FRONTDESK_SESSION_STATE_REF,
                FRONTDESK_REQUIREMENTS_REF,
                FRONTDESK_CONTROL_REF,
                report_ref,
                metrics_ref,
            ],
            evidence_refs=[
                FRONTDESK_DIALOGUE_REF,
                FRONTDESK_ASSISTANT_TURN_REF,
                FRONTDESK_SESSION_STATE_REF,
                FRONTDESK_REQUIREMENTS_REF,
                FRONTDESK_CONTROL_REF,
            ],
            metrics={"metric_ref": metrics_ref},
        )
        write_json_ref(root, report_ref, report.to_dict())
        return mf.WorkerAdapterResult(
            execution_report=report,
            worker_result=mf.WorkerResult(status="completed", execution_report_ref=report_ref),
            metrics={"metric_ref": metrics_ref},
        )


def _frontdesk_contract(
    *,
    request_id: str,
    audience: str,
    language: str,
    research_intensity: ResearchIntensity | str,
    live_extension_mode: bool,
) -> dict[str, Any]:
    intensity = ResearchIntensity(research_intensity)
    return {
        "schema_version": "missionforge_deepresearch.frontdesk_contract.v1",
        "contract_id": f"deepresearch-frontdesk-{request_id}",
        "objective": "Turn a vague research need into an approval-ready DeepResearch requirements document.",
        "audience": audience,
        "language": language,
        "research_intensity": intensity.value,
        "live_extension_mode": bool(live_extension_mode),
        "required_outputs": [FRONTDESK_REQUIREMENTS_REF, FRONTDESK_CONTROL_REF],
    }


def _write_frontdesk_workspace(run_root: Path, *, contract: Mapping[str, Any]) -> None:
    write_json_ref(run_root, FRONTDESK_CONTRACT_REF, contract)
    write_json_ref(run_root, FRONTDESK_WORKSPACE_POLICY_REF, {"policy_id": "deepresearch-frontdesk", "root_ref": "."})
    write_text_ref(run_root, FRONTDESK_BRIEF_REF, _frontdesk_brief())
    if not (run_root / FRONTDESK_ASSISTANT_TURN_REF).exists():
        write_json_ref(run_root, FRONTDESK_ASSISTANT_TURN_REF, _empty_assistant_turn())
    if not (run_root / FRONTDESK_SESSION_STATE_REF).exists():
        write_json_ref(run_root, FRONTDESK_SESSION_STATE_REF, _empty_session_state())
    if not (run_root / FRONTDESK_REQUIREMENTS_REF).exists():
        write_text_ref(run_root, FRONTDESK_REQUIREMENTS_REF, "# DeepResearch 调研需求文档\n\n状态：待澄清。\n")
    if not (run_root / FRONTDESK_CONTROL_REF).exists():
        write_json_ref(
            run_root,
            FRONTDESK_CONTROL_REF,
            {
                "schema_version": "missionforge_deepresearch.frontdesk_control.v1",
                "decision": "needs_user_answer",
                "requirements_ref": FRONTDESK_REQUIREMENTS_REF,
                "assistant_turn_ref": FRONTDESK_ASSISTANT_TURN_REF,
                "session_state_ref": FRONTDESK_SESSION_STATE_REF,
                "research_request_ref": "",
            },
        )


def deepresearch_frontdesk_flow_run_id(request_id: str) -> str:
    """Return the FrontDesk flow id used for ContextPackage resume."""

    return f"deepresearch-frontdesk-{request_id}"


def evaluate_frontdesk_resume_state(
    *,
    request_id: str,
    workspace: str | Path = ".",
    audience: str = "R&D team",
    language: str = "zh",
    research_intensity: ResearchIntensity | str = ResearchIntensity.STANDARD,
    live_extension_mode: bool = False,
) -> str:
    """Evaluate the latest FrontDesk ContextPackage and write diagnostics."""

    root = Path(workspace).resolve()
    run_root = root / f"runs/{request_id}"
    if not run_root.exists():
        return ""
    write_project_manifest(run_root, request_id=request_id)
    contract = _frontdesk_contract(
        request_id=request_id,
        audience=audience,
        language=language,
        research_intensity=research_intensity,
        live_extension_mode=live_extension_mode,
    )
    contract_hash = mf.stable_json_hash(contract)
    if (run_root / FRONTDESK_INITIAL_INPUT_REF).exists():
        _write_frontdesk_workspace(run_root, contract=contract)
    return evaluate_project_context_packages(
        run_root,
        request_id=request_id,
        expectations={
            "frontdesk": _frontdesk_restore_expectation(
                run_root=run_root,
                request_id=request_id,
                contract=contract,
                contract_hash=contract_hash,
                live_extension_mode=live_extension_mode,
            )
        },
    )


def _frontdesk_flow(*, live_extension_mode: bool) -> mf.Flow:
    return mf.Flow(
        id="deepresearch-frontdesk",
        steps=[_frontdesk_step(live_extension_mode=live_extension_mode)],
        artifacts=[
            mf.Artifact(FRONTDESK_ASSISTANT_TURN_REF, role=mf.ArtifactRole.STATE, owner="piworker"),
            mf.Artifact(FRONTDESK_SESSION_STATE_REF, role=mf.ArtifactRole.STATE, owner="piworker"),
            mf.Artifact(FRONTDESK_REQUIREMENTS_REF, role=mf.ArtifactRole.OUTPUT, owner="piworker"),
            mf.Artifact(FRONTDESK_CONTROL_REF, role=mf.ArtifactRole.DECISION, owner="piworker"),
        ],
        toolsets=[_frontdesk_academic_toolset()] if live_extension_mode else [],
    )


def _frontdesk_step(*, live_extension_mode: bool) -> mf.Step:
    tools = ["read", "write", "edit", "academic"] if live_extension_mode else ["read", "write", "edit"]
    return mf.Step(
        id="frontdesk",
        brief=(
            "Interact with the user as a DeepResearch FrontDesk. Clarify the research need, "
            "challenge vague scope, inspect available conversation refs, optionally use live tools "
            "for lightweight validation, and write a research requirements document plus a control decision."
        ),
        inputs=[
            FRONTDESK_CONTRACT_REF,
            FRONTDESK_INITIAL_INPUT_REF,
            FRONTDESK_DIALOGUE_REF,
            FRONTDESK_BRIEF_REF,
            FRONTDESK_ASSISTANT_TURN_REF,
            FRONTDESK_SESSION_STATE_REF,
            FRONTDESK_REQUIREMENTS_REF,
            FRONTDESK_CONTROL_REF,
        ],
        outputs=[
            FRONTDESK_ASSISTANT_TURN_REF,
            FRONTDESK_SESSION_STATE_REF,
            FRONTDESK_REQUIREMENTS_REF,
            FRONTDESK_CONTROL_REF,
        ],
        read=["frontdesk"],
        write=[
            FRONTDESK_ASSISTANT_TURN_REF,
            FRONTDESK_SESSION_STATE_REF,
            FRONTDESK_REQUIREMENTS_REF,
            FRONTDESK_CONTROL_REF,
        ],
        tools=tools,
        runtime_budget={"timeout_seconds": 900},
        network=live_extension_mode,
        role=mf.PiWorkerCallRole.FRONTDESK_AUTHOR,
    )


def _frontdesk_flow_context(
    *,
    request_id: str,
    contract: Mapping[str, Any],
    contract_hash: str,
) -> mf.StepCompileContext:
    flow_id = deepresearch_frontdesk_flow_run_id(request_id)
    return mf.StepCompileContext(
        flow_id=flow_id,
        contract_id=str(contract["contract_id"]),
        contract_hash=contract_hash,
        contract_ref=FRONTDESK_CONTRACT_REF,
        workspace_policy_ref=FRONTDESK_WORKSPACE_POLICY_REF,
    )


def _frontdesk_restore_step_context(
    *,
    request_id: str,
    contract: Mapping[str, Any],
    contract_hash: str,
) -> mf.StepCompileContext:
    flow_id = deepresearch_frontdesk_flow_run_id(request_id)
    return mf.StepCompileContext(
        flow_id=flow_id,
        contract_id=str(contract["contract_id"]),
        contract_hash=contract_hash,
        contract_ref=FRONTDESK_CONTRACT_REF,
        workspace_policy_ref=FRONTDESK_WORKSPACE_POLICY_REF,
        ref_prefix=f"kernel/{flow_id}/runs/{flow_id}/steps/001-frontdesk",
        call_id=f"{flow_id}-001-frontdesk",
    )


def _frontdesk_restore_expectation(
    *,
    run_root: Path,
    request_id: str,
    contract: Mapping[str, Any],
    contract_hash: str,
    live_extension_mode: bool,
) -> mf.ContextPackageRestoreExpectation:
    compiled = mf.compile_step(
        _frontdesk_step(live_extension_mode=live_extension_mode),
        context=_frontdesk_restore_step_context(
            request_id=request_id,
            contract=contract,
            contract_hash=contract_hash,
        ),
        toolsets={"academic": _frontdesk_academic_toolset()} if live_extension_mode else {},
    )
    store = mf.FileRefStore(run_root)
    visible_ref_hashes = {
        ref: store.hash_ref(ref)
        for ref in compiled.piworker_call.visible_refs
        if store.exists(ref)
    }
    return mf.ContextPackageRestoreExpectation(
        role=compiled.piworker_call.role.value,
        run_id=deepresearch_frontdesk_flow_run_id(request_id),
        step_id=compiled.step.id,
        contract_ref=compiled.piworker_call.contract_ref,
        contract_hash=compiled.piworker_call.contract_hash,
        permission_manifest_ref=compiled.permission_manifest_ref,
        permission_manifest_hash=mf.stable_json_hash(compiled.permission_manifest.to_dict()),
        step_spec_hash=compiled.step.spec_hash,
        tool_schema_hash=mf.stable_json_hash({"allowed_tools": list(compiled.permission_manifest.allowed_tools)}),
        context_compiler_version="missionforge.context_runtime.v1",
        visible_ref_hashes=visible_ref_hashes,
    )


def _write_frontdesk_compat_runtime_refs(run_root: Path, step_result: mf.StepRunResult) -> None:
    """Keep legacy FrontDesk debug refs available while Kernel owns runtime state."""

    write_json_ref(run_root, FRONTDESK_PERMISSION_MANIFEST_REF, step_result.compiled.permission_manifest.to_dict())
    write_json_ref(run_root, "frontdesk/kernel/step_spec.json", step_result.compiled.step.to_dict())


def _compile_frontdesk_call(
    *,
    call_id: str,
    contract: Mapping[str, Any],
    contract_hash: str,
    live_extension_mode: bool,
) -> mf.CompiledStep:
    step = _frontdesk_step(live_extension_mode=live_extension_mode)
    context = mf.StepCompileContext(
        flow_id=f"deepresearch-frontdesk-{contract['contract_id']}",
        contract_id=str(contract["contract_id"]),
        contract_hash=contract_hash,
        contract_ref=FRONTDESK_CONTRACT_REF,
        workspace_policy_ref=FRONTDESK_WORKSPACE_POLICY_REF,
        permission_manifest_ref=FRONTDESK_PERMISSION_MANIFEST_REF,
        ref_prefix="frontdesk/kernel",
        call_id=call_id,
    )
    toolsets = {"academic": _frontdesk_academic_toolset()} if live_extension_mode else {}
    return mf.compile_step(step, context=context, toolsets=toolsets)


def _frontdesk_academic_toolset() -> mf.Toolset:
    return mf.Toolset(
        id="academic",
        package="local:extensions/pi-academic-sources",
        tools=["academic_provider_capabilities", "academic_search", "academic_fetch", "citation_lookup", "repo_search"],
        capability=mf.ExtensionCapability.WEB,
        network=True,
    )


def _frontdesk_brief() -> str:
    return """# DeepResearch FrontDesk Brief

You are the DeepResearch FrontDesk. Your job is not to write the final report.
Your job is to actively clarify the user's research need until it is ready for
approval and execution.

Responsibilities:
- Read `frontdesk/initial_input.md` and `frontdesk/dialogue.jsonl`.
- Behave like a conversational requirements interviewer. Your primary user
  output on unclear turns is a direct reply and focused questions, not a
  polished research plan.
- Ask sharp questions when scope, audience, evidence standard, timeframe,
  deliverable shape, exclusions, or success criteria are unclear.
- Challenge vague or over-broad requests. Suggest narrower research boundaries.
- If useful, state hypotheses and assumptions explicitly for the user to accept
  or correct.
- When useful, offer 2-4 candidate choices that a TUI can render as a
  keyboard-selectable menu. Put the most defensible recommendation first and
  reserve the final option for the user's own custom idea.
- Treat seed papers, PDFs, OpenAlex keys, and other provider credentials as
  optional accelerators. Do not block a valid research run just because they are
  unavailable.
- When live tools are available, use them sparingly to validate the shape of the
  problem, identify representative terminology/sources/repos, and correct false
  assumptions before asking the user to approve the research direction.
- Do not perform the full DeepResearch report here. Stop at a high-quality
  requirements document and a small set of validation notes.
- Maintain three orthogonal artifacts:
  - `frontdesk/assistant_turn.json`: the next user-facing conversational turn.
  - `frontdesk/session_state.json`: durable requirements-discovery state.
  - `frontdesk/research_requirements.md`: the approval snapshot, only polished
    when the user is close to approval.
- Maintain `frontdesk/frontdesk_control.json` only as routing/control metadata.

Control decisions:
- `needs_user_answer`: more user input is needed. Include concise questions.
- `ready_for_approval`: the requirements document is good enough for user
  approval. Include no more than minor open assumptions.

Assistant turn requirements:
- Always write `frontdesk/assistant_turn.json`.
- Use schema_version `missionforge_deepresearch.frontdesk_assistant_turn.v1`.
- Include `message`: a short direct reply to the user that explains your
  current understanding and what you need next.
- Include `questions`: an array of 2-5 objects when more input is needed. Each
  object should have `question`, `why`, and optional `answer_hint`.
- A question may include `choices`: an array of objects with `label`,
  `description`, and optional `recommended` or `freeform`. Use choices when the
  user is choosing among distinct research directions, evidence standards,
  source-depth budgets, or report shapes.
- Include optional `current_hypothesis` and `user_unlock`: what the user's next
  answer will decide or unlock.
- When `needs_user_answer`, include 2-5 high-value questions in `questions`.
  Avoid asking generic checklist questions; each question should reduce real
  ambiguity in this research request.

Session state requirements:
- Always write `frontdesk/session_state.json`.
- Use schema_version `missionforge_deepresearch.frontdesk_session_state.v1`.
- Track `known_facts`, `open_ambiguities`, `candidate_directions`,
  `accepted_assumptions`, `rejected_directions`, and `readiness_notes`.
- This state is for recovery and audit; do not make it the user-facing answer.

Control artifact requirements:
- Always include `assistant_turn_ref`, `session_state_ref`, `requirements_ref`,
  and `research_request_ref`.
- Do not set `ready_for_approval` just because you can draft a plausible plan.
  Use `ready_for_approval` only after the dialogue has enough scope, audience,
  evidence standard, output shape, and exclusions for a good research run, or
  when the user explicitly says the current requirements are sufficient.
- For a normal vague first message, prefer `needs_user_answer`.

When `ready_for_approval`, ensure the requirements document contains:
- research title;
- background and motivation;
- core research questions;
- scope and non-goals;
- target audience;
- preferred language;
- evidence expectations;
- optional accelerators such as seed papers/PDFs/provider keys if available,
  with explicit note that they are not required;
- expected report structure;
- constraints and assumptions;
- validation notes with any inspected refs/tool findings when live tools were used;
- a one-paragraph executable topic suitable for DeepResearch.
"""


def _append_dialogue(run_root: Path, role: str, content: str) -> None:
    if not content.strip():
        return
    path = resolve_workspace_ref(run_root, FRONTDESK_DIALOGUE_REF)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"role": role, "content": content.strip()}, ensure_ascii=False, sort_keys=True) + "\n")


def _read_dialogue(run_root: Path) -> list[dict[str, Any]]:
    path = resolve_workspace_ref(run_root, FRONTDESK_DIALOGUE_REF)
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _next_frontdesk_call_id(run_root: Path, request_id: str) -> str:
    attempt_root = resolve_workspace_ref(run_root, "frontdesk/attempts")
    if not attempt_root.exists():
        return f"deepresearch-frontdesk-{request_id}-001"
    count = len([item for item in attempt_root.iterdir() if item.is_dir()])
    return f"deepresearch-frontdesk-{request_id}-{count + 1:03d}"


def _frontdesk_status(run_root: Path, call_status: str) -> str:
    if call_status != mf.PiWorkerCallResultStatus.COMPLETED.value:
        return call_status
    try:
        control = read_json_ref(run_root, FRONTDESK_CONTROL_REF, "frontdesk_control")
    except mf.ContractValidationError:
        return "blocked"
    decision = control.get("decision")
    if decision in {"needs_user_answer", "ready_for_approval"}:
        return str(decision)
    return "blocked"


def _write_research_request_projection(
    run_root: Path,
    *,
    request_id: str,
    audience: str,
    language: str,
    research_intensity: ResearchIntensity | str,
) -> str:
    requirements = read_text_ref(run_root, FRONTDESK_REQUIREMENTS_REF)
    topic = _topic_from_requirements(requirements.strip())
    request = AcademicResearchRequest(
        request_id=request_id,
        topic=topic,
        audience=audience,
        language=language,
        research_intensity=research_intensity,
        constraints=[f"Use approved requirements from {FRONTDESK_REQUIREMENTS_REF}."],
    )
    write_json_ref(run_root, FRONTDESK_RESEARCH_REQUEST_REF, request.to_dict())
    write_json_ref(
        run_root,
        FRONTDESK_RESEARCH_PROJECTION_REF,
        {
            "schema_version": "missionforge_deepresearch.frontdesk_research_projection.v1",
            "requirements_ref": FRONTDESK_REQUIREMENTS_REF,
            "requirements_hash": _text_hash(requirements),
            "research_request_ref": FRONTDESK_RESEARCH_REQUEST_REF,
        },
    )
    return FRONTDESK_RESEARCH_REQUEST_REF


def _topic_from_requirements(requirements: str) -> str:
    marker = "可执行调研题目："
    for line in requirements.splitlines():
        if line.strip().startswith(marker):
            topic = line.split(marker, 1)[1].strip()
            if topic:
                return topic
    return "基于已批准调研需求文档完成 DeepResearch：" + requirements[:800]


def _text_hash(text: str) -> str:
    return mf.stable_json_hash({"text": text})


def _fixture_requirements(initial: str, *, decision: str) -> str:
    topic = initial.replace("\n", " ").strip()
    return "\n".join(
        [
            "# DeepResearch 调研需求文档",
            "",
            "## 研究标题",
            topic or "待定调研主题",
            "",
            "## 背景与动机",
            "用户希望把初始想法整理成可执行的深度调研任务。",
            "",
            "## 核心研究问题",
            "- 该领域有哪些代表性工作？",
            "- 主要技术路线、工程边界和证据强度是什么？",
            "",
            "## 范围与非目标",
            "- 覆盖论文、工程系统、开源实现和局限。",
            "- 不要求运行实验或安装第三方项目。",
            "",
            "## 证据期望",
            "优先使用论文、官方文档、仓库文件、发布说明和可追溯网页。",
            "",
            "## 预期报告结构",
            "范围与方法、证据基础、主要路线、对比矩阵、失败模式、证据缺口、参考文献。",
            "",
            "## 状态",
            "可审批。" if decision == "ready_for_approval" else "仍需用户回答澄清问题。",
            "",
            f"可执行调研题目：{topic}",
            "",
        ]
    )


def _fixture_assistant_turn(decision: str) -> dict[str, Any]:
    if decision == "ready_for_approval":
        return {
            "schema_version": "missionforge_deepresearch.frontdesk_assistant_turn.v1",
            "message": "我已经根据你的补充把调研需求整理到可审批状态；请用 /show 检查文档，确认后输入 /approve。",
            "current_hypothesis": "用户需要一份可服务工程选型和文献综述的 DeepResearch 需求。",
            "user_unlock": "用户审批后即可冻结需求并启动正式研究。",
            "questions": [],
        }
    return {
        "schema_version": "missionforge_deepresearch.frontdesk_assistant_turn.v1",
        "message": "我先不生成正式调研计划。为了把需求压实，需要先确认调研目的、证据标准和范围边界。",
        "current_hypothesis": "用户有研究方向，但最终用途、证据深度和范围边界还不明确。",
        "user_unlock": "回答这些问题后，FrontDesk 才能判断是偏工程选型、论文综述还是系统设计。",
        "questions": [
            {
                "question": "你希望综述服务于工程选型、论文综述、还是系统设计？",
                "why": "这决定报告重点是可落地工具链、学术脉络，还是架构方案。",
                "answer_hint": "例如：工程选型，需要能指导我们是否投入实现。",
                "choices": [
                    {
                        "label": "工程选型",
                        "description": "强调工具链、可落地方案、风险和投入判断。",
                        "recommended": True,
                    },
                    {
                        "label": "论文综述",
                        "description": "强调研究脉络、方法分类、代表论文和开放问题。",
                    },
                    {
                        "label": "系统设计",
                        "description": "强调目标架构、模块边界、集成路径和实现约束。",
                    },
                    {
                        "label": "自定义想法",
                        "description": "用户输入自己的方向、约束或混合方案。",
                        "freeform": True,
                    },
                ],
            },
            {
                "question": "是否需要覆盖开源代码和工具链集成细节？",
                "why": "这决定是否使用 intensive 模式做 repo/code audit。",
                "answer_hint": "例如：需要覆盖 MLIR/HLS/Vitis 相关仓库和接口边界。",
                "choices": [
                    {
                        "label": "需要",
                        "description": "检索论文同时检查相关仓库、文档和接口边界。",
                        "recommended": True,
                    },
                    {
                        "label": "不需要",
                        "description": "聚焦论文和元数据，减少代码审计成本。",
                    },
                    {
                        "label": "自定义范围",
                        "description": "用户指定只看部分仓库、框架或工程证据。",
                        "freeform": True,
                    },
                ],
            },
        ],
    }


def _fixture_session_state(decision: str) -> dict[str, Any]:
    return {
        "schema_version": "missionforge_deepresearch.frontdesk_session_state.v1",
        "known_facts": ["用户正在形成 DeepResearch 调研需求。"],
        "open_ambiguities": [] if decision == "ready_for_approval" else [
            "最终用途尚未确认。",
            "是否需要代码/仓库级证据尚未确认。",
        ],
        "candidate_directions": ["工程选型", "论文综述", "系统设计"],
        "accepted_assumptions": [] if decision != "ready_for_approval" else [
            "需要面向工程选型和文献综述。",
        ],
        "rejected_directions": [],
        "readiness_notes": [
            "可审批。" if decision == "ready_for_approval" else "需要用户继续澄清关键范围。"
        ],
    }


def _empty_assistant_turn() -> dict[str, Any]:
    return {
        "schema_version": "missionforge_deepresearch.frontdesk_assistant_turn.v1",
        "message": "我会先通过对话澄清调研需求；当前还没有足够信息生成可审批需求文档。",
        "current_hypothesis": "",
        "user_unlock": "",
        "questions": [],
    }


def _empty_session_state() -> dict[str, Any]:
    return {
        "schema_version": "missionforge_deepresearch.frontdesk_session_state.v1",
        "known_facts": [],
        "open_ambiguities": [],
        "candidate_directions": [],
        "accepted_assumptions": [],
        "rejected_directions": [],
        "readiness_notes": [],
    }


def _outer_ref(run_ref: str, inner_ref: str) -> str:
    return mf.validate_ref(f"{run_ref}/{inner_ref}", "deepresearch_frontdesk.outer_ref")


def _dedupe_refs(refs: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for ref in refs:
        if not ref:
            continue
        safe_ref = mf.validate_ref(ref, "deepresearch_frontdesk.ref")
        if safe_ref not in seen:
            result.append(safe_ref)
            seen.add(safe_ref)
    return result
