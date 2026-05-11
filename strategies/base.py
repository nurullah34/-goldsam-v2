from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class Signal:
    """Bir stratejinin ürettiği işlem niyeti."""
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


class Strategy(ABC):
    """Tüm stratejilerin uyduğu sözleşme.

    Bot her döngüde aktif olan stratejinin ``check()`` metodunu çağırır.
    Strateji bir ``Signal`` döndürürse bot işlem açar; ``None`` ise hiçbir
    şey yapmaz.
    """

    # Alt sınıf tarafından override edilir
    key: str = ""               # "dengeli_8t"
    display: str = ""           # "8T"
    timeframes: list[str] = []  # ["M1"] / ["M30","H2","H3","H4"]
    symbols: list[str] = []     # ["GOLD#"]

    # UI'dan beslenen ayarlar
    enabled: bool = False
    lot: float = 0.0
    sl_usd: float = 0.0
    trail_activate_usd: float = 1.0
    avg_threshold_usd: Optional[float] = None
    avg_lot: Optional[float] = None

    def apply_settings(self, *, enabled: bool, lot: float, sl_usd: float,
                       trail_activate_usd: float = 1.0,
                       avg_threshold_usd: Optional[float] = None,
                       avg_lot: Optional[float] = None) -> None:
        self.enabled = enabled
        self.lot = lot
        self.sl_usd = sl_usd
        self.trail_activate_usd = trail_activate_usd
        self.avg_threshold_usd = avg_threshold_usd
        self.avg_lot = avg_lot

    @abstractmethod
    def check(self, bars_by_tf: dict[str, list[dict]]) -> Optional[Signal]:
        """Kombinasyon oluştu mu? Oluştuysa Signal, oluşmadıysa None."""
        ...
