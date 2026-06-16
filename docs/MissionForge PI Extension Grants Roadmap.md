# MissionForge 按需挂载 Pi 生态扩展 Roadmap

## 1. 背景与目标

Pi 原生 coding agent 默认工具集很小，主要是 `read`、`edit`、`write`、`bash`。这对基础编码任务足够，但面对真实工程场景会很快遇到能力缺口，例如：

- Web search / URL fetch / GitHub repo clone；
- MCP 生态工具；
- LSP、lint、type-check、formatter；
- 子代理、并行任务、动态 workflow；
- 本地知识库、长期记忆、上下文压缩；
- 浏览器、PDF、视频、可视化预览等能力。

Pi 生态已经通过 `pi install npm:<package>` 提供了大量 extension / skill / prompt / theme 包。MissionForge 不应该在 core 中预装这些工具，也不应该把 Pi 生态能力硬编码进核心运行时。

目标是建立一条清晰链路：

```text
MissionForge core 声明能力
  -> 编排阶段按任务选择需要的扩展
  -> 编译阶段安装并锁定扩展
  -> 部署/运行阶段在沙箱内挂载扩展
  -> 执行记录进入 refs-first 证据链
```

核心原则：

1. **core 只声明，不安装。**
2. **编排决定需要什么工具，不由 agent 在执行中任意扩权。**
3. **部署前先 compile，把声明解析为已安装、已锁定的扩展集。**
4. **运行时只加载 manifest 和 lockfile 中允许的工具。**
5. **风险归属明确：用户选择安装的第三方扩展，由用户承担供应链与联网行为风险。MissionForge 负责显式声明、边界执行和审计记录。**

---

## 2. 设计立场

### 2.1 MissionForge 的职责

MissionForge 的核心价值不是替用户审计所有第三方工具，而是提供：

- 冻结的 `TaskContract`；
- 明确的 `WorkspacePolicy`；
- 明确的 `PermissionManifest`；
- 可审计的 refs-first 运行证据；
- executor / judge 分离；
- repair / revision 显式化；
- replay 时可以还原关键决策输入。

因此扩展机制也应服务这些目标。

MissionForge 应该回答：

- 当前任务声明了哪些扩展？
- 每个扩展的 package、版本、能力类别是什么？
- 它是否需要网络、命令、环境变量或特殊沙箱权限？
- 编译后实际安装的是哪个精确版本和 integrity hash？
- 运行时加载了哪些扩展？
- agent 使用工具的行为是否留有足够证据？

MissionForge 不应该负责：

- 审计每个 npm 包的源码；
- 判断用户是否应该信任某个扩展作者；
- 在 `network_policy=enabled` 后阻止所有可能的数据外发；
- 替用户承担安装第三方扩展的供应链风险。

### 2.2 风险归属

#### 安装风险

第三方扩展安装带来的供应链风险由用户承担。谁选择安装，谁负责信任该包。

MissionForge 可以提供安全默认值，例如：

- 推荐 `npm ci --ignore-scripts`；
- 生成 lockfile；
- 记录 integrity；
- 在 runtime 校验实际加载版本。

但这些是可审计性和可复现性的机制，不是包安全承诺。

#### 联网风险

使用大模型本身已经意味着把任务上下文发送给用户配置的模型 endpoint。但这并不等于所有联网扩展都可以隐式外发数据。

区别在于：

- 模型 endpoint 是用户显式配置的信任域；
- 扩展代码可能访问任意第三方 endpoint。

因此 MissionForge 不需要替用户阻止所有外发，但必须让网络能力成为显式权限：

- 如果 `network_policy=disabled`，声明需要网络的扩展不得加载或不得执行联网功能；
- 如果 `network_policy=enabled`，表示用户显式接受联网工具可能产生的数据外发；
- 该选择必须进入 manifest / runtime report / decision ledger，方便事后审计。

---

## 3. 生命周期 Roadmap

### 0. 收口原则

MissionForge 的 extension 机制只做四件事：

1. core 声明可用能力；
2. 编排层选择需要的扩展；
3. 部署前把声明编译成 lock；
4. runtime 只加载 lock 中允许的工具，并把结果写入 refs-first 证据链。

不要把“扩展安装”“工具加载”“命令执行”“网络访问”揉成一层代码，也不要为了适配某个包把 core 变成产品分支。

