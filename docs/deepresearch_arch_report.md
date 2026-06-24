# Deep Research 输出"干涩""AI味重"根因诊断报告

> **生成日期**: 2026-06-23
> **目标**: MissionForge Deep Research 框架升级重构指导
> **分析对象**: Deep Research Skill v5.0 + `integrations/deepresearch` 代码 + FPGA 编译框架文献综述样本输出
> **诊断方法**: 交叉比对研究报告输出文本与框架全部核心源码（kernel_v2.py、product_contract.py、frontdesk.py、methodology.md、report_template.md、verify_claim_support.py 等共 10+ 文件）

---

## 一句话结论

**你的框架在"工程正确性"上投入了过量注意力（结构校验、引用追踪、artifact 边界、schema 版本控制），但在"研究洞察力"和"写作质感"上几乎是真空的。**

报告读起来像一份由合规检查员填写的标准化表单，而不是一个有判断力的研究者写出来的。

这不是 prompt 微调能解决的问题——这是**架构性的设计缺失**，分布在六个层次上。下面逐层展开，每个根因都附带具体的代码位置。

---

## 目录

1. [根因 1：Section 定义是刚性骨架，不是思维框架](#根因-1section-定义是刚性骨架不是思维框架)
2. [根因 2：Guidance 全是流程指令，零洞察引导](#根因-2guidance-全是流程指令零洞察引导)
3. [根因 3：Quality Dimensions 衡量的是完整性而非质量](#根因-3quality-dimensions-衡量的是完整性而非质量)
4. [根因 4：三角色流水线中没有洞察者](#根因-4三角色流水线中没有洞察者)
5. [根因 5：验证脚本是纯词法级别的](#根因-5验证脚本是纯词法级别的)
6. [根因 6：Intensity Profile 控制的是预算不是思想深度](#根因-6intensity-profile-控制的是预算不是思想深度)
7. [根因 7：方法论 Phase 5 缺乏洞察生成机制](#根因-7方法论-phase-5-缺乏洞察生成机制)
8. [根因 8：证据天花板太低](#根因-8证据天花板太低)
9. [根因 9：Prose Style 是完全盲区](#根因-9prose-style-是完全盲区)
10. [根因 10：HTML 渲染器是最小实现](#根因-10html-渲染器是最小实现)
11. [综合诊断图](#综合诊断图)
12. [改进建议（按优先级排序）](#改进建议按优先级排序)

---


## 根因 1：Section 定义是刚性骨架，不是思维框架

**代码位置**：`integrations/deepresearch/src/missionforge_deepresearch/product_contract.py` 第 29-79 行，`_REPORT_SECTION_DEFINITIONS`

```python
_REPORT_SECTION_DEFINITIONS = [
    {"section_id": "scope_and_method", ...},
    {"section_id": "evidence_base", ...},
    {"section_id": "major_lines_of_work", ...},
    {"section_id": "comparison_matrix", ...},
    {"section_id": "counterevidence_and_failure_modes", ...},
    {"section_id": "source_gaps", ...},
    {"section_id": "references", ...},
]
```

这 7 个 section 被硬编码为输出合约的必填项（`output_contract.required_sections`）。无论调研主题是 FPGA 编译框架、量子计算还是区块链共识算法，**每一份报告都必须精确包含这 7 个 section**。

### 问题本质

这 7 个 section 是"文档结构"，不是"分析框架"。人类专家写综述时，会根据领域特性选择叙事角度——可能是以技术争议为主线、以时间演进为主线、以工程选型决策为主线、或者以某个反直觉发现为主线。你的框架没有给 researcher 这种自由度。

### 实际效果

报告变成了"往 7 个格子里填内容"的填空题，而不是围绕一个中心论点组织论证。读者感受到的是机械的完整性，而不是思想的穿透力。

### 改进方向

- 将 `_REPORT_SECTION_DEFINITIONS` 从硬编码改为"推荐模板 + 可扩展"
- 允许 researcher 根据主题特性提出自定义 section（需 reviewer 批准）
- 新增 `narrative_strategy` 字段到 `AcademicResearchRequest`，让 FrontDesk 阶段就确定叙事角度

---

## 根因 2：Guidance 全是流程指令，零洞察引导

**代码位置**：`kernel_v2.py` 的 `_researcher_brief()` 函数（约 100+ 行字符串拼接）

这是 researcher PiWorker 收到的唯一"如何做研究"的指令。逐条分析其内容：

| 指令类型 | 示例 | 占比 |
|---------|------|------|
| 流程控制 | "Work in phases: plan → evidence batch → synthesis → repair" | ~30% |
| Artifact 管理 | "Treat `state/research_state.json` as your working posterior" | ~25% |
| 引用格式 | "Use citations like [S1] for material claims" | ~15% |
| 预算约束 | "Do not spend the whole PiWorker budget on source gathering" | ~10% |
| **洞察/写作指导** | **（完全不存在）** | **0%** |

### 关键缺失

整个 brief 中**没有任何一条**以下类型的指令：

- ❌ "在开始写作前，先形成一个可辩护的中心论点（thesis statement）"
- ❌ "寻找不同来源之间的矛盾或张力——这些往往是最好的切入点"
- ❌ "不要按论文发表顺序罗列，要按技术逻辑重组"
- ❌ "用具体的数据/案例来支撑抽象的判断，避免空泛描述"
- ❌ "每一段落应该让读者知道：这个信息为什么重要？它挑战了什么常识？"

### 结果

PiWorker（无论是哪个模型）收到的信号是："完成流程，填充 artifact，通过 reviewer 检查。" 它自然地输出最安全、最符合格式要求但最缺乏灵魂的内容。

### 改进方向

在 `_researcher_brief()` 末尾追加一个 `## Insight & Writing Quality` 区块（约 15-20 条指令），覆盖：
1. Thesis-first writing 要求
2. Cross-source tension identification
3. "So what?" test for every claim
4. Anti-pattern list（AI-typical phrases to avoid）

---


## 根因 3：Quality Dimensions 衡量的是"完整性"而非"质量"

**代码位置**：`product_contract.py` 第 81-112 行，`_QUALITY_DIMENSIONS`

```python
_QUALITY_DIMENSIONS = [
    {"dimension_id": "coverage",
     "standard": "Cover the major schools of work, not only the first sources found."},
    {"dimension_id": "freshness",
     "standard": "Separate recent findings from historical background and stale claims."},
    {"dimension_id": "citation_integrity",
     "standard": "Tie material claims to source ids and expose source provenance."},
    {"dimension_id": "synthesis",
     "standard": "Explain relationships, tradeoffs, and disagreement instead of listing papers."},
    {"dimension_id": "delta",
     "standard": "Keep run-to-run changes in research_delta.md..."},
    {"dimension_id": "gaps_and_counterevidence",
     "standard": "Expose source gaps, weak evidence, counterevidence, and failure modes."},
]
```

### 分析

6 个维度中，只有 `synthesis` 稍微触及"分析深度"，但它的标准仍然是 **"explain relationships instead of listing papers"**——这是**最低门槛的综合**，不是专家级洞察。

### 完全没有测量的维度

| ❌ 未测量 | 为什么重要 |
|-----------|-----------|
| 论点的原创性或非显而易见性 | 区分"信息汇总"与"洞察报告" |
| 叙事结构和阅读节奏 | 决定读者是否能读完 |
| 是否提出了让读者重新思考问题的角度 | 这是专家价值的体现 |
| 数据/证据与结论之间的推理强度 | 防止"证据→跳跃性结论" |
| 写作的 voice 和 perspective | 区分 AI 文本与人类专家文本 |

**这意味着：即使一份报告完全满足所有 6 个 quality dimensions（满分），它仍然可以是枯燥的、AI味的、缺乏吸引力的。你的质量系统不检测它声称要优化的事情。**

### 改进方向

新增以下 quality dimensions：

```python
{"dimension_id": "insight_depth",
 "standard": "Present at least one non-obvious insight that reorganizes "
            "the reader's understanding of the field, supported by "
            "cross-source evidence triangulation."},
 {"dimension_id": "narrative_coherence",
 "standard": "Report follows a clear argumentative arc with a defensible "
            "central thesis; sections build on each other rather than "
            "standing as independent information blocks."},
 {"dimension_id": "reader_value",
 "standard": "Every major section answers 'So what?' — why this matters "
            "to the target audience and what action or decision it informs."},
]
```

---

## 根因 4：三角色流水线中没有"洞察者"

**代码位置**：`kernel_v2.py` 的 `build_deepresearch_kernel_v2_flow()` 函数

```python
researcher = Step(id="researcher", brief="Own the DeepResearch workspace: gather evidence...")
reviewer  = Step(id="reviewer", brief="Review the researcher-owned workspace...")
judge      = Step(id="judge",   brief="Independently judge the final package...")
```

### 三角色职责与激励方向

| 角色 | 职责 | 激励方向 |
|------|------|---------|
| researcher | 收集证据、写报告、维护 artifact | **完成率**——把格子填满 |
| reviewer | 检查完整性、决定是否返工 | **合规性**——找缺陷 |
| judge | 对照 contract 和 rubric 判定 | **合同符合度**——通过/不通过 |

**问题：三个角色都是"守门员"，没有一个是"进攻方"。没有人被激励去产生深刻的洞察、独特的角度、或引人入胜的叙述。**

### 对比参考

顶级咨询公司（McKinsey/BCG）的报告生产流程通常有一个专门的 **"Insight Partner"** 或 **"Narrative Lead"** 角色，其唯一职责就是确保报告有强有力的 central thesis 和引人入胜的故事线。你的框架里这个角色完全缺席。

### 改进方向（二选一）

**方案 A**：在 `build_deepresearch_kernel_v2_flow()` 中新增第四个 role `synthesist`，在 reviewer 之后、judge 之前运行，职责是：
- 审读 draft 的 narrative quality
- 标记弱论证段落
- 提出至少一个可增强洞察力的修改建议
- 输出 `synthesis_observation.json`

**方案 B**（更轻量）：扩展 `reviewer_rubric()`，加入 narrative quality 评估维度，让 reviewer 不仅检查"缺不缺 section"，还检查"有没有灵魂"。如果 reviewer 判定 narrative quality 不达标，返回 `revise_report_for_insight` 而非 `ready_for_judge`。

---

## 根因 5：验证脚本是纯词法级别的，无法检测"干涩"

**代码位置**：`scripts/verify_claim_support.py` 第 89-166 行，`compute_support_score()`

```python
def compute_support_score(claim_text, evidence_quotes):
    # Token overlap (Jaccard-like) — 40% weight
    # Number match — 25% weight
    # Year match — 15% weight
    # Entity match — 20% weight
    score = 0.4 * token_overlap + 0.25 * number_match \
          + 0.15 * year_match + 0.2 * entity_match
```

### 这是一个纯词法重叠计算器

它能检测到：
- ✅ claim 中出现的数字是否在 evidence 中出现
- ✅ 年份是否匹配
- ✅ 实体名称是否一致
- ✅ 词汇是否有 Jaccard 重叠

**它完全无法区分**：

| 能检测 | 不能检测 |
|--------|---------|
| "[S17] 报告了 4.9ms 延迟"是否在 evidence 中 | 这个延迟数字是否被赋予了正确的语境和意义 |
| claim 是否引用了存在的 source_id | 分析是肤浅的还是深入的 |
| 实体名称是否一致 | 写作是否有 voice、有节奏、有观点 |

### 更深层的问题

这个验证器的设计哲学是"防止幻觉"（这是对的），但它隐含地告诉整个系统：**只要引用正确、事实有据，这份报告就是合格的。** 这恰恰是"数据收集 + 机械拼接"模式的根源——系统认为引用正确性等价于报告质量。

### 改进方向

在 `verify_claim_support.py` 中新增启发式质量检测模块 `check_prose_quality(report_text)`：

```python
def check_prose_quality(text: str) -> dict:
    """Heuristic prose-quality checks that don't need LLM calls."""
    # 1. 平均段落长度过短 → 可能过于碎片化
    paragraphs = [p for p in text.split('\n\n') if len(p.strip()) > 10]
    avg_para_len = sum(len(p) for p in paragraphs) / max(len(paragraphs), 1)
    
    # 2. AI-typical reporting phrases density
    ai_patterns = [
        r'值得注意的是', r'需要指出的是', r'综上所述',
        r'可以看出', r'研究表明', r'具体而言',
        r'It is worth noting', r'It should be noted that',
    ]
    ai_phrase_density = sum(len(re.findall(p, text)) for p in ai_patterns) / max(len(text), 1)
    
    # 3. Transition words density (too low = disjointed)
    transition_words = ['however', 'therefore', 'moreover', 
                        'conversely', 'nevertheless', 'thus']
    # ... count per 1000 chars
    
    return {
        'avg_paragraph_length': avg_para_len,
        'ai_phrase_density': round(ai_phrase_density, 4),
        'fragmentation_risk': avg_para_len < 150,
        'ai_pattern_risk': ai_phrase_density > 0.003,
    }
```

---


## 根因 6：Intensity Profile 控制的是预算，不是思想深度

**代码位置**：`product_contract.py` 第 148-188 行，`research_intensity_profile()`

```python
ResearchIntensity.STANDARD: ResearchIntensityProfile(
    max_sources=24, min_source_records=8,
    max_review_rounds=2, piworker_timeout_seconds=900,
    guidance="Produce a serious web, paper, and repository-metadata survey..."
)
ResearchIntensity.INTENSIVE: ResearchIntensityProfile(
    max_sources=64, min_source_records=24,
    max_review_rounds=4, piworker_timeout_seconds=1800,
    guidance="Produce a repository/code-audit-backed technical report..."
)
```

### STANDARD → INTENSIVE 的区别

| 参数 | STANDARD | INTENSIVE | 本质 |
|------|----------|-----------|------|
| 来源数量 | 24 | 64 | 数量 |
| 最少记录数 | 8 | 24 | 数量 |
| 审查轮次 | 2 | 4 | 数量 |
| 超时时间 | 900s | 1800s | 预算 |
| guidance | metadata survey | code-audit-backed | **证据类型** |

**这些都是数量参数，没有一个质量控制参数涉及思想的深度、分析的锐利度、或写作的吸引力。**

INTENSIVE 模式的 guidance 说 "Classify claims as `code_evidence`, `readme_or_docs_claim`, `paper_or_web_claim`, `inference`, or `not_found`"——这是**证据分类**，不是**分析深化**。

### 改进方向

在 `ResearchIntensityProfile` 中新增分析深度参数：

```python
@dataclass(frozen=True)
class ResearchIntensityProfile:
    # ... existing fields ...
    
    # NEW: analysis depth parameters
    min_cross_source_insights: int = 1   # 至少 N 个跨来源洞察
    require_thesis_statement: bool = False  # INTENSIVE=True
    require_narrative_arc: bool = False     # INTENSIVE=True
    anti_pattern_enforcement: bool = False   # 检测 AI-typical 写作模式
    synthesis_depth_standard: str = (
        "list-and-summarize"  # vs "thesis-driven" / "argumentative"
    )
```

---

## 根因 7：方法论 Phase 5 (SYNTHESIZE) 缺乏"洞察生成"机制

**代码位置**：`reference/methodology.md` Phase 5 定义

Phase 5 SYNTHESIZE 的核心指令是：

1. "Draft each required section"
2. "Weave evidence into claims"
3. "Maintain citation integrity"
4. "Prose-first (≥80%, bullets sparingly)"

### 注意

**"Prose-first (≥80%, bullets sparingly)"——这是整个方法论中唯一的写作风格指导**，而且它只控制了格式（多用段落少用列表），完全不涉及风格、voice、或论述力度。

### 方法论中没有的步骤

| 缺失步骤 | 为什么重要 |
|---------|-----------|
| Generate hypothesis / form thesis | 没有中心论点 = 没有叙事骨架 |
| Find counter-intuitive patterns | 平庸的综述只重复已知信息 |
| Stress-test argument against strongest counterarguments | 反证编织进论证才是专家写法 |
| Narrative arc design | 决定读者是否能被吸引并读完 |

### 改进方向

在 Phase 4.5（Outline Refinement）和 Phase 5（SYNTHESIZE）之间插入新的 **Phase 4.75 (INSIGHT GENERATION)**：

```
Phase 4.5 Outline Refinement
  ↓
Phase 4.75 Insight Generation  ← 新增
  - Form thesis statement (1-2 sentences that capture the report's core argument)
  - Identify 2-3 cross-source tensions or surprises
  - Map each section's role in supporting/challenging the thesis
  - Design narrative arc: setup → tension → resolution → implication
  ↓
Phase 5 Synthesize
  - Write with thesis as north star
  - Weave counter-evidence into each argument (not as separate section)
  - Every paragraph passes the "So what?" test
```

---

## 根因 8：证据天花板太低——metadata-only 运行可通过并输出强结论

回到你提供的研究报告，第 3 段（"范围与方法"章节末尾）有一段非常关键的自我声明：

> "需要明确的是，本次运行没有执行任何仓库代码、没有安装项目、没有跑 benchmark，也没有调用 Vivado/Vitis/Vitis HLS/TVM/FINN/hls4ml/Allo 等 CLI。仓库证据主要来自 GitHub 元数据与主题标签，而非 README、docs、examples、tests、workflow、源码入口的逐文件审计。"

这段话出现在报告中是因为框架要求声明证据局限（`source_gaps` section 是必填项）。

### 问题

**框架允许这种"只看了 GitHub 首页就写了 16000 字综述"的运行通过并输出为最终产品。**

一个有标准的研究框架应该在 evidence quality 低于某个阈值时：
1. 自动降级结论强度（不能写"FINN 的优势来自..."而只能写"根据仓库描述，FINN 定位为..."）
2. 要求补充更深层的证据才能做出更强的断言
3. 在 reviewer/judge 阶段对"证据质量-结论强度不匹配"进行拦截

当前框架的 `source_gaps` section 只是一个"免责声明槽位"，不是一个"质量控制闸门"。

### 改进方向

在 `_reviewer_rubric()` 和 `_judge_rubric()` 中新增证据-结论匹配检查：

```python
# reviewer_rubric() 新增段落:
"""
Evidence-Conclusion Calibration Check:
- If source_packet.evidence_strength is predominantly 'metadata' or 'abstract_only':
  - Block any claim that uses strong causal language ("proves", "demonstrates", 
    "shows that") unless backed by full-text or code-level evidence.
  - Require downgrade of claim verbs to attribution language 
    ("according to repo description", "the abstract suggests").
  - If >40% of claims are 'inference' grade, flag as 'evidence-conclusion mismatch'
    regardless of citation integrity passing.
"""
```

---


## 根因 9：Prose Style 在整个框架中是完全的盲区

### 全局搜索结果

对 Deep Research 框架的全部代码文件进行了关键词搜索：

| 搜索关键词 | 命中数 |
|-----------|--------|
| `style` / `voice` / `tone` / `narrative` | **0** |
| `engaging` / `compelling` / `insight` | **0**（仅 quality dimension 中一次 "clearer field understanding"） |
| `expert` / `perspective` / `judgment` | **0**（仅在 audience 字段中出现） |
| `avoid` / `AI` / `mechanical` / `formulaic` | **0** |
| `boring` / `dry` / `interesting` | **0** |

**整个 Deep Research 框架的代码库、模板、prompt、rubric、验证脚本中，没有任何一处提到 prose style、narrative quality、reader engagement、或如何避免 AI-typical writing patterns。**

这不是遗漏——这是**设计盲区**。框架的设计者显然认为"研究质量"等于"引用正确 + 结构完整 + 有反证 + 有缺口声明"，而完全忽略了"研究质量"也等于"有人想读、读了有收获、读完记得住"。

### 改进方向

1. 在 `_researcher_brief()` 中新增 **Anti-Pattern List**：
   ```
   ## Anti-Patterns to Avoid
   - Do NOT start consecutive paragraphs with similar phrases
   - Do NOT use "值得注意的是/需要指出的是/综上所述" more than once per section
   - Do NOT present information without explaining why it matters
   - Do NOT use hedging language ("可能/或许/一定程度上") for claims that are well-supported
   - Do NOT let any paragraph exceed 15 lines without a topic sentence shift
   ```

2. 新增一个 `writing_style_guide.md` 文件到 `manuals/` 目录，作为 researcher 的写作参考。

---

## 根因 10：HTML 渲染器是最小实现，不支撑专业排版

**代码位置**：`kernel_v2.py` 的 `_render_report_html()` 函数

```python
def _render_report_html(markdown):
    # 手写的 markdown→HTML 转换器（约 40 行）
    # 支持: <p> 段落, <h1>-<h6> 标题, <pre> 表格, <ul>/<li> 列表
    # 内联 CSS: system-ui font, max-width 960px
```

### 不支持的功能

| 缺失功能 | 影响 |
|---------|------|
| 语法高亮 | 代码块不可读 |
| 图片/图表嵌入 | 无法展示架构图/对比图 |
| 引用块样式（blockquote） | 重要引述无法视觉突出 |
| 脚注/尾注 | 长文档导航困难 |
| 目录导航（TOC） | 无法快速跳转 |
| 响应式布局 | 移动端体验差 |
| 任何视觉层次设计 | 报告看起来像纯文本 |

虽然这不直接导致"干涩"（内容才是主因），但它说明框架对"最终交付物的专业感"投入不足——进一步印证了整体偏向"工程正确性"而非"用户体验"的设计取向。

### 改进方向

替换 `_render_report_html()` 为成熟的 Markdown 渲染方案：
- 方案 A：使用 Python `markdown` 库 + 扩展（codehilite、tables、toc）
- 方案 B：调用外部工具如 `pandoc`
- 方案 C：接入前端 Markdown 渲染组件

---

## 综合诊断图

```
┌─────────────────────────────────────────────────────────────┐
│                    用户感知："干""AI味重"                      │
│                                                             │
│  ┌─────────────┐  ┌─────────────┐  ┌──────────────────────┐ │
│  │ 结构层面     │  │ 指令层面     │  │ 评估层面              │ │
│  │             │  │             │  │                      │ │
│  │ • 7个固定   │  │ • Guidance  │  │ • Quality Dims       │ │
│  │   Section   │  │   零洞察引导 │  │   只衡量完整性        │ │
│  │   = 填空题  │  │ • 无 thesis │  │ • verify_claim_support│ │
│  │             │  │   生成步骤  │  │   = 词法重叠计算器    │ │
│  └──────┬──────┘  └──────┬──────┘  └──────────┬───────────┘ │
│         │                │                     │             │
│         v                v                     v             │
│  ┌─────────────┐  ┌─────────────┐  ┌──────────────────────┐ │
│  │ 角色层面     │  │ 方法论层面   │  │ 证据层面              │ │
│  │             │  │             │  │                      │ │
│  │ • 三角色全是 │  │ • Phase 5   │  │ • 允许 metadata-only │ │
│  │   守门员    │  │   无洞察生成│  │   evidence 通过       │ │
│  │   无进攻方  │  │ • Prose style│  │ • source_gaps 只是   │ │
│  │             │  │   盲区      │  │   免责声明           │ │
│  └─────────────┘  └─────────────┘  └──────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

---

## 改进建议（按优先级排序）

### P0 —— 必须做的架构改动（预计工作量：2-3 天）

#### P0-1：在 `_researcher_brief()` 中注入洞察引导指令

**文件**：`integrations/deepresearch/src/missionforge_deepresearch/kernel_v2.py`  
**函数**：`_researcher_brief()`  
**改动量**：约 50 行文本追加

在 brief 末尾追加以下内容：

```python
## Insight & Writing Quality Requirements

### Thesis-First Writing
Before drafting any section, form a defensible thesis statement (1-2 sentences)
that captures your core argument about this field. Every section must either
support, challenge, or refine this thesis. Write the thesis in
`state/research_state.json.core_thesis`.

### Cross-Source Tension Identification
Identify at least 2-3 non-obvious tensions, contradictions, or surprises
across your sources. These are often the most valuable insights. Examples:
- Source A claims X works well; Source B shows X fails under condition Y.
- Paper C's benchmark looks strong but uses an unrealistic baseline.
- Tool D's README says it supports feature F, but all real users report gaps.

### The "So What?" Test
For every major claim you make, explicitly answer: Why does this matter to the
reader? What decision does it inform? What assumption does it challenge?
If a claim passes the citation check but fails the "So what?" test,
downgrade it to a supporting detail or remove it.

### Anti-Patterns to Avoid
- Do NOT start >1 paragraph per section with the same transition phrase.
- Do NOT use empty signposting phrases ("值得注意的是", "需要指出的是",
  "综上所述", "It is worth noting") more than ONCE per section.
- Do NOT present information without explaining its significance.
- Do NOT use excessive hedging for well-supported claims.
- Do NOT let any paragraph exceed 15 lines without a topic shift.
```

#### P0-2：新增 `insight_depth` Quality Dimension

**文件**：`product_contract.py`  
**位置**：`_QUALITY_DIMENSIONS` 列表  
**改动量**：约 10 行

```python
{"dimension_id": "insight_depth",
 "standard": (
     "Present at least one non-obvious insight that reorganizes "
     "the reader's understanding of the field. This insight must be "
     "supported by cross-source evidence triangulation (not just a single "
     "source) and must go beyond summarizing what individual sources say."
 ),
 "user_visible_value": "deeper field insights and original analysis"},
```

#### P0-3：扩展 Reviewer Rubric 加入 Narrative Quality 评估

**文件**：`kernel_v2.py`  
**函数**：`_reviewer_rubric()`  
**改动量**：约 20 行

在 rubric 中追加：

```python
"""
Narrative Quality Check (NEW):
- Does the report have a discernible central argument or thesis?
- Is there a logical progression from problem → evidence → analysis → implication?
- Are counter-evidence and limitations woven INTO arguments rather than
  isolated in their own sections?
- Is the writing free of repetitive AI-typical patterns?

If narrative quality is weak:
- Use `revise_report_for_insight` (new decision value) instead of `ready_for_judge`.
- Include specific paragraphs or sections that need rewriting in observation.
"""
```

同时在 `build_deepresearch_kernel_v2_flow()` 的 routes 中注册新路由：

```python
"reviewer.revise_report_for_insight": "researcher",  # NEW
```

---

### P1 —— 应该做的改进（预计工作量：3-5 天）

#### P1-4：在方法论 Phase 4.5 和 Phase 5 之间插入 Phase 4.75 (Insight Generation)

**文件**：`reference/methodology.md`  
**改动量**：重写 Phase 4.5-5 区域，约 100 行

```
Phase 4.75 INSIGHT GENERATION (NEW)
  Input: outline from 4.5, source_packet, research_state
  Output: thesis_statement, insight_list, narrative_arc_plan
  
  Steps:
  4.75.1 Form Thesis Statement
    - Synthesize the strongest pattern/tension from gathered evidence
    - Write as 1-2 arguable sentences (not a flat summary)
    - Save to state/research_state.json.core_thesis
  
  4.75.2 Identify Cross-Source Insights
    - Find 2-3 contradictions, surprises, or non-obvious connections
    - Each insight must cite ≥2 sources with different implications
    - Save to state/research_state.json.insights[]
  
  4.75.3 Design Narrative Arc
    - Map each required section's role: setup? tension? evidence? resolution?
    - Ensure the arc has a shape, not just a list of topics
    - Save to state/research_state.json.narrative_arc
  
  4.75.4 Self-Critique
    - Challenge own thesis: what's the strongest counterargument?
    - If thesis cannot survive counterargument, revise or downgrade
    - Document what the report will NOT cover and why
```

#### P1-5：让 `source_gaps` 成为真正的质量闸门

**文件**：`kernel_v2.py`  
**函数**：`_reviewer_rubric()`, `_judge_rubric()`  
**改动量**：各约 15 行

核心逻辑：当 `source_packet` 中 metadata/abstract_only 类型的证据占比超过阈值时：

1. 自动降级结论强度要求（强因果动词 → 归属动词）
2. 要求 researcher 明确标注哪些结论是 inference 级别
3. reviewer 对 "evidence-conclusion mismatch" 有权拦截

#### P1-6：在 `verify_claim_support.py` 中加入启发式 prose quality 检测

**文件**：`scripts/verify_claim_support.py`  
**改动量**：新增函数约 40 行

参见根因 5 中的代码示例。将此检测集成到 `validate_report` CLI 子命令中。

---

### P2 —— 锦上添花（预计工作量：2-3 天）

#### P2-7：Intensity Profile 加入分析深度参数

**文件**：`product_contract.py`  
**类**：`ResearchIntensityProfile`  
**改动量**：约 15 行新字段

参见根因 6 中的代码示例。

#### P2-8：HTML Renderer 升级

**文件**：`kernel_v2.py`  
**函数**：`_render_report_html()`  
**改动量**：替换为成熟渲染方案，约 100 行

#### P2-9：建立"好报告样本库"

- 收集 3-5 份人类专家写的优秀技术综述作为 reference
- 提取其叙事结构、段落模式、论证技巧
- 将关键特征编码为 brief 中的 few-shot examples

---

## 实施路线图建议

```
Week 1: P0-1 (Guidance 注入) + P0-2 (Quality Dimension)
  ↓ 立即见效：researcher 输出质量应有可观测提升
Week 2: P0-3 (Reviewer Rubric 扩展) + P1-6 (Prose Heuristic)
  ↓ 构建闭环：不仅生成更好，还能检测更好
Week 3: P1-4 (Phase 4.75 方法论) + P1-5 (Evidence Gate)
  ↓ 结构深化：从 prompt 补丁升级为方法论改进
Week 4: P2-7~P9 (Profile 参数、Renderer、样本库)
  ↓ 打磨完善：从"能用"到"专业"
```

---

## 附录：代码修改清单速查

| # | 文件 | 函数/区域 | 改动类型 | 优先级 |
|---|------|----------|---------|-------|
| 1 | `kernel_v2.py` | `_researcher_brief()` | 追加 ~50 行洞察指令 | P0 |
| 2 | `product_contract.py` | `_QUALITY_DIMENSIONS` | 追加 3 个 dimension | P0 |
| 3 | `kernel_v2.py` | `_reviewer_rubric()` | 追加 ~20 行 narrative 检查 | P0 |
| 4 | `kernel_v2.py` | `build_deepresearch_kernel_v2_flow()` | 追加 1 条路由 | P0 |
| 5 | `reference/methodology.md` | Phase 4.5-5 区域 | 重写，插入 Phase 4.75 | P1 |
| 6 | `kernel_v2.py` | `_reviewer_rubric()` + `_judge_rubric()` | 追加证据-结论校准 | P1 |
| 7 | `scripts/verify_claim_support.py` | 新增 `check_prose_quality()` | 新增 ~40 行 | P1 |
| 8 | `product_contract.py` | `ResearchIntensityProfile` | 新增 5 个字段 | P2 |
| 9 | `kernel_v2.py` | `_render_report_html()` | 替换为成熟渲染 | P2 |
| 10 | `manuals/writing_style_guide.md` | 新建文件 | 写作风格指南 | P2 |

---

> **文档结束**
>
> 本报告基于 MissionForge Deep Research Skill v5.0 全部源码与实际输出样本的交叉分析生成。
> 所有代码引用均来自 `manstein-lzn/missionforge` 仓库 `main` 分支的最新提交。
> 如需针对某个具体改动的详细 diff 或实现讨论，请指明编号。

