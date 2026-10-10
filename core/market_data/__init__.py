"""统一的多源行情入口与本地技术指标。

外部站点只负责返回结构化 OHLCV；指标和解释均在本地计算。这样以后接入
iFinD、Wind 或券商行情时，只需要新增 Provider，不需要改 Agent 和研究档案。
"""

from core.market_data.free import FreeMarketDataGateway, MarketFetch
from core.market_data.ifind import IfindDataService, MarketDataGateway
from core.market_data.technical import technical_snapshot

__all__ = [
    "FreeMarketDataGateway", "IfindDataService", "MarketDataGateway",
    "MarketFetch", "technical_snapshot",
]
