---
name: industry-research
description: >-
  Use this skill when the user wants to understand an industry,
  technology theme, value chain, market structure, supply/demand shift,
  competitive landscape, industry catalysts, risks, or which companies
  participate in an industry.
  Do not use this skill for direct buy/sell recommendations,
  position sizing, portfolio allocation, or pure company-only deep dives.
---

# industry-research

行业研究的工作合同。Agent 选中这个 Skill 之后按步骤走，Tool 取来源，LLM 只做拆问、抽取、对照和起草。数字以证据为准。

这个文件不执行研究，也不许在这里填行情或收入。

## WHEN TO USE

用户要理解一个行业、技术主题、价值链、市场结构、供需变化、竞争格局、产业催化、风险，或问哪些公司参与这个行业。

不要用于直接买卖、仓位、组合配置，或只研究某一家公司。

## INPUT

只收 research_question、as_of、market_scope、industry_or_theme、可选的短 user_context、depth。字段说明见下方「输入」。

## 核心产品定位：变化优先，不是行业百科

行业档案由两层组成：

- **Stable Baseline**：行业边界、基础产业链、商业模式，低频更新。
- **Change Ledger**：技术路线、政策、需求预期、供给瓶颈和价值量迁移，高频更新。

首次研究必须建立完整基线；后续研究默认先回答：旧预期是什么、新事实是什么、预期上调还是下调、影响哪个产业链节点、谁可能受益/受损、成立条件和下一验证点。没有变化时明确写「本轮没有足以改变判断的新事实」，不要重写行业介绍冒充更新。

## PROFESSIONAL RESEARCH STACK

全面研究不是把来源分类全部搜一遍，而是形成四层可验证结构：

1. **Structure Map**：行业边界、合理参考类、生命周期、市场规模/增速/利润率、竞争结构与外部变量。
2. **Economic Engine**：产业链、利润池、量价成本、资本密集度、ROIC/自由现金流，以及增长由行业扩张还是份额提升驱动。
3. **Expectation Engine**：把叙事翻译成可观察变量；区分事实、预测和市场叙事；说明当前定价需要兑现的增长、份额或利润率门槛。
4. **Update Engine**：新事实如何改变旧假设；用基准/上行/下行情景、代表公司业绩、里程碑和证伪条件持续更新。

研究假设先经过 possible / plausible / probable 检查，再进入叙事到数字的因果链。历史基准率是先验，不是结论；新证据改变概率，而不是让模型把热门叙事直接写成事实。

## PLAYBOOK ROUTING

本 Skill 是通用研究合同，不为每个行业复制一套 Agent。选定研究对象后加载一个行业 Playbook；Playbook 只提供该行业特有的分类、指标、财务验证重点、来源优先级和搜索配方，不能修改证据规则或替模型预填结论。

当前五个 Playbook：

- 光模块：`config/research_playbooks/optical_module.yaml`
- PCB / 覆铜板：`config/research_playbooks/pcb_ccl.yaml`
- 半导体制造（设备 / 材料）：`config/research_playbooks/semiconductor.yaml`
- 消费：`config/research_playbooks/consumer.yaml`
- 房地产：`config/research_playbooks/real_estate.yaml`

遇到细分赛道时按「产业域 → 细分环节 → 研究对象」路由，不新建重复 Skill。例如“光模块测试”加载光模块 Playbook 并聚焦测试设备与服务；“半导体材料”加载半导体制造 Playbook 并聚焦材料节点。若没有命中 Playbook，使用通用框架并把分类保留为待确认，不能凭相似词硬归类。

首次建立档案时使用 Playbook 的完整指标；后续更新只围绕用户关注环节、已有缺口和变化日志选择查询。Playbook 是可配置研究镜头，不是固定路线，Planner 仍可根据新证据生成下一步动作。

## REQUIRED STEPS

下面十三个问题是每次全面行业研究都要回答的。回答不了的写成 UNKNOWN，不要补数字。

1. Industry Boundary
这个行业到底是什么？

2. Structural Change
需求 / 供给 / 技术 / 政策发生了什么变化？

3. Value Chain
产业链怎么拆？

4. Transmission
变化如何沿产业链传导？

5. Economics
量 / 价 / 成本 / 毛利 / 份额怎么变化？

6. Competition
谁更可能拿到增量？

7. Company Exposure
哪些上市公司真正暴露？

8. Catalysts / Risks
什么会推动 / 证伪？

9. Thesis
当前最重要的研究判断是什么？

还必须显式核对四个变化维度：

10. Technology Route Stage
技术路线处于概念、送样、客户验证、量产还是规模收入？替代的是哪一层？

11. Policy / Supply-chain Constraint
政策是传闻、征求意见、正式规则还是已执行？适用产品代际、产地/BOM 口径和时间是什么？

