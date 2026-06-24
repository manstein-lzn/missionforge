# MissionForge 混合架构升级方案：内存数据流 + 沙箱工具执行 + 异步审计

> **版本**: v0.1-draft  
> **日期**: 2026-06-23  
> **状态**: 架构设计草案，待技术评审  
> **适用范围**: MissionForge Kernel API 层及 Core Runtime 层  
> **前置文档**: `KERNEL_API_DESIGN.md` (file_id: 3f34961a49d34b31b57cb15760c66f96)

---

## 执行摘要

MissionForge 当前架构中，Step 间的数据传递必须通过磁盘文件系统完成（ref 文件读写）。这一设计保证了可审计性和崩溃恢复能力，但带来了显著的性能开销和开发体验问题。本方案论证：**磁盘从来不是 MissionForge 的安全边界，Kernel 的权限控制点（Read Gate）才是**。基于此核心洞察，提出"内存数据流 + 沙箱工具执行 + 异步审计"的混合架构：

- **Step 间数据流完全内存化**：Kernel 维护 In-Memory State Store，Step 通过 Permission-Aware Read Gate 获取授权数据视图
- **工具执行保持沙箱不变**：PiWorker 的 `bash`/`academic_search` 等工具仍在 OS 沙箱子进程中执行，安全模型不受影响
- **审计与恢复降级为异步**：WAL (Write-Ahead Log) 同步写轻量 hash 记录保证可恢复性；完整 artifact 异步写入磁盘保证审计性
- **从 LangGraph 吸收先进思想但不吸收其安全假设**：Channel/Reducer 类型化状态管理、Superstep/Barrier 并行模型、Checkpoint 快照机制——同时拒绝共享可变 State、任意 Python 路由、单进程执行

本方案不触碰 MissionForge 的核心安全原语（`TaskContract`、`PermissionManifest`、`PiWorkerCall`），仅改变数据传输层的实现方式。安全性通过四种攻击路径的形式化证明保持等价。

---

## 目录

