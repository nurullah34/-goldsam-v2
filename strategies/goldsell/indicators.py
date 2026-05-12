"""GoldSell — indikatörler ve HTF level builder.

Spec: goldsell deneme1/STRATEGY_SPEC.md §2
  ATR(5/20/50), range_z50, fractal_high/low (2L/2R look-ahead safe),
  PDH (previous day high), PWH (previous week high).
"""
from __future__ import annotations

from datetime import datetime

import numpy as np
import pandas as pd


# ───── M1 indikatörleri ──────────────────────────────────────────

def _atr(df: pd.DataFrame, n: int) -> pd.Series:
    h, l, c = df["high"], df["low"], df["close"]
    tr = pd.concat(
        [h - l, (h - c.shift()).abs(), (l - c.shift()).abs()],
        axis=1,
    ).max(axis=1)
    return tr.rolling(n).mean()


def add_m1_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["atr5"]  = _atr(df, 5)
    df["atr20"] = _atr(df, 20)
    df["atr50"] = _atr(df, 50)

    rng = df["high"] - df["low"]
    df["range"] = rng
    mean50 = rng.rolling(50).mean()
    std50 = rng.rolling(50).std(ddof=0)
    df["range_z50"] = (rng - mean50) / std50.replace(0, np.nan)

    # Fractal high/low: bar j fractal_high ise high[j] > high[j-2..j+2] (kendisi hariç)
    # Look-ahead safe: bar i'de tarama yapılırken sadece j <= i-2 fractal'ları geçerli.
    hh = df["high"].values
    ll = df["low"].values
    n = len(df)
    is_fh = np.zeros(n, dtype=bool)
    is_fl = np.zeros(n, dtype=bool)
    for j in range(2, n - 2):
        h = hh[j]
        if h > hh[j - 1] and h > hh[j - 2] and h > hh[j + 1] and h > hh[j + 2]:
            is_fh[j] = True
        lo = ll[j]
        if lo < ll[j - 1] and lo < ll[j - 2] and lo < ll[j + 1] and lo < ll[j + 2]:
            is_fl[j] = True
    df["is_fh"] = is_fh
    df["is_fl"] = is_fl
    return df


# ───── HTF Levels (PDH, PWH) ─────────────────────────────────────

def build_htf_levels(bars_d1: list[dict], now_iso: str,
                     max_age_days: int = 10) -> list[dict]:
    """D1 bar'lardan PDH ve PWH'leri liste olarak üret.

    Her level: {"price": float, "time": datetime, "type": "PDH"|"PWH"}
    Sadece son `max_age_days` gün içindeki level'lar dahil edilir.
    """
    if not bars_d1:
        return []
    df = pd.DataFrame(bars_d1)
    # Date kolonu
    df["date"] = pd.to_datetime(df["time"].astype(str)).dt.date

    levels: list[dict] = []
    now_dt = datetime.fromisoformat(now_iso)
    cutoff_date = (now_dt - pd.Timedelta(days=max_age_days)).date()

    # PDH: her günün high'ı bir önceki günün level'ı olarak ertesi gün geçerli
    for i in range(len(df) - 1):
        d = df.iloc[i]
        if d["date"] < cutoff_date:
            continue
        levels.append({
            "price": float(d["high"]),
            "time":  datetime.combine(d["date"], datetime.min.time()),
            "type":  "PDH",
        })

    # PWH: haftalık resample → her haftanın high'ı
    try:
        df_idx = df.set_index(pd.to_datetime(df["time"].astype(str)))
        weekly_high = df_idx["high"].resample("W").max().dropna()
        for ts, hi in weekly_high.items():
            d = ts.date()
            if d < cutoff_date:
                continue
            levels.append({
                "price": float(hi),
                "time":  datetime.combine(d, datetime.min.time()),
                "type":  "PWH",
            })
    except Exception:
        pass

    return levels
