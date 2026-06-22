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

根包刻意只暴露一组小而正交的程序员 API：

- `TaskContract`、`WorkspacePolicy`、`PermissionManifest`
- `WorkerBrief`、`JudgeRubric`
- `PiWorkerCall`、`PiWorkerCallResult`
- `create_default_piworker_adapter`、`run_piworker_call`
- refs、evidence、extension、sandbox、progress 等边界原语

更高层的产品语义属于外部 integration，例如 `integrations/deepresearch`；
它不应该进入 `src/missionforge` 的产品中立核心。

## 安装

```bash
python3 -m pip install -e .
npm ci --ignore-scripts --prefix workers/pi-agent-runtime
npm run build --prefix workers/pi-agent-runtime
```

## 最小调用

```python
from missionforge import PiWorkerCall, PiWorkerCallRole, run_piworker_call

call = PiWorkerCall(
    call_id="call-001",
    role=PiWorkerCallRole.EXECUTOR,
    contract_id="contract-001",
    contract_hash="sha256:" + "a" * 64,
    contract_ref="contract/task_contract.json",
    objective="Produce reports/final.md from the visible refs.",
    visible_refs=["contract/task_contract.json"],
    writable_refs=["reports"],
    expected_output_refs=["reports/final.md"],
    permission_manifest_ref="policy/permission_manifest.json",
)

result = run_piworker_call(call, workspace="/tmp/missionforge-run")
```

`PiWorkerCallResult` 是运行边界证据，不是语义验收结论。语义接受必须来自
独立 judge 角色或产品 integration 生成的验收 artifact。

## DeepResearch

当前可用的 DeepResearch 路径是简化后的 kernel-v2 runner：

```bash
PYTHONPATH=src:integrations/deepresearch/src \
python3 -m missionforge_deepresearch.cli academic kernel-v2-run \
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