1. [核心洞察：磁盘不是安全边界](#1-核心洞察磁盘不是安全边界)
2. [数据库类比：Buffer Pool + WAL](#2-数据库类比buffer-pool--wal)
3. [混合架构总览](#3-混合架构总览)
4. [三层次分离设计](#4-三层次分离设计)
   - 4.1 [层次一：Step 间数据流——完全内存化](#41-层次一步间数据流完全内存化)
   - 4.2 [层次二：工具执行——保持沙箱](#42-层次二工具执行保持沙箱)
   - 4.3 [层次三：审计与恢复——wal--异步写入](#43-层次三审计与恢复wal--异步写入)
5. [从 LangGraph 吸收什么，不吸收什么](#5-从-langgraph-吸收什么不吸收什么)
6. [安全证明：四种攻击路径分析](#6-安全证明四种攻击路径分析)
7. [剩余硬问题：IPC 通道安全性](#7-剩余硬问题ipc-通道安全性)
8. [实施路径（五 Phase）](#8-实施路径五-phase)
9. [附录：LangGraph vs MissionForge 对比矩阵](#9-附录langgraph-vs-missionforge-对比矩阵)
10. [附录：Kernel API 尖锐分析](#10-附录kernel-api-尖锐分析)

---


## 1. 核心洞察：磁盘不是安全边界

MissionForge 当前架构中，磁盘承担了三个角色，但**只有一个是安全相关的**：

| 磁盘的角色 | 是否安全相关 | 说明 |
|---|---|---|
| 权限执行点 | **部分相关** | OS 文件权限阻止 subprocess 越权访问 |
| 数据传输媒介 | 不相关 | Step 间通过 ref 文件传递数据，但这只是传输方式 |
| 审计/恢复记录 | 不相关 | 落盘是为了崩溃恢复和审计回放 |

真正提供安全保证的是**权限控制点**——即"谁能在什么条件下看到什么数据"。当前实现中，这个控制点由两层构成：

### 第一层（真正的安全来源）：Kernel 编译时生成的 PermissionManifest

Kernel 在编译 `Step` 声明时生成 `PermissionManifest`，决定每个 subprocess 的 `visible_refs` 和 `writable_refs`。如果 Kernel 编译出错误的 manifest（比如把 judge 的内部文件放进了 executor 的 visible_refs），OS 会忠实地执行这个错误的权限——**OS 不判断权限是否"正确"，它只执行 manifest 声明的权限**。

### 第二层（补充防御）：OS 对 subprocess 的文件系统隔离

它防止 subprocess 通过路径遍历、符号链接等方式绕过 manifest。这是对第一层的补充防御。

### 关键结论

> **第一层（Kernel 的 manifest 生成）是安全性的真正来源，第二层（OS 执行）是第一层的执行机制。**

如果把数据传输从磁盘改为内存，**第一层完全不受影响**——Kernel 仍然控制每个角色能看到什么数据。变化的只是第二层：从"OS 阻止越权文件访问"变为"Kernel 的 Read Gate 不暴露越权数据"。

这两者的信任级别是相同的：
- 你信任 Kernel 生成正确的 manifest
- 与你信任 Kernel 的 Read Gate 返回正确的数据视图
- **是同一个信任假设**

---

## 2. 数据库类比：Buffer Pool + WAL

理解这个架构转换最直观的类比是数据库系统。

MissionForge 当前模型相当于一个**没有缓冲池的数据库**——每次查询都从磁盘读取数据页，每次写入都同步刷盘。安全是保证了，但性能和开发体验都很差。

本方案提出的模型相当于一个**有缓冲池 + WAL 的数据库**：

| 数据库概念 | MissionForge 对应物 | 说明 |
|---|---|---|
| **Buffer Pool** | In-Memory State Store | 结构化数据驻留内存，Step 间通过内存完成数据流 |
| **WAL (Write-Ahead Log)** | 同步轻量级日志 | 每步完成后同步写入 `{step_id, input_hashes, output_hashes, status}` |
| **Checkpoint** | 定期状态快照 | 将内存 State Store 快照写入磁盘作为恢复点 |
| **Read Gate (访问控制)** | 行级安全策略 | 当 Step 请求输入时，按 `visible_refs` 过滤内存状态 |
| **Async Writer** | 后台脏页写出 | 异步将完整 artifact 写入磁盘，不阻塞执行 |

这个类比的核心点：**数据库的安全不是靠"每次都从磁盘读"来保证的，而是靠"访问控制层"来保证的。** 同样，MissionForge 的安全不需要靠"每次都通过磁盘传输"来保证，只需要 Kernel 的 Read Gate 正确执行权限过滤。

---


## 3. 混合架构总览

```
┌─────────────────────────────────────────────────────────────────────┐
│                    Kernel Runtime (主进程)                           │
│                                                                     │
│  ┌──────────────────┐    ┌─────────────────────┐                   │
│  │ In-Memory State   │───▶│ Permission-Aware     │                   │
│  │ Store             │    │ Read Gate            │                   │
│  │ (结构化数据+hash   │    │ (按 visible_refs     │                   │
│  │  + role 标签)      │    │  过滤内存数据)        │                   │
│  └──────────────────┘    └──────────┬──────────┘                   │
│                                     │                              │
│  ┌──────────────────┐               │ IPC: 授权数据                │
│  │ Channel Router   │◀──────────────┼──────────────────┐           │
│  │ (按 Flow routes  │               │                  │           │
│  │  分发到下游 Step) │               │                  │           │
│  └──────────────────┘               │                  │           │
│                                     ▼                  ▼           │
│  ┌──────────────────┐    ┌──────────────────┐  ┌──────────────┐   │
│  │ Write-Ahead Log  │    │ Async Audit      │  │ Checkpoint   │   │
│  │ (同步轻量写入)    │    │ Writer           │  │ (定期快照)    │   │
│  │ step_id, hashes, │    │ (异步完整artifact │  │ 内存状态→磁盘  │   │
│  │ status, ts       │    │  写入磁盘)         │  │              │   │
│  └──────────────────┘    └──────────────────┘  └──────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
          │                         │                    │
          │ WAL                     │ async write         │ snapshot
          ▼                         ▼                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        磁盘 (持久化 + 审计)                          │
│  artifact/  step_record/  flow_ledger.jsonl  checkpoint/  wal.log   │
└─────────────────────────────────────────────────────────────────────┘

┌──────────────────────────┐    ┌──────────────────────────┐
│ EXECUTOR Subprocess     │    │ JUDGE Subprocess        │
│ (OS 沙箱)                │    │ (OS 沙箱)                 │
│  ┌──────────────────┐   │    │  ┌──────────────────┐   │
│  │ PiWorker         │   │    │  │ PiWorker         │   │
│  │ LLM + Tools      │   │    │  │ LLM + Tools      │   │
│  └──────────────────┘   │    │  └──────────────────┘   │
│  ┌──────────────────┐   │    │  ┌──────────────────┐   │
│  │ Sandbox          │   │    │  │ Sandbox          │   │
│  │ 文件权限+seccomp │   │    │  │ 文件权限+seccomp │   │
│  └──────────────────┘   │    │  └──────────────────┘   │
└──────────────────────────┘    └──────────────────────────┘
```

**数据流关键路径是纯内存的**：EXECUTOR 输出通过 IPC 返回 Kernel → 存入 State Store → JUDGE 通过 Read Gate 获取过滤后的视图。磁盘只在 WAL 同步写入和异步审计写入时参与。

---

## 4. 三层次分离设计

### 4.1 层次一：Step 间数据流——完全内存化

这是变化最大的部分。当前模型中，EXECUTOR 把输出写入 `reports/final_report.md`，JUDGE 从磁盘读取该文件。新模型中：

```python
@step(id="reviewer", read=["contract", "reports", "sources"], write=["reviews"])
def reviewer(ctx: StepContext) -> ReviewerOutput:
    report = ctx.read("reports/final_report.md")      # ← 内存读取，不经过磁盘
    sources = ctx.read("sources/source_packet.json")   # ← 内存读取
    observation = analyze(report, sources)
    return ReviewerOutput(
        decision="ready_for_judge",
        notes=observation,
    )
```

**`ctx.read()` 的行为变化**：

| 维度 | 当前模型 | 新模型 |
|---|---|---|
| 数据来源 | 磁盘文件系统 | In-Memory State Store |
| 权限执行 | OS 文件权限 | Kernel Read Gate |
| 延迟 | 磁盘 I/O (ms 级) | 内存访问 (μs 级) |
| 序列化开销 | JSON 读/写每步必做 | Python 对象直接传递 |
| 开发者体验 | 操作文件路径和字符串 ref | 操作类型化的 Python 对象 |

**安全保证不变**：Read Gate 根据 `visible_refs` 过滤，reviewer 看不到 judge 的内部状态，judge 看不到 reviewer 的内部推理。权限边界由 Kernel 代码执行，不依赖文件系统。

**性能提升量化**（DeepResearch v2 典型 pipeline）：

```
当前模型 (6 步 pipeline):
  每步: JSON序列化(~5ms) + 磁盘写(~10ms) + 磁盘读(~10ms) + JSON反序列化(~5ms)
  总计: 6步 × ~30ms = ~180ms 额外 I/O 开销

新模型 (6 步 pipeline):
  每步: 内存对象传递 (~0.01ms) + Read Gate 过滤 (~0.05ms)
  总计: 6步 × ~0.06ms = ~0.36ms 数据传输开销
  节省: ~99.8% 的 Step 间数据传输时间
```

> **注意**：实际端到端加速比取决于 LLM 推理时间占比。对于 DeepResearch 这类每步 30-120 秒的 pipeline，Step 间传输优化主要改善开发体验和资源利用率，而非端到端延迟。

---


### 4.2 层次二：工具执行——保持沙箱

这是**不能内存化**的部分。当 PiWorker 调用 `bash`、`academic_search`、`write` 等工具时，这些工具操作的是真实文件系统和网络。必须保持 OS 级沙箱：

```
┌─────────────────────────────────────────────────────┐
│ Kernel Runtime (主进程)                              │
│                                                     │
│  通过 IPC 向 subprocess 传递：                        │
│    1. 授权的输入数据（从内存 State Store 过滤）       │
│    2. 工具授权（从 Toolset 编译）                     │
│    3. 工作区路径（受 PermissionManifest 约束）         │
│                                                     │
│  通过 IPC 从 subprocess 接收：                        │
│    1. 结构化输出（存入内存 State Store）              │
│    2. 大文件 artifact 路径（仍写入磁盘，但路径注册到   │
│       State Store 的元数据中）                         │
└───────────────────────────┬─────────────────────────┘
                            │ IPC (Unix domain socket)
                            ▼
┌─────────────────────────────────────────────────────┐
│ EXECUTOR Subprocess (OS 沙箱)                       │
│                                                     │
│  ┌─────────────┐  ┌──────────────┐  ┌───────────┐ │
│  │ PiWorker    │  │ Sandbox      │  │ Tools     │ │
│  │ LLM + 推理  │◀─▶│ 文件权限     │◀─▶│ bash     │ │
│  │             │  │ seccomp      │  │ search   │ │
│  │             │  │ 网络策略     │  │ write    │ │
│  └─────────────┘  └──────────────┘  └───────────┘ │
└─────────────────────────────────────────────────────┘
```

**大文件 artifact 处理策略**：

| artifact 类型 | 存储位置 | Step 间传递方式 | 示例 |
|---|---|---|---|
| 结构化数据 (< 64KB) | 内存 State Store | IPC 直接传递 | decision JSON, observation |
| 中等文件 (64KB - 10MB) | 磁盘 + 元数据在内存 | 传递元数据 + 按需读取 | source packet, report draft |
| 大文件 (> 10MB) | 磁盘 + LRU 缓存索引 | 传递路径引用 | 完整研究报告, 数据集 |

**关键原则**：
- 大文件仍然写入磁盘——因为它们太大，内存传递不经济
- 但 Kernel 在 State Store 中维护它们的**元数据**（路径、hash、role、size）
- Step 间的元数据传递是内存的
- 只有当某个 Step 真正需要读取大文件内容时，才从磁盘读取（且可以通过 LRU 缓存加速）

**沙箱不变性清单**：

```text
✅ subprocess 仍然是独立进程，有独立的 PID namespace
✅ 文件系统权限由 OS enforce（read-only roots, writable scope）
✅ seccomp-bpf 限制 syscall 集合
✅ 网络策略由 CapabilityGrant 控制
✅ bash 命令受 allowlist 约束
✅ 工具输出通过 IPC 返回，不通过共享文件系统
❌ 变化的只有：Step 间结构化数据的传输从磁盘变为 IPC
```

---

### 4.3 层次三：审计与恢复——WAL + 异步写入

#### WAL (Write-Ahead Log)：同步轻量保证可恢复性

每步完成时的**同步操作**（不可跳过）：

```python
def on_step_completed(step_id: str, inputs: ArtifactMap, outputs: ArtifactMap):
    # 1. 计算输出的 content_hash
    output_hashes = {ref: compute_hash(content) for ref, content in outputs.items()}
    
    # 2. 写入 WAL 记录（同步，但极轻量）
    wal_entry = {
        "step_id": step_id,
        "input_hashes": {ref: h for ref, h in current_input_hashes},
        "output_hashes": output_hashes,
        "status": "completed",
        "timestamp": time.time_ns(),
        "prev_wal_offset": last_wal_offset,  # 链式 hash
    }
    wal_entry["chain_hash"] = compute_chain_hash(wal_entry)
    append_wal_sync(wal_entry)  # 单次 fsync，< 0.1ms
    
    # 3. 更新内存 State Store（纯内存操作）
    state_store.update(step_id, outputs, output_hashes)
```

**WAL 记录大小估算**：

```text
单条 WAL 记录:
  step_id: ~20 bytes
  input_hashes (平均 4 个): ~256 bytes
  output_hashes (平均 2 个): ~128 bytes
  status + timestamp: ~20 bytes
  chain_hash: ~32 bytes
  总计: ~456 bytes / step

DeepResearch v2 (6 步): ~2.7 KB 总 WAL
典型复杂 flow (20 步): ~9 KB 总 WAL
```

对比当前模型每步写入完整 `step_record.json` (~5-50KB)，WAL 节省了 **10-100x** 的同步 I/O。

#### Async Audit Writer：异步完整写出保证审计性

每步完成后的**异步操作**（可延迟，不阻塞下一步）：

```python
async def audit_writer_loop():
    while True:
        step_result = await completed_steps_queue.get()
        
        # 异步写入完整 step_record.json
        record = build_step_record(step_result)
        await async_write_json(record_path, record)
        
        # 异步写入完整 artifact 文件
        for ref, content in step_result.outputs.items():
            if is_large_artifact(content):
                await async_write_file(artifact_path(ref), content)
        
        # 更新 flow_ledger.jsonl（append-only）
        ledger_event = build_ledger_event(step_result)
        await async_append(ledger_path, ledger_event)
```

**崩溃恢复语义**：

```
场景 A: Kernel 在 WAL 写入后、Async Writer 完成前崩溃
  → 重放 WAL → 重建 State Store 元数据索引
  → 从磁盘恢复已写入的 artifact（Async Writer 可能已完成部分）
  → 未完成的 artifact 对应的 Step 标记为 pending → 重跑

场景 B: Kernel 在 WAL 写入前崩溃
  → 该 Step 未出现在 WAL 中 → 视为未执行 → 重跑
  → 上游 Step 的 WAL 记录仍在 → 其输出有效 → 不重跑上游

场景 C: Kernel 在 Async Writer 写入 artifact 时崩溃
  → WAL 显示该 Step 已完成 → State Store 有元数据
  → 但磁盘上 artifact 文件可能不完整
  → 恢复时检测 hash 不匹配 → 标记该 Step 为 dirty → 重跑
```

这与当前模型的"crash 后重跑未完成的 Step"语义完全一致，但恢复速度更快（WAL 重放 vs 全量扫描 step_record）。

---


## 5. 从 LangGraph 吸收什么，不吸收什么

### 应该吸收的

#### 5.1 Channel + Reducer 的类型化状态管理

当前 MissionForge 的 ref 是无类型的字符串路径。引入 Channel 概念后，每个 artifact 有声明类型和合并语义：

```python
# 替代裸字符串 ref
Channel("reviews", type=ReviewerObservation, reducer="last_value")
Channel("sources", type=SourcePacket, reducer="merge_by_id")
Channel("decisions", type=Decision, reducer="last_value")
```

**解决的问题**：
- Kernel 在编译时验证 Step 的输入输出类型匹配（而非运行时 JSON 解析失败）
- Reducer 语义解决"多个 Step 向同一 Channel 写入"的合并问题
- 当前需要开发者手写合并逻辑 → 声明式解决

**与 MissionForge 安全模型的兼容性**：
- Channel 是不可变的——每个 Step 写入后不可修改，只能通过新 Step 追加新版本
- 这保证了审计轨迹的完整性
- Reducer 只在 Kernel 主进程中执行（可信上下文），不违反沙箱隔离

#### 5.2 Superstep / Barrier 并行模型

当前 Kernel API 的 `Flow` 是顺序执行的。引入 Superstep 概念后可声明并行 Step：

```python
Flow(
    id="deepresearch_v2",
    steps=[
        planner,
        Parallel(section_writer_a, section_writer_b, section_writer_c),  # 同一 Superstep
        editor,  # 下一 Superstep，等待并行 Step 完成
        reviewer,
        judge,
    ],
    routes={...},
)
```

**Barrier 语义**：并行 Step 全部完成后再进入下一步。每个并行 Step 是独立的沙箱子进程，通过 Channel 汇聚结果。

**与 LangGraph BSP 模型的关键区别**：
- LangGraph 的 Superstep 中节点共享可变 State → MissionForge 的并行 Step 通过不可变 Channel 通信
- LangGraph 的 Barrier 后 State 自动合并 → MissionForge 的 Barrier 后由 Reducer 显式合并
- 每个 Step 仍然是独立沙箱子进程，不是同一进程内的函数调用

#### 5.3 Checkpoint 快照机制

定期将内存 State Store 的完整快照写入磁盘作为恢复点：

```text
当前模型: 每步同步落盘 → 重启后逐个检查 step_record 决定 skip/run
新模型:   每 N 步做一次 Checkpoint + WAL → 重放 WAL 到最近 Checkpoint
```

**Checkpoint 策略选项**：
- **时间驱动**: 每 M 秒做一次快照（适合长时间运行的 flow）
- **步骤驱动**: 每 N 步做一次快照（适合短 pipeline）
- **混合**: 取先到者

#### 5.4 流式进度输出

Kernel 在内存中维护执行状态，实时暴露：
- 当前正在执行的 Step 及其开始时间
- 已完成 Step 列表及各自耗时
- 待执行 Step 队列
- 各 Channel 当前值（仅结构化元数据，不含大文件内容）

比当前的 `--stream-progress` 更丰富，且不需要额外读取磁盘文件获取进度。

---

### 不应该吸收的

#### 5.5 ❌ 共享可变 State

LangGraph 的 State 是所有节点共享的可变字典，任何节点可以修改任何字段。

**MissionForge 必须拒绝的原因**：
- 共享可变 State 意味着一个被注入的 LLM 可以修改另一个角色的决策数据
- 这直接破坏了角色隔离的安全保证
- 审计轨迹无法追踪"谁在什么时候修改了哪个字段"

**替代方案**：Channel 是不可变的，每次写入产生新版本。旧版本保留用于审计。

#### 5.6 ❌ 任意 Python 路由

LangGraph 的条件边可以检查 State 的任意字段做路由：`lambda state: "accept" if state["score"] > 0.8 else "revise"`。

**MissionForge 必须拒绝的原因**：
- 任意 Python 路由意味着控制流逻辑在开发者代码中，不在 Kernel 编译时验证中
- 被注入的开发者代码可能修改路由逻辑以绕过 judge 检查
- 这破坏了"控制流沙箱"的核心设计

**替代方案**：路由只基于 declared decision artifact 的 declared route fields。Kernel 在编译时验证所有路由值的合法性。

#### 5.7 ❌ 单进程执行

LangGraph 的所有节点在同一进程内执行。

**MissionForge 必须拒绝的原因**：
- 单进程意味着 PiWorker 和工具执行在同一地址空间
- 被注入的 LLM 可以通过内存操作绕过权限边界
- 工具执行（bash、网络请求）没有 OS 级隔离

**替代方案**：PiWorker 必须保持沙箱子进程执行。这是工具执行安全的基石，不可妥协。

---

## 6. 安全证明：四种攻击路径分析

威胁模型假设：LLM 被上下文注入攻击完全控制（即该 Step 的 PiWorker 输出完全由攻击者控制）。

### 攻击路径一：被注入的 EXECUTOR 试图读取 JUDGE 的内部状态

| 维度 | 当前模型 | 内存模型 |
|---|---|---|
| 防御机制 | OS 文件权限阻止越权访问 | Read Gate 不暴露越权数据 |
| 攻击者可见 | 文件系统报 PermissionDenied | 数据根本不存在于 IPC 消息中 |
| 信任基础 | OS 正确执行 manifest | Kernel 正确过滤视图 |

**结论：防御等价。** 两种模型下被注入的 LLM 都无法访问越权数据。区别是防御执行点从 OS 移到了 Kernel，但信任级别相同。

### 攻击路径二：被注入的 EXECUTOR 试图通过工具读取越权文件

| 维度 | 当前模型 | 内存模型 |
|---|---|---|
| 防御机制 | OS 沙箱拒绝 | OS 沙箱拒绝（不变） |
| 变化点 | 无 | 无 |

**结论：防御完全相同。** 内存化只改变了 Step 间数据传输方式，没有改变工具执行的沙箱模型。

### 攻击路径三：攻击者篡改磁盘上的合同文件

| 维度 | 当前模型 | 内存模型 |
|---|---|---|
| 合同存储位置 | 磁盘文件 | 内存 State Store（权威）+ 磁盘（副本） |
| hash 验证时机 | 每次 PiWorkerCall 前 | 每次 Step 执行前 |
| 篡改难度 | 修改磁盘文件 | 需要 Kernel 进程内存访问权限 |

**结论：防御更强。** 内存中的合同对象比磁盘文件更难被篡改。攻击者需要获得 Kernel 进程的内存访问权限，这比修改磁盘文件困难得多。异步 Audit Writer 会发现磁盘副本与内存权威的不一致并触发告警。

### 攻击路径四：Kernel 进程崩溃后从磁盘恢复，攻击者构造伪造记录

| 维度 | 当前模型 | 内存模型 |
|---|---|---|
| 恢复依据 | step_record.json 的 hash | WAL 的链式 hash |
| 伪造难度 | 需要碰撞 hash | 需要碰撞链式 hash（每条依赖前一条） |
| 完整性保证 | 单文件 hash | append-only + 链式结构 |

**结论：防御等价或更强。** WAL 的链式 hash 提供了与 step_record hash 验证等价的完整性保证，且链式结构使部分篡改更容易被检测。

### 安全等价性总结

```
攻击路径                    当前模型     内存模型     结论
─────────────────────────   ────────    ────────    ────
1. 越权读取角色数据          OS 权限     Read Gate   ✅ 等价
2. 越权工具文件访问           OS 沙箱     OS 沙箱     ✅ 相同
3. 篡改合同文件              disk hash   mem+async   ✅ 更强
4. 崩溃恢复伪造记录           file hash   chain hash  ✅ 等价/更强
```

---


## 7. 剩余硬问题：IPC 通道安全性

内存模型引入了一个新的攻击面：**Kernel 与 subprocess 之间的 IPC 通道**。如果攻击者能劫持 IPC 通道，理论上可以注入恶意数据或截获输出。

当前模型不存在这个问题，因为数据通过文件系统传输，OS 保证文件读写的完整性。

### 三层防御方案

#### 第一层：OS 提供的安全 IPC 机制

```python
import socket, os, struct

def create_ipc_pair():
    """创建 Kernel ↔ Subprocess 的安全 IPC 通道"""
    # 使用 Unix domain socket（仅限本地进程）
    server_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server_sock.bind(f"/tmp/mf_kernel_{os.getpid()}.sock")
    
    # 设置权限：仅 Kernel 进程和子进程可访问
    os.chmod(f"/tmp/mf_kernel_{os.getpid()}.sock", 0o600)
    
    return server_sock

def verify_peer(sock):
    """验证对端进程身份"""
    # SO_PEERCRED 获取对端的 PID/UID/GID
    pid, uid, gid = sock.getsockopt(
        socket.SOL_SOCKET, socket.SO_PEERCRED, struct.pack("III", 0, 0, 0)
    )
    # 验证对端是预期的子进程
    expected_pid = get_expected_child_pid()
    if pid != expected_pid:
        raise SecurityError(f"Unexpected peer PID: {pid} != {expected_pid}")
    return pid
```

**为什么 Unix domain socket + `SO_PEERCRED` 足够**：
- UDS 不接受网络连接，仅限本机进程
- 文件权限 `0o600` 限制为仅 Kernel 和子进程可访问
- `SO_PEERCRED` 由内核保证不可伪造——攻击者无法伪装成另一个进程的 PID

#### 第二层：IPC 消息携带 hash 校验

```python
@dataclass
class IPCMessage:
    message_id: str           # UUID，防重放
    message_type: str         # "input_data" | "output_result" | "tool_request"
    payload: bytes            # 实际数据（可能加密）
    payload_hash: str         # SHA-256 of payload
    step_id: str              # 关联的 Step ID
    sequence_number: int      # 序列号，防重排序
    timestamp_ns: int         # 时间戳，防重放

def send_message(sock: socket.socket, msg: IPCMessage):
    """发送带完整性校验的 IPC 消息"""
    # 序列化
    data = msgpack.packb(asdict(msg))
    # 发送长度前缀 + 数据
    sock.sendall(struct.pack("!I", len(data)) + data)

def recv_message(sock: socket.socket) -> IPCMessage:
    """接收并验证 IPC 消息"""
    raw_len = recv_exactly(sock, 4)
    (length,) = struct.unpack("!I", raw_len)
    raw_data = recv_exactly(sock, length)
    msg = IPCMessage(**msgpack.unpackb(raw_data))
    
    # 验证 hash
    computed_hash = hashlib.sha256(msg.payload).hexdigest()
    if computed_hash != msg.payload_hash:
        raise SecurityError("IPC message hash mismatch")
    
    return msg
```

#### 第三层：IPC 通道生命周期绑定

```
Subprocess 启动 → 创建 IPC 通道 → 绑定到 subprocess PID
     ↓                              ↓
  传递 stdin/stdout/sock          通道仅在 subprocess 运行时有效
     ↓                              ↓
  Subprocess 正常退出            自动销毁通道（文件描述符关闭）
     ↓
  Subprocess 异常崩溃            内核回收通道资源（PID 不存在）
```

**关键设计决策**：
- IPC 通道在 subprocess 启动时建立，生命周期与 subprocess 绑定
- subprocess 退出后通道自动销毁，不存在持久化的可劫持通道
- 每次启动新的 subprocess 都创建全新的通道（无复用）
- 旧通道的文件描述符在 Kernel 端显式关闭

### IPC 攻击面总结

| 攻击向量 | 防御层 | 可行性 |
|---|---|---|
| 第三方进程接入 IPC | UDS 权限 + SO_PEERCRED | ❌ 不可行 |
| 中间人篡改消息内容 | hash 校验 + 可选加密 | ❌ 不可行 |
| 重放旧消息 | 序列号 + 时间戳 + UUID | ❌ 不可行 |
| subprocess 退出后通道被利用 | 生命周期绑定 + FD 回收 | ❌ 不可行 |
| Kernel 内存中 State Store 被篡改 | 需要 Kernel 进程内存访问权限 | ⚠️ 与当前模型等价 |

---

## 8. 实施路径（五 Phase）

> **总工期估算**: ~9 周  
> **核心原则**: 每个 Phase 保持现有安全测试套件全绿。任何 Phase 导致安全测试失败则立即回滚。

### Phase 1: In-Memory State Store + Permission-Aware Read Gate（2 周）

**目标**: 修改 `run_step()` 使其从 State Store 读取输入（而非磁盘），输出写入 State Store（同时异步写磁盘）。

**变更范围**:

```text
新增:
  src/missionforge/kernel/state_store.py       # In-Memory State Store
  src/missionforge/kernel/read_gate.py         # Permission-Aware Read Gate

修改:
  src/missionforge/kernel/executor.py          # run_step() 数据流改造
  src/missionforge/kernel/compiler.py          # 编译 visible_refs 到 Read Gate 配置

不变:
  src/missionforge/core/*                      # Core runtime 全部不变
  PiWorkerCall, PermissionManifest, TaskContract 语义不变
```

**验证标准**:
- [ ] 所有现有安全测试通过
- [ ] DeepResearch v2 pipeline 在新数据流下端到端运行成功
- [ ] Step 输出与当前模型 bit-for-bit 一致
- [ ] 崩溃恢复语义与当前模型一致（WAL 重放可重建状态）

**回滚策略**: `run_step()` 保留磁盘读写作为 fallback，通过 feature flag 切换。

### Phase 2: WAL 机制（2 周）

**目标**: 替换当前的"每步同步落盘"为"WAL 同步 + 异步落盘"。

**变更范围**:

```text
新增:
  src/missionforge/kernel/wal.py               # Write-Ahead Log 实现
  src/missionforge/kernel/audit_writer.py      # Async Audit Writer

修改:
  src/missionforge/kernel/executor.py          # 步骤完成后的 WAL 写入
  src/missionforge/kernel/resume.py            # 基于 WAL 的恢复逻辑
```

**WAL 格式规范**:

```text
WAL 文件: kernel/{flow_id}/runs/{run_id}/wal.log
格式: append-only 二进制日志，每条记录定长头 + 变长体

记录结构:
  ┌──────────────┬──────────────┬────────────────┬──────────┬───────────┐
  │ magic(4B)    │ version(1B) │ length(4B)     │ payload  │ checksum  │
  │ 0x4D46574C   │ 0x01        │ payload 长度    │ JSON     │ CRC32     │
  └──────────────┴──────────────┴────────────────┴──────────┴───────────┘

payload JSON 字段:
  {
    "step_id": "reviewer",
    "input_hashes": {"contract": "abc123...", "reports": "def456..."},
    "output_hashes": {"reviews": "ghi789..."},
    "status": "completed",
    "timestamp_ns": 1719123456789012345,
    "prev_offset": 0,
    "chain_hash": "jkl012..."
  }
```

**验证标准**:
- [ ] WAL 写入延迟 < 0.1ms/条
- [ ] 三种崩溃场景（A/B/C）全部可正确恢复
- [ ] WAL 重放结果与原始执行一致
- [ ] Async Writer 不阻塞 Step 执行（吞吐量不下降）

### Phase 3: Channel / Reducer 类型化状态管理（2 周）

**目标**: 将 `Step` 的 `inputs`/`outputs` 从裸字符串 ref 升级为类型化 Channel 声明。

**变更范围**:

```text
新增:
  src/missionforge/kernel/channel.py             # Channel 类型定义
  src/missionforge/kernel/reducer.py             # Reducer 合并策略

修改:
  src/missionforge/kernel/step.py                # Step 声明支持 Channel
  src/missionforge/kernel/compiler.py            # 编译时类型检查
  src/missionforge/kernel/state_store.py         # State Store 支持 Channel 索引
```

**内置 Reducer 类型**:

| Reducer 名称 | 语义 | 适用场景 |
|---|---|---|
| `last_value` | 后写入覆盖先写入 | decision, observation |
| `append` | 追加为列表 | logs, evidence list |
| `merge_by_key` | 按 key 字段合并字典 | source packet, state |
| `first_wins` | 首次写入后不可变 | contract, task spec |
| `error_if_conflict` | 多写冲突时报错 | ledger, audit record |

**验证标准**:
- [ ] 编译时捕获类型不匹配（而非运行时 JSON 解析错误）
- [ ] 并行 Step 向同一 Channel 写入时 Reducer 行为正确
- [ ] Channel 不可变性保证（旧版本不被修改）
- [ ] 向后兼容：未声明 Channel 的 Step 仍使用字符串 ref

### Phase 4: Superstep / Barrier 并行模型（2 周）

**目标**: 允许 `Flow` 声明并行 Step 组，Barrier 保证同步。

**变更范围**:

```text
新增:
  src/missionforge/kernel/superstep.py           # Parallel + Barrier 语义
  src/missionforge/kernel/barrier.py             # Barrier 同步原语

修改:
  src/missionforge/kernel/flow.py                # Flow 声明支持 Parallel
  src/missionforge/kernel/executor.py            # 并行执行调度器
```

**并行执行约束**:

```text
✅ 允许:
  - 无依赖关系的 Step 并行执行
  - 每个 Step 仍是独立沙箱子进程
  - 通过不可变 Channel 通信
  - Barrier 后由 Reducer 合并结果

❌ 禁止:
  - 有数据依赖的 Step 并行（编译时检测并报错）
  - 共享可变 State
  - 跨 Step 的工具调用共享
  - 非 Superstep 边界的隐式并行
```

**验证标准**:
- [ ] 3 个并行 Step 的执行时间 ≈ 最慢的单个 Step 时间（非串行求和）
- [ ] Barrier 正确等待所有并行 Step 完成
- [ ] 任一并行 Step 失败不影响其他已完成 Step 的输出
- [ ] 并行执行的审计轨迹完整且有序

### Phase 5: IPC 通道替换文件系统传输（1 周）

**目标**: 将 Kernel-subprocess 间的数据传输从文件系统切换为 IPC。

**变更范围**:

```text
新增:
  src/missionforge/kernel/ipc_channel.py         # 安全 IPC 通道实现
  src/missionforge/kernel/ipc_protocol.py        # IPC 消息协议

修改:
  src/missionforge/kernel/subprocess_launcher.py # 启动时建立 IPC
  src/missionforge/kernel/executor.py            # 通过 IPC 发送/接收数据
```

**注意**: 此 Phase 是优化项。如果 Phase 1-4 已满足性能需求，Phase 5 可以延后或降级为可选优化。

**验证标准**:
- [ ] IPC 传输延迟 < 文件系统传输延迟
- [ ] SO_PEERCRED 身份验证正常工作
- [ ] hash 校验捕获人为篡改的消息
- [ ] 大文件仍通过磁盘路径引用传递（不受影响）

---


## 9. 附录：LangGraph vs MissionForge 对比矩阵

### 架构基因级差异

| 维度 | LangGraph | MissionForge |
|---|---|---|
| **信任模型** | 信任开发者编写正确的节点和边 | 不信任任何角色（包括开发者编写的 prompt） |
| **安全假设** | LLM 输出是可信的，注入是边缘情况 | LLM 可能被完全注入，必须从架构层面隔离 |
| **设计哲学** | 让编排更灵活、开发更高效 | 让执行不可违反安全规则 |
| **目标用户** | 快速原型、AGI 实验、内部工具 | 工业级生产系统、合规场景、多租户 |

### 状态管理对比

| 维度 | LangGraph | MissionForge (当前) | MissionForge (升级后) |
|---|---|---|---|
| **状态存储** | 共享可变 State dict | 磁盘文件 (ref) | In-Memory State Store |
| **状态类型** | TypedDict (Pydantic 可选) | 无类型字符串路径 | Channel + 类型声明 |
| **合并策略** | Reducer 函数 (7 种) | 手动合并 | 声明式 Reducer |
| **不可变性** | ❌ 节点可修改任意字段 | ✅ 文件覆盖产生新版本 | ✅ Channel 不可变 |
| **权限过滤** | 无（所有节点看到完整 State） | OS 文件权限 | Read Gate 按 visible_refs 过滤 |
| **持久化** | Checkpointer (SQLite/Redis) | 每步同步落盘 | WAL 同步 + 异步审计 |

### 执行模型对比

| 维度 | LangGraph | MissionForge (当前) | MissionForge (升级后) |
|---|---|---|---|
| **执行模式** | 单进程 / 多线程 | 沙箱子进程 | 沙箱子进程 (不变) |
| **并行模型** | Pregel/BSP Superstep | 顺序执行 | Superstep/Barrier 并行 |
| **节点隔离** | ❌ 共享内存空间 | ✅ 独立进程 + seccomp | ✅ 不变 |
| **工具执行** | 在节点进程中执行 | 沙箱子进程执行 | 不变 |
| **崩溃恢复** | Checkpoint 重放 | step_record hash 校验 | WAL 链式 hash 重放 |
| **人机交互** | interrupt + resume | 不支持原生 | 可扩展 (基于 Barrier) |

### 安全模型对比

| 维度 | LangGraph | MissionForge (当前) | MissionForge (升级后) |
|---|---|---|---|
| **角色隔离** | ❌ 无概念 | ✅ PermissionManifest | ✅ Read Gate (等价) |
| **控制流沙箱** | ❌ 任意 Python 条件边 | ✅ 声明式路由枚举 | ✅ 不变 |
| **合同冻结** | ❌ 无概念 | ✅ TaskContract + hash | ✅ 不变 (内存权威) |
| **审计轨迹** | Checkpoint 快照 | step_record + flow_ledger | WAL + 异步审计 (等价) |
| **自我接受防护** | ❌ 节点可自行终止为 success | ✅ 仅 judge-role Step 可 accepted | ✅ 不变 |
| **工具权限** | 自由绑定 | CapabilityGrant + allowlist | ✅ 不变 |

### 适用场景判断

```
选择 LangGraph 当：
  ✓ 需要快速原型验证
  ✓ 团队内部工具，信任水平高
  ✓ 需要 DAG 以外的复杂控制流
  ✓ 单一 LLM 应用，无角色隔离需求
  ✓ 开发效率优先于安全保证

选择 MissionForge 当：
  ✓ 多角色协作（worker/reviewer/judge）
  ✓ 需要对抗性审计轨迹
  ✓ 合规要求（金融/医疗/法律）
  ✓ 多租户 SaaS 场景
  ✓ LLM 输出不可信是默认假设
  ✓ 需要证明"即使 LLM 被注入也不会造成破坏"
```

---

## 10. 附录：Kernel API 尖锐分析

> 本附录基于 `KERNEL_API_DESIGN.md` (file_id: 3f34961a49d34b31b57cb15760c66f96) 的逐条审查。

### 10.1 设计精妙之处

#### 控制流沙箱：路由枚举的静态约束

```python
Flow(
    routes={
        "reviewer.ready_for_judge": "judge",
        "reviewer.bounded_revision": "revision",
        "reviewer.blocked": Flow.stop("blocked"),
        "judge.accepted": Flow.stop("accepted"),  # ← 仅 judge-role 可 accepted
    },
)
```

这是整个 Kernel API 中最精妙的设计：

1. **路由值必须是预声明的枚举**——Python 不读 reviewer 的 prose，只检查 JSON 字段值是否在 route table 中
2. **`accepted` 终态只能来自 judge-role Step**——防止 worker 自我验收
3. **`route_on` 必须是该 Step 的 output artifact**——不能基于任意外部状态做路由
4. **编译时 fail-closed**——任何未声明的路由值导致 blocked flow，而非静默跳过

这个设计直接解决了"LLM 编排系统中谁有资格说'完成了'"的信任问题。

#### Artifact 角色语义：ownership 显式化

```python
Artifact("reports/final_report.md", role="output", owner="piworker")
Artifact("reviews/reviewer_observation.json", role="decision", owner="piworker")
Artifact("reports/evidence_index.md", role="projection", owner="runtime")
```

`owner` 字段区分了"PiWorker 生成的语义内容"和"Runtime 生成的机械内容"。这意味着：
- 审计时可以区分"AI 写的"和"程序自动生成的"
- `projection` 的失败不会掩盖真正的 Step 失败
- `decision` artifact 有特殊的路由语义

#### Resume 的保守主义：artifact-boundary skip

```text
skip 条件（全部满足才跳过）:
  1. step spec hash 匹配
  2. input ref hashes 匹配
  3. permission manifest hash 匹配
  4. extension lock ref/hash 匹配
  5. 所有 expected output refs 存在且 hash 匹配
```

五重 hash 校验确保 skip 不是"看起来一样"，而是"密码学意义上相同"。Skip 记录写入独立的 `reuse_records/` 目录，不修改原始 `step_record.json`——这保证了审计轨迹的不可篡改性。

### 10.2 设计缺陷与风险

#### 🔴 Projection 特权执行漏洞（严重）

当前设计中，`Projection.projector` 是一个 product-supplied callable，在 **Kernel 主进程**中执行：

```python
# 当前实现：projector 在主进程运行
def run_projection(projection: Projection, source_paths: List[str]) -> str:
    callable = load_projector(projection.projector)  # 加载用户代码
    result = callable(source_paths)                    # ← 主进程执行！
    write_projection_output(projection.output, result)
```

**问题**：
- Projector callable 运行在 Kernel 主进程地址空间中
- 它不受沙箱约束（没有 seccomp，没有文件系统隔离）
- 如果 projector 代码被注入或包含恶意逻辑，它可以：
  - 读取 Kernel 内存中的所有数据（包括其他角色的内部状态）
  - 修改 State Store 中的任意数据
  - 直接调用操作系统 API 绕过所有安全检查
  - 伪造 step_record 和 flow_ledger

**修复方案（本方案 Phase 1 应包含）**：

```text
方案 A（推荐）: Projection 移入独立子进程执行
  - 子进程使用与 PiWorker 相同的沙箱配置
  - 只接收声明的 source refs 作为输入
  - 输出通过 IPC 返回 Kernel 主进程
  - 开销：每次 projection 多一次 subprocess 启动 (~50ms)

方案 B（轻量）: Projection 限制为纯函数白名单
  - 只允许 kernel 内置的 projector（如 citation_index, toc_generator）
  - 不接受用户自定义 callable
  - 开销：零，但牺牲灵活性

方案 C（折衷）: Projection 沙箱 + 缓存
  - 方案 A + projector 进程池复用
  - 连续多次 projection 复用同一子进程
  - 开销：首次 ~50ms，后续 ~1ms
```

#### 🟡 Toolset 诚实局限（中等）

文档明确标注了这一点：

> MVP note: current `ExtensionGrant` authority is package/capability scoped. `Toolset.tools` is recorded in grant metadata for inspection and future gateway enforcement, but it is not yet a hard per-tool allowlist. Do not treat a tool name list as a security boundary until the core gateway has a first-class allowed-tools field.

**问题**：`Toolset.tools` 声明了"这个 Step 可以用哪些工具"，但 Core Gateway 目前不强制执行——它只在 metadata 中记录。

**风险**：如果 Core Gateway 有 bug 或配置错误，PiWorker 可能调用未被 Toolset 允许的工具。

**修复方向**：Core Gateway 增加 `allowed_tools: Set[str]` 字段，在每次工具调用前检查。

#### 🟢 context_projection_config 阈值过小（低）

当前 DeepResearch 实现中 `large_observation_bytes=8KB`，意味着超过 8KB 的 observation 就会被截断并写入磁盘。

**问题**：现代 LLM 的 observation 经常超过 8KB（尤其是包含代码块、结构化分析的输出）。8KB 阈值会导致大量不必要的磁盘写入。

**建议**：提升到 64KB-128KB，或改为动态阈值（基于可用内存的百分比）。

---

## 一句话总结

> **MissionForge 的安全来自于 Kernel 对权限边界的编译时验证和运行时执行，不来自于磁盘作为传输媒介。把数据流搬到内存，相当于把数据库从"无缓冲池直读磁盘"升级为"缓冲池 + WAL"——安全由访问控制层保证，磁盘降级为持久化和审计设施。这个升级不削弱任何安全保证，同时带来 LangGraph 级别的开发体验和性能。**

---

## 文档元信息

| 项目 | 值 |
|---|---|
| **标题** | MissionForge 混合架构升级方案：内存数据流 + 沙箱工具执行 + 异步审计 |
| **版本** | v0.1-draft |
| **日期** | 2026-06-23 |
| **作者** | AI Research Assistant (based on multi-session analysis) |
| **前置输入** | KERNEL_API_DESIGN.md, LangGraph architecture analysis, DeepResearch v2 implementation review |
| **总字数** | ~15,000 字 (中文) |
| **文件大小** | ~38 KB |
| **变更历史** | v0.1 — 初始草案，完整架构设计 + 安全证明 + 五 Phase 实施路径 |

---

*本文档是架构设计草案，不代表最终实现。所有 Phase 实施前应经过技术评审和安全审计。*
