"""MULTI100 — 8 strateji tarifi (multi100.py'den port edildi).

Hepsi LONG yönlü (yutucu mum, MACD cross, BB, vb. — dip/dönüş paternleri).
Her fonksiyon (df, i) → bool döner.

  S04 — Engulfing (Yutucu Mum)
  S11 — MACD Histogram cross-up
  S12 — Heikin-Ashi 3 kırmızı sonra yeşil
  S17 — Strong bullish body (>70% range)
  S19 — Üçlü mum desteği (kırmızı + 2 yeşil)
  S22 — 4 ardışık yeşil mum
  S26 — BB mid cross-up
  S30 — Higher lows + bullish bar
"""
from __future__ import annotations

import pandas as pd


def s04(df: pd.DataFrame, i: int) -> bool:
    if i < 1:
        return False
    bar = df.iloc[i]
    prev = df.iloc[i - 1]
    return (
        prev["close"] < prev["open"]
        and bar["close"] > bar["open"]
        and bar["close"] >= prev["open"]
        and bar["open"] <= prev["close"]
    )


def s11(df: pd.DataFrame, i: int) -> bool:
    if i < 27:
        return False
    ema12 = df["close"].ewm(span=12).mean()
    ema26 = df["close"].ewm(span=26).mean()
    macd = ema12 - ema26
    hist = macd - macd.ewm(span=9).mean()
    return hist.iloc[i - 1] <= 0 and hist.iloc[i] > 0


def s12(df: pd.DataFrame, i: int) -> bool:
    if i < 4:
        return False
    return (
        bool(df["ha_red"].iloc[i - 3])
        and bool(df["ha_red"].iloc[i - 2])
        and bool(df["ha_red"].iloc[i - 1])
        and not bool(df["ha_red"].iloc[i])
    )


def s17(df: pd.DataFrame, i: int) -> bool:
    bar = df.iloc[i]
    rng = bar["high"] - bar["low"]
    body = bar["close"] - bar["open"]
    return body > 0 and body > rng * 0.7


def s19(df: pd.DataFrame, i: int) -> bool:
    if i < 3:
        return False
    b0 = df.iloc[i - 2]
    b1 = df.iloc[i - 1]
    b2 = df.iloc[i]
    return (
        b0["close"] < b0["open"]
        and b1["close"] > b1["open"]
        and b2["close"] > b2["open"]
    )


def s22(df: pd.DataFrame, i: int) -> bool:
    if i < 3:
        return False
    for j in range(i - 3, i + 1):
        if df.iloc[j]["close"] <= df.iloc[j]["open"]:
            return False
    return True


def s26(df: pd.DataFrame, i: int) -> bool:
    if i < 21:
        return False
    prev = df.iloc[i - 1]
    bar = df.iloc[i]
    return prev["close"] < prev["bb_mid"] and bar["close"] > bar["bb_mid"]


def s30(df: pd.DataFrame, i: int) -> bool:
    if i < 10:
        return False
    bar = df.iloc[i]
    prev_lows = df["low"].iloc[i - 10 : i - 5].min()
    recent_low = df["low"].iloc[i - 5 : i].min()
    return recent_low > prev_lows and bar["close"] > bar["open"]


# Strateji adı → fonksiyon eşlemesi
STRATS = {
    "S04": s04,
    "S11": s11,
    "S12": s12,
    "S17": s17,
    "S19": s19,
    "S22": s22,
    "S26": s26,
    "S30": s30,
}
