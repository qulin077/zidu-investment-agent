# AI Native 与技术架构

> 本文以 2026-10-11 本地代码为准。旧版固定 Router / 确定性 DAG 仍有兼容文件，但不再代表当前 /agent 主架构。

## 1. 先说人话：这个 Agent 到底做了什么

用户不用先学会选“公司研究、行业研究还是事件研究”。他只需要说问题：

> “完整研究东山精密，重点看 PCB 和光模块业务变化，以及市场现在预期了什么。”

系统先理解真实任务和是否需要澄清，再读取与这家公司相关的历史研究和用户偏好；随后规划要查什么，调用公告、财报、行情、iFinD 和公开网页工具；每拿到一轮结果就检查“还缺什么”，缺关键证据就换查询或来源继续找；最后由强模型只基于已读证据形成报告，确定性检查器决定它能标成 Complete、Partial 还是 Source Unavailable。

当用户表达交易计划时，模型只能生成草稿；只有用户确认后才保存。复盘时系统取回当时版本，而不是拿今天的信息改写过去。

这就是本产品的 Harness：**让模型负责理解和分析，让工具负责取得事实，让代码负责边界、状态、检查和写入权限。**

## 2. 总体架构

~~~mermaid
flowchart LR
    U[用户] --> FE[Next.js Web\nAgent / Research / Review]
    FE --> API[FastAPI]
    API --> P[ModelActionPlanner\n理解意图与选择下一动作]
    P --> C[Context Assembler\n按任务装载最小上下文]
    P --> H[Bounded Agent Runtime\nAction → Observation]
    H --> T[Tool Registry\n白名单与权限]
    T --> RS[Research Skills]
    T --> DS[Decision Recorder]
    T --> RV[Guided Review]
    T --> MQ[Memory Query]
    RS --> SRC[财报/公告/行情/iFinD/网页/PDF]
    RS --> EV[Source → Evidence → Claim → Thesis]
    EV --> CC[Coverage + Citation + Temporal Gates]
    DS --> WG[User Confirm Write Gate]
    RV --> EC[Entry Context vs Current Context]
    CC --> DB[(SQLite + 版本化研究档案)]
    WG --> DB
    EC --> DB
    DB --> C
~~~

代码对应关系：

| 层 | 本地实现 |
|---|---|
| Web | web/app/agent、web/app/research、web/app/review |
| HTTP API | app/api/agent.py、research_os.py、review.py |
| 外层 Planner | core/agent/planner.py |
| 外层 Runtime | core/agent/harness.py |
| Context | core/agent/context.py、compaction.py、personal_context.py |
| Tool / 权限 | core/agent/tool_registry.py、skill_registry.py |
| 研究运行时 | core/research/workspace.py |
| 公司 Coverage | core/research/company_coverage.py |
| 证据与写入检查 | core/research/source_policy.py、extract.py、write_gate.py、temporal.py |
| Decision / Review | core/review/recorder、guided、lifecycle.py、memory |
| 持久化 | migrations + SQLite；研究正文和来源缓存为本地派生资产 |

## 3. 两层 Agent Loop，而不是一个巨大 Prompt

### 3.1 外层：跨能力 Planner

外层 ModelActionPlanner 看见：

- 用户当前消息；
- 最近 12 条对话；
- 旧对话的压缩摘要；
- 当前策略、工作流和少量状态；
- Tool 目录与权限；
- 运行时日期和时间。

它输出 CHAT 或 CALL_TOOL，并可在 Observation 后继续选择下一 Tool。语义模型不可用时，确定性 Semantic Router 降级接管；它是 fallback，不是主架构。

外层最多 12 步，作用是防止跨工具死循环，不限制一份研究内部要读多少来源。相同 Tool + 相同任务会被重复动作检查器阻止。

### 3.2 内层：研究证据循环

研究 Skill 内部执行：

> 强模型规划 → 多来源并行检索 → 打开正文/PDF → 模型逐篇抽取 Claim → 确定性验证 → 检查 Coverage → 针对缺口补搜 → 强模型综合 → Coverage 再检查 → 保存版本。

当前 Research Workspace **没有“四轮后无条件停止”**。它依据三件事停止：

