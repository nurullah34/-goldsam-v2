"""Strategy engine — aktif stratejileri sırayla tarayıp Signal toplar.

M5'te sadece sinyali log'a düşürür; M6'da TradeExecutor'a verir.
"""
from __future__ import annotations

from typing import Callable, Optional

try:
    import MetaTrader5 as mt5
except ImportError:
    mt5 = None

from core.bar_provider import fetch_bars
from strategies.base import Signal, Strategy


class StrategyEngine:
    def __init__(self, log: Callable[[str], None]) -> None:
        self.log = log
        self._strategies: list[Strategy] = []
        # M6'da set edilecek: signal → execute(sig)
        self.on_signal: Optional[Callable[[Signal, Strategy], None]] = None
        # M7: kullanıcı UI'dan seçer
        self.symbol: str = "GOLD#"          # concurrent count için
        self.max_concurrent: int = 999      # Sınırsız default
        self._limit_warned: bool = False    # spam log önleme

    def register(self, strategy: Strategy) -> None:
        self._strategies.append(strategy)

    def reset(self) -> None:
        self._strategies.clear()

    def active_magics(self) -> set[int]:
        """Tüm aktif stratejilerin magic numaralarını döndür (PositionMonitor için)."""
        magics: set[int] = set()
        for s in self._strategies:
            if s.enabled:
                magics |= self._strategy_magics(s)
        return magics

    def tick(self) -> None:
        """Her aktif stratejiyi tara, sinyal varsa işle."""
        if mt5 is None:
            return

        for strat in self._strategies:
            if not strat.enabled:
                continue
            if strat.lot <= 0:
                continue

            # Aynı stratejiden açık pozisyon var mı? (default: tek pozisyon)
            if self._has_open_position(strat):
                continue

            # Bar çek (her TF için ayrı)
            bars_by_tf: dict[str, list[dict]] = {}
            for tf in strat.timeframes:
                count = 7300 if tf == "M1" else 250
                bars_by_tf[tf] = fetch_bars(strat.symbols[0], tf, count)
                if not bars_by_tf[tf]:
                    return

            try:
                sig = strat.check(bars_by_tf)
            except Exception as e:
                self.log(f"[{strat.display}] HATA: {e}")
                continue

            if sig is None:
                continue

            # M7: concurrent limit kontrolü — sinyal var ama açık pozisyon limiti dolu mu?
            if self.max_concurrent < 999:
                count = self._concurrent_count()
                if count >= self.max_concurrent:
                    if not self._limit_warned:
                        self.log(
                            f"⛔ {strat.display}: concurrent limit dolu "
                            f"({count}/{self.max_concurrent}) — sinyal atlandı. "
                            f"Açık pozisyonların trailing'i devam ediyor."
                        )
                        self._limit_warned = True
                    continue

            self._limit_warned = False
            self._handle_signal(sig, strat)

    def _has_open_position(self, strat: Strategy) -> bool:
        if mt5 is None:
            return False
        positions = mt5.positions_get(symbol=strat.symbols[0]) or []
        # Strateji magic'leri ile karşılaştır — 8T LONG/SHORT için aynı strat
        # iki yöne de bakar (20270001 ve 20270002 birlikte sayılır).
        strat_magics = self._strategy_magics(strat)
        return any(p.magic in strat_magics for p in positions)

    def _concurrent_count(self) -> int:
        """Bot'un ilgilendiği sembol için tüm açık pozisyon sayısı (manuel + bot)."""
        if mt5 is None:
            return 0
        positions = mt5.positions_get(symbol=self.symbol) or []
        return len(positions)

    def _strategy_magics(self, strat: Strategy) -> set[int]:
        """Bir stratejinin kullandığı magic numaralarını döndür.

        Her strateji kendi 'magic' attribute'unda tek bir numara tutar.
        Eski 8T (LONG + SHORT birlikte) modelinde set döndürülürdü;
        artık her yön ayrı strateji olduğu için tek elemanlı.
        """
        magic = getattr(strat, "magic", None)
        if isinstance(magic, int):
            return {magic}
        if isinstance(magic, (set, list, tuple)):
            return set(magic)
        return set()

    def _handle_signal(self, sig: Signal, strat: Strategy) -> None:
        side_txt = "LONG" if sig.side == "buy" else "SHORT"
        self.log(
            f"🎯 SİNYAL → {strat.display} {side_txt} @ {sig.symbol} "
            f"| lot={sig.lot}  SL=${sig.sl_usd}  magic={sig.magic}"
        )

        if self.on_signal is not None:
            try:
                self.on_signal(sig, strat)
            except Exception as e:
                self.log(f"on_signal HATA: {e}")
