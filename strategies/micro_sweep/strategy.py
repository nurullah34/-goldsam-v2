"""Micro-Sweep Strategy — 27 modülün tek bir strateji altında paralel çalıştırılması.

Spec: MICRO_SWEEP_SPEC.md, STRATEGY_CATALOG.md

Tasarım:
  * Engine bunu TEK strateji olarak görür (kart: "Micro-Sweep").
  * `magic` attribute'u 27 magic'lik bir SET — PositionMonitor hepsi için
    trailing yapar, engine _has_open_position kontrolünde de bu set kullanılır.
  * Aynı anda max 1 Micro-Sweep pozisyonu açık olabilir (spec §3).
    27 modülden hangisi tetiklerse onun magic'i ile pozisyon açılır.
  * Modüller priority sırasında taranır (PERFECT → ELITE → STRONG).
  * Yalnız BUY (LONG) sinyali.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

import pandas as pd

from strategies.base import Signal, Strategy
from strategies.micro_sweep.indicators import (
    build_m1_context, compute_h1_bull, compute_daily_props, _atr
)
from strategies.micro_sweep.recipes import MODULES
from strategies.micro_sweep.setups import detect_s1, detect_s3, detect_s6


# 27 modül için 20270101..20270127 aralığı (8T, MULTI100 ile çakışmaz)
MAGIC_BASE = 20270100


class MicroSweepStrategy(Strategy):
    """27 modüllü Micro-Sweep — BUY-only XAUUSD scalping."""

    timeframes = ["M1", "H1", "D1"]

    def __init__(self, symbol: str = "GOLD#") -> None:
        self.symbols = [symbol]
        self.key = "micro_sweep"
        self.display = "Micro-Sweep"
        # magic SET: engine ve monitor 27'sini birden tanısın
        self.magic: set[int] = {MAGIC_BASE + off for _, off, _ in MODULES}
        self._last_bar_time: Optional[str] = None
        # priority sırası (recipes.MODULES'taki sıra zaten priority)
        self._modules = MODULES

    def check(self, bars_by_tf: dict[str, list[dict]]) -> Optional[Signal]:
        m1 = bars_by_tf.get("M1", [])
        h1 = bars_by_tf.get("H1", [])
        d1 = bars_by_tf.get("D1", [])

        # Yeterli veri yoksa atla (atr_pct için 500 bar, EMA200 için 210)
        if len(m1) < 520 or len(h1) < 210 or len(d1) < 25:
            return None

        # YENİ BAR KONTROLÜ — Multi100 ile aynı pattern
        current_bar_time = m1[-1]["time"]
        if self._last_bar_time is None:
            # Warm-up: bot start anında mevcut barı 'görmüş' say, sinyal verme
            self._last_bar_time = current_bar_time
            return None
        if self._last_bar_time == current_bar_time:
            return None
        self._last_bar_time = current_bar_time

        # Indikatörleri hesapla
        try:
            df_m1 = build_m1_context(m1)
        except Exception:
            return None
        if len(df_m1) < 25:
            return None

        # Setup'lar SON KAPANAN bar üzerinde (bars[-2]) — bars[-1] güncel oluşan bar
        df_closed = df_m1.iloc[:-1]
        if len(df_closed) < 25:
            return None
        closed_bar = df_closed.iloc[-1]

        # H1 bull
        try:
            h1_bull = compute_h1_bull(h1)
        except Exception:
            h1_bull = False

        # D1 props + adr20 + günlük range
        try:
            daily = compute_daily_props(d1)
            df_d1 = pd.DataFrame(d1)
            adr20 = float(_atr(df_d1, 20).iloc[-1])
            last_d = d1[-1]
            daily_range = float(last_d["high"] - last_d["low"])
            daily_low = float(last_d["low"])
        except Exception:
            daily = {"daily_bull": False}
            adr20 = 0.0
            daily_range = 0.0
            daily_low = 0.0

        # Setup tetikleyici
        try:
            s1 = detect_s1(df_closed)
            s3 = detect_s3(df_closed)
            s6 = detect_s6(df_closed, daily, adr20, daily_range, daily_low)
        except Exception:
            return None
        if not (s1 or s3 or s6):
            return None

        # Setup id (priority: S3 > S6 > S1 — S3 spec'te en yüksek WR)
        if s3:
            setup_id = "S3"
        elif s6:
            setup_id = "S6"
        else:
            setup_id = "S1"

        # Hour (broker server time = bar timestamp'in hour'u)
        try:
            hour = datetime.fromisoformat(closed_bar["time"]).hour
        except Exception:
            hour = 0

        # Outer killzone gate (spec §6 safety: hour ∈ [9, 19])
        if not (9 <= hour <= 19):
            return None

        # cum3, atr_pct, vol_ratio, recent_bear, daily_bull, h1_bull
        atr_pct = closed_bar.get("atr_pct")
        if pd.isna(atr_pct):
            atr_pct = None
        cum3 = float(closed_bar.get("cum3", 0))
        vol_med = float(closed_bar.get("vol_med20") or 0)
        vol_ratio = (float(closed_bar["volume"]) / vol_med) if vol_med > 0 else 0.0
        recent_bear = bool(closed_bar.get("recent_bear", False))

        ctx = {
            "hour": hour,
            "s1": s1,
            "s3": s3,
            "s6": s6,
            "daily_bull": bool(daily.get("daily_bull", False)),
            "h1_bull": bool(h1_bull),
            "atr_pct": atr_pct,
            "cum3": cum3,
            "vol_ratio": vol_ratio,
            "recent_bear": recent_bear,
        }

        # MS-P05 (pure-S3) için özel kural: sadece S3 tetiklemesi olmalı.
        # Diğer modüller "any setup" kabul eder.
        for module_id, offset, fn in self._modules:
            if module_id == "MS-P05" and not s3:
                continue
            try:
                if not fn(ctx):
                    continue
            except Exception:
                continue

            magic = MAGIC_BASE + offset
            return Signal(
                side="buy",
                symbol=self.symbols[0],
                lot=self.lot,
                magic=magic,
                sl_usd=self.sl_usd,
                comment=f"{module_id}_{setup_id}",
                trail_activate_usd=self.trail_activate_usd,
                avg_threshold_usd=self.avg_threshold_usd,
                avg_lot=self.avg_lot,
            )
        return None