12. Value Migration
价值量和利润池向哪个环节迁移？哪些环节价值量下降？成立条件是什么？

13. Expectation Delta
旧预测、新预测、预测方、预测期、数值、上调/下调幅度和分歧是什么？

14. Reference Class / Base Rate
行业处于什么生命周期？合理参考类是什么？历史增长、渗透率、利润率和资本回报区间是什么？

15. Causal Model
核心叙事对应哪个输入变量，经由什么中间变量，最终体现在哪个经营/财务指标？最弱的一环是什么？

16. Capital Economics
增长需要多少投入资本？ROIC、经济利润、自由现金流和资本开支强度是否支持“好行业”的判断？

17. Implied Expectations
当前定价要求行业兑现怎样的需求、份额、价格或利润率？事实与这个兑现门槛的 GAP 是什么？

18. Conditional Scenarios
基准、上行、下行情景分别由什么条件触发？不用无依据的精确概率。

Skill 的执行步骤仍然是下面的 Step 1 到 Step 13。计划可以更细，但不能跳过上述问题。

## REQUIRED TOOLS

search_web、read_webpage、read_pdf、search_local_research、get_market_data；已配置时使用 iFinD 新闻/公告语义检索补充市场预期、技术路线和政策变化。

来源恢复顺序：官方/API → 可直接读取正文 → iFinD 等带原始 URL 的语义片段 → 独立转载/镜像 → UNKNOWN。ReAct 可以更换查询和来源，但不能绕过登录墙、验证码或反爬限制。

没有接上的工具就停。不用来源以外的记忆填空。

## DAILY UPDATE INBOX

每日看板的新闻采集器只做候选发现，不直接更新行业 Thesis：

1. 将标题、摘要和标签与用户已经跟踪的行业、细分环节、公司和事件做匹配。
2. 命中政策、技术路线、订单/产能、业绩修订或反证信号时，生成 `PENDING` 更新候选。
3. 用户点击「核验并回写」后，本 Skill 才打开原文、寻找一手来源和独立反证，并检查它改变了哪个已有假设。
4. 只有可靠正文、时间口径和覆盖检查通过，才能向 Change Ledger 追加新版本；否则保留为待核对或明确“没有变化”。

新闻标题、搜索摘要、推送文案永远不是 Claim。每日扫描不得自动创建“受益逻辑”，不得覆盖 Stable Baseline，也不得把热门新闻自动提升为活跃事件。

## OUTPUT CONTRACT

输出必须能对上下方 JSON：行业边界、价值链、驱动、技术路线、竞争、公司暴露、催化、风险、Claim、冲突、未决问题和 Thesis。Thesis 的每条判断要有 evidence_refs。没有证据就写 UNKNOWN。

用户可见结果必须保存为长期行业档案，而不是一次性文章。档案固定分成：

1. 基础产业逻辑（低频更新）
2. 产业链与价值传导
3. 技术路线、竞争与瓶颈
4. 量 / 价 / 成本 / 产能 / 利用率 / 利润率
5. 代表公司季度业绩验证
6. 市场预期与叙事
7. 本轮逻辑变化
8. 活跃事件及其影响变量
9. 风险、失效条件和反证
10. 领先 / 同步 / 滞后监控指标
11. 技术路线阶段变化
12. 政策、产地与供应链约束
13. 价值量与利润池迁移
14. 预期修订表（旧值 / 新值 / 预测方 / 期间 / 方向）
15. 历史基准、生命周期与参考类
16. 叙事到数字的因果模型
17. 资本回报与增长质量
18. 市场隐含预期与兑现门槛
19. 条件化情景与触发变量

事实、卖方预测和市场叙事必须分栏。变化日志只记录新事实造成的判断变化；重新排版旧材料不算变化。

## ABSTENTION RULES

没有可靠正文、工具失败、或关键事实没有引文时，停止写正式 Thesis。不知道的比例、客户和份额保持 UNKNOWN。详见下方 Abstention。

## PROHIBITED BEHAVIOR

禁止买卖、目标价、仓位、组合配置、把券商预测写成 FACT、把推断写成 FACT、冲突取平均、把主题映射写成「核心受益」。详见下方「LLM 不可以做」。

## DONE CRITERIA

十三个问题都有着落：答得上的挂证据，答不上的留在 Open Questions。冲突并列保留。Thesis 追加新版本，不覆盖旧版。详见下方「完成条件」。

## 输入

只收这些字段，不要把整段聊天历史塞进来：

```text
research_question
as_of
market_scope
industry_or_theme
user_context   可选，短补充
depth          brief | deep
```

## Workflow

