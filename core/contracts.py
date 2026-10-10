"""数据集契约：每个数据集允许多旧、覆盖率底线是多少、由谁产出。

现状是 33 个 data/raw 目录没有统一约定，每个消费方各自判断数据能不能用。
这里把约定声明化，校验逻辑只写一遍。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from core.calendar import Freshness
from core.store import STORE, Store


@dataclass(frozen=True)
class Dataset:
    """一个数据集的契约声明。"""

    name: str
    table: str
    freshness: Freshness
    description: str
    date_column: str = "date"
    # 覆盖率按股票池计算，None 表示该数据集与股票池无关
    min_coverage: Optional[float] = None
    required_columns: Sequence[str] = field(default_factory=tuple)


DATASETS: Dict[str, Dataset] = {
    "quote_daily": Dataset(
        name="quote_daily",
        table="quote_daily",
        freshness=Freshness(max_age_days=7, label="行情"),
        description="池内标的日线行情，所有技术判定的基础",
        min_coverage=0.9,
        required_columns=("code", "date", "close"),
    ),
    "news_item": Dataset(
        name="news_item",
        table="news_item",
        freshness=Freshness(max_age_days=3, label="新闻"),
        description="金十快讯、政策要闻、叙事文章的统一收件箱",
        date_column="published_at",
        required_columns=("id", "source", "published_at", "title"),
    ),
    "position_snapshot": Dataset(
        name="position_snapshot",
        table="position_snapshot",
        freshness=Freshness(max_age_days=7, label="持仓快照"),
        description="持仓历史真相源，按日追加",
        required_columns=("date", "code", "qty"),
    ),
    "account_snapshot": Dataset(
        name="account_snapshot",
        table="account_snapshot",
        freshness=Freshness(max_age_days=7, label="账户快照"),
        description="账户权益曲线",
        required_columns=("date", "equity"),
    ),
    "trade": Dataset(
        name="trade",
        table="trade",
        freshness=Freshness(max_age_days=30, label="成交流水"),
        description="历史成交，复盘与行为归因的底稿",
        required_columns=("id", "date", "code", "side"),
    ),
    "instrument": Dataset(
        name="instrument",
        table="instrument",
        freshness=Freshness(max_age_days=3650, label="标的主数据"),
        description="股票池主数据，代码与板块的唯一出口",
        date_column="",
        required_columns=("code",),
    ),
}


@dataclass
class DatasetStatus:
    name: str
    description: str
    rows: int
    asof: str
    age: Optional[int]
    ok: bool
    issues: List[str] = field(default_factory=list)
    coverage: Optional[float] = None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "rows": self.rows,
            "asof": self.asof,
            "age": self.age,
            "ok": self.ok,
            "issues": self.issues,
            "coverage": self.coverage,
        }


def inspect(
    dataset: Dataset,
    store: Store = STORE,
    ref: Any = None,
    universe_size: int = 0,
) -> DatasetStatus:
    """检查单个数据集的行数、新鲜度与覆盖率。"""
    issues: List[str] = []
    rows = store.count(dataset.table)
    if rows == 0:
        return DatasetStatus(
            name=dataset.name,
            description=dataset.description,
            rows=0,
            asof="",
            age=None,
            ok=False,
            issues=["表为空，尚未采集"],
        )

    asof = ""
    age: Optional[int] = None
    ok = True
    if dataset.date_column:
        asof = store.max_date(dataset.table, dataset.date_column) or ""
        result = dataset.freshness.check(asof, ref)
        age = result.age
        if not result.ok:
            ok = False
            issues.append(result.reason)

    coverage: Optional[float] = None
    if dataset.min_coverage is not None and universe_size > 0 and asof:
        covered = int(
            store.scalar(
                "SELECT COUNT(DISTINCT code) FROM {0} WHERE {1} = ?".format(
                    dataset.table, dataset.date_column
                ),
                (asof,),
            )
            or 0
        )
        coverage = covered / universe_size
        if coverage < dataset.min_coverage:
            ok = False
            issues.append(
                "最新日覆盖率 {0}/{1}={2:.1%}，低于阈值 {3:.0%}".format(
                    covered, universe_size, coverage, dataset.min_coverage
                )
            )

    return DatasetStatus(
        name=dataset.name,
        description=dataset.description,
        rows=rows,
        asof=asof,
        age=age,
        ok=ok,
        issues=issues,
        coverage=coverage,
    )


def inspect_all(
    store: Store = STORE, ref: Any = None, universe_size: int = 0
) -> List[DatasetStatus]:
    return [
        inspect(dataset, store=store, ref=ref, universe_size=universe_size)
        for dataset in DATASETS.values()
    ]
