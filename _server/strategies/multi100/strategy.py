"""MULTI100 Strategy — bir TF için 8 alt-stratejiyi tarar.

Her timeframe (M30/H2/H3/H4) için ayrı bir Multi100Strategy instance
oluşturulur. Engine her tick'te her instance'a `check()` çağırır.

Sadece **LONG** sinyali üretir (orijinal multi100.py'de sell yok).
"""
from __future__ import annotations

from typing import Optional

import pandas as pd

from strategies.base import Signal, Strategy
from strategies.multi100.indicators import add_indicators
from strategies.multi100.recipes import STRATS


# Magic numarası — her TF için ayrı
MAGIC_MAP = {
    "M30": 20270011,
    "H2":  20270012,
    "H3":  20270013,
    "H4":  20270014,
}


class Multi100Strategy(Strategy):
    """MULTI100 — tek TF için 8 alt-strateji tarayıcısı."""

    @classmethod
    def all_timeframes(cls) -> list[str]:
        return list(MAGIC_MAP.keys())

    def __init__(self, timeframe: str, symbol: str = "GOLD#") -> None:
        if timeframe not in MAGIC_MAP:
            raise ValueError(f"Geçersiz TF: {timeframe}. {list(MAGIC_MAP)}")
        self.timeframe = timeframe
        self.symbols = [symbol]
        self.timeframes = [timeframe]
        self.key = f"multi100_{timeframe.lower()}"
        self.display = f"MULTI100 {timeframe}"
        self.magic = MAGIC_MAP[timeframe]
        self._last_bar_time: Optional[str] = None  # yeni bar kontrolü

    def check(self, bars_by_tf: dict[str, list[dict]]) -> Optional[Signal]:
        bars = bars_by_tf.get(self.timeframe, [])
        if len(bars) < 60:
            return None

        # YENİ BAR KONTROLÜ — bot start anında veya aynı bar üzerinde
        # tekrar tarama yapma. multi100.py orijinalindeki 'new_bar' mantığı:
        #   - İlk çağrı: warm-up (sinyal verme, sadece time kaydet)
        #   - Aynı bar tekrar: skip
        #   - Yeni bar: tara
        current_bar_time = bars[-1]["time"]
        if self._last_bar_time is None:
            # Warm-up — bot ilk çağrıda mevcut barı 'görmüş' say
            self._last_bar_time = current_bar_time
            return None
        if self._last_bar_time == current_bar_time:
            return None  # aynı bar, tekrar tetikleme yok
        self._last_bar_time = current_bar_time

        df = pd.DataFrame(bars)
        try:
            df = add_indicators(df)
        except Exception:
            return None

        i = len(df) - 1
        for sname, sfn in STRATS.items():
            try:
                if sfn(df, i):
                    return Signal(
                        side="buy",
                        symbol=self.symbols[0],
                        lot=self.lot,
                        magic=self.magic,
                        sl_usd=self.sl_usd,
                        comment=f"M100_{self.timeframe}_{sname}",
                        trail_activate_usd=self.trail_activate_usd,
                        avg_threshold_usd=self.avg_threshold_usd,
                        avg_lot=self.avg_lot,
                    )
            except Exception:
                continue
        return None
