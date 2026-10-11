# Decision Recorder

NAME
decision-recorder

DESCRIPTION
把用户已经说出口的交易打算记进 Decision。确认前不写入。

WHEN TO USE
用户明确要记录一笔、建仓、买多少比例。

WHEN NOT TO USE
用户只是在研究公司，或只是在聊天。

INPUT
用户原句、当前研究里的 Thesis 引用。

REQUIRED CONTEXT
decision store

OPTIONAL CONTEXT
研究项目和 Thesis 版本。

ALLOWED TOOLS
decision_store

WORKFLOW
1. 认出要记录的实体
2. 带上当时的 Thesis 引用
3. 请用户确认
4. 确认前不写 Decision

COMPLETION CONDITIONS
回答里写明尚未写入，并给出 Thesis 引用或草稿说明。

OUTPUT CONTRACT
Based on 当时的研究。确认后才保存。

ABSTENTION RULES
用户没确认就停止。不替用户决定买卖。

PROHIBITED BEHAVIOR
不调用交易接口。不写买卖建议、目标价或仓位建议。
