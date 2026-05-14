"""Çekirdek veri tipleri — strategies/'den bağımsız.

Bot v2.x sonrası lokal strateji çalıştırmıyor; sinyaller VPS sunucusundan
gelir. Ama trade_executor / position_monitor / lifecycle hâlâ ``Signal``
dataclass'ını kullanıyor, o yüzden burada tutuyoruz.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class Signal:
    """Bir işlem niyeti (kim ürettiyse — lokal veya bulut)."""
    side: str                 # "buy" | "sell"
    symbol: str
    lot: float
    magic: int
    sl_usd: float
    comment: str = ""
    trail_activate_usd: float = 1.0
    # Kayıpta yeni işlem (averajlama) — opsiyonel
    avg_threshold_usd: Optional[float] = None
    avg_lot: Optional[float] = None
    # Bulut sinyallerinde — server'daki SQLite ID (idempotency için)
    server_signal_id: Optional[int] = None
    strategy_name: str = ""    # "DENGELI_8T_LONG", "MULTI100_M30", vs.
