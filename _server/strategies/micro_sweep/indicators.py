"""Micro-Sweep — M1/H1/D1 indikatör hesaplamaları.

Spec: MICRO_SWEEP_SPEC.md §4
  ATR(14) M1, EMA50/200 H1, session-anchored VWAP, vol_med20,
  atr_pct (500-bar percentile), low20 (shift-1), cum3, daily props.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def _atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    h, l, c = df["high"], df["low"], df["close"]
    tr = pd.concat(
        [h - l, (h - c.shift()).abs(), (l - c.shift()).abs()],
        axis=1,
    ).max(axis=1)
    return tr.rolling(n).mean()


def _ema(series: pd.Series, n: int) -> pd.Series:
    return series.ewm(span=n, adjust=False).mean()


def _session_vwap(df: pd.DataFrame) -> pd.Series:
    """Session-anchored VWAP — broker günü 00:00'da reset.

    bar['time'] formatı: 'YYYY-MM-DDTHH:MM:SS' (broker server time'a göre).
    """
    typical = (df["high"] + df["low"] + df["close"]) / 3.0
    tpv = typical * df["volume"].astype(float)
    # Tarih kısmı ile session grupla
    date_key = df["time"].astype(str).str.slice(0, 10)
    cum_tpv = tpv.groupby(date_key).cumsum()
    cum_v = df["volume"].astype(float).groupby(date_key).cumsum()
    return cum_tpv / cum_v.replace(0, np.nan)


def _percentile_rank(s: pd.Series, window: int = 500) -> pd.Series:
    """Her bar için: son ``window`` bar içindeki rank'i [0,1]."""
    def _pct(x):
        last = x.iloc[-1]
        return float((x <= last).sum()) / len(x)
    return s.rolling(window, min_periods=20).apply(_pct, raw=False)


def build_m1_context(bars_m1: list[dict]) -> pd.DataFrame:
    """M1 bar listesi → indikatör'lerle dolu DataFrame.

    Sütunlar: standart OHLCV + atr / ema / vwap / vol_med20 / atr_pct /
    low20 / cum3 / m1_bullish / recent_bear.
    """
    df = pd.DataFrame(bars_m1)
    if df.empty:
        return df

    df["atr"] = _atr(df, 14)
    df["vol_med20"] = df["volume"].rolling(20).median()
    df["vwap"] = _session_vwap(df)
    df["atr_pct"] = _percentile_rank(df["atr"], 500)
    df["low20"] = df["low"].rolling(20).min().shift(1)  # shift-1: lookahead engelleme
    df["cum3"] = (df["close"] - df["open"]).rolling(3).sum()
    df["m1_bullish"] = df["close"] > df["open"]
    df["recent_bear"] = df["cum3"] < -0.3 * df["atr"]
    return df


def compute_h1_bull(bars_h1: list[dict]) -> bool:
    """H1: EMA50 > EMA200 AND close > EMA50."""
    if len(bars_h1) < 210:
        return False
    df = pd.DataFrame(bars_h1)
    ema50 = _ema(df["close"], 50).iloc[-1]
    ema200 = _ema(df["close"], 200).iloc[-1]
    close = df["close"].iloc[-1]
    return bool(ema50 > ema200 and close > ema50)


def compute_daily_props(bars_d1: list[dict]) -> dict:
    """D1 son barı (oluşmakta olan/son kapanan) → daily candle properties.

    Returns:
      daily_bull, daily_body_ratio, daily_open_pos, daily_close_pos
    """
    if not bars_d1:
        return {"daily_bull": False}
    last = bars_d1[-1]
    o, h, l, c = last["open"], last["high"], last["low"], last["close"]
    rng = max(h - l, 1e-9)
    return {
        "daily_bull": bool(c > o),
        "daily_body_ratio": abs(c - o) / rng,
        "daily_open_pos": (o - l) / rng,
        "daily_close_pos": (c - l) / rng,
    }