### 阶段 A：声明 Declaration

位置：MissionForge core Python 层。

新增一个扩展授权结构，作为 `PermissionManifest` 的一部分。

建议命名：`ExtensionGrant` 或 `ToolGrant`。

示例结构：

```python
@dataclass(frozen=True)
class ExtensionGrant:
    grant_id: str
    package: str              # 例如 "npm:pi-web-access" 或 "local:extensions/pi-academic-sources"
    version_spec: str         # 声明期可以是范围，编译后必须精确
    capability: str           # 例如 "web", "mcp", "lsp", "subagent", "memory"
    config_ref: str | None = None
    requires_network: bool = False
    requires_bash: bool = False
    required_env: list[str] = field(default_factory=list)
    sandbox_profile_ref: str | None = None
    integrity: str | None = None
```

然后在 `PermissionManifest` 增加：

```python
tool_grants: list[ExtensionGrant] = field(default_factory=list)
```

声明阶段只表达意图：这个任务允许挂载哪些扩展。它不安装、不 import、不执行第三方代码。

#### 声明期示例

```json
{
  "manifest_id": "executor-permission-manifest",
  "schema_version": "permission_manifest.v2",
  "readable_refs": ["contract", "inputs"],
  "writable_refs": ["artifacts", "reports"],
  "allowed_commands": ["npm test", "python -m pytest"],
  "network_policy": "enabled",
  "tool_grants": [
    {
      "grant_id": "web-access",
      "package": "npm:pi-web-access",
      "version_spec": "0.10.7",
      "capability": "web",
      "config_ref": "policy/extensions/pi-web-access.json",
      "requires_network": true,
      "requires_bash": false,
      "required_env": [],
      "sandbox_profile_ref": null,
      "integrity": null
    }
  ]
}
```

### 阶段 B：编排 Orchestration

位置：Product Integration / FrontDesk / task compiler。

编排层根据任务类型、角色和风险边界决定扩展授权。

原则：

- executor 可以比 judge 拥有更多工具；
- judge 默认应更保守，除非评审确实需要联网或 LSP；
- repair 阶段继承原 contract 的工具边界，除非发生 explicit revision；
- 扩展授权是 frozen task truth 的一部分，不应由 agent 在运行中自己修改。

#### 典型策略

| 场景 | executor grants | judge grants |
|---|---|---|
| 纯代码修改 | read/edit/write/bash + lsp | read + maybe bash test |
| 依赖外部文档 | web-access | read only, optionally web-access |
| 大型重构 | lsp + subagents + code search | lsp + test bash |
| MCP 产品集成 | mcp-adapter with config_ref | usually disabled unless judging requires same service |
| 安全审计 | code search + lsp + maybe subagents | independent audit tools |

### 阶段 C：编译 Compilation

位置：新增 CLI / script，例如：

```bash
python -m missionforge.adapters.cli extensions compile \
  --manifest contract/permission_manifest.json \
  --out compiled/extension_lock.json \
  --install-root .missionforge/extensions
```

编译阶段做几件事：

1. 读取 `PermissionManifest.tool_grants`；
2. 解析 `npm:<package>` 或 `local:<workspace/ref>`；
3. 安装或复制对应包；
4. 锁定精确版本；
5. 记录 integrity / resolved URL；
6. 生成 `extension_lock.json`；
7. 可选地把 `integrity` 回填到 compiled manifest 或 runtime deployment bundle。

默认编译模式只校验已安装扩展。需要真实安装时，调用方必须显式选择
`--mode install`，并让安装行为落在受控的安装根目录里。

当前实现支持两种包来源：

- `npm:`：写入受控安装根目录的 `package.json`，执行 `npm install
  --ignore-scripts --package-lock=false`；
- `local:`：从当前工程工作区复制本地 Pi extension 包到安装根目录，
  用于尚未发布到 npm 的产品内置扩展。

#### extension_lock.json 示例

