"""Açık pozisyon takibi — periyodik SL güncellemesi (trailing).

Her tick'te:
  1. MT5'ten açık pozisyonları çek
  2. Her pozisyon için lifecycle.compute_new_sl() çağır
  3. Yeni SL eski SL'den iyi ise mt5.order_send(SLTP) ile güncelle
  4. Kapanan ticket'lar için log mesajı bırak

"Bot dışı pozisyonları da yönet" switch'i açıksa magic kontrolü
yapılmadan tüm pozisyonlara trailing uygulanır.
"""
from __future__ import annotations

from typing import Callable, Iterable, Optional

try:
    import MetaTrader5 as mt5
except ImportError:
    mt5 = None

from core.lifecycle import compute_new_sl


class PositionMonitor:
    def __init__(self, log: Callable[[str], None], symbol: str = "GOLD#") -> None:
        self.log = log
        self.symbol = symbol
        self.trail_activate_usd: float = 1.0
        self.manage_manual_positions: bool = False
        self._known_tickets: set[int] = set()

    # ─── Ayar setter'ları ─────────────────────────────────────
    def set_trail_activate(self, usd: float) -> None:
        self.trail_activate_usd = max(0.5, float(usd))

    def set_manage_manual(self, enabled: bool) -> None:
        self.manage_manual_positions = bool(enabled)

    # ─── Tick ─────────────────────────────────────────────────
    def tick(self, bot_magics: Iterable[int]) -> None:
        if mt5 is None:
            return

        bot_magics_set = set(bot_magics)

        positions = mt5.positions_get(symbol=self.symbol)
        if positions is None:
            return
        positions = list(positions)

        si = mt5.symbol_info(self.symbol)
        tick = mt5.symbol_info_tick(self.symbol)
        if si is None or tick is None:
            return

        live_tickets: set[int] = set()
        for p in positions:
            live_tickets.add(p.ticket)

            # Bot'a ait mi yoksa manuel mi?
            is_bot_pos = p.magic in bot_magics_set
            if not is_bot_pos and not self.manage_manual_positions:
                continue

            side = "buy" if p.type == mt5.POSITION_TYPE_BUY else "sell"
            current_sl = float(p.sl or 0)

            new_sl = compute_new_sl(
                side=side,
                entry=float(p.price_open),
                bid=float(tick.bid),
                ask=float(tick.ask),
                current_sl=current_sl,
                lot=float(p.volume),
                tick_value=float(si.trade_tick_value),
                tick_size=float(si.trade_tick_size),
                digits=int(si.digits),
                stops_level_points=int(getattr(si, "trade_stops_level", 0) or 0),
                profit_usd=float(p.profit),
                trail_activate_usd=self.trail_activate_usd,
            )

            if new_sl is None:
                continue

            self._modify_sl(p, new_sl, side)

        # Kapanan pozisyonları tespit et
        closed = self._known_tickets - live_tickets
        for t in closed:
            self.log(f"📤 Pozisyon kapandı #{t}")
        self._known_tickets = live_tickets

    def _modify_sl(self, position, new_sl: float, side: str) -> None:
        if mt5 is None:
            return
        request = {
            "action":   mt5.TRADE_ACTION_SLTP,
            "position": int(position.ticket),
            "symbol":   self.symbol,
            "sl":       float(new_sl),
            "tp":       float(position.tp or 0.0),
        }
        r = mt5.order_send(request)
        if r is None or r.retcode != mt5.TRADE_RETCODE_DONE:
            err = r.retcode if r else mt5.last_error()
            self.log(f"SL modify HATA #{position.ticket}: {err}")
            return

        side_txt = "L" if side == "buy" else "S"
        self.log(
            f"🔒 SL #{position.ticket} [{side_txt}] → {new_sl:.{2}f}  "
            f"(entry {position.price_open:.2f})"
        )
