# 自渡 ThesisLoop：评测与测试记录

测试日期：2026-10-11  
测试对象：本地工作区代码 + 隔离的公开 Demo 数据库  
原则：开发期 Eval 不暴露给用户；用户看到的是研究覆盖、证据状态和需确认动作。

## 1. 我们评什么

产品不是用“回答像不像研报”作为唯一标准，而是把质量拆成四条可失败的链路：

| 链路 | 关键问题 | 失败时怎么处理 |
| --- | --- | --- |
| Research | 来源是否存在、关键事实是否有原文、事实/预测/推断是否混淆 | Claim 拒绝写入或档案标记 `PARTIAL` |
| Decision Recorder | 是否只抽取用户说过的 Thesis、预期、计划和失效条件 | 缺失字段进入 Human in the Loop，不自动补写 |
| Guided Review | 是否把事实偏差、执行偏差和用户归因分开 | 未经用户确认不进入 `REVIEWED` |
| Memory | 是否把一次复盘过早概括成模式或规则 | 只生成候选；Pattern / Rule 需用户确认 |

## 2. 自动化 Eval 结果

### Research Eval

命令：

```bash
python -m evals.research.runner --model fixture
```

结果：32/32 通过，失败 0。六类硬门禁均为 0：

- fabricated source：0
- unsupported critical fact：0
- wrong evidence link：0
- temporal leak：0
- fact / inference confusion：0
- direct exposure overclaim：0

其中包含两个从真实失败轨迹固化的回归案例：

1. “AI 安全”被错误当作不明确主题，研究计划没有覆盖定义、起源、时间线、主体、事件阶段和产业影响；
2. 东山精密卖方预期来源不足，目标价修订与普通市场叙事混在一起。

### Decision Recorder Gate

命令：

```bash
python -m evals.recorder.runner --model heuristic --set gate
```

结果：44/44 通过。关键字段召回率 100%，不支持字段率 0%，关键幻觉 0，缺失检测召回率 100%，拒答准确率 100%，否定、纠错、数字绑定和证券代码关键错误均为 0。

### Guided Review Eval

命令：

```bash
python -m evals.review.runner
```

结果：30/30 通过，unsupported critical 为 0。

### Memory Eval

命令：

```bash
python -m evals.memory.runner
```

结果：30/30 通过；归因泄漏、情绪臆测、不支持规则、过早生成 Pattern 均为 0。

> 这些结果证明的是当前确定性夹具与回归集没有触发已定义错误，不等于线上任意问题 100% 正确，也不等于产品已经验证投资收益。

## 3. 题目要求的四类测试

### 3.1 Happy Path

场景：用户研究东山精密 → 查看版本化公司档案 → 记录一条事前 Decision → 添加模拟 Execution → 生成确定性 Outcome → 用户确认复盘。

验证：

- Demo 初始化生成 1 个公司档案，含 6 个来源、4 个原子 Claim、三年年报和最新半年报；
- Decision 按 `DRAFT → PLANNED → ACTIVE → CLOSED → REVIEW_PENDING → REVIEWED` 转换；
- Outcome 只由 execution + quote 计算；
- 数据标记 `demo=1`、`environment=demo`，没有真实账户记录。

复现：

```bash
python scripts/init_competition_demo.py --db /tmp/thesisloop-demo.db
python scripts/competition_smoke.py --db /tmp/thesisloop-demo.db
```

### 3.2 缺数据

场景：公开 Demo 为避免分发受限材料，不携带实时行情、完整市场叙事和独立反证。

预期行为：

- Coverage Checker 输出 `PARTIAL`，显示 13/17 项；
- 壁垒、实时股价与隐含预期不由模型记忆补齐；
- 研究页仍展示已验证内容、缺口和下一步监控，而不是整个报告消失。

结果：PASS。

### 3.3 接口失败

覆盖的故障：搜索失败、网页正文不可读、付费墙、模型未配置、行情过期、数据覆盖不足。

预期行为：

- 工具返回结构化错误码与可恢复状态；
- Planner 可换查询、换来源或继续使用已有证据；
- 没有安全且不重复的下一步时停止，并保留缺口；
- 不用搜索摘要或模型记忆伪造事实；
- 行情过期或覆盖不足会阻止下游市场结论。

结果：相关单测通过。全量测试日志中的“行情过期”“覆盖 8/10”是负向夹具主动触发保护，不是测试失败。

### 3.4 极端输入与合规

覆盖：用户直接要求买卖建议、缺证券代码、否定句、修改上一句话、同一段出现多个数字、历史成交没有主观记录、重复工具调用、Prompt 中包含伪来源或越权写入要求。

预期行为：

- 不输出确定性买卖、目标仓位或收益承诺；
- 证券代码与数字绑定失败时不写入；
- 历史缺失的主观动机保持 `unavailable`，禁止模型补写；
- 写入 Decision / Pattern / Rule 前由 Policy Gate 和 Human in the Loop 控制；
- 工具重复、越权或失败时安全停止。

结果：PASS。

## 4. 工程回归

```bash
python -m unittest discover -s tests -p 'test_*.py'
```

结果：537/537 通过，用时 174.716 秒。控制台末尾的 `FAIL board quotes: 行情过期` 与 `FAIL quote coverage 8/10` 来自故意构造的负向 Guard 用例；unittest 总结果为 `OK`，说明坏数据被正确拒绝。

前端比赛模式：

```bash
NEXT_PUBLIC_DEMO_MODE=1 NEXT_PUBLIC_API_BASE=http://localhost:8787 npm run build
```

结果：Next.js production build 成功，23 个路由完成类型检查与构建。

安全导出：377 个白名单源文件；个人数据/runtime 文件 0，绝对本机路径 0。另有 228 个缓存或 runtime 文件被导出器二次拦截；`.env.example` 只有空变量和示例占位符。

前端依赖升级到 Next.js 16.4.0 / React 19.2.0 后重新生产构建通过，`npm audit` 结果为 0 vulnerability。

公开 GitHub 仓库的 `competition-checks` 在全新 Ubuntu Runner 上重新安装依赖并运行包级测试、4 组 Eval 与 Next.js production build。首次运行暴露 `.cursor/skills` 被个人仓库 `.gitignore` 排除的问题；修复为只放行 6 个 Runtime Skills 后，2026-10-11 的远程 CI 已完成并通过：[Actions Run 38108914351](https://github.com/qulin077/zidu-investment-agent/actions/runs/38108914351)。这次失败被保留为发布可复现性 BadCase，而不是删除测试。

## 5. 尚未完成的验证

- 尚未完成 3—5 名外部目标用户的可用性测试，因此不写“用户满意度”或“节省时间”结论；
- 当前机器没有 Docker，Compose 尚未做容器级冒烟；
- 公开静态 Demo 已部署成功并设为公开访问；完整双服务 Runtime 的云端 CORS、SSE、模型密钥与持久化卷仍待端到端验证；
- 远程大模型输出具有非确定性，正式上线仍需对固定案例做模型版本回归，而不能只看 fixture 成绩。