Step 1   Clarify Research Question
Step 2   Build Research Plan
Step 3   Define Industry Boundary
Step 4   Build Value Chain
Step 5   Identify Key Drivers
Step 6   Search Evidence
Step 7   Extract Atomic Claims
Step 8   Cross-check Claims
Step 9   Identify Conflicts / Unknowns
Step 10  Map Companies to Value Chain
Step 11  Identify Catalysts / Risks
Step 12  Build Research Thesis
Step 13  Save Versioned Research Object

每条变化记录至少保存：

```text
change_type
old_expectation
new_fact_or_expectation
direction            UP | DOWN | MIXED | UNCHANGED
affected_nodes
beneficiaries
losers
premises
next_verification
confidence
evidence_refs
```

先出 Research Plan，再取证。不要在 Step 1 直接写「空间很大，建议关注某某」。

## LLM 可以做

- 把问题拆成可核对的子问题
- 从已读到的正文里抽 Atomic Claim，并标 FACT / ESTIMATE / INFERENCE / OPINION
- 对照多条 Claim，指出共同事实、冲突和缺口
- 起草 Thesis，每句判断挂 evidence_refs
- 把缺口写成 Open Question

## LLM 不可以做

- 编造客户、收入占比、订单金额、份额、技术参数、财务数字
- 把一个来源说成已证实事实
- 把券商预测写成 FACT
- 把推断写成 FACT
- 冲突时取平均，或挑一个数字当成结论
- 目标价、Buy、Sell、仓位、组合配置
- 没有产品且没有客户证据时写「核心供应商」
- 把主题映射写成这家公司一定受益
- 工具没读到正文时，用模型记忆补「最新事实」

## 证据

- Source 是文档。Evidence 是文档里的一段，带位置。
- PDF 的位置至少要有页码。
- FACT 至少一条 SUPPORT 证据，且引文必须出现在来源正文。
- INFERENCE 必须列出 premise_claim_ids。
- 两个独立来源都支持，才是 CORROBORATED。一个来源保持 SINGLE_SOURCE。
- 来源互相矛盾则 CONTESTED，不由模型裁定。
- `available_at` 晚于 Thesis `as_of` 的来源不能进入这一版。

## 公司映射

| exposure_type | 含义 |
|---|---|
| DIRECT | 产品证据 + 公告或电话会级别的客户/收入证据 |
| INDIRECT | 产品相关，收入或客户还没核对到一手文件 |
| THEMATIC | 市场把它放进主题，实证弱 |
| UNKNOWN | 证据不足 |

收入占比不知道就写 UNKNOWN。

## 完成条件

不以写完一篇文章为完成。

1. Industry boundary defined
2. Value chain built
3. Key drivers identified
4. Critical claims grounded
5. Conflicts exposed
6. Company exposure evidence-labeled
7. Catalysts / risks defined
8. Open questions explicit
9. Thesis version saved

## Abstention

没有可靠正文时输出 Unknown，并停止写正式 Thesis。

例如：某公司 AI 收入占比 UNKNOWN。不要估一个比例。

工具失败时记录 Search Failed / Source Read Failed / PDF Parse Failed，不要用 Exception 把失败吞掉。

## 输出

```json
{
  "research_question": "",
  "industry_definition": "",
  "value_chain": [],
  "key_drivers": [],
  "technology_routes": [],
  "policy_supply_chain": [],
  "value_migration": [],
  "expectation_deltas": [],
  "change_ledger": [],
  "market_structure": [],
  "company_mapping": [],
  "catalysts": [],
  "risks": [],
  "claims": [],
  "conflicts": [],
  "open_questions": [],
  "thesis": {},
  "evidence_refs": []
}
```

Thesis 是会版本化的判断，不是推荐列表。

## 分析链

九问仍然要答。往下看的时候按这条链走，有证据才写数字：

System Change → Demand / Supply Change → Physical / Economic Constraint → Value Chain → Bottleneck / Scarcity → Substitutes → Economics → Company Commercial Exposure → Market Narrative / Expectations → Catalyst → Risk → Disconfirmation → Industry Thesis

Economics 只在来源里写得清的时候写 Volume、Price、Cost、Margin、Capacity、Capex、Utilization、Working Capital、Market Share。写不出就留 UNKNOWN。

公司暴露要带商业化阶段：DEVELOPMENT、SAMPLE、QUALIFICATION、DESIGN_WIN、MASS_PRODUCTION、ORDER、REVENUE_RECOGNIZED、UNKNOWN。送样不是认证，认证不是订单，订单不是收入，产品存在不是核心供应商。

搜索摘要只是线索。打开正文之后才能抽 Evidence。反证要问什么事实会让这条判断不成立。没找到反证只记 NO_COUNTEREVIDENCE_FOUND_IN_CHECKED_SOURCES，不能写成已经证实。
