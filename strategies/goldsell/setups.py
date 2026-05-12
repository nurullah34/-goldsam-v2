"""GoldSell — 5 setup detector.

Spec: goldsell deneme1/STRATEGY_SPEC.md §3
  BSL_AR, RFAH, MWA, SCST, PEC.
Detection sırası SABİT (composite name deterministik olsun):
  BSL_AR → RFAH → MWA → SCST → PEC
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import Optional

import numpy as np
import pandas as pd


SETUP_ORDER = ["BSL_AR", "RFAH", "MWA", "SCST", "PEC"]


def _safe(v) -> Optional[float]:
    if v is None: return None
    if isinstance(v, float) and math.isnan(v): return None
    return float(v)


# ───── BSL_AR — Buy-Side Liquidity Sweep + Aggressive Rejection ──

def detect_BSL_AR(df: pd.DataFrame, i: int, lookback: int = 80) -> bool:
    if i < lookback or i < 5:
        return False
    bar = df.iloc[i]
    atr20 = _safe(bar["atr20"])
    if atr20 is None or atr20 <= 0:
        return False
    # Look-ahead safe: sadece j <= i-2 fractal'ları
    fh_window = df["is_fh"].iloc[max(0, i - lookback):i - 1]
    recent_fh_idx = fh_window[fh_window].index.tolist()
    if len(recent_fh_idx) < 3:
        return False
    highs = df["high"].loc[recent_fh_idx].values
    top3 = sorted(highs)[-3:]
    if not top3 or top3[-1] <= 0:
        return False
    cluster_mean = float(np.mean(top3))
    if cluster_mean <= 0:
        return False
    cluster_range = (max(top3) - min(top3)) / cluster_mean
    if cluster_range > 0.0015:
        return False
    cluster_hi = max(top3)
    cluster_lo = min(top3)

    if bar["high"] <= cluster_hi:    return False
    if bar["close"] >= cluster_lo:   return False
    if (bar["high"] - bar["low"]) < 0.8 * atr20:  return False
    if bar["close"] >= bar["open"]:  return False
    return True


# ───── RFAH — Reclaim Failure Above HTF High ─────────────────────

def detect_RFAH(df: pd.DataFrame, i: int, htf_levels: list[dict],
                reclaim_window: int = 8) -> bool:
    if i < reclaim_window or i < 5:
        return False
    bar = df.iloc[i]
    atr20 = _safe(bar["atr20"])
    if atr20 is None or atr20 <= 0:
        return False
    if bar["close"] >= bar["open"]:  return False
    if (bar["high"] - bar["low"]) < 0.6 * atr20:  return False

    try:
        bar_time = datetime.fromisoformat(bar["time"])
    except Exception:
        return False

    # Aktif level'lar — bar time'ından önce oluşmuş ve max_age içinde (zaten filtered)
    active = [lv for lv in htf_levels if lv["time"] <= bar_time]
    if not active:
        return False

    recent_high = df["high"].iloc[max(0, i - reclaim_window + 1):i + 1].max()
    for lv in active:
        lvp = lv["price"]
        if bar["close"] < lvp <= recent_high:
            return True
    return False


# ───── MWA — Multi-Wick Upper Absorption ─────────────────────────

def detect_MWA(df: pd.DataFrame, i: int, n_window: int = 10,
               min_wicks: int = 3, band_atr: float = 0.4) -> bool:
    if i < n_window:
        return False
    bar = df.iloc[i]
    atr20 = _safe(bar["atr20"])
    if atr20 is None or atr20 <= 0:
        return False
    if bar["close"] >= bar["open"]:  return False
    if (bar["high"] - bar["low"]) < 0.5 * atr20:  return False

    win = df.iloc[i - n_window + 1:i + 1]
    body_hi = win[["open", "close"]].max(axis=1)
    upper_wick = win["high"] - body_hi
    rng = (win["high"] - win["low"]).replace(0, np.nan)
    ratio = upper_wick / rng
    wick_mask = ratio > 0.55
    n_wicks = int(wick_mask.sum())
    if n_wicks < min_wicks:
        return False
    wick_highs = win["high"][wick_mask].values
    if len(wick_highs) == 0:
        return False
    band = float(wick_highs.max() - wick_highs.min())
    if band > band_atr * atr20:
        return False
    return True


# ───── SCST — Stop Cascade Sell Trigger ──────────────────────────

def detect_SCST(df: pd.DataFrame, i: int, lookback: int = 25,
                min_breaks: int = 2) -> bool:
    if i < lookback or i < 10:
        return False
    bar = df.iloc[i]
    if bar["close"] >= bar["open"]:  return False

    fl_window = df["is_fl"].iloc[max(0, i - lookback):i - 1]
    recent_fl_idx = fl_window[fl_window].index.tolist()
    if len(recent_fl_idx) < 3:
        return False
    fl_prices = df["low"].loc[recent_fl_idx].values
    if len(fl_prices) == 0:
        return False
    last10_low = float(df["low"].iloc[max(0, i - 9):i + 1].min())
    breaks = int(np.sum(last10_low < fl_prices))
    if breaks < min_breaks:
        return False
    if bar["close"] >= float(np.min(fl_prices)):  return False
    return True


# ───── PEC — Parabolic Exhaustion Collapse ───────────────────────

def detect_PEC(df: pd.DataFrame, i: int, lookback: int = 200,
               z_thresh: float = 1.8) -> bool:
    if i < lookback or i < 5:
        return False
    bar = df.iloc[i]
    if bar["close"] >= bar["open"]:  return False

    # Son 5 bar kümülatif range
    rng5_cur = float((df["high"].iloc[i - 4:i + 1] - df["low"].iloc[i - 4:i + 1]).sum())
    rng5_series = []
    for j in range(i - lookback, i):
        if j - 4 < 0:
            continue
        rng5_series.append(
            float((df["high"].iloc[j - 4:j + 1] - df["low"].iloc[j - 4:j + 1]).sum())
        )
    if len(rng5_series) < 50:
        return False
    arr = np.array(rng5_series)
    mu, sd = float(arr.mean()), float(arr.std(ddof=0))
    if sd <= 0:
        return False
    z = (rng5_cur - mu) / sd
    if z < z_thresh:
        return False

    # Yukarı yön kontrolü
    if bar["close"] >= float(df["close"].iloc[i - 4]):  return False
    if i - 5 < 0:
        return False
    if float(df["high"].iloc[i - 4:i].max()) <= float(df["high"].iloc[i - 5]):
        return False

    # Upper wick gücü
    body_hi = max(bar["open"], bar["close"])
    rng = bar["high"] - bar["low"]
    if rng <= 0:
        return False
    if (bar["high"] - body_hi) < 0.3 * rng:
        return False
    return True


# ───── Composite triggered list ──────────────────────────────────

def detect_all(df: pd.DataFrame, i: int, htf_levels: list[dict]) -> list[str]:
    """Tüm 5 setup'ı sırayla kontrol et — tetiklenenler SETUP_ORDER sırasında."""
    triggered: list[str] = []
    try:
        if detect_BSL_AR(df, i): triggered.append("BSL_AR")
    except Exception:
        pass
    try:
        if detect_RFAH(df, i, htf_levels): triggered.append("RFAH")
    except Exception:
        pass
    try:
        if detect_MWA(df, i): triggered.append("MWA")
    except Exception:
        pass
    try:
        if detect_SCST(df, i): triggered.append("SCST")
    except Exception:
        pass
    try:
        if detect_PEC(df, i): triggered.append("PEC")
    except Exception:
        pass
    return triggered
