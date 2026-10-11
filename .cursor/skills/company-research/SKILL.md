---
name: company-research
description: >-
  Use this skill when the user asks how a listed company makes money, what
  drives its revenue or profit, what the market is pricing, or where the
  company sits in an industry. Do not use this skill for direct buy/sell
  recommendations, position sizing, target prices, or portfolio allocation.
---

# company-research

回答这家公司靠什么赚钱、什么在驱动利润、市场在定价什么、哪些假设和已核对事实不一样、什么事实会验证或推翻。

不生成自己的买入、卖出、目标价或仓位建议。可以引用并比较券商已经发布的评级、目标价和
盈利预测，但必须标明机构、日期、预测期间、来源等级和后续是否已被同机构修订。

## 输入

```text
research_question
as_of
market_scope
company          公司名或代码
user_context     可选，短补充
research_mode    可选，FULL_DOSSIER / FOCUSED / INCREMENTAL_UPDATE
focus            可选，用户确认的本轮重点
user_thesis      可选，用户原始判断；保留原话，不替用户改写成结论
industry_project 可选，已有行业研究的 project_id
```

已有行业研究只作为上下文读入。不另开一个 Agent。没有行业研究时写 industry_context=UNKNOWN。

## Human checkpoint

只在研究方向会实质改变、而用户尚未说清时追问一次，不把对话变成表单：

- “这家公司怎么样 / 帮我研究一下”这类宽泛首问，先问一个关键问题：更关心基本盘与壁垒、
  财报与最新变化、增长与利润弹性、市场预期与估值、风险与失效条件，还是完整档案。
- 用户已经点明财报、利润、产品、竞争、预期、估值、风险等焦点时直接研究，不再确认。
- “有什么新变化 / 更新档案”直接走增量更新，先读旧档案再搜新增证据。
- 用户说“完整档案 / 全面研究”时直接建立完整基线。
- 同一公司的已确认 focus 可以复用；用户主动换焦点时以新问题为准。
- 每次最多问一个会改变研究路线的问题。用户自由回答即可，不要求使用固定选项。

研究开始后保存 `focus`、`research_mode` 和用户原始假设。不要把用户假设当成已验证事实。
更详细的模式选择见 [references/intake-and-modes.md](references/intake-and-modes.md)。

## Business Model

先回答：

- 卖什么？
- 卖给谁？
- 怎么收费？
- 收入是一次性还是持续性？
- 成本主要来自什么？
- 资本密集还是轻资产？

答不上的写 UNKNOWN。

## 持久化公司档案

每次研究都更新同一份档案，而不是生成一篇新的资料堆砌：

1. 公司基本盘：卖什么、卖给谁、业务分部、收入与利润来源
2. 核心壁垒：技术/IP、规模与成本、客户/渠道、认证与转换成本、定价权
3. 财务质量：收入、利润率、现金流、资本开支、营运资本、ROIC/ROE 和负债
4. 当前核心判断：增长变量、利润驱动、判断成立条件
5. 行业位置：空间、竞争格局、份额与产业链议价位置
6. 市场预期：公司指引、一致预期、卖方预测、市场叙事分别保存；同一机构按日期保留修订时间线
7. 股价与预期：当前价格及日期、估值上下文、股价隐含预期、基本面预期、GAP
8. 催化剂：能验证或改变预期的可核对事件
9. 变化日志：新事实、预期上调/下调、判断增强/削弱、没有变化
10. 风险与失效条件
11. 下一步监控指标

内部仍可用 Claim ID 和 Source ID 保持证据关系，但默认回答不得显示 `C12`、`S4`
等内部编号。正文只显示简洁脚注 `[1]`，末尾给可点击来源；内部编号留在证据抽屉和数据库。

分部尽量按产品、业务、地区或客户类型拆。总收入不能代替分部。

收入驱动按商业模式选一种：销量 × 价格，客户 × 客单价，或产能 × 利用率 × 售价。不要把三种树套在同一家公司上。

利润往下看到毛利、费用、经营利润和自由现金流。增长要能说清为什么，不能只复述一个百分比。

## 财务

`FULL_DOSSIER` 和首次全面研究必须先建立官方财报基线，再读电话会、研报和市场观点：

1. 按 `as_of` 确定应已披露的最近三个完整财年。
2. 优先直连交易所/巨潮资讯公告目录，分别打开三份完整年度报告；只有目录不可用时才回退到网页搜索。保存正文和来源。
3. 再打开最新季报/半年报，用来解释年报后的变化，不拿单季替代三年基线。
4. 先做同口径表，再做解释。覆盖不全就标出缺失年份和 UNKNOWN，不从媒体文章补财务数字。

默认输出两张三年表：

- 盈利与现金流：营业收入、同比、毛利率、经营利润率、归母净利润、扣非归母净利润、经营现金流、自由现金流。
- 资产负债与投入：资产负债率、有息负债、现金、流动比率、应收/收入、存货/收入、资本开支、自由现金流。

另做产品/业务结构表：年度、产品/业务、收入、收入占比、毛利率。没有安全解析到分部数据时明确 UNKNOWN，不能用公司总收入代替。

财务风险至少检查：审计意见与关键审计事项、口径/重述、利润与现金流背离、应收和存货相对收入的变化、负债与短债、减值/商誉、资本开支和自由现金流。无保留意见不等于没有经营风险。

比率由 `core/research/finance.py` 和 `core/research/financial_analysis.py` 计算，模型不心算。详细口径、可比性检查和风险框架见 [references/financial-statement-analysis.md](references/financial-statement-analysis.md)。