```json
{
  "schema_version": "missionforge_extension_lock.v1",
  "compiled_at": "2026-06-15T00:00:00Z",
  "source_permission_manifest_ref": "contract/permission_manifest.json",
  "extensions": [
    {
      "grant_id": "web-access",
      "package": "npm:pi-web-access",
      "name": "pi-web-access",
      "version": "0.10.7",
      "resolved": "https://registry.npmjs.org/pi-web-access/-/pi-web-access-0.10.7.tgz",
      "integrity": "sha512-...",
      "capability": "web",
      "requires_network": true,
      "install_path": ".missionforge/extensions/node_modules/pi-web-access"
    }
  ]
}
```

#### 编译期安全默认值

推荐但不强制：

```bash
npm install --ignore-scripts
npm audit signatures
npm ls --json
```

注意：`--ignore-scripts` 可能导致部分扩展不可用。是否允许 install scripts，应作为用户或部署配置的明确选择。

### 阶段 D：部署 Deployment

位置：部署包构建 / runtime image 构建。

部署阶段把以下内容打包到 runtime 环境：

- MissionForge Python core；
- Node sidecar；
- `PermissionManifest`；
- `WorkspacePolicy`；
- `extension_lock.json`；
- `.missionforge/extensions/node_modules` 或对应 bundle；
- sandbox runtime，例如 bubblewrap 配置。

目标：runtime 不再联网安装依赖，只加载已编译、已锁定的扩展。

### 阶段 E：运行 Runtime Loading

位置：`workers/pi-agent-runtime/src/tools.ts` / `runtime.ts`。

当前 `createMissionForgeTools` 是固定工具数组：

- read；
- edit；
- write；
- context-snapshot；
- bash，条件是 `allowed_commands.length > 0`。

需要改造成 async loader：

```typescript
export async function createMissionForgeTools(options: MissionForgeToolOptions): Promise<AgentTool[]> {
  const baseTools = createBaseMissionForgeTools(options);
  const extensionTools = await loadExtensionTools(options);
  return [...baseTools, ...extensionTools];
}
```

加载流程：

```typescript
for (const grant of permissionManifest.tool_grants ?? []) {
  const locked = extensionLock.findByGrantId(grant.grant_id);
  verifyGrantMatchesLock(grant, locked);
  verifyNetworkPolicy(grant, permissionManifest.network_policy);
  verifyEnvAllowlist(grant, permissionManifest.env_allowlist);
  verifySandboxProfile(grant, sandboxProfile);

  const provider = await importExtensionProvider(locked.install_path);
  const tools = await provider.createMissionForgeTools({
    grant,
    config: loadConfigRef(grant.config_ref),
    workspaceRoot,
    permissionManifest,
    sandboxProfile,
    gateway,
    recorder
  });

  register tools;
}
```

---

## 4. Runtime 接口建议

### 4.1 MissionForge-aware Extension Provider

为避免任意 Pi 扩展绕过 MissionForge 边界，推荐定义一个轻量适配接口。

```typescript
export interface MissionForgeExtensionProvider {
  manifest: {
    name: string;
    version: string;
    capabilities: string[];
    requiresNetwork?: boolean;
    requiresBash?: boolean;
  };

  createMissionForgeTools(context: MissionForgeExtensionContext): Promise<AgentTool[]>;
}

export interface MissionForgeExtensionContext {
  grant: ExtensionGrant;
  config: unknown;
  workspaceRoot: string;
  permissionManifest: PermissionManifest;
  sandboxProfile?: SandboxProfile;
  gateway: ToolGateway;
  recorder: EvidenceRecorderLike;
}
```

理想状态下，扩展都实现这个接口，所有文件、命令、网络相关操作都走 MissionForge 注入的上下文。

### 4.2 兼容普通 Pi extension

现实中大部分 Pi extension 不会立即支持 MissionForge 接口。因此可以支持两类加载方式：

1. `missionforge_provider`：原生支持 MissionForge，优先推荐；
2. `pi_extension_adapter`：通过适配器加载普通 Pi extension，能力和审计较弱。

普通 Pi extension 的加载策略：

- 必须声明 `adapter_mode: "untrusted_pi_extension"`；
- 必须运行在沙箱中；
- 如果声明 `requires_network=true`，则需要 `network_policy=enabled`；
- runtime report 中必须标记为 lower-observability tool；
- judge 阶段默认不加载 untrusted extension，除非 manifest 显式允许。

---

## 5. 沙箱策略

### 5.1 沙箱负责什么

沙箱主要负责：

