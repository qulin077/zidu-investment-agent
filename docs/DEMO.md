# 演示与提交说明

## 1. 120 秒演示脚本

### 0—15 秒：问题与产品

打开 Agent 首页：

> 自主投资者不缺新闻和答案，缺的是把研究、当时判断、实际执行和复盘连接起来。自渡是一个长期 Investment Agent，不替用户荐股，而是维护可验证、可更新、可复用的个人投资工作流。

### 15—45 秒：Agent 规划与取证

点击“完整研究东山精密”示例：

> Agent 先理解意图，再把全面公司研究拆成财报、管理层交流、卖方预期、市场叙事和反证。这里展示的是可核验 Trace：查了什么、读了什么、还缺什么、为什么停止；不展示模型隐藏思维链。

为了控制演示时间，随后打开已生成的公开档案。

### 45—80 秒：Research

打开 Research → 东山精密：

> 报告不是一段长回答，而是长期 Dossier。三年年报和最新半年报以表格呈现；公司事实、卖方预测和市场叙事分层；每个关键结论可以回到来源。公开 Demo 没有实时行情和受限材料，所以 Coverage 如实标成 Partial，不让模型靠记忆补齐。

### 80—105 秒：Decision

回到 Agent，点击“记录模拟决策”：

> 模型只把用户原话解析成 Thesis、验证条件和失效点草稿。没有用户确认，就不能写入 Decision。确认后系统冻结当时研究版本，避免事后用新信息改写旧判断。

### 105—120 秒：Review

打开 Review → 东山精密（模拟）：

> Outcome 由模拟成交和行情确定性计算；Agent 对照事前 Thesis、实际执行和新事实，一次问一个归因问题。复盘结论、Pattern 和 Rule 都需要用户确认。这形成研究—决策—执行—复盘—记忆闭环。

结束语：

> 这个产品的价值不是写更长的研报，而是让事实可回查、失败可暴露、关键判断由人确认、历史能被下一轮继续使用。

## 2. 推荐演示路径

1. `/agent`
2. `/research?session=RY-DEMO-0001`
3. `/review`
4. `/review/D-20260430-002384-01`

## 3. 提交清单

| 交付物 | 状态 | 位置 |
| --- | --- | --- |
| 可操作 Web URL | 待部署后填写 | README 顶部 / 答题系统 |
| 源代码仓库 | 安全导出与冷启动通过，待推送 | 独立公开仓库 |
| README | 已完成 | `README.md` |
| 产品方案 | 已完成 | `docs/PRODUCT.md` |
| 用户研究与问题证据 | 已完成 | `docs/USER_RESEARCH.md` |
| AI Native 架构 | 已完成 | `docs/ARCHITECTURE.md` |
| AI 使用与验证记录 | 已完成 | `docs/AI_USAGE.md` |
| 测试说明 | 已完成 | `docs/EVAL_TEST.md` |
| 隐私与部署说明 | 已完成 | `docs/PRIVACY_DEPLOYMENT.md` |
| 60—180 秒视频 | 可选，尚未录制 | 建议按本脚本录屏 |

## 4. 评委快速验证

```bash
python scripts/init_competition_demo.py --db /tmp/thesisloop-demo.db
python scripts/competition_smoke.py --db /tmp/thesisloop-demo.db
```

期望看到：1 个东山精密 Research 档案、6 个公开来源、1 条完整 `REVIEWED` 模拟 Decision、0 条私人数据。

已在脱离个人仓库的全新目录验证上述结果；线上 URL 与仓库链接在发布完成后回填。
