"""GoldSam Server — strateji engine (5sn loop).

Her tick:
  1. VPS MT5'ten barlari çek (M1/M5/M30/H1/H2/H3/H4/D1)
  2. 6 stratejiyi çalıştır
  3. Sinyal varsa DB'ye yaz
"""
from __future__ import annotations

import threading
import time
from datetime import datetime
from typing import Callable

from config import (
    DEFAULT_SL_USD, DEFAULT_TRAIL_ACTIVATE_USD,
    SYMBOL, TICK_INTERVAL_SEC,
)
import db
from bar_provider import fetch_bars, is_connected

# Stratejiler — bot ile aynı import path'leri
from strategies.dengeli_8t import Dengeli8T
from strategies.multi100.strategy import Multi100Strategy
from strategies.micro_sweep.strategy import MicroSweepStrategy
from strategies.goldsell.strategy import GoldSellStrategy
from strategies.genis.strategy import GenisStrategy


# Strateji listesi — server-side fixed config
def build_strategies(symbol: str) -> list:
    strategies = []

    # 8T LONG
    s = Dengeli8T(direction="long", symbol=symbol)
    s.apply_settings(enabled=True, lot=0.02, sl_usd=DEFAULT_SL_USD,
                     trail_activate_usd=DEFAULT_TRAIL_ACTIVATE_USD)
    strategies.append(s)

    # 8T SHORT
    s = Dengeli8T(direction="short", symbol=symbol)
    s.apply_settings(enabled=True, lot=0.02, sl_usd=DEFAULT_SL_USD,
                     trail_activate_usd=DEFAULT_TRAIL_ACTIVATE_USD)
    strategies.append(s)

    # MULTI100 (4 TF)
    for tf in Multi100Strategy.all_timeframes():
        s = Multi100Strategy(timeframe=tf, symbol=symbol)
        s.apply_settings(enabled=True, lot=0.02, sl_usd=DEFAULT_SL_USD,
                         trail_activate_usd=DEFAULT_TRAIL_ACTIVATE_USD)
        strategies.append(s)

    # MICRO-S
    s = MicroSweepStrategy(symbol=symbol)
    s.apply_settings(enabled=True, lot=0.02, sl_usd=DEFAULT_SL_USD,
                     trail_activate_usd=DEFAULT_TRAIL_ACTIVATE_USD)
    strategies.append(s)

    # GOLDS (SELL-only)
    s = GoldSellStrategy(symbol=symbol)
    s.apply_settings(enabled=True, lot=0.02, sl_usd=DEFAULT_SL_USD,
                     trail_activate_usd=DEFAULT_TRAIL_ACTIVATE_USD)
    strategies.append(s)

    # GENIS (BUY-only)
    s = GenisStrategy(symbol=symbol)
    s.apply_settings(enabled=True, lot=0.02, sl_usd=DEFAULT_SL_USD,
                     trail_activate_usd=DEFAULT_TRAIL_ACTIVATE_USD)
    strategies.append(s)

    return strategies


class Engine:
    """5sn tick loop — strateji çalıştır + sinyal yaz."""

    def __init__(self, log: Callable[[str], None] = print) -> None:
        self.log = log
        self.symbol = SYMBOL
        self._running = False
        self._thread: threading.Thread | None = None
        self._strategies: list = []
        self._signal_count = 0
        self._last_tick: datetime | None = None
        self._mt5_ok = False

    @property
    def status(self) -> dict:
        return {
            "running":      self._running,
            "mt5_ok":       self._mt5_ok,
            "strategies":   len(self._strategies),
            "signal_count": self._signal_count,
            "last_tick":    self._last_tick.isoformat(timespec="seconds")
                           if self._last_tick else None,
            "symbol":       self.symbol,
        }

    def start(self) -> None:
        if self._running:
            return
        self._strategies = build_strategies(self.symbol)
        self.log(f"Engine: {len(self._strategies)} strateji yüklendi")
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=10)

    def _loop(self) -> None:
        # İlk tick — warm-up için tüm timeframe'leri çek + her stratejiyi bir kez çağır
        while self._running:
            try:
                self._tick()
            except Exception as e:
                self.log(f"Engine tick HATA: {e}")
            time.sleep(TICK_INTERVAL_SEC)

    def _tick(self) -> None:
        # MT5 bağlı mı?
        if not is_connected():
            self._mt5_ok = False
            return
        self._mt5_ok = True

        # Bar verisini çek (her strateji'nin kullandığı tüm TF'leri toplu çek)
        needed_tfs: set[str] = set()
        for s in self._strategies:
            needed_tfs.update(s.timeframes)

        bars_by_tf: dict[str, list[dict]] = {}
        for tf in needed_tfs:
            count = 7300 if tf == "M1" else 250
            bars_by_tf[tf] = fetch_bars(tf, count)

        # Her stratejiyi çalıştır
        for strat in self._strategies:
            try:
                sig = strat.check(bars_by_tf)
            except Exception as e:
                self.log(f"[{strat.display}] check HATA: {e}")
                continue

            if sig is None:
                continue

            # Magic SET olabilir (MicroSweep) — Signal'in kendi magic'i tek int
            sig_magic = int(sig.magic) if isinstance(sig.magic, int) else 0
            signal_id = db.insert_signal(
                strategy=strat.display,
                side=sig.side,
                symbol=sig.symbol,
                lot=float(sig.lot),
                magic=sig_magic,
                sl_usd=float(sig.sl_usd),
                comment=str(sig.comment),
                trail_activate_usd=float(sig.trail_activate_usd),
            )
            self._signal_count += 1
            side_txt = "LONG" if sig.side == "buy" else "SHORT"
            self.log(
                f"🎯 SİNYAL #{signal_id} → {strat.display} {side_txt} "
                f"@ {sig.symbol} | lot={sig.lot} SL=${sig.sl_usd} magic={sig_magic} "
                f"({sig.comment})"
            )

        self._last_tick = datetime.utcnow()
