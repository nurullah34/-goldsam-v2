"""Cloud strategy engine — VPS sunucusundan sinyal alıp UI kart ayarlarıyla
işleme dönüştürür.

v1.x'te lokal strategy_engine bar verisini tarayıp lokal stratejilerin
``check(bars)`` metoduna sorardı. v2.x sonrası lokal strateji YOK; sunucu
zaten MT5 demo hesabıyla bar tarayıp sinyal üretiyor, biz sadece çekip
kullanıcının kart ayarlarıyla (lot/SL/trail) emir açıyoruz.

API'yi koruduk: ``engine.reset()``, ``engine.register_card(...)``,
``engine.active_magics()``, ``engine.tick()``, ``engine.on_signal=...``
— agent_worker hâlâ aynı arayüzü kullanır.
"""
from __future__ import annotations

from datetime import datetime
from typing import Callable, Optional

try:
    import MetaTrader5 as mt5
except ImportError:
    mt5 = None

from core.kriptoly_client import KriptolyClient, signal_from_server
from core.magic_map import card_for_magic, label_for_magic
from core.types import Signal


# Her UI kartının ayarları — magic numarasına göre lookup edilir
class _CardSettings:
    __slots__ = ("card_id", "label", "lot", "sl_usd", "trail_activate_usd",
                 "magics")

    def __init__(self, card_id: str, label: str, lot: float, sl_usd: float,
                 trail_activate_usd: float, magics: set[int]) -> None:
        self.card_id = card_id
        self.label = label
        self.lot = float(lot)
        self.sl_usd = float(sl_usd)
        self.trail_activate_usd = float(trail_activate_usd)
        self.magics = set(int(m) for m in magics)


