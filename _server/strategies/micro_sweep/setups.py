"""Micro-Sweep setup detection — S1, S3, S6.

Spec: MICRO_SWEEP_SPEC.md §5
  S1 — VWAP-Dip Scalper
  S3 — Micro-Sweep Reclaim (HIGHEST WR)
  S6 — Trend-Day First Pullback

Hepsi M1 son kapanmış bar üzerinde çalışır. Return: {"S1": bool, "S3": bool, "S6": bool}.
"""
from __future__ import annotations

import math
from typing import Optional

import pandas as pd


def _last_safe(s: pd.Series) -> Optional[float]:
    v = s.iloc[-1] if len(s) else None
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return None
    return float(v)


def detect_s1(df_m1: pd.DataFrame) -> bool:
    """S1: VWAP-Dip — bullish bar, vwap'tan ≥0.3 ATR aşağı, vol ≥ 0.7×med20."""
    bar = df_m1.iloc[-1]
    vwap = _last_safe(df_m1["vwap"])
    atr = _last_safe(df_m1["atr"])
    vol_med = _last_safe(df_m1["vol_med20"])
    if vwap is None or atr is None or atr <= 0 or vol_med is None or vol_med <= 0:
        return False
    if not bool(bar["m1_bullish"]):
        return False
    if (vwap - bar["close"]) < 0.3 * atr:
        return False
    if bar["volume"] < 0.7 * vol_med:
        return False
    return True


def detect_s3(df_m1: pd.DataFrame) -> bool:
    """S3: Micro-Sweep Reclaim — low20 altı süpürme + reclaim."""
    bar = df_m1.iloc[-1]
    atr = _last_safe(df_m1["atr"])
    low20 = _last_safe(df_m1["low20"])
    if atr is None or atr <= 0 or low20 is None:
        return False
    if not bool(bar["m1_bullish"]):
        return False
    if bar["low"] >= low20:
        return False
    if (low20 - bar["low"]) < 0.4 * atr:
        return False
    if bar["close"] <= low20:
        return False
    return True


def detect_s6(df_m1: pd.DataFrame, daily: dict, adr20: float, daily_range: float,
              daily_low: float) -> bool:
    """S6: Trend-Day First Pullback — günlük rejim koşulları + intraday fib."""
    bar = df_m1.iloc[-1]
    if not bool(bar["m1_bullish"]):
        return False
    if not daily.get("daily_bull", False):
        return False
    if daily.get("daily_body_ratio", 0) < 0.55:
        return False
    if daily.get("daily_open_pos", 1) > 0.25:
        return False
    if daily.get("daily_close_pos", 0) < 0.55:
        return False
    if adr20 <= 0 or daily_range <= 0:
        return False
    rcr = daily_range / adr20
    if not (0.35 <= rcr <= 0.85):
        return False
    fib38 = daily_low + 0.38 * daily_range
    fib62 = daily_low + 0.62 * daily_range
    close = float(bar["close"])
    if not (fib62 <= close <= fib38 + 0.1 * daily_range):
        # spec'teki şart: fib62 <= close <= fib38 + 0.1*range
        return False
    return True
