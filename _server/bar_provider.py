"""VPS-side MT5 bar provider — `metadinleme` (XM Demo) MT5'e bağlanır.

Bot-side bar_provider'dan farkı: spesifik MT5 path (`MT5_PATH`) ile bağlanır.
Strategy modülleri buradaki `fetch_bars`'ı kullanır.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

try:
    import MetaTrader5 as mt5
except ImportError:
    mt5 = None

from config import MT5_PATH, SYMBOL


_TF_MAP: dict[str, object] = {}
_INIT_OK = False


def _init() -> bool:
    global _INIT_OK
    if mt5 is None:
        return False
    if _INIT_OK:
        return True
    ok = mt5.initialize(path=MT5_PATH)
    if not ok:
        return False
    mt5.symbol_select(SYMBOL, True)
    _TF_MAP["M1"]  = mt5.TIMEFRAME_M1
    _TF_MAP["M5"]  = mt5.TIMEFRAME_M5
    _TF_MAP["M15"] = mt5.TIMEFRAME_M15
    _TF_MAP["M30"] = mt5.TIMEFRAME_M30
    _TF_MAP["H1"]  = mt5.TIMEFRAME_H1
    _TF_MAP["H2"]  = mt5.TIMEFRAME_H2
    _TF_MAP["H3"]  = mt5.TIMEFRAME_H3
    _TF_MAP["H4"]  = mt5.TIMEFRAME_H4
    _TF_MAP["D1"]  = mt5.TIMEFRAME_D1
    _INIT_OK = True
    return True


def is_connected() -> bool:
    if mt5 is None:
        return False
    if not _init():
        return False
    info = mt5.account_info()
    return info is not None


def account_info() -> Optional[dict]:
    if not _init():
        return None
    info = mt5.account_info()
    if info is None:
        return None
    return {
        "login":   info.login,
        "server":  info.server,
        "company": info.company,
        "balance": float(info.balance),
        "equity":  float(info.equity),
    }


def fetch_bars(timeframe: str, count: int = 250) -> list[dict]:
    """OHLCV + volume + spread (bot'taki ile aynı format)."""
    if not _init():
        return []
    tf = _TF_MAP.get(timeframe)
    if tf is None:
        return []

    rates = mt5.copy_rates_from_pos(SYMBOL, tf, 0, count)
    if rates is None or len(rates) == 0:
        return []

    bars: list[dict] = []
    for r in rates:
        t = datetime.fromtimestamp(int(r["time"]), tz=timezone.utc)
        try:
            vol = int(r["tick_volume"])
        except (ValueError, KeyError, IndexError):
            vol = 0
        try:
            spr = int(r["spread"])
        except (ValueError, KeyError, IndexError):
            spr = 0
        bars.append({
            "time":   t.strftime("%Y-%m-%dT%H:%M:%S"),
            "open":   float(r["open"]),
            "high":   float(r["high"]),
            "low":    float(r["low"]),
            "close":  float(r["close"]),
            "volume": vol,
            "spread": spr,
        })
    return bars
