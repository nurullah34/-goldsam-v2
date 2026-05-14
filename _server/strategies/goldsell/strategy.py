"""GoldSell — XAUUSD SELL-only microstructure strategy (production: MEGA_B config).

Spec: goldsell deneme1/STRATEGY_SPEC.md, configs.json

Tasarım:
  * SELL-only (sat işlemleri)
  * 5 setup × 10 filter; production = MEGA_B (en stabil 60g %96.72)
  * Bar i close'da detect → bar i+1 open'da SELL (engine'in new-bar
    detection'ı zaten bunu doğal olarak sağlıyor: bars[-1] = oluşan yeni bar,
    bars[-2] = az önce kapanmış bar — biz [-2]'yi kontrol edip [-1]'in open'ına gireriz)
  * Magic = 20270200 (production tek magic)
  * Aynı anda max 1 pozisyon (engine sağlıyor)
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

import pandas as pd

from strategies.base import Signal, Strategy
from strategies.goldsell.indicators import add_m1_indicators, build_htf_levels
from strategies.goldsell.setups import detect_all
from strategies.goldsell.filters import pass_all_filters


# Production config: MEGA_B (configs.json'dan, %96.72 60g stabil)
MEGA_B_CONFIG = {
    "name": "MEGA_B",
    "filters": {
        "allow_hours":      "GOLDEN_HOURS",
        "conf_min":         2,
        "atr_min":          3.0,
        "whitelist_combos": "WHITE_BROAD",
        "spread_max_pts":   20,
        "vol_expansion":    1.3,
    },
}

MAGIC = 20270200


class GoldSellStrategy(Strategy):
    """XAUUSD SELL-only — MEGA_B (production) config."""

    timeframes = ["M1", "D1"]

    def __init__(self, symbol: str = "GOLD#", config: dict = MEGA_B_CONFIG) -> None:
        self.symbols = [symbol]
        self.key = "goldsell"
        self.display = "GOLDS"
        self.magic = MAGIC
        self._config = config
        self._last_bar_time: Optional[str] = None

    def check(self, bars_by_tf: dict[str, list[dict]]) -> Optional[Signal]:
        m1 = bars_by_tf.get("M1", [])
        d1 = bars_by_tf.get("D1", [])
        if len(m1) < 260 or len(d1) < 10:
            return None

        # Yeni bar kontrolü — Multi100/Micro-S ile aynı pattern
        current_bar_time = m1[-1]["time"]
        if self._last_bar_time is None:
            # warm-up
            self._last_bar_time = current_bar_time
            return None
        if self._last_bar_time == current_bar_time:
            return None
        self._last_bar_time = current_bar_time

        # Indikatörleri hesapla (tüm bar listesi üzerinde — fractal look-ahead-safe)
        try:
            df = add_m1_indicators(pd.DataFrame(m1))
        except Exception:
            return None

        # Setup detection: SON KAPANAN bar = df.iloc[-2] (df.iloc[-1] güncel oluşan)
        if len(df) < 260:
            return None
        i = len(df) - 2
        closed_bar = df.iloc[i]

        # HTF levels — şimdiki bar zamanına göre
        try:
            htf_levels = build_htf_levels(d1, closed_bar["time"], max_age_days=10)
        except Exception:
            htf_levels = []

        try:
            triggered = detect_all(df, i, htf_levels)
        except Exception:
            return None
        if not triggered:
            return None

        composite = "+".join(triggered)

        # ATR ve range_z değerleri (filter'lar için)
        def _num(v):
            try:
                f = float(v)
                return None if pd.isna(f) else f
            except Exception:
                return None

        atr5 = _num(closed_bar.get("atr5"))
        atr20 = _num(closed_bar.get("atr20"))
        atr50 = _num(closed_bar.get("atr50"))
        rngz = _num(closed_bar.get("range_z50"))
        spread_pts = int(closed_bar.get("spread", 0) or 0)

        bar_dict = {
            "time":  closed_bar["time"],
            "open":  float(closed_bar["open"]),
            "high":  float(closed_bar["high"]),
            "low":   float(closed_bar["low"]),
            "close": float(closed_bar["close"]),
        }

        try:
            ok = pass_all_filters(
                bar_dict, triggered, composite,
                atr5, atr20, atr50, rngz, spread_pts, self._config,
            )
        except Exception:
            return None
        if not ok:
            return None

        # Signal — bar i+1'in open'ında SELL gir (engine immediate market order = bar i+1 open)
        return Signal(
            side="sell",
            symbol=self.symbols[0],
            lot=self.lot,
            magic=self.magic,
            sl_usd=self.sl_usd,
            comment=f"GS_{composite}",
            trail_activate_usd=self.trail_activate_usd,
            avg_threshold_usd=self.avg_threshold_usd,
            avg_lot=self.avg_lot,
        )
