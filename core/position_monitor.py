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

import time
from typing import Callable, Iterable, Optional

try:
    import MetaTrader5 as mt5
except ImportError:
    mt5 = None

from core.lifecycle import compute_new_sl


# MT5 retcode'lar: 10018 = TRADE_DISABLED (market kapalı), 10027 = REQUOTE, vs.
# Bunları sessizce yut (spam önlemek için)
SILENT_RETCODES = {10018, 10027, 10004, 10014}


class PositionMonitor:
    def __init__(self, log: Callable[[str], None], symbol: str = "GOLD#") -> None:
        self.log = log
        self.symbol = symbol
        self.trail_activate_usd: float = 1.0
        self.manage_manual_positions: bool = False
        self._known_tickets: set[int] = set()
        self._silent_warned: bool = False  # market kapalı uyarısı spam önleyici
        # Kapanmış ama P/L'i MT5 history'sine henüz düşmemiş ticket'lar için retry
        # {ticket: attempts_left}
        self._pending_closes: dict[int, int] = {}
        self._MAX_PENDING_RETRIES = 6  # ~30 sn (6 × 5 sn tick)

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

        # Kapanan pozisyonları tespit et — P/L ile birlikte logla
        closed = self._known_tickets - live_tickets
        for t in closed:
            pnl = self._fetch_close_profit(t)
            if pnl is None:
                # MT5 deal henüz history'e düşmedi — pending kuyruğuna al, sonra dene
                self._pending_closes[t] = self._MAX_PENDING_RETRIES
            else:
                self._log_close(t, pnl)
        self._known_tickets = live_tickets

        # Pending kapanmaları yeniden dene
        if self._pending_closes:
            resolved: list[int] = []
            for t, left in list(self._pending_closes.items()):
                pnl = self._fetch_close_profit(t)
                if pnl is not None:
                    self._log_close(t, pnl)
                    resolved.append(t)
                else:
                    left -= 1
                    if left <= 0:
                        # 30 sn'de hâlâ deal yok — sessizce kapandı diye logla
                        self.log(f"📤 Pozisyon kapandı #{t}  (P/L history'e düşmedi)")
                        resolved.append(t)
                    else:
                        self._pending_closes[t] = left
            for t in resolved:
                self._pending_closes.pop(t, None)

    def _log_close(self, ticket: int, pnl: float) -> None:
        sign = "+" if pnl >= 0 else ""
        emoji = "💰" if pnl > 0 else ("💸" if pnl < -0.001 else "📤")
        self.log(f"{emoji} Pozisyon kapandı #{ticket}  P/L: {sign}${pnl:.2f}")

    def _fetch_close_profit(self, ticket: int) -> Optional[float]:
        """history_deals_get ile kapanış deal'larını bul, net P/L döndür.

        position_id = ticket eşleşen DEAL_ENTRY_OUT deal'ların profit + komisyon + swap'ı toplanır.
        """
        if mt5 is None:
            return None
        now = int(time.time())
        try:
            deals = mt5.history_deals_get(now - 86400 * 2, now + 60)
        except Exception:
            return None
        if deals is None:
            return None

        total = 0.0
        found = False
        for d in deals:
            if d.position_id == ticket and d.entry in (mt5.DEAL_ENTRY_OUT, mt5.DEAL_ENTRY_INOUT):
                total += float(d.profit or 0) + float(d.commission or 0) + float(d.swap or 0)
                found = True
        return round(total, 2) if found else None

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
            err = r.retcode if r else None
            # Market kapalı / requote gibi spam'leri 1 kez logla
            if err in SILENT_RETCODES:
                if not self._silent_warned:
                    self.log(f"⏸ SL modify atlandı (market kapalı / retcode {err}). Bu uyarı tekrarlanmayacak.")
                    self._silent_warned = True
                return
            self._silent_warned = False
            self.log(f"❌ SL modify HATA #{position.ticket}: retcode={err}")
            return

        self._silent_warned = False

        # Locked $ hesapla
        locked_usd = self._calc_locked_usd(position, new_sl, side)
        side_txt = "L" if side == "buy" else "S"
        if locked_usd is None:
            locked_str = ""
        else:
            sign = "+" if locked_usd >= 0 else ""
            locked_str = f"  ({sign}${locked_usd:.2f} locked)"

        self.log(
            f"🔒 SL #{position.ticket} [{side_txt}] → {new_sl:.2f}  "
            f"(entry {position.price_open:.2f}){locked_str}"
        )

    def _calc_locked_usd(self, position, new_sl: float, side: str) -> Optional[float]:
        """SL'in entry'ye göre lock'ladığı net $ kâr."""
        if mt5 is None:
            return None
        si = mt5.symbol_info(self.symbol)
        if si is None or si.trade_tick_size <= 0:
            return None
        usd_per_dollar = (si.trade_tick_value / si.trade_tick_size) * position.volume
        if usd_per_dollar <= 0:
            return None
        if side == "buy":
            locked_price = new_sl - position.price_open
        else:
            locked_price = position.price_open - new_sl
        return round(locked_price * usd_per_dollar, 2)