1. 必需证据已覆盖；
2. 已没有安全且不重复的查询；
3. 来源不可访问或证据不足，明确以 Partial / Source Unavailable 结束。

搜索次数不是“研究完成”的判断标准。资源保护与业务完成度分开：即使未来增加时间/成本保护，也只能返回带原因的 Partial，不能伪装为 Complete。

## 4. 一轮公司研究时序

~~~mermaid
sequenceDiagram
    participant U as 用户
    participant P as Planner
    participant C as Context
    participant R as Company Research
    participant S as Source Skills
    participant M as Reader / Extractor
    participant G as Coverage Checker
    participant D as Dossier Store

    U->>P: 完整研究东山精密，重点看预期变化
    P->>C: 读取该公司旧档案、用户 focus、最近对话
    C-->>P: 最小上下文包
    P->>R: 调用 company-research
    R->>R: 强模型生成 8–12 个可验证问题
    par 官方财报与公告
        R->>S: filing-analysis
    and 管理层交流
        R->>S: management-communication
    and 卖方预期
        R->>S: sell-side-expectations
    and 市场叙事
        R->>S: market-narrative
    and 反证
        R->>S: risk-disconfirmation
    end
    S->>M: 打开正文 / PDF
    M-->>R: Atomic Claims + 引文位置
    R->>G: 检查来源通道、财务基线和档案模块
    alt 有可执行缺口
        G-->>R: Missing expectations / risk / segment
        R->>S: 生成不重复查询或更换来源
        S->>M: 继续阅读
    else 无可安全补搜路径
        G-->>R: Partial / Attempted Unavailable
    end
    R->>R: 强模型基于 Claim 综合，不接触未读“最新事实”
    R->>D: 保存来源、Claim、Coverage、Dossier 和版本
    D-->>U: HTML 研究档案 + 来源 + 缺口 + Trace
~~~

## 5. Skills：专业框架与个性化之间的“度”

Skill 不是把回答写死，而是一个工作合同：

| 字段 | 作用 |
|---|---|
| Trigger | 什么时候使用，什么时候不用 |
| Input | 只接任务需要的字段，避免整段历史污染 |
| Research Questions | 全面研究必须覆盖的专业问题 |
| Tools / Source Order | 去哪里找，什么来源能证明什么 |
| Workflow | 先规划、再取证、再综合、再检查 |
| HITL | 哪些歧义和写入必须由人决定 |
| Done | 什么叫覆盖完整 |
| Abstain | 什么情况下必须 UNKNOWN / Partial |
| Output | 产物结构与持久化字段 |

Planner 仍能根据用户关注点和证据动态决定查询；Skill 则保证“全面研究”不会因为模型当天发挥不同而漏掉财报、预期、反证或监控指标。

### 核心 Skills

| Skill | 专业框架 | 个性化 |
|---|---|---|
| company-research | 公司基本盘、三年财务、壁垒、驱动、预期、股价 Gap、风险、监控 | 首问只澄清一个会改变路线的问题；保存每家公司 focus |
| industry-research | Structure、Economics、Expectation、Update 四层；18 个专业问题 | 叠加行业 Playbook 和用户偏好的产业链环节 |
| event-impact | 离散事件状态机或演化主题时间线、基线、传导、兑现 | 用户选择更关注定义、产业影响、公司映射或时间线 |
| decision-recorder | 原话抽取为 Thesis / Plan 草稿 | 用户确认才能写入；保留原句与编辑差异 |
| guided-review | Entry Thesis、执行、新事实、结果分层 | 一次问一个问题，归因由用户确认 |
| memory-query | 只查已确认 Pattern / Active Rule | 不把一次聊天升级成人格标签 |

### 行业 Playbook

同一个 industry-research Skill 根据研究对象加载光模块、PCB/覆铜板、半导体制造、消费、房地产 Playbook。Playbook 只补充行业特有指标、来源和搜索配方，不能修改证据规则或预填结论。

## 6. company-research 为什么拆成“原子来源动作”

这不是把一个公司研究拆成五个聊天机器人，而是一个总控 Skill 并行调用五条只读证据通道：

