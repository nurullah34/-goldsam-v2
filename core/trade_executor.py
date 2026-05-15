"""Trade executor — Signal alıp gerçek MT5 piyasa emri açar.

SL fiyatı, kullanıcının ``sl_usd`` değerinden lot + tick_value'ye göre
türetilir (backtest_may8_v2.py mantığı):

    usd_per_dollar = (trade_tick_value / trade_tick_size) * lot
    sl_dist_price  = sl_usd / usd_per_dollar

LONG için SL = entry - sl_dist; SHORT için SL = entry + sl_dist.
"""
from __future__ import annotations

from typing import Callable, Optional

try:
    import MetaTrader5 as mt5
except ImportError:
    mt5 = None

from core.types import Signal


class TradeExecutor:
    def __init__(self, log: Callable[[str], None]) -> None:
        self.log = log

    def execute(self, signal: Signal) -> Optional[int]:
        """Emir aç. Başarılıysa ticket numarası, başarısızsa None döner."""
        if mt5 is None:
            self.log("MT5 paketi yok — emir atılamaz.")
            return None

        symbol = signal.symbol
        if not mt5.symbol_select(symbol, True):
            self.log(f"Sembol seçilemedi: {symbol}")
            return None

        si = mt5.symbol_info(symbol)
        tick = mt5.symbol_info_tick(symbol)
        if si is None or tick is None:
            self.log(f"Sembol/tick bilgisi alınamadı: {symbol}")
            return None

        digits = max(int(si.digits), 2)

        # SL hesaplama — eger sl_usd > 0 ise: lot basina $1 fiyat hareketi
        # ile USD karsiligi formul. sl_usd <= 0 ise SL'siz emir (MT5'e
        # sl=0.0 gonderirsek SL set edilmez — kullanici SL'siz islem
        # almak isteyebilir, bu meşru bir secim).
        sl_dist_price = 0.0
        if signal.sl_usd > 0:
            if si.trade_tick_size <= 0:
                self.log("trade_tick_size = 0, SL hesaplanamadı. SL'siz emir gönderiliyor.")
            else:
                usd_per_dollar = (si.trade_tick_value / si.trade_tick_size) * signal.lot
                if usd_per_dollar > 0:
                    sl_dist_price = signal.sl_usd / usd_per_dollar

        if signal.side == "buy":
            price = tick.ask
            sl_price = round(price - sl_dist_price, digits) if sl_dist_price > 0 else 0.0
            order_type = mt5.ORDER_TYPE_BUY
        else:  # "sell"
            price = tick.bid
            sl_price = round(price + sl_dist_price, digits) if sl_dist_price > 0 else 0.0
            order_type = mt5.ORDER_TYPE_SELL

        request = {
            "action":       mt5.TRADE_ACTION_DEAL,
            "symbol":       symbol,
            "volume":       float(signal.lot),
            "type":         order_type,
            "price":        float(price),
            "sl":           float(sl_price),
            "tp":           0.0,
            "magic":        int(signal.magic),
            "comment":      signal.comment[:31],   # MT5 31 char limit
            "type_time":    mt5.ORDER_TIME_GTC,
            "type_filling": self._get_filling(si),
        }

        result = mt5.order_send(request)
        if result is None:
            self.log(f"order_send None döndü — last_error: {mt5.last_error()}")
            return None
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            self.log(
                f"EMİR REDDEDİLDİ ({result.retcode}): {result.comment} "
                f"| req: {signal.side} {signal.lot} @ {price} SL {sl_price}"
            )
            return None

        side_txt = "LONG" if signal.side == "buy" else "SHORT"
        sl_text = f"SL {sl_price:.{digits}f}" if sl_price > 0 else "SL YOK"
        self.log(
            f"✅ EMİR AÇILDI #{result.order} | {side_txt} {signal.lot} lot @ "
            f"{result.price:.{digits}f} | {sl_text} | magic={signal.magic}"
        )
        return int(result.order)

    @staticmethod
    def _get_filling(symbol_info) -> int:
        if mt5 is None:
            return 0
        mode = symbol_info.filling_mode
        if mode & 2:
            return mt5.ORDER_FILLING_IOC
        if mode & 1:
            return mt5.ORDER_FILLING_FOK
        return mt5.ORDER_FILLING_RETURN
