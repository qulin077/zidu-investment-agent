"""全局路径与运行配置。core 下所有模块只从这里取路径，不再各自 parents[1]。"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

CONFIG_DIR = ROOT / "config"
DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
DAILY_DIR = DATA_DIR / "daily"
LOG_DIR = DATA_DIR / "logs"

# 现有脚本的产物位置，采集层从这里回灌历史
QUOTES_DIR = RAW_DIR / "quotes"
JIN10_DIR = RAW_DIR / "jin10"
NARRATIVE_DIR = RAW_DIR / "narrative"
POLICY_DIR = RAW_DIR / "policy"

UNIVERSE_YAML = CONFIG_DIR / "universe.yaml"
HOLIDAYS_YAML = CONFIG_DIR / "market_holidays.yaml"

TRADING_DIR = ROOT / "10-我的交易"
HOLDINGS_SNAPSHOT_CSV = TRADING_DIR / "持仓" / "持仓_快照.csv"
HOLDINGS_LATEST_CSV = TRADING_DIR / "持仓" / "持仓_最新.csv"
ACCOUNT_SNAPSHOT_CSV = TRADING_DIR / "持仓" / "账户快照.csv"
TRADES_CSV = TRADING_DIR / "交易记录" / "交易流水.csv"


@dataclass(frozen=True)
class Settings:
    """运行期配置。通过环境变量覆盖，便于测试时指向临时目录。"""

    db_path: Path
    http_cache_dir: Path
    http_timeout: int = 30
    http_attempts: int = 3
    # 同一 host 两次请求之间的最小间隔，避免把数据源打挂
    http_min_interval: float = 0.35
    http_cache_ttl: int = 900

    @property
    def db_url(self) -> str:
        return f"sqlite:///{self.db_path}"


def _env_path(key: str, default: Path) -> Path:
    raw = os.environ.get(key)
    return Path(raw).expanduser().resolve() if raw else default


def load_settings() -> Settings:
    return Settings(
        db_path=_env_path("SA_DB_PATH", DATA_DIR / "workstation.db"),
        http_cache_dir=_env_path("SA_HTTP_CACHE", DATA_DIR / "cache" / "http"),
        http_timeout=int(os.environ.get("SA_HTTP_TIMEOUT", "30")),
        http_attempts=int(os.environ.get("SA_HTTP_ATTEMPTS", "3")),
        http_min_interval=float(os.environ.get("SA_HTTP_MIN_INTERVAL", "0.35")),
        http_cache_ttl=int(os.environ.get("SA_HTTP_CACHE_TTL", "900")),
    )


SETTINGS = load_settings()