行业和生命周期决定优先指标：制造业看量价、原料、产能、存货和资本开支；软件看 ARR、留存和获客；医药看管线、研发和现金跑道；周期品看价格与成本曲线；金融看资本和资产质量。生命周期是分析标签，不是公司披露事实，证据不足就 UNKNOWN。详见 [references/industry-and-lifecycle.md](references/industry-and-lifecycle.md)。

估值只给上下文：市盈率、EV/EBITDA、市销率、历史倍数、同行倍数。不写目标价。

## Expectations

四类分开保存，不能混成一句“市场认为”：

```text
CONSENSUS_DATA
MANAGEMENT_GUIDANCE
SELL_SIDE_ESTIMATE
MARKET_NARRATIVE
```

没有可靠一致预期时，consensus_view = UNKNOWN。

卖方预测不是一个静态数字。每条至少保存：机构、报告日期、评级、目标价（若披露）、预测期间、
收入/利润/EPS 预测、估值方法、核心假设、相对上一版的上调/下调，以及来源等级。按机构形成
时间线，旧值标为历史版本，不得被新值静默覆盖。数据商语义片段和媒体转述只能作为线索层；
能找到原始研报时必须回溯原文，找不到时明确标成“原始研报待补”。详细规则见
[references/sell-side-expectations.md](references/sell-side-expectations.md)。

Variant Perception 只有在证据支持差异时才写。否则 status = NO_VERIFIED_VARIANT。

字段：consensus_view、our_view、gap、validation_signal、invalidation_signal。

“公司变好”不等于“股价低估”。预期 GAP 必须回答两件事：基本面可能如何变化，以及
当前价格已隐含什么。缺少一致预期、盈利口径或估值输入时，gap_direction 必须是 UNKNOWN，
不能用主题热度或单日涨跌代替反向估值。

## 首次研究与后续更新

- 首次研究建立完整基线，并保存来源正文、结构化档案和未决问题。
- 后续先读取旧档案，再检查上次联网时间以后的公告、财报、业绩说明会和预期修正。
- 只有新增来源或同一来源内容更新后产生的 Claim 才进入“新事实”。
- 从未变化的旧来源重新抽出一句话，只算重新分类，不算公司发生了变化。
- 没有变化时明确写“没有发现足以改变判断的新证据”，不要把旧事实包装成更新。

## 并行来源 Skill

`company-research` 是总控 Skill。第一次建立基线或检查新增信息时，首轮按用户焦点并行执行
以下只读来源 Skill，完成后统一进入 Claim、冲突检查和公司档案；它们不能各自直接下结论：

| Source Skill | 主要材料 | 允许回答 | 不允许回答 |
| --- | --- | --- | --- |
| `filing-analysis` | 最近三年官方年报、最新季报/半年报、公告、交易所问询 | 三年财务基线、分部结构、已披露事实、风险 | 未披露的未来业绩 |
| `management-communication` | 电话会、业绩说明会、投资者关系记录 | 管理层解释、指引、经营变量 | 把指引写成已实现业绩 |
| `sell-side-expectations` | 券商研报目录、iFinD 资讯语义片段、公开评级聚合页、研报摘要和可读原文 | 盈利预测、评级、目标价、估值假设和预测修正时间线 | 单独证明公司经营事实；把二手摘要冒充原始研报 |
| `market-narrative` | 雪球等市场观点 | 市场在讨论什么、争议在哪里 | 证明收入、客户或订单 |
| `risk-disconfirmation` | 问询、下修、减值、诉讼和反方材料 | 风险与证伪条件 | 因为没搜到就证明风险不存在 |

同一公告的转载只算一个来源。财报与官方 IR 是一手层；券商是预测层；雪球等社区内容始终是
低置信度观点层。来源之间有冲突时并列保存，不取平均，不用低层级来源覆盖高层级原文。

卖方通道必须按发布日期和预期修订信号排序，不能按 URL 排序；至少同时检索“盈利预测/一致预期”
和“目标价/评级/上调/下调”，并覆盖常见境内外机构名称。候选很多但正文全部打不开时，状态是
`ATTEMPTED_UNAVAILABLE`，不是“没有卖方覆盖”。启用 iFinD 时，公司研究除财务交叉校验外，还要
并行调用公司资讯语义搜索补充卖方与催化线索；其返回片段保持 `VENDOR_EXCERPT` 标识。

`filing-analysis` 内部先按三个财年分别检索，不能把“三年财报”压成一次泛搜索。完整档案未尝试三年年报前，不进入最终综合；来源确实不可读时记录覆盖缺口后继续。

首轮 fan-out 后只针对仍缺少的 Business Model、Financial Trend、Key Driver、Expectations
和 Risk 做有限补搜；不是把所有来源无限爬一遍。

## 商业化阶段

DEVELOPMENT、SAMPLE、QUALIFICATION、DESIGN_WIN、MASS_PRODUCTION、ORDER、REVENUE_RECOGNIZED、UNKNOWN。

送样不是量产。订单不是收入。笔记里的产品句不是 DIRECT。DIRECT 仍要产品证据，加上公告或电话会级别的客户或收入证据。

## 完成条件

1. Business Model PASS
2. Revenue Drivers PASS
3. Financial Trend PASS
4. Industry Context PASS 或 UNKNOWN_EXPLICIT
5. Critical Claims GROUNDED
6. Company Exposure GROUNDED
7. Expectations PASS 或 UNKNOWN_EXPLICIT
8. Risks PASS
9. Disconfirmation ATTEMPTED
10. Invalidation PASS
11. Monitoring PASS

## 禁止

- 由产品自行生成买卖结论、目标价、仓位或组合配置；引用卖方已发布目标价必须带机构、日期和来源等级
- 把指引写成已实现业绩
- 编造一致预期
- 没有证据的预期差
- 用搜索摘要代替正文
- 把样品写成量产，把订单写成收入
