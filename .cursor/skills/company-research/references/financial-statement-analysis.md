# Financial statement analysis

## 顺序

1. 读业务与会计口径：公司卖什么、分部怎么划、收入何时确认、是否发生会计政策或合并范围变化。
2. 读利润表：收入由量/价/客户数驱动还是并购驱动；毛利、费用和经营利润为何变化。
3. 读资产负债表：增长占用了多少应收、存货和固定资产；债务期限与现金是否匹配。
4. 读现金流量表：利润是否变成经营现金流；资本开支后还剩多少自由现金流。
5. 读附注、审计意见和管理层讨论：数字变化的口径、一次性因素、关键估计和风险。
6. 最后连接三表与经营驱动，不从一个同比数字直接得出趋势。

## 三年标准表

金额统一转为亿元，保留原始金额和来源。比例由程序计算；缺少分母时不算。

| 组别 | 字段 | 计算/核对 |
| --- | --- | --- |
| 增长 | 营业收入、同比 | `本期/上期-1`；检查重述与并购 |
| 盈利 | 毛利率、经营利润率、净利率 | 分母均为收入；分部毛利与合并毛利分开 |
| 质量 | 归母、扣非、经营现金流、现金利润比 | `OCF/归母净利润`，连续多年而非单年判断 |
| 投入 | 资本开支、Capex/收入、自由现金流 | `OCF-Capex`；区分维持与扩张性开支 |
| 营运 | 应收/收入、存货/收入、合同负债 | 同比和收入增速一起看；最好再算周转天数 |
| 杠杆 | 总负债、资产负债率、有息负债、现金、流动比率 | 继续拆短债、长期债、利息覆盖和到期结构 |
| 回报 | ROE、ROIC | 使用平均权益/投入资本；区分杠杆和经营改善 |

## 产品/业务结构表

优先取年报的分行业、分产品、分地区和主要客户披露：

| 年度 | 产品/业务 | 收入 | 占比 | 同比 | 毛利率 | 收入确认口径 | 来源 |
| --- | --- | ---: | ---: | ---: | ---: | --- | --- |

同名分部跨年口径变化时不要强行拼接。记录“更名/合并/拆分/处置”，并把不可比年份标为不可比。

## 可比性检查

- 年报是否为修订版，比较数是否重述。
- 币种、单位、会计准则、合并范围和收入确认是否一致。
- 归母净利润与扣非归母净利润不能混用。
- 年报、半年报和单季口径不能直接横比；TTM 要明确计算区间。
- 收入增长如果来自并购、汇率或会计变化，和内生增长分开。
- 分部加总与合并口径的抵销项保留，不硬凑 100%。

## 风险筛查

- 审计：非标意见、持续经营、关键审计事项、会计差错更正、监管问询。
- 收入：期末突增、合同资产/应收快于收入、客户集中、退货或渠道库存。
- 利润：扣非明显弱于归母、毛利率异常、政府补助/公允价值/资产处置贡献。
- 现金：利润增长而 OCF 持续走弱；FCF 连续为负却缺少可验证的扩产回报。
- 资产：存货积压、跌价准备、应收账龄、商誉与减值、在建工程长期不转固。
- 负债：流动比率、短债/现金、利息覆盖、受限资金、担保和表外承诺。

阈值只是提醒，不是结论。最终必须和同行、商业模式及周期位置比较。

## 方法来源

- [CFA Institute · Company Analysis: Past and Present](https://www.cfainstitute.org/insights/professional-learning/refresher-readings/2026/company-analysis-past-and-present)：业务模型、历史报表、量价驱动、营运资本、资本开支与资本结构。
- [CFA Institute · Financial Analysis Techniques](https://www.cfainstitute.org/insights/professional-learning/refresher-readings/2026/financial-analysis-techniques)：共同比、周转、偿债与行业专属指标。
- [CFA Institute · Equity Research Report Essentials](https://www.cfainstitute.org/sites/default/files/-/media/documents/support/research-challenge/challenge/rc-equity-research-report-essentials.pdf)：商业、行业、历史财务、预测、估值与风险的研究报告结构。
- [SEC · Beginners' Guide to Financial Statements](https://www.sec.gov/about/reports-publications/investorpubsbegfinstmtguide)：三表、MD&A、现金与利润、常用比率。
- [SEC · Financial Reporting Manual, Topic 9](https://www.sec.gov/about/divisions-offices/division-corporation-finance/financial-reporting-manual/frm-topic-9)：MD&A 应解释经营结果、财务状况及现金流质量，而非只复述百分比。
- [中国证监会 · 公开发行证券的公司信息披露内容与格式准则第2号](https://www.csrc.gov.cn/csrc/c101954/c7547588/content.shtml)：中国上市公司年度报告披露框架。
- [IFRS 8 · Operating Segments](https://www.ifrs.org/issued-standards/list-of-standards/ifrs-8-operating-segments/)：分部、产品服务、地区和主要客户信息。