- 限制 agent 和扩展可见文件范围；
- 限制可写范围；
- 限制可执行命令；
- 隔离宿主环境；
- 限制环境变量暴露；
- 在可能时限制网络命名空间。

这可以大幅降低"任意工具"对宿主系统造成破坏的风险。

### 5.2 沙箱不负责什么

沙箱不等于完整安全承诺。它不负责：

- 审计第三方包源码；
- 保证联网工具不外发已授权可见的数据；
- 让所有工具行为自动可 replay；
- 证明工具输出没有被外部服务影响；
- 替用户决定是否信任某个 extension。

### 5.3 与 network_policy 的关系

`network_policy` 是 MissionForge 的显式权限声明。

建议规则：

- `disabled`：不得加载 `requires_network=true` 的扩展；
- `restricted`：只允许加载可被 runtime/network proxy 限制目标域名的扩展；
- `enabled`：允许联网扩展，用户承担联网行为风险；
- 所有联网扩展加载事件必须进入 runtime report。

---

## 6. 审计与 Replay

为了保持 MissionForge 的 refs-first 设计，扩展相关信息需要进入运行证据链。

建议新增或扩展以下 refs：

```text
policy/permission_manifest.json
compiled/extension_lock.json
reports/extension_load_report.json
reports/execution_report.json
ledgers/decision_ledger.jsonl
```

### 6.1 extension_load_report.json

示例：

```json
{
  "schema_version": "missionforge_extension_load_report.v1",
  "call_id": "executor-001",
  "loaded_extensions": [
    {
      "grant_id": "web-access",
      "package": "npm:pi-web-access",
      "version": "0.10.7",
      "integrity": "sha512-...",
      "capability": "web",
      "requires_network": true,
      "network_policy_at_load": "enabled",
      "adapter_mode": "untrusted_pi_extension",
      "status": "loaded"
    }
  ],
  "rejected_extensions": []
}
```

### 6.2 ToolObservation

现有工具调用已经通过 `ToolObservationRecorder` 记录。扩展工具也应该尽量进入同一套 observation 体系。

对于 MissionForge-aware extension：

- 每次 tool call 都记录 tool name、arguments digest、output ref / output digest；
- 大输出继续走 raw ref + projection stub；
- 禁止把 secrets / stdout body / provider payload 直接写入 durable truth。

对于普通 Pi extension：

- 至少记录加载事件；
- 尽可能记录 tool call envelope；
- runtime report 标记 observation completeness。

---

## 7. 能力分级

建议引入 capability 词表，而不是任意字符串无约束增长。

初始 capability：

| capability | 说明 | 默认风险 |
|---|---|---|
| `code_search` | 文件/内容搜索 | low |
| `lsp` | LSP、lint、type-check、formatter | low-medium |
| `web` | Web search/fetch | high |
| `mcp` | MCP adapter | high |
| `browser` | 浏览器控制 | high |
| `subagent` | 子代理/并行 agent | medium-high |
| `memory` | 长期记忆/知识库 | medium-high |
| `preview` | markdown/html/pdf preview | medium |
| `workflow` | 动态 workflow 编排 | medium-high |
| `ui` | 交互式 UI / ask-user | medium |

策略建议：

- low capability 可以更宽松地在沙箱内加载；
- high capability 必须显式声明；
- high capability 默认不进入 judge，除非明确需要；
- `mcp`、`browser`、`web` 必须受 `network_policy` 约束；
- `subagent` 必须受 max concurrency / budget / workspace scope 约束。

---

## 8. 与现有代码的落地点

### 8.1 Python core

文件：`src/missionforge/task_contract.py`

改动：

1. bump `PERMISSION_MANIFEST_SCHEMA_VERSION`；
2. 新增 `ExtensionGrant` dataclass；
3. `PermissionManifest` 增加 `tool_grants`；
4. `from_dict` / `validate` / `to_dict` 支持新字段；
5. 增加测试：
   - 空 tool_grants 兼容旧 manifest；
   - grant_id 唯一性；
   - package 格式校验；
   - version_spec 非空；
   - capability 受控词表；
   - requires_network 与 network_policy 的 hard-check 不在 dataclass validate 中做，而在 runtime/deployment validate 中做。

### 8.2 Node contract parser

文件：`workers/pi-agent-runtime/src/contract.ts`

