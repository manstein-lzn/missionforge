# MissionForge

MissionForge 是一个以 PiWorker 为中心的轻量运行时内核。

PiWorker 负责语义工作：理解任务、执行研究、综合判断、提出修复。
MissionForge 负责硬边界：冻结任务合同、工作区引用、权限清单、证据记录、
运行进度、密钥排除、角色隔离和独立 judge 产物。

## 当前形态

```text
FrontDesk 或 ProductIntegration
  -> TaskContract + WorkerBrief + JudgeRubric + PermissionManifest
  -> PiWorkerCall
  -> run_piworker_call(...)
  -> PiWorkerCallResult
  -> product judge / package / resume logic
```

根包暴露一组小而正交的程序员 API，并随包携带默认 PiAgent runtime：

- `TaskContract`、`WorkspacePolicy`、`PermissionManifest`
- `WorkerBrief`、`JudgeRubric`
- `PiWorkerCall`、`PiWorkerCallResult`
- `create_piagent_runtime_config`、`create_default_piworker_adapter`、
  `run_piworker_call`
- refs、evidence、extension、sandbox、progress 等边界原语
- packaged PiAgent runtime discovery / preflight

更高层的产品语义属于外部 integration，例如 `integrations/deepresearch`；
它不应该进入 `src/missionforge` 的产品中立核心。

## 安装

```bash
python3 -m pip install -e .
```

`missionforge` Python 包会携带 PiAgent runtime 的源码、构建入口和 npm
manifest。默认 adapter 在真正执行 PiAgent 前，会把包内 runtime 物化到
`$MISSIONFORGE_RUNTIME_HOME`，或默认的用户 cache 目录，并在该目录中执行
`npm ci --ignore-scripts`。导入 `missionforge` 本身不会写入当前目录、安装 npm
依赖或启动 worker。

Linux 强隔离 sandbox 是显式启用能力：

```bash
python3 -m pip install -e ".[sandbox-linux]"
```

该 extra 表示应用要求 Linux bubblewrap/seccomp 后端；系统仍需提供 `bwrap` 和
`libseccomp`。没有这个后端时，MissionForge 仍提供 context、contract、refs、
permission manifest、tool gateway 和 PiAgent 控制面，但不能宣称对任意 bash/code
execution 提供 OS 级强隔离。

可以在应用启动时做能力检查：

```python
import missionforge as mf

report = mf.preflight_pi_agent_runtime(require_sandbox_linux=True)
if not report.available:
    raise RuntimeError(report.failures)
```

## 最小调用

```python
import missionforge as mf

call = mf.PiWorkerCall(
    call_id="call-001",
    role=mf.PiWorkerCallRole.EXECUTOR,
    contract_id="contract-001",
    contract_hash="sha256:" + "a" * 64,
    contract_ref="contract/task_contract.json",
    objective="Produce reports/final.md from the visible refs.",
    visible_refs=["contract/task_contract.json"],
    writable_refs=["reports"],
    expected_output_refs=["reports/final.md"],
    permission_manifest_ref="policy/permission_manifest.json",
)

result = mf.run_piworker_call(call, workspace="/tmp/missionforge-run")
```

`PiWorkerCallResult` 是运行边界证据，不是语义验收结论。语义接受必须来自
独立 judge 角色或产品 integration 生成的验收 artifact。

## DeepResearch

DeepResearch 是随仓库维护的完整示例工程，但按外部应用方式使用
MissionForge：示例源码只通过 `import missionforge` 调用公开 API。安装
`missionforge-deepresearch` 后运行：

```bash
missionforge-deepresearch academic kernel-v2-run \
  --topic "你的调研主题" \
  --request-id research-001 \
  --workspace /tmp/mf-dr \
  --research-intensity standard \
  --live-extension-mode \
  --kernel-v2-adapter-mode piworker \
  --piworker-provider-config-source codex_current \
  --stream-progress
```

CLI 会输出已经存在的关键文件绝对路径，包括 `final_report`、`source_packet`、
`result_package`、`judge_report` 和 `usage_summary`。

## 验证

```bash
PYTHONPATH=src python3 -m unittest \
  tests.test_public_api_boundary \
  tests.test_piworker_call \
  tests.test_pi_agent_runtime_adapter \
  tests.test_kernel_api

PYTHONPATH=src:integrations/deepresearch/src python3 -m unittest \
  integrations.deepresearch.tests.test_kernel_v2 \
  integrations.deepresearch.tests.test_cli \
  integrations.deepresearch.tests.test_deepresearch_import_boundaries

npm test --prefix workers/pi-agent-runtime
```

## 设计原则

- 原始聊天记录不是可执行任务真相。
- 冻结后的 `TaskContract`，或显式 revision，才是持久任务权威。
- 代码可以拒绝格式错误、不安全、过期、未授权或缺少引用的输出。
- 代码不假装执行产品级语义判断。
- 产品语义属于 integrations、profiles、manuals、rubrics 和 artifacts。
- MissionForge core 保持产品中立，并围绕 PiWorker 运行边界构建。

建议从这些文档开始：

- [Kernel API Design](docs/KERNEL_API_DESIGN.md)
- [Deep Research Roadmap](docs/DEEP_RESEARCH_ROADMAP.md)
- [API Boundary](docs/API_BOUNDARY.md)
