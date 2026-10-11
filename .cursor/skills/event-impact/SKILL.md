---
name: event-impact
description: >-
  Use this skill when the user asks what a specific event, policy, product
  launch, platform change, supply shock, corporate action, geopolitical
  development, or evolving cross-industry theme changes; how it developed;
  how it transmits through an industry; and whether it is being implemented or
  reflected in demand and earnings. Do not use it for company-only deep dives
  or buy/sell advice.
---

# event-impact

把事件维护成可持续更新的研究对象，而不是新闻摘要。事件研究必须回答：事件是否真实、相对什么基线发生了变化、通过什么中间变量传导、市场原来预期什么、下一步如何验证。

## WHEN TO USE

用于具体政策、产品平台、公司行动、供需冲击、地缘事件，或由多个主体和子事件共同推动的长期主题。行业全景走 industry-research，公司基本面走 company-research。

## OBJECT MODES

先判断研究对象，不允许把两类对象混在同一个模板里：

- `DISCRETE_EVENT`：存在可定位的主体、动作、日期和适用范围，例如一项新规、产品发布、订单、战争升级。
- `EVOLVING_THEME`：由多个主体、框架、事故、技术进展和监管动作持续推动，例如 AI 安全、AI 治理。主题没有唯一“官方公告”，必须拆成定义、起源、子事件时间线、当前催化和产业影响。

用户把主题口语化为“某某事件”时，先按对象本质识别；不能因为包含“事件”两个字就强行寻找一个不存在的单一公告。

## EVENT TYPES

- 政策与监管：先核对状态、适用范围、生效时间、执行细则和豁免。
- 产品与技术平台：区分发布、送样、验证、量产、交付和规模收入。
- 公司行动：订单、合同、并购、重组、扩产、停产、涨价；核对生效条件、履约和财务影响。
- 供需冲击：区分短期扰动、库存调整、永久产能变化和替代供给。
- 宏观与地缘：拆成商品、运费、汇率、利率、供应链和资本开支等可观察变量。

## STATE MACHINE

```text
UNVERIFIED → ANNOUNCED → DEFINED → IMPLEMENTING → REALIZED
      └──────────────→ INVALIDATED
                         REALIZED → FADING
```

- UNVERIFIED：只有传闻、二手转述或主体不清。
- ANNOUNCED：存在官方宣布，但范围、时间或执行机制仍不完整。
- DEFINED：正式规则、合同或技术规格已经明确。
- IMPLEMENTING：已进入执行、建设、验证、量产或交付。
- REALIZED：订单、收入、利润、现金流或可核验行业数据已经兑现。
- FADING：影响衰减，基线正在恢复，或已被市场/产业吸收。
- INVALIDATED：取消、撤回、失败，或关键因果链被反证。

状态只能由新证据推进或回退；发布会措辞不能直接跳到 REALIZED。

## REQUIRED EVIDENCE

1. Event Definition：原始来源、主体、时间、适用范围。
2. Pre-event Baseline：事件前的规则、配置、供需、价格或市场预期。
3. Status / Stage：当前位于状态机哪个阶段，依据是什么。
4. What Changed：相对基线真正改变的变量。
5. Causal Chain：输入变化 → 中间变量 → 产业链节点 → 经营/财务结果。
6. Economic Variables：数量、价格、成本、价值量、资本开支、产能或订单。
7. Affected Nodes：直接、间接、可能受损的节点；不输出“受益股名单”。
8. Expectation Delta：旧预期、新预期、预测方、期间、修订方向与分歧。
9. Conditional Scenarios：基准、上行、下行情景及各自触发条件。
10. Milestones：下一日期、动作、负责主体和验证来源。
11. Earnings Link：是否兑现到合同、订单、收入、利润或现金流。
12. Risk / Invalidation：延迟、豁免、替代、取消和最弱因果环节。

## EVOLVING THEME EVIDENCE

长期主题使用另一套覆盖合同：

