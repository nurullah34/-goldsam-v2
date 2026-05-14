"""GENIS — LSVC-MTF-BELock (Goldbuybuy spec).

Spec: Goldbuybuy/STRATEGY_SPEC.md
  Long-only XAU/USD, M1 sinyal + M5 trend onayı, BE+$1 lock trail.
  Backtest 45g: 500 trade, %97.40 WR, +$1092.

Entry koşulları (hepsi M1 bar kapanışında):
  1) M5 close[0] > M5 close[10]              — M5 trend yukarı
  2) M1 close > M1 open                       — bullish bar
  3) M1 close > prev M1 high                  — higher high break
  4) M1 volume > SMA(volume, 20) * 1.2        — hacim teyidi
  5) UTC 7 <= hour < 20                       — session filtresi
  6) Cooldown: son loss'tan 3 M1 bar geçmiş  — whipsaw koruması
  7) Açık pozisyon yok                        — engine sağlıyor

Magic: 20270300 (tek magic, BUY-only)

Trail: $1 activate + $0.50 step (bot'un mevcut lifecycle'ı — spec'teki
$0.50 lock + $0.50 trail eşit, $0.01 step yerine $0.50 kullanılıyor;
yakın yaklaşıklık).
"""
from __future__ import annotations

import time as _time
from datetime import datetime
from typing import Optional

try:
    import MetaTrader5 as mt5
except ImportError:
    mt5 = None

from strategies.base import Signal, Strategy


MAGIC = 20270300

# Spec UTC 07-20. XM Global GMT+3 (EEST) — broker hour offset.
# Bar timestamp'imiz broker server time olduğu için broker hour kullanıyoruz.
BROKER_GMT_OFFSET = 3
SESSION_START_BROKER = 7 + BROKER_GMT_OFFSET   # 10
SESSION_END_BROKER = 20 + BROKER_GMT_OFFSET    # 23

COOLDOWN_SECONDS = 3 * 60   # 3 M1 bar = 3 dakika


class GenisStrategy(Strategy):
    """LSVC-MTF-BELock — XAU/USD BUY-only."""

    timeframes = ["M1", "M5"]

    def __init__(self, symbol: str = "GOLD#") -> None:
        self.symbols = [symbol]
        self.key = "genis"
        self.display = "GENIS"
        self.magic = MAGIC
        self._last_bar_time: Optional[str] = None

    def check(self, bars_by_tf: dict[str, list[dict]]) -> Optional[Signal]:
        m1 = bars_by_tf.get("M1", [])
        m5 = bars_by_tf.get("M5", [])
        if len(m1) < 25 or len(m5) < 12:
            return None

        # YENİ BAR KONTROLÜ — M1 üzerinden
        current_bar_time = m1[-1]["time"]
        if self._last_bar_time is None:
            self._last_bar_time = current_bar_time
            return None
        if self._last_bar_time == current_bar_time:
            return None
        self._last_bar_time = current_bar_time

        # Sinyal SON KAPANAN bar üzerinde (m1[-2]); m1[-1] yeni oluşan
        if len(m1) < 23:  # 20 vol SMA + buffer
            return None
        bar = m1[-2]
        prev = m1[-3]

        # Cond 1: M5 close[0] > M5 close[10]
        try:
            m5_close_now = float(m5[-1]["close"])
            m5_close_back = float(m5[-11]["close"])
        except (IndexError, KeyError, ValueError):
            return None
        if m5_close_now <= m5_close_back:
            return None

        # Cond 2: M1 bullish bar
        if float(bar["close"]) <= float(bar["open"]):
            return None

        # Cond 3: Higher high break
        if float(bar["close"]) <= float(prev["high"]):
            return None

        # Cond 4: Volume confirmation — SMA(20) bars ÖNCESİ (bar dahil değil)
        recent20 = m1[-22:-2]   # son kapanmış bardan önceki 20 bar
        if len(recent20) < 20:
            return None
        vol_avg = sum(float(b.get("volume", 0) or 0) for b in recent20) / 20.0
        if vol_avg <= 0:
            return None
        if float(bar.get("volume", 0) or 0) <= vol_avg * 1.2:
            return None

        # Cond 5: Session filter (UTC 7-20 → broker GMT+3: 10-23)
        try:
            bar_dt = datetime.fromisoformat(bar["time"])
        except Exception:
            return None
        if not (SESSION_START_BROKER <= bar_dt.hour < SESSION_END_BROKER):
            return None

        # Cond 6: Cooldown — son loss'tan 3 dakika
        if self._in_cooldown():
            return None

        # Cond 7: açık pozisyon — engine kontrol ediyor

        return Signal(
            side="buy",
            symbol=self.symbols[0],
            lot=self.lot,
            magic=self.magic,
            sl_usd=self.sl_usd,
            comment="GENIS_LSVC",
            trail_activate_usd=self.trail_activate_usd,
            avg_threshold_usd=self.avg_threshold_usd,
            avg_lot=self.avg_lot,
        )

    def _in_cooldown(self) -> bool:
        """Son COOLDOWN_SECONDS içinde kendi magic'imizle kapanmış bir LOSS varsa True."""
        if mt5 is None:
            return False
        now = int(_time.time())
        try:
            deals = mt5.history_deals_get(now - COOLDOWN_SECONDS - 60, now + 60)
        except Exception:
            return False
        if not deals:
            return False
        for d in deals:
            try:
                if int(getattr(d, "magic", 0) or 0) != self.magic:
                    continue
                if d.entry not in (mt5.DEAL_ENTRY_OUT, mt5.DEAL_ENTRY_INOUT):
                    continue
            except Exception:
                continue
            if float(getattr(d, "profit", 0) or 0) >= 0:
                continue
            # Loss deal
            try:
                t = int(d.time)
            except Exception:
                continue
            if now - t < COOLDOWN_SECONDS:
                return True
        return False
