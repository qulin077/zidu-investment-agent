# Memory Query

NAME
memory-query

DESCRIPTION
从已经确认的 Pattern 和 Rule 里查找重复问题。

WHEN TO USE
用户明确要看自己是不是又在重复某个错误，或问有什么规则。

WHEN NOT TO USE
用户只是在说自己累，或随口提到追高但没有要求核对。

INPUT
用户原句。

REQUIRED CONTEXT
patterns
rules

OPTIONAL CONTEXT
当前实体。

ALLOWED TOOLS
decision_store

WORKFLOW
1. 读取已确认 Pattern
2. 读取生效 Rule
3. 只返回对得上的条目

COMPLETION CONDITIONS
对不上就说明记忆里没有，不从聊天记录编造。

OUTPUT CONTRACT
Pattern 和 Rule 列表，或明确的未命中。

ABSTENTION RULES
未确认的猜测不写入记忆。

PROHIBITED BEHAVIOR
不把一次聊天说成已经确认的行为模式。不给买卖建议。