改动：

- 增加 `ExtensionGrant` 类型；
- `PermissionManifest` 类型增加 `tool_grants`；
- runtime input 允许携带 `extension_lock_ref` 或直接携带 lock payload ref。

### 8.3 Node tools loader

文件：`workers/pi-agent-runtime/src/tools.ts`

改动：

- 将 `createMissionForgeTools` 改成 async；
- 保留 base tools 构建；
- 新增 `loadExtensionTools`；
- 校验 grant 与 lock；
- 校验 network policy；
- 生成 extension load report。

### 8.4 Runtime

文件：`workers/pi-agent-runtime/src/runtime.ts`

改动：

当前：

```typescript
const tools = createMissionForgeTools(...)
```

改为：

```typescript
const tools = await createMissionForgeTools(...)
```

并在 EvidenceRecorder 中记录 extension load report。

### 8.5 CLI

新增命令：

```bash
python -m missionforge.adapters.cli extensions compile
python -m missionforge.adapters.cli extensions inspect
python -m missionforge.adapters.cli extensions verify
```

职责：

- compile：安装并生成 lock；
- inspect：展示 manifest 声明和 lock 匹配情况；
- verify：部署/运行前校验扩展完整性。

---

## 9. 迭代计划

### Milestone 1：声明模型

目标：core 能表达扩展授权，但 runtime 暂不加载。

交付：

- `ExtensionGrant`；
- `PermissionManifest.tool_grants`；
- schema version bump；
- Python 单元测试；
- 文档示例。

### Milestone 2：编译与 lockfile

目标：把声明解析为可部署扩展清单。

交付：

- `extension_lock.json` schema；
- CLI `extensions compile`；
- CLI `extensions verify`；
- npm install root 约定；
- lockfile 测试。

### Milestone 3：runtime loader skeleton

目标：runtime 能读取 lockfile，加载 mock / local MissionForge-aware extension。

交付：

- async `createMissionForgeTools`；
- `loadExtensionTools`；
- `MissionForgeExtensionProvider` interface；
- extension load report；
- faux test extension。

### Milestone 4：普通 Pi extension adapter

目标：支持一部分现有 Pi extension。

交付：

- adapter mode；
- untrusted extension sandbox policy；
- 加载事件审计；
- 至少验证一个低风险扩展，例如 code search / lsp 类工具。

### Milestone 5：联网扩展与 network_policy

目标：支持 web / MCP 类扩展，但必须显式授权。

交付：

- `requires_network` 校验；
- `network_policy=disabled` 拒绝加载；
- `network_policy=enabled` 允许加载并记录；
- restricted 模式可以先保留为 unsupported hard policy，后续接网络代理或域名 allowlist。

### Milestone 6：Product Integration 使用

目标：让 SkillFoundry 或其他产品 shell 在编排时生成 tool_grants。

交付：

- executor/judge 不同 grants 示例；
- repair 继承 grants；
- revision 修改 grants；
- cookbook 示例。

---

## 10. 推荐默认策略

短期默认：

1. core 支持声明；
2. runtime 默认不加载任何扩展；
3. 只有 compile 后的 lockfile 中存在的扩展才能加载；
4. `network_policy=disabled` 时禁止联网扩展；
5. judge 默认不加载 high-risk 扩展；
6. 所有 extension load 事件写入 report。

中期默认：

1. 支持 MissionForge-aware extension；
2. 支持低风险普通 Pi extension；
3. high-risk 普通 Pi extension 必须显式 adapter mode；
4. restricted network 暂时作为 unsupported hard policy，直到有网络代理实现。

长期目标：

1. 形成 MissionForge extension provider 规范；
2. 为热门 Pi 扩展维护官方 adapter；
3. Product Integration 能按任务 profile 自动选择扩展；
4. replay 能完整说明：当时加载了哪些工具、版本、能力、网络策略和关键调用证据。

---

## 11. 一句话总结

MissionForge 不应该把 Pi 生态扩展预装进 core，也不应该让 agent 执行中任意扩权。正确模型是：**core 声明扩展授权，编排选择所需能力，编译阶段安装并锁定，部署阶段把扩展带入沙箱，运行时按 manifest + lockfile 加载，并把加载与使用证据写入 refs-first 账本。**
