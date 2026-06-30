from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import os
import subprocess
import sys
import unittest


class ImportSideEffectTests(unittest.TestCase):
    def test_importing_package_does_not_write_to_cwd(self) -> None:
        with TemporaryDirectory() as tmpdir:
            script = (
                "from pathlib import Path\n"
                "before = sorted(p.relative_to(Path.cwd()).as_posix() for p in Path.cwd().rglob('*'))\n"
                "import missionforge\n"
                "after = sorted(p.relative_to(Path.cwd()).as_posix() for p in Path.cwd().rglob('*'))\n"
                "assert before == after, (before, after)\n"
            )
            env = dict(os.environ)
            repo_src = Path(__file__).resolve().parents[1] / "src"
            env["PYTHONPATH"] = str(repo_src)

            result = subprocess.run(
                [sys.executable, "-c", script],
                cwd=tmpdir,
                env=env,
                check=False,
                text=True,
                capture_output=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)

    def test_default_run_piworker_call_does_not_write_to_cwd(self) -> None:
        with TemporaryDirectory() as tmpdir:
            script = (
                "from pathlib import Path\n"
                "from missionforge import ContractValidationError, PiWorkerCall, PiWorkerCallRole, run_piworker_call\n"
                "before = sorted(p.relative_to(Path.cwd()).as_posix() for p in Path.cwd().rglob('*'))\n"
                "call = PiWorkerCall(\n"
                "    call_id='call-001',\n"
                "    role=PiWorkerCallRole.EXECUTOR,\n"
                "    contract_id='contract-001',\n"
                "    contract_hash='sha256:' + 'a' * 64,\n"
                "    contract_ref='contract/task_contract.json',\n"
                "    objective='Produce output.',\n"
                "    visible_refs=['contract/task_contract.json'],\n"
                "    writable_refs=['out'],\n"
                "    expected_output_refs=['out/report.txt'],\n"
                "    permission_manifest_ref='policy/permission_manifest.json',\n"
                ")\n"
                "try:\n"
                "    run_piworker_call(call)\n"
                "except ContractValidationError as exc:\n"
                "    assert 'filesystem workspace requires explicit workspace' in str(exc), str(exc)\n"
                "else:\n"
                "    raise AssertionError('default run_piworker_call should fail closed without workspace')\n"
                "after = sorted(p.relative_to(Path.cwd()).as_posix() for p in Path.cwd().rglob('*'))\n"
                "assert before == after, (before, after)\n"
            )
            env = dict(os.environ)
            repo_src = Path(__file__).resolve().parents[1] / "src"
            env["PYTHONPATH"] = str(repo_src)

            result = subprocess.run(
                [sys.executable, "-c", script],
                cwd=tmpdir,
                env=env,
                check=False,
                text=True,
                capture_output=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)

    def test_default_run_step_with_store_aware_adapter_does_not_write_to_cwd(self) -> None:
        with TemporaryDirectory() as tmpdir:
            script = (
                "from pathlib import Path\n"
                "from missionforge.kernel import Step, StepCompileContext, run_step\n"
                "from missionforge.runtime_results import ExecutionReport, WorkerAdapterResult, WorkerResult\n"
                "class Adapter:\n"
                "    adapter_family = 'cwd-side-effect-test'\n"
                "    def run_call(self, call, *, workspace=None, store=None, evidence_store=None, call_spec=None, exit_criteria=None, stop_conditions=None, extension_lock_ref=None):\n"
                "        output_ref = call.expected_output_refs[0]\n"
                "        report_ref = 'attempts/call/pi_agent_execution_report.json'\n"
                "        store.write_text(output_ref, 'report\\n')\n"
                "        report = ExecutionReport(report_id='R-call', call_id=call.call_id, status='completed', produced_artifacts=[output_ref], changed_refs=[output_ref], evidence_refs=[])\n"
                "        store.write_json(report_ref, report.to_dict())\n"
                "        return WorkerAdapterResult(execution_report=report, worker_result=WorkerResult(status='completed', execution_report_ref=report_ref))\n"
                "before = sorted(p.relative_to(Path.cwd()).as_posix() for p in Path.cwd().rglob('*'))\n"
                "step = Step(id='writer', brief='Write report.', inputs=['contract/task_contract.json'], outputs=['reports/final.md'], read=['contract'], write=['reports'])\n"
                "context = StepCompileContext(flow_id='flow1', contract_id='contract1', contract_hash='sha256:' + 'a' * 64)\n"
                "result = run_step(step, context=context, adapter=Adapter())\n"
                "assert result.store is not None\n"
                "result.store.write_json('check/ref.json', {'ok': True})\n"
                "after = sorted(p.relative_to(Path.cwd()).as_posix() for p in Path.cwd().rglob('*'))\n"
                "assert before == after, (before, after)\n"
            )
            env = dict(os.environ)
            repo_src = Path(__file__).resolve().parents[1] / "src"
            env["PYTHONPATH"] = str(repo_src)

            result = subprocess.run(
                [sys.executable, "-c", script],
                cwd=tmpdir,
                env=env,
                check=False,
                text=True,
                capture_output=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)

    def test_default_run_flow_with_store_aware_adapter_does_not_write_to_cwd(self) -> None:
        with TemporaryDirectory() as tmpdir:
            script = (
                "from pathlib import Path\n"
                "from missionforge.kernel import Artifact, ArtifactRole, Flow, Step, StepCompileContext, run_flow\n"
                "from missionforge.runtime_results import ExecutionReport, WorkerAdapterResult, WorkerResult\n"
                "class Adapter:\n"
                "    adapter_family = 'cwd-flow-side-effect-test'\n"
                "    def run_call(self, call, *, workspace=None, store=None, evidence_store=None, call_spec=None, exit_criteria=None, stop_conditions=None, extension_lock_ref=None):\n"
                "        store.write_text('reports/final.md', 'report\\n')\n"
                "        report_ref = 'attempts/call/pi_agent_execution_report.json'\n"
                "        report = ExecutionReport(report_id='R-call', call_id=call.call_id, status='completed', produced_artifacts=['reports/final.md'], changed_refs=['reports/final.md'], evidence_refs=[])\n"
                "        store.write_json(report_ref, report.to_dict())\n"
                "        return WorkerAdapterResult(execution_report=report, worker_result=WorkerResult(status='completed', execution_report_ref=report_ref))\n"
                "before = sorted(p.relative_to(Path.cwd()).as_posix() for p in Path.cwd().rglob('*'))\n"
                "step = Step(id='writer', brief='Write report.', inputs=['contract/task_contract.json'], outputs=['reports/final.md'], read=['contract'], write=['reports'])\n"
                "flow = Flow(id='flow1', steps=[step], artifacts=[Artifact('reports/final.md', role=ArtifactRole.OUTPUT, owner='piworker')])\n"
                "context = StepCompileContext(flow_id='flow1', contract_id='contract1', contract_hash='sha256:' + 'a' * 64)\n"
                "result = run_flow(flow, context=context, adapter=Adapter())\n"
                "assert result.store is not None\n"
                "after = sorted(p.relative_to(Path.cwd()).as_posix() for p in Path.cwd().rglob('*'))\n"
                "assert before == after, (before, after)\n"
            )
            env = dict(os.environ)
            repo_src = Path(__file__).resolve().parents[1] / "src"
            env["PYTHONPATH"] = str(repo_src)

            result = subprocess.run(
                [sys.executable, "-c", script],
                cwd=tmpdir,
                env=env,
                check=False,
                text=True,
                capture_output=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)

    def test_default_run_steps_batch_with_store_aware_adapters_does_not_write_to_cwd(self) -> None:
        with TemporaryDirectory() as tmpdir:
            script = (
                "from pathlib import Path\n"
                "from missionforge.kernel import Step, StepCompileContext, run_steps_batch\n"
                "from missionforge.runtime_results import ExecutionReport, WorkerAdapterResult, WorkerResult\n"
                "class Adapter:\n"
                "    adapter_family = 'cwd-batch-side-effect-test'\n"
                "    def run_call(self, call, *, workspace=None, store=None, evidence_store=None, call_spec=None, exit_criteria=None, stop_conditions=None, extension_lock_ref=None, runtime_progress_sink=None):\n"
                "        output_ref = call.expected_output_refs[0]\n"
                "        report_ref = 'attempts/' + call.call_id + '/pi_agent_execution_report.json'\n"
                "        store.write_text(output_ref, 'report for ' + call.call_id + '\\n')\n"
                "        report = ExecutionReport(report_id='R-' + call.call_id, call_id=call.call_id, status='completed', produced_artifacts=[output_ref], changed_refs=[output_ref], evidence_refs=[])\n"
                "        store.write_json(report_ref, report.to_dict())\n"
                "        return WorkerAdapterResult(execution_report=report, worker_result=WorkerResult(status='completed', execution_report_ref=report_ref))\n"
                "def adapter_factory(step):\n"
                "    return Adapter()\n"
                "before = sorted(p.relative_to(Path.cwd()).as_posix() for p in Path.cwd().rglob('*'))\n"
                "steps = [\n"
                "    Step(id='a', brief='A.', inputs=['inputs/a.txt'], outputs=['out/a/report.txt'], read=['inputs'], write=['out/a']),\n"
                "    Step(id='b', brief='B.', inputs=['inputs/b.txt'], outputs=['out/b/report.txt'], read=['inputs'], write=['out/b']),\n"
                "]\n"
                "context = StepCompileContext(flow_id='flow1', contract_id='contract1', contract_hash='sha256:' + 'a' * 64)\n"
                "result = run_steps_batch(steps, context=context, adapter_factory=adapter_factory, concurrency=2)\n"
                "assert result.store is not None\n"
                "after = sorted(p.relative_to(Path.cwd()).as_posix() for p in Path.cwd().rglob('*'))\n"
                "assert before == after, (before, after)\n"
            )
            env = dict(os.environ)
            repo_src = Path(__file__).resolve().parents[1] / "src"
            env["PYTHONPATH"] = str(repo_src)

            result = subprocess.run(
                [sys.executable, "-c", script],
                cwd=tmpdir,
                env=env,
                check=False,
                text=True,
                capture_output=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)

    def test_default_run_piworker_call_batch_with_store_aware_adapters_does_not_write_to_cwd(self) -> None:
        with TemporaryDirectory() as tmpdir:
            script = (
                "from pathlib import Path\n"
                "from missionforge import PiWorkerCall, PiWorkerCallBatch, PiWorkerCallRole, run_piworker_call_batch\n"
                "from missionforge.runtime_results import ExecutionReport, WorkerAdapterResult, WorkerResult\n"
                "HASH = 'sha256:' + 'a' * 64\n"
                "def call(call_id, output_ref):\n"
                "    return PiWorkerCall(call_id=call_id, role=PiWorkerCallRole.EXECUTOR, contract_id='contract1', contract_hash=HASH, contract_ref='contract/task_contract.json', objective='Produce output.', visible_refs=['contract/task_contract.json'], writable_refs=[output_ref.rsplit('/', 1)[0]], expected_output_refs=[output_ref], permission_manifest_ref='policy/permission_manifest.json')\n"
                "class Adapter:\n"
                "    adapter_family = 'cwd-piworker-batch-side-effect-test'\n"
                "    def run_call(self, call, *, workspace=None, store=None, evidence_store=None, call_spec=None, exit_criteria=None, stop_conditions=None, extension_lock_ref=None, runtime_progress_sink=None):\n"
                "        output_ref = call.expected_output_refs[0]\n"
                "        report_ref = 'attempts/' + call.call_id + '/pi_agent_execution_report.json'\n"
                "        store.write_text(output_ref, 'report for ' + call.call_id + '\\n')\n"
                "        report = ExecutionReport(report_id='R-' + call.call_id, call_id=call.call_id, status='completed', produced_artifacts=[output_ref], changed_refs=[output_ref], evidence_refs=[])\n"
                "        store.write_json(report_ref, report.to_dict())\n"
                "        return WorkerAdapterResult(execution_report=report, worker_result=WorkerResult(status='completed', execution_report_ref=report_ref))\n"
                "def adapter_factory(call):\n"
                "    return Adapter()\n"
                "before = sorted(p.relative_to(Path.cwd()).as_posix() for p in Path.cwd().rglob('*'))\n"
                "batch = PiWorkerCallBatch(batch_id='batch1', calls=[call('call-a', 'out/a/report.txt'), call('call-b', 'out/b/report.txt')], concurrency=2)\n"
                "result = run_piworker_call_batch(batch, adapter_factory=adapter_factory)\n"
                "assert result.store is not None\n"
                "after = sorted(p.relative_to(Path.cwd()).as_posix() for p in Path.cwd().rglob('*'))\n"
                "assert before == after, (before, after)\n"
            )
            env = dict(os.environ)
            repo_src = Path(__file__).resolve().parents[1] / "src"
            env["PYTHONPATH"] = str(repo_src)

            result = subprocess.run(
                [sys.executable, "-c", script],
                cwd=tmpdir,
                env=env,
                check=False,
                text=True,
                capture_output=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)


if __name__ == "__main__":
    unittest.main()