| 原子动作 | 主要材料 | 能证明 | 不能证明 |
|---|---|---|---|
| filing-analysis | 三年官方年报、最新季报/半年报、公告 | 财务基线、分部与已披露事实 | 未披露未来业绩 |
| management-communication | 业绩会、电话会、IR 活动记录 | 管理层解释和指引 | 已实现收入 |
| sell-side-expectations | 券商预测、评级、目标价及修订 | 市场预期与假设 | 公司经营事实 |
| market-narrative | 媒体、雪球等观点 | 市场在讨论什么 | 客户、订单或收入 |
| risk-disconfirmation | 问询、下修、减值、诉讼、反方材料 | 风险和证伪条件 | “没搜到”等于没有风险 |

拆开的价值是并行、可观察和可诊断：市场预期为空时，可以看到是没搜索、没结果、正文打不开，还是读到了但不能支持结论，而不是只得到一个 UNKNOWN。

## 7. 模型分层：把算力花在高杠杆处

当前本地实现支持两档 OpenAI-Compatible 模型，通过环境变量配置：

| 环节 | 当前职责 | 模型策略 |
|---|---|---|
| 外层意图与 Tool 选择 | 理解用户要解决什么 | 通用运行模型 LLM_MODEL |
| 研究规划 | 决定 8–12 个可验证问题和第一步 | 强分析模型 RESEARCH_LLM_MODEL |
| 搜索、API、下载、去重 | 机械取数和重试 | 确定性代码，不消耗强模型 |
| 逐篇阅读与 Claim 抽取 | 把正文转成带引文的原子事实 | 通用运行模型 |
| 财务比率与时间检查 | 增长率、现金转化、时间可见性 | 确定性代码，不让模型心算 |
| 最终 Dossier 与 Thesis | 跨来源综合、冲突、预期差、反证 | 强分析模型 |
| Coverage / Write Gate | 完整度、引用、写入权限 | 确定性代码 |

当前 .env.example 推荐研究强模型使用 DeepSeek V4 Pro + high reasoning；供应商不是架构本身，替换兼容模型不改变业务层。

## 8. Context Engineering

### Hot Context

- 最近 12 条消息；
- 当前任务、实体、研究焦点、Active Workflow；
- Planner 需要的工具目录和运行时日期。

### Compacted Context

更早消息由确定性压缩器保留到最多 2,400 字，并记录压缩到哪条消息。它避免把全部聊天重复送入模型，但当前仍是截断式摘要，不是成熟的语义事实抽取，这是已知限制。

### Domain Slice

Context Assembler 按当前 Skill 装载：

- Research：当前项目、Thesis、最多 8 条相关 Claim、Open Questions、最近 Run；
- Review：指定 Decision、Plan、最近成交、Review、Entry/Current Thesis；
- Memory：已确认 Pattern 与 Active Rule；
- Decision：当前研究引用与相关规则。

明确跳过 full_chat、all_trades、other_research，防止上下文污染和 Token 浪费。

## 9. 共同记忆与领域记忆

~~~mermaid
flowchart TD
    K[Shared Kernel] --> S[投资策略与时间周期]
    K --> P[已确认 Pattern]
    K --> R[Active Rule]
    K --> W[Active Workflow]
    CR[公司/行业/事件研究记忆] --> SRC[Source / Evidence / Claim]
    CR --> TH[版本化 Thesis / Change Ledger]
    DR[决策与复盘记忆] --> D[Decision / Plan / Execution]
    DR --> O[Outcome / Attribution]
    TH --> L[Context Link]
    D --> L
    O --> P
    P --> R
~~~

- 共同记忆保存用户的投资周期、研究偏好、已确认规则与当前工作流；
- 研究记忆保存客观来源、Claim、版本化 Thesis 和变化日志；
- 决策/复盘记忆保存个人当时判断、计划、成交和归因；
- Context Link 将某个 Decision 固定到特定 Research Thesis 版本。

模型记忆不能作为外部事实；研究事实仍需来源。未确认的 Pattern 不进入 Shared Kernel。

## 10. Evidence 与可信性

研究对象按以下链路保存：

