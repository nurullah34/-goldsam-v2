"""MT5'ten OHLCV bar çekici."""
from __future__ import annotations

from datetime import datetime, timezone

try:
    import MetaTrader5 as mt5
except ImportError:
    mt5 = None


TF_MAP = {
    "M1":  None,  # mt5.TIMEFRAME_M1 — runtime'da bağlanır
    "M5":  None,
    "M15": None,
    "M30": None,
    "H1":  None,
    "H2":  None,
    "H3":  None,
    "H4":  None,
    "D1":  None,
}


def _init_tf_map() -> None:
    if mt5 is None:
        return
    TF_MAP["M1"]  = mt5.TIMEFRAME_M1
    TF_MAP["M5"]  = mt5.TIMEFRAME_M5
    TF_MAP["M15"] = mt5.TIMEFRAME_M15
    TF_MAP["M30"] = mt5.TIMEFRAME_M30
    TF_MAP["H1"]  = mt5.TIMEFRAME_H1
    TF_MAP["H2"]  = mt5.TIMEFRAME_H2
    TF_MAP["H3"]  = mt5.TIMEFRAME_H3
    TF_MAP["H4"]  = mt5.TIMEFRAME_H4
    TF_MAP["D1"]  = mt5.TIMEFRAME_D1


_init_tf_map()


def fetch_bars(symbol: str, timeframe: str, count: int = 200) -> list[dict]:
    """Son ``count`` adet bar'ı OHLCV dict listesi olarak döndür.

    Strateji formatı: ``{"time": ISO-str, "open", "high", "low", "close"}``
    """
    if mt5 is None:
        return []

    tf = TF_MAP.get(timeframe)
    if tf is None:
        return []

    # Sembolü Market Watch'a ekle (yoksa copy_rates None döner)
    mt5.symbol_select(symbol, True)

    rates = mt5.copy_rates_from_pos(symbol, tf, 0, count)
    if rates is None or len(rates) == 0:
        return []

    bars: list[dict] = []
    for r in rates:
        t = datetime.fromtimestamp(int(r["time"]), tz=timezone.utc)
        bars.append({
            "time":  t.strftime("%Y-%m-%dT%H:%M:%S"),
            "open":  float(r["open"]),
            "high":  float(r["high"]),
            "low":   float(r["low"]),
            "close": float(r["close"]),
        })
    return bars