1. Definition / Scope：准确含义、边界和子分支，明确“它不是什么”。
2. Origin / Baseline：概念起源和升温前的技术、政策与市场基线。
3. Timeline：按主体与发布日期排列的独立子事件，不能把一篇汇总文的句子拼成时间线。
4. Current Catalysts：本轮为什么升温，哪些是新事实，哪些只是旧叙事重复。
5. Actor Map：公司、监管、标准组织、研究机构的行动与立场。
6. Technical / Policy Tracks：风险、评测、红队、防护、模型与算力安全、监管和责任等分支。
7. Causal Chain：能力/事故/规则 → 安全投入或合规约束 → 产品需求/成本 → 经营影响。
8. Economic Variables：安全预算、合规成本、算力、保险、评测采购等可观察变量。
9. Affected Nodes：直接受益、间接受益、承压和方向不确定的环节及成立条件；不列“受益股名单”。
10. Market Narrative / Expectation Delta：市场在交易什么、旧预期和新预期是什么、事实差在哪里。
11. Milestones：下一标准、评测、有效日期、披露或事故复盘。
12. Risk / Invalidation：哪些反证说明只是短期炒作或因果链不成立。

## SOURCE ORDER

优先级不是绝对真伪等级，而是验证顺序：

1. 监管、交易所、政府、标准组织、公司公告和正式发布材料。
2. 财报、电话会、投资者交流、合同进展和客户/供应商交叉披露。
3. 行业机构、数据服务、卖方预测。
4. 新闻、专家观点和社交媒体只作为线索或市场叙事。

传闻必须保留原始出处和公司或监管澄清。搜索摘要不是证据。材料无法打开时更换官方入口、镜像或独立来源；用尽安全且不重复的查询后，把缺口保留为待核对。

## UPDATE RULE

首次建立完整基线。后续更新只回答：状态是否变化、哪个假设被增强或削弱、哪个数字被修订、下一个里程碑是什么。事件成为长期结构变化时，写回行业档案的变化日志；兑现到公司财务时，写回公司档案；但事件自身历史不能被覆盖或删除。

## DAILY UPDATE INBOX

每日新闻可以触发事件候选，但不能自动推进状态机。系统先把候选放进每日看板的 Research 收件箱，并标出它可能关联的事件、行业或公司。用户确认后才运行本 Skill：打开原文、补搜官方来源、建立事件前基线、寻找反证，并判断它是新事件、旧事件的新里程碑，还是无效噪音。

满足证据门槛后才追加事件版本；需要影响行业或公司档案时，分别生成可审计的回写，而不是复制新闻摘要。无法读取正文、只有单一二手转述、或因果链没有新增信息时，保持 `PENDING/UNVERIFIED`，不改变原状态。

## WORKFLOW

离散事件：确认事件指称 → 打开一手原文 → 建立事件前基线 → 判定状态 → 提取真正增量 → 构建传导链 → 量化经济变量 → 对照市场预期 → 建立条件化情景 → 列出里程碑与反证 → 保存新版本。

演化主题：定义边界 → 建立起源基线 → 按主体搜集子事件 → 形成可核对时间线 → 识别当前催化 → 拆技术/政策分支 → 构建产业传导 → 映射正向/负向/条件性影响 → 区分事实和市场叙事 → 列出验证点与反证 → 保存主题版本。

## OUTPUT CONTRACT

离散事件输出长期事件档案：一句话判断、本轮变化、事件定义、事件前基线、当前状态、真正增量、传导链、经济变量、受影响节点、预期差、条件化情景、里程碑、业绩兑现、风险/失效条件、证据缺口和来源。

演化主题输出主题跟踪档案：定义与边界、起源、时间线、为什么现在升温、主体与行动、技术与政策分支、传导链、经济变量、可能受益/承压板块及条件、市场叙事与事实差、预期变化、下一验证点、风险与反证、证据缺口和来源。

## ABSTENTION

没有原文就不写增量金额；没有基线就不声称“新增”；没有中间变量就不从事件直接跳到公司业绩；没有合同、订单或收入证据就不写“已经兑现”。不给买卖建议、目标价或仓位。

## PROHIBITED BEHAVIOR

禁止把传闻写成正式规则、把发布写成量产、把送样写成订单、把产业链相关性写成公司收入、把情景写成确定预测，或输出买卖、目标价和仓位建议。