> Source（文档） → Evidence（带位置的原文片段） → Claim（FACT / ESTIMATE / INFERENCE / OPINION） → Thesis（带证据引用的判断）

关键规则：

- PDF 引用至少带页码；
- FACT 必须有正文中的 SUPPORT Evidence；
- INFERENCE 必须列 premise Claim；
- 两个独立来源支持才是 Corroborated；
- 来源冲突标成 Contested，不自动平均；
- available_at 晚于 as_of 的来源不得进入历史版本；
- 关键数字不在 Claim / Evidence 中，Write Gate 阻止写入；
- 搜索摘要、聊天记忆、模型常识不能直接成为事实。

## 11. Coverage 与停止逻辑

模型可以决定“下一步搜什么”，但不能决定“这份全面研究算不算完整”。

公司完整档案的确定性 Coverage Checker 检查：

- 五个来源通道是否执行、可读或已明确不可得；
- 最近三年年报和最新一期定期报告；
- 公司基本盘、分部、壁垒、行业位置、驱动；
- 公司/卖方/市场预期与股价 Gap；
- 风险、反证、失效条件和监控指标。

状态含义：

| 状态 | 含义 |
|---|---|
| Complete | 要求的来源动作与档案模块都有可核对证据 |
| Partial | 仍有模块缺失，或已尝试但公开资料不可得 |
| Source Unavailable | 关键官方来源已尝试但当前不可取得 |
| Interrupted | 运行异常，未完成内容不会伪装成报告 |

UNKNOWN 也必须分原因：未搜索、无结果、正文不可读、来源冲突、证据不足，而不是一个模糊占位词。

## 12. Policy Gate 与 Human in the Loop

Tool Registry 给每个动作分三类权限：

- READ_ONLY：可以直接读取；
- WRITE_DRAFT：只能写草稿；
- USER_CONFIRM：必须明确确认后执行。

四个关键门：

1. 新鲜度门：最新行情先检查并刷新，失败则降级；
2. 研究门：关键来源不可读时不能产出正常 Complete；
3. 决策门：模型解析后只是草稿，用户确认才进入 Decision；
4. 记忆门：一次复盘只能产生 Mistake，多个案例才形成 Pattern，Rule 仍需用户激活。

## 13. Trace 与可观测性

前端展示：

- Planner 识别的任务；
- 执行了哪条来源 Skill；
- 搜索返回多少线索；
- 哪些正文成功打开或失败；
- 模型从哪些来源抽取了多少 Claim；
- Coverage 通过多少项、仍缺什么；
- 最终为什么停止。

不展示模型隐藏思维链。每次 Agent Turn 保存 Action / Observation、耗时、停止原因；失败 Trace 可脱敏转成 BadCase 和回归 Eval。

## 14. 当前能力与真实限制

### 已实现

- 模型主导的 Tool 选择与 Observation 后续规划；
- 公司 / 行业 / 事件三类长期研究档案；
- 五路公司来源并行搜索与正文阅读；
- 强模型规划和最终综合、弱模型逐篇抽取；
- Coverage、时间完整性、引用和写入门；
- Decision 确认、Entry Thesis 绑定、Guided Review；
- Shared Memory 与领域记忆隔离；
- 可视化 Trace 和 BadCase 捕获。

### 做不到或仍不稳定

- 免费网页存在反爬、动态渲染、登录墙和 PDF 解析失败；
- iFinD 是否可用取决于服务端 Token、额度与权限；
- 券商研报全文和机构一致预期覆盖仍不完整；
- 后台研究 Worker 当前是单进程、单 Worker，不适合多用户并发；
- Context Compaction 仍较简单；
- 尚无生产级用户认证、权限、限流和监控；
- 尚未证明提高真实投资收益或形成 PMF。

## 15. 旧架构清理

本地仍保留 config/research_harness.yaml、旧 research-harness Skill 和 runtime Skill，用于历史兼容或旧 CLI 说明；其内容描述固定 DAG / 四房间，不代表当前 Model Planner + Tool Registry + Adaptive Research 架构。

比赛安全导出已排除这三份旧说明，避免评委同时看到两套互相冲突的架构。后续可在确认无旧入口依赖后再从个人仓库退役，不在本轮破坏性删除。
