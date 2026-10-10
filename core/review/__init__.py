"""Review Agent 核心域。

Decision 是一次完整投资意图，可以挂 1:N Execution。
Execution 是成交事实，不能反推 thesis / plan / emotion。

EX_ANTE：事前记录。POST_HOC：成交之后为了复盘建立，不进 Plan Adherence。
"""