class StrategyEngine:
    """Geri uyumluluk için aynı sınıf adı; içeride cloud poll yapar."""

    def __init__(self, log: Callable[[str], None]) -> None:
        self.log = log
        self._cards: dict[str, _CardSettings] = {}
        self.on_signal: Optional[Callable[[Signal, Optional[object]], None]] = None
        self.symbol: str = "GOLD#"
        self.max_concurrent: int = 999
        self._limit_warned: bool = False
        # Hafta sonu koruması — kullanıcı kasa panelinden açar
        self.weekend_protection: bool = False
        self._weekend_warned: bool = False
        # VPS client (app.py set eder)
        self.client: Optional[KriptolyClient] = None

    # ───── API (eski + yeni) ───────────────────────────────────

    def set_client(self, client: KriptolyClient) -> None:
        self.client = client

    def reset(self) -> None:
        self._cards.clear()
        if self.client is not None:
            # Yeni başlangıçta son sinyalden devam et — eski sinyaller tekrar
            # uygulanmasın. (heartbeat sonrası already-picked olmuştur.)
            pass

    def register_card(self, card_id: str, label: str, magics,
                      lot: float, sl_usd: float,
                      trail_activate_usd: float) -> None:
        """Bir UI kartını magic listesi ile kaydet."""
        if isinstance(magics, int):
            magics_set = {magics}
        else:
            magics_set = set(int(m) for m in magics)
        self._cards[card_id] = _CardSettings(
            card_id=card_id, label=label,
            lot=lot, sl_usd=sl_usd,
            trail_activate_usd=trail_activate_usd,
            magics=magics_set,
        )

    def active_magics(self) -> set[int]:
        magics: set[int] = set()
        for c in self._cards.values():
            magics |= c.magics
        return magics

    # ───── Tick (poll) ─────────────────────────────────────────

    def tick(self) -> None:
        """Sunucudan bekleyen sinyalleri çek, kart ayarlarıyla emir aç."""
        if self.client is None or not self.client.has_credentials():
            return

        if self._is_weekend_blackout():
            if not self._weekend_warned:
                self.log(
                    "🛑 Hafta sonu koruması aktif: Cuma 17:00-23:59 arası "
                    "yeni emir alınmıyor. Açık pozisyonların trailing'i sürer."
                )
                self._weekend_warned = True
            return
        self._weekend_warned = False

        # Bekleyen sinyalleri çek
        try:
            raws = self.client.poll_signals()
        except Exception as e:
            self.log(f"poll_signals hatası: {e}")
            return

        if not raws:
            return

        for raw in raws:
            magic = int(raw.get("magic", 0))
            side = raw.get("side", "")
            card_id = card_for_magic(magic)

            if card_id is None:
                # Tanınmayan magic — server yeni strateji eklemiş olabilir
                self.log(f"⚠ Tanınmayan magic={magic}, atlandı")
                continue

            card = self._cards.get(card_id)
            if card is None:
                # Bu kart kapalı → sinyali atla, ama logla
                self.log(
                    f"↷ {label_for_magic(magic)} sinyali geldi "
                    f"({side.upper()}) ama kart kapalı — atlandı"
                )
                continue

            if card.lot <= 0:
                self.log(f"↷ {card.label}: lot 0, sinyal atlandı")
                continue

            # Aynı magic ile açık pozisyon varsa atla (tek pozisyon kuralı)
            if self._has_open_position(magic):
                continue

            # Concurrent limit
            if self.max_concurrent < 999:
                count = self._concurrent_count()
                if count >= self.max_concurrent:
                    if not self._limit_warned:
                        self.log(
                            f"⛔ Concurrent limit dolu "
                            f"({count}/{self.max_concurrent}) — sinyal atlandı"
                        )
                        self._limit_warned = True
                    continue
            self._limit_warned = False

            # Server lot=0, sl=0, symbol=GOLD# placeholder gönderir;
            # bot kendi UI sembolu (engine.symbol = kullanicinin broker'inda
            # ne varsa: XAUUSD, GOLD, GOLD#, vs.) ve kart ayarlarini kullanir.
            sig = signal_from_server(
                raw,
                lot_override=card.lot,
                sl_override=card.sl_usd,
                trail_override=card.trail_activate_usd,
                symbol_override=self.symbol,
            )

            # Kart adi zaten yon icerebilir (8T LONG / 8T SHORT / GOLDS).
            # Cift LONG/SHORT yazimi onlemek icin sadece kart adinda yoksa side ekle.
            side_txt = "LONG" if side == "buy" else "SHORT"
            label_upper = card.label.upper()
            if side_txt in label_upper:
                header = card.label
            else:
                header = f"{card.label} {side_txt}"
            sl_text = f"SL=${sig.sl_usd}" if sig.sl_usd > 0 else "SL YOK"
            self.log(
                f"🎯 SİNYAL #{raw.get('id', '?')} → {header} "
                f"@ {sig.symbol} | lot={sig.lot} {sl_text} magic={magic}"
            )

            if self.on_signal is not None:
                try:
                    self.on_signal(sig, None)
                except Exception as e:
                    self.log(f"on_signal HATA: {e}")

    # ───── Helpers ─────────────────────────────────────────────

    def _has_open_position(self, magic: int) -> bool:
        if mt5 is None:
            return False
        try:
            positions = mt5.positions_get(symbol=self.symbol) or []
            return any(int(getattr(p, "magic", 0)) == magic for p in positions)
        except Exception:
            return False

    def _concurrent_count(self) -> int:
        """Sadece BOT'un acttigi pozisyonlari sayar (magic filter).

        Bot magic numaralari: 20270001-2 (8T), 20270011-14 (MULTI100),
        20270101-127 (MICRO-S), 20270200 (GOLDS), 20270300 (GENIS).
        Manuel acilan pozisyonlar (magic=0 veya bot disindaki magic'ler)
        SAYILMAZ — kullanici manuel islem acsa bile concurrent limit'e
        dahil edilmez.
        """
        if mt5 is None:
            return 0
        try:
            positions = mt5.positions_get(symbol=self.symbol) or []
            bot_magics = self.active_magics()
            if not bot_magics:
                return 0  # hicbir kart aktif degil
            return sum(
                1 for p in positions
                if int(getattr(p, "magic", 0)) in bot_magics
            )
        except Exception:
            return 0

    def _concurrent_count_RAW(self) -> int:
        """ESKI mantik — manuel + bot toplam (referans icin)."""
        if mt5 is None:
            return 0
        try:
            positions = mt5.positions_get(symbol=self.symbol) or []
            return len(positions)
        except Exception:
            return 0

    def _is_weekend_blackout(self) -> bool:
        if not self.weekend_protection:
            return False
        now = datetime.now()
        if now.weekday() == 4 and 17 <= now.hour < 24:
            return True
        return False
