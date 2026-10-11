# AI 使用与验证记录

日期：2026-10-11  
项目：自渡 ThesisLoop

## 1. 使用了哪些 AI

| 工具 / 模型 | 用途 | 是否直接决定产品结论 |
| --- | --- | --- |
| Cursor | 早期原型、页面与脚本开发、在本地 Markdown 研究库中协作 | 否，代码和研究结果由作者检查 |
| Codex | 阅读本地项目、重构 Agent Harness、写测试、整理比赛版和代码 Review | 否，修改需通过本地构建、测试和人工 Review |
| DeepSeek（OpenAI-Compatible） | 运行时意图理解、研究规划、逐篇文档阅读、Claim 抽取与最终综合 | 不能单独写入关键个人状态；外部事实需证据和 Gate |
| iFinD MCP | 金融数据与资讯工具，不是推理模型 | 作为数据源，关键公司事实仍优先回到公告/财报 |

## 2. AI 在开发中参与了什么

1. 读代码并把早期“固定关键词 Router + 固定路线”还原成实际架构问题；
2. 将公司研究拆成财报、管理层交流、卖方预期、市场叙事、反证五条可观察来源通道；
3. 设计 Model Planner、Context Slice、Tool Registry、Coverage Contract 与 Policy Gate 的边界；
4. 根据真实使用失败补充行业/事件研究模板、HITL 和版本化档案；
5. 编写/修改前后端、测试、Eval、匿名 Demo、隐私导出和提交文档；
6. 对本地代码、数据边界和构建结果进行审计。

AI 没有替代作者完成产品取舍：目标用户、核心闭环、禁止荐股、关键写入确认、比赛版信息架构和公开数据边界均由作者根据自己的长期投资工作流决定。

## 3. 关键错误与人工修正记录

| 迭代 | AI / 系统的不合理结果 | 人工判断 | 修改 | 验证 |
| --- | --- | --- | --- | --- |
| 1. 意图路由 | “今天盘面如何”走固定板块摘要，不判断数据是否更新；天气/日期等基础问题也被生硬拒绝 | Agent 应先理解用户真实意图和工具可用性 | 用 ModelActionPlanner 作为主路由，确定性 Router 只做降级；加入运行时日期与工具状态 | Agent workflow tests |
| 2. 公司研究 | 搜到几条材料就停止，或固定四轮后结束，报告只剩技术面 | 轮数不是研究完成标准 | 内层改成 Coverage 驱动的补搜与停止；无安全新查询才 `PARTIAL` | Company Coverage tests |
| 3. 文档理解 | 只抽固定字段，很多内容变成 UNKNOWN；长文没有被模型按语义阅读 | 财报/研报应先读取正文，再形成原子 Claim | Reader + LLM Claim extraction；财务计算和引用检查仍用代码 | Research 32-case Eval |
| 4. AI 安全事件 | 将“AI安全”当作模糊关键词，未覆盖定义、起源、时间线、关键主体与产业影响 | 这是常见投资主题研究，应允许先澄清再建立事件档案 | 新增演化主题路径、HITL 和必需证据模板；保存为 Bad Case | `ai_safety_theme_misclassified` 回归通过 |
| 5. 东山精密预期 | 市场预期为空，花旗目标价修订等线索没有进入研究；不同性质来源混在一起 | 预期研究要区分公司指引、一致预期、卖方修订和市场叙事 | 增强卖方查询配方、来源分级、目标价/盈利预测时间线和证据过滤 | `dongshan_sell_side_expectations_missing` 回归通过 |
| 6. 研究展示 | Markdown 原样堆在页面，C 编号和 UNKNOWN 影响可读性 | 证据链应可审计，但主报告应先可读 | HTML 卡片、财务表格、Coverage、来源链接和执行 Trace；内部 Claim ID 不直接展示 | Next.js build + 页面人工检查 |
| 7. 比赛发布 | 原仓库包含个人交易、研究笔记、行情缓存和本地数据库 | 不能直接公开个人工作仓库 | 白名单导出、匿名 Fixture、合成交易、`.dockerignore`、空环境变量 | 安全导出扫描 + Demo smoke |
| 8. 远程 CI | 本地包级测试通过，但第一次 GitHub CI 找不到 Runtime Skills | `.cursor/skills` 被个人仓库的 IDE 忽略规则排除，说明“本机可运行”不等于“仓库可复现” | `.gitignore` 改为仅放行 6 个产品 Skill，并增加回归断言 | GitHub Actions Run 38108914351 通过 |

## 4. AI 产物如何被验证

### 代码层

- 每轮重要修改后运行 `git diff --check`、Next.js production build 和对应 Python tests；
- 最终运行 537 项单元/集成测试；
- Demo 数据库做首次初始化、重复初始化和 smoke 检查；
- 导出目录扫描个人路径、数据库、密钥和运行时数据。

### 研究层

- 模型只能基于已打开正文提出 Claim；
- FACT、ESTIMATE、INFERENCE、OPINION 分开保存；
- 数字需要来源、时间、单位/口径；
- 搜索摘要不能直接进入事实层；
- Coverage 不足就显示 `PARTIAL`，不让模型用常识补齐；
- 真实失败轨迹脱敏后固化成确定性回归案例。

### 人机边界

- Decision Recorder 只生成草稿；
- 复盘归因、情绪和反事实由用户确认；
- 单次复盘不能直接生成 Active Rule；
- 不存储模型隐藏思维链，只展示可核验的计划、工具、观察、缺口和停止原因。

## 5. 最终实测结果

- Research：32/32，6 类可信性硬门禁 0 失败；
- Recorder Gate：44/44；
- Guided Review：30/30；
- Memory：30/30；
- Python 单元/集成：537/537；
- Next.js production build：PASS；
- npm dependency audit：0 vulnerability；
- 安全导出：个人数据/runtime 文件 0，绝对本机路径 0。

这些结果不代表真实用户价值已经成立。外部可用性测试、线上模型版本回归和部署后的端到端验证仍列为后续计划。
