"""Trailing SL hesaplaması — saf matematik, MT5 çağrısı yok.

Spread'i hesaba katar:
  * LONG: kapanış BID'den, SL BID'in altında olmalı.
  * SHORT: kapanış ASK'tan, SL ASK'ın üstünde olmalı.

BE (break-even) seviyesini doğrudan entry'ye koymayız — spread + güvenlik
buffer'ı kadar kâr tarafına kaydırırız. Aksi halde MT5 SL'i anında
tetikler ve spread kadar zarar yazılır.

Ladder ($0.50 adımlarla kâr kilitleme) trail_activate ulaşıldıktan sonra
çalışır. Tüm hesaplar position.profit (MT5 net P/L) bazlı, dolayısıyla
spread + komisyon zaten içeride.
"""
from __future__ import annotations

from typing import Optional

STEP_USD = 0.50
SAFETY_BUFFER_USD = 0.10   # SL'i tetiklemeyecek küçük marj


def compute_new_sl(
    side: str,
    entry: float,
    bid: float,
    ask: float,
    current_sl: float,
    lot: float,
    tick_value: float,
    tick_size: float,
    digits: int,
    stops_level_points: int,
    profit_usd: float,
    trail_activate_usd: float = 1.0,
) -> Optional[float]:
    """Yeni SL fiyatını hesapla. Mevcut SL'den iyiyse döndür, değilse None.

    Argümanlar
    ----------
    side               : "buy" | "sell"
    entry              : pozisyonun açılış fiyatı (position.price_open)
    bid, ask           : anlık piyasa fiyatları
    current_sl         : mevcut SL fiyatı (0 olabilir)
    lot                : pozisyon hacmi
    tick_value         : symbol_info.trade_tick_value
    tick_size          : symbol_info.trade_tick_size
    digits             : fiyat ondalık basamak sayısı
    stops_level_points : symbol_info.trade_stops_level (broker min mesafe)
    profit_usd         : MT5'in verdiği anlık net P/L (position.profit)
    trail_activate_usd : kullanıcı seçimi ($1-$5)

    Dönüş
    -----
    Yeni SL fiyatı veya None (değişiklik gerekmiyorsa).
    """
    if tick_size <= 0:
        return None
    usd_per_dollar = (tick_value / tick_size) * lot
    if usd_per_dollar <= 0:
        return None

    if profit_usd < trail_activate_usd:
        return None

    # GARANTİ KÂR mantığı (MULTI100 tarzı):
    #   profit $1 ulaştığında  → locked = $1.00  (BE değil, +$1 garantili)
    #   profit $1.5             → locked = $1.50
    #   profit $2.0             → locked = $2.00
    # Yani locked_usd = trail_activate + extra_steps * STEP_USD.
    # Kullanıcı "bir kez $1 gördüm, $1'i kaybetmem" demek istiyor.
    extra_steps = int((profit_usd - trail_activate_usd) / STEP_USD)
    if extra_steps < 0:
        extra_steps = 0
    locked_usd = trail_activate_usd + extra_steps * STEP_USD

    # locked_usd'yi fiyat mesafesine çevir
    locked_price_dist = locked_usd / usd_per_dollar

    digits = max(int(digits), 2)
    # Sadece broker stops_level + minimum 2 tick güvenlik.
    # Spread zaten profit_usd hesabında (MT5 position.profit) içerildiği için
    # min_dist'e EKLEMEYİZ — yoksa SL gereksiz yere geride kalır.
    min_dist = max(stops_level_points * tick_size, tick_size * 2)

    if side == "buy":
        # LONG: SL bid'in altında olmalı. SL = entry + locked_profit.
        new_sl = round(entry + locked_price_dist, digits)
        # KRİTİK: broker stops_level uzaklığını cap olarak KULLANMA — bu, locked
        # profit'i kırpıyor (lock $1 yerine $0.40 olabiliyor). Yeterli mesafe
        # yoksa bu tick'te HİÇ update etme; bid daha çok hareket edince
        # tekrar denenecek.
        if new_sl > round(bid - min_dist, digits):
            return None
        # SL en az entry seviyesinde olmalı (BE veya kâr tarafı)
        if new_sl < entry:
            return None
        if new_sl > current_sl + 1e-9:
            return new_sl
    else:
        # SHORT: SL ask'ın üstünde olmalı. SL = entry - locked_profit.
        new_sl = round(entry - locked_price_dist, digits)
        if new_sl < round(ask + min_dist, digits):
            return None  # broker stops_level müsait değil, sonra dene
        if new_sl > entry:
            return None
        if current_sl <= 0 or new_sl < current_sl - 1e-9:
            return new_sl

    return None
