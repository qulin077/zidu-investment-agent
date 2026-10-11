# 自渡 ThesisLoop｜同花顺 AI Native 投资产品创新提交页

## 提交入口

| 交付物 | 链接 |
| --- | --- |
| 可实际操作的 Web 产品 | <https://zidu-thesisloop.nuttyloon3.chatgpt.site> |
| 公开源代码仓库 | <https://github.com/qulin077/zidu-investment-agent> |
| AI 使用与验证记录 | [AI_USAGE.md](AI_USAGE.md) |
| 测试说明 | [EVAL_TEST.md](EVAL_TEST.md) |
| 远程 CI | <https://github.com/qulin077/zidu-investment-agent/actions/runs/38108914351> |

## 一句话产品

自渡是面向有自主研究习惯的个人投资者的长期 Investment Agent：它把跨来源公司/行业/事件研究沉淀为可持续更新、可回查的档案，再冻结用户当时的投资 Thesis，对照模拟执行、新事实和结果完成结构化复盘，最终只在用户确认后沉淀个人 Pattern 与 Rule。

## 核心主链路

```text
问题 → Agent 规划与工具调用 → Source / Evidence / Claim / Thesis
     → 版本化 Research → 用户确认 Decision → 模拟 Execution
     → Review → 用户确认 Pattern / Rule
```

LLM 负责意图、规划、长文阅读与跨来源综合；Tools 获取财报、公告、行情、iFinD 与网页；Harness 管理 Context、权限、状态、补搜和安全停止；确定性代码检查时点、引用、Coverage 与 Outcome；Human in the Loop 控制关键写入。

## 已验证

- Research 32/32，6 类可信性硬门禁 0 失败；Recorder 44/44；Review 30/30；Memory 30/30；
- 本地单元/集成测试 537/537，前端 production build 通过，npm audit 0 vulnerability；
- GitHub CI 在干净环境重新执行包级测试、4 组 Eval 与前端构建，最终通过；
- 公开 Demo 使用公开 Fixture 和模拟交易；证据不足显示 `PARTIAL`，不输出荐股、收益承诺或确定性预测。

> 未完成 3–5 名外部目标用户可用性测试，因此不宣称效率、满意度或投资收益已提升。
