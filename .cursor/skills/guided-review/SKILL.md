# Guided Review

NAME
guided-review

DESCRIPTION
把决策当时的 Thesis 和现在的 Thesis 并排给用户看。

WHEN TO USE
用户要复盘某一笔、问这笔为什么错。

WHEN NOT TO USE
用户还没指定要复盘的决策，或只是在研究一家公司。

INPUT
用户原句、Decision、决策时的 Thesis。

REQUIRED CONTEXT
decision

OPTIONAL CONTEXT
当前研究结论。

ALLOWED TOOLS
decision_store
research_store

WORKFLOW
1. 找到要复盘的 Decision
2. 读出 Decision-time Thesis
3. 读出当前 Thesis
4. 标出变化
5. 询问研究错误是否要写入，等待确认

COMPLETION CONDITIONS
没有挂上 Thesis 时先问是哪一笔。不自动写研究错误。

OUTPUT CONTRACT
Decision Time、Current、Changes，以及需要用户确认的问题。

ABSTENTION RULES
没有 Decision 就不编造复盘结论。

PROHIBITED BEHAVIOR
不把研究错误自动写入。不给下一笔的买卖建议。
