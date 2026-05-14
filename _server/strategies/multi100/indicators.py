"""MULTI100 için indikatör hesaplamaları — RSI, ATR, Bollinger, Heikin-Ashi."""
from __future__ import annotations

import pandas as pd


def rsi(series: pd.Series, n: int = 14) -> pd.Series:
    delta = series.diff()
    up = delta.clip(lower=0).rolling(n).mean()
    dn = (-delta.clip(upper=0)).rolling(n).mean()
    rs = up / dn.replace(0, 1e-10)
    return 100 - 100 / (1 + rs)


def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    h, l, c = df["high"], df["low"], df["close"]
    tr = pd.concat(
        [h - l, (h - c.shift()).abs(), (l - c.shift()).abs()],
        axis=1,
    ).max(axis=1)
    return tr.rolling(n).mean()


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Df'e RSI, ATR, Bollinger ve Heikin-Ashi kolonları ekler."""
    df = df.copy()
    df["rsi"] = rsi(df["close"])
    df["atr"] = atr(df)
    df["bb_mid"] = df["close"].rolling(20).mean()
    df["bb_std"] = df["close"].rolling(20).std()
    df["bb_lower"] = df["bb_mid"] - 2 * df["bb_std"]

    # Heikin-Ashi
    ha_close = (df["open"] + df["high"] + df["low"] + df["close"]) / 4
    ha_open = ha_close.copy()
    for i in range(1, len(df)):
        ha_open.iloc[i] = (ha_open.iloc[i - 1] + ha_close.iloc[i - 1]) / 2
    df["ha_close"] = ha_close
    df["ha_open"] = ha_open
    df["ha_red"] = ha_close < ha_open
    return df
