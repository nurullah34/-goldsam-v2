"""8T (DENGELİ) — dip/peak + 3 bar + bounce/drop kombinasyonu.

Algoritma kaynak: C:\\Users\\nurul\\OneDrive\\Masaüstü\\8t-algorithm\\detector.py
Lifecycle kaynak: 8T sinyal\\backtest_may8_v2.py (SL $75, trail $1/$0.50 ladder)

GOLDSAM V2'ye bot olarak gömülmüştür.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from strategies.base import Signal, Strategy


# 8T algoritma sabitleri (detector.py ile birebir)
DIP_FOLLOW_BARS = 3
GAP_TOLERANCE_MIN = 1.0
BOUNCE_PCT = 0.0002

# Çoklu pencere taraması — 3sa/6sa/9sa/12sa/24sa/3gün/5gün
WINDOWS = [180, 360, 540, 720, 1440, 4320, 7200]

# Magic numarası — 8T LONG: 20270001, SHORT: 20270002
MAGIC_LONG = 20270001
MAGIC_SHORT = 20270002


def _time_diff_min(t1_iso: str, t2_iso: str) -> float:
    try:
        t1 = datetime.fromisoformat(t1_iso)
        t2 = datetime.fromisoformat(t2_iso)
        return (t2 - t1).total_seconds() / 60.0
    except Exception:
        return -1.0


def detect_8t_long(bars: list[dict], window_bars: int,
                   bounce_pct: float = BOUNCE_PCT) -> Optional[dict]:
    """8T LONG: pencerede dip + tam 3 bar + dip kırılmamış + bounce."""
    n = len(bars)
    if n < window_bars + 2:
        return None
    cur = n - 1
    search_start = max(0, cur - window_bars)

    dip_idx = search_start
    dip_low = bars[search_start]["low"]
    for i in range(search_start + 1, cur):
        if bars[i]["low"] < dip_low:
            dip_low = bars[i]["low"]
            dip_idx = i

    if cur - dip_idx != DIP_FOLLOW_BARS:
        return None

    elapsed = _time_diff_min(bars[dip_idx]["time"], bars[cur]["time"])
    if abs(elapsed - DIP_FOLLOW_BARS) > GAP_TOLERANCE_MIN:
        return None

    if dip_idx == search_start and search_start > 0:
        if bars[search_start - 1]["low"] <= dip_low:
            return None

    for i in range(dip_idx + 1, cur + 1):
        if bars[i]["low"] < dip_low:
            return None

    bounce_thr = dip_low * (1 + bounce_pct)
    if not any(bars[i]["high"] >= bounce_thr for i in range(dip_idx + 1, cur + 1)):
        return None

    return {
        "direction": "LONG",
        "dip_time": bars[dip_idx]["time"],
        "dip_price": float(dip_low),
        "confirm_time": bars[cur]["time"],
        "confirm_price": float(bars[cur]["close"]),
        "window_bars": int(window_bars),
    }


def detect_8t_short(bars: list[dict], window_bars: int,
                    bounce_pct: float = BOUNCE_PCT) -> Optional[dict]:
    """8T SHORT — LONG'un aynası (peak + drop)."""
    n = len(bars)
    if n < window_bars + 2:
        return None
    cur = n - 1
    search_start = max(0, cur - window_bars)

    peak_idx = search_start
    peak_high = bars[search_start]["high"]
    for i in range(search_start + 1, cur):
        if bars[i]["high"] > peak_high:
            peak_high = bars[i]["high"]
            peak_idx = i

    if cur - peak_idx != DIP_FOLLOW_BARS:
        return None

    elapsed = _time_diff_min(bars[peak_idx]["time"], bars[cur]["time"])
    if abs(elapsed - DIP_FOLLOW_BARS) > GAP_TOLERANCE_MIN:
        return None

    if peak_idx == search_start and search_start > 0:
        if bars[search_start - 1]["high"] >= peak_high:
            return None

    for i in range(peak_idx + 1, cur + 1):
        if bars[i]["high"] > peak_high:
            return None

    drop_thr = peak_high * (1 - bounce_pct)
    if not any(bars[i]["low"] <= drop_thr for i in range(peak_idx + 1, cur + 1)):
        return None

    return {
        "direction": "SHORT",
        "dip_time": bars[peak_idx]["time"],
        "dip_price": float(peak_high),
        "confirm_time": bars[cur]["time"],
        "confirm_price": float(bars[cur]["close"]),
        "window_bars": int(window_bars),
    }


class Dengeli8T(Strategy):
    """8T plug-in — tek yönlü (LONG ya da SHORT).

    Her yön ayrı instance:
      * LONG  → magic = MAGIC_LONG
      * SHORT → magic = MAGIC_SHORT
    Aynı dip/peak birden çok pencerede tetiklenebileceğinden
    ``dip_time`` ile cluster dedup yapılır.
    """

    timeframes = ["M1"]

    def __init__(self, direction: str, symbol: str = "GOLD#") -> None:
        if direction not in ("long", "short"):
            raise ValueError("direction must be 'long' or 'short'")
        self.direction = direction
        self.symbols = [symbol]
        self._seen: set[str] = set()
        self._last_bar_time: Optional[str] = None   # yeni bar kontrolü

        if direction == "long":
            self.key = "dengeli_8t_long"
            self.display = "8T LONG"
            self.magic = MAGIC_LONG
            self._detect = detect_8t_long
            self._side = "buy"
        else:
            self.key = "dengeli_8t_short"
            self.display = "8T SHORT"
            self.magic = MAGIC_SHORT
            self._detect = detect_8t_short
            self._side = "sell"

    def check(self, bars_by_tf: dict[str, list[dict]]) -> Optional[Signal]:
        bars = bars_by_tf.get("M1", [])
        if len(bars) < min(WINDOWS) + 2:
            return None

        # Yeni bar kontrolü — bot start sonrası geçmişteki paternleri
        # tetiklememek için warm-up + same-bar dedup
        current_bar_time = bars[-1]["time"]
        if self._last_bar_time is None:
            self._last_bar_time = current_bar_time
            return None
        if self._last_bar_time == current_bar_time:
            return None
        self._last_bar_time = current_bar_time

        for w in WINDOWS:
            if len(bars) < w + 2:
                continue

            sig = self._detect(bars, w, BOUNCE_PCT)
            if sig is None:
                continue

            key = sig["dip_time"]
            if key in self._seen:
                continue
            self._seen.add(key)

            if len(self._seen) > 5000:
                self._seen = set(list(self._seen)[-2500:])

            return Signal(
                side=self._side,
                symbol=self.symbols[0],
                lot=self.lot,
                magic=self.magic,
                sl_usd=self.sl_usd,
                comment=f"{self.display.replace(' ', '_')}_W{w}",
                trail_activate_usd=self.trail_activate_usd,
                avg_threshold_usd=self.avg_threshold_usd,
                avg_lot=self.avg_lot,
            )
        return None
