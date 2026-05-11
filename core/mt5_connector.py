from __future__ import annotations

from typing import Optional

try:
    import MetaTrader5 as mt5
except ImportError:
    mt5 = None


class MT5Connector:
    """MT5 terminaline bağlanıp hesap bilgisini okur.

    M2 kapsamında sadece initialize + account_info. AutoTrading otomatik
    açma + bağlantıyı sürdürme (M3+) sonra eklenecek.
    """

    def __init__(self) -> None:
        self._connected: bool = False
        self._account_info: Optional[dict] = None
        self._last_error: str = ""

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def account_info(self) -> Optional[dict]:
        return self._account_info

    @property
    def last_error(self) -> str:
        return self._last_error

    def connect(self) -> bool:
        """MT5'i başlat ve hesap bilgisini oku. Başarı/başarısızlık döndürür."""
        if mt5 is None:
            self._last_error = "MetaTrader5 paketi yüklü değil."
            return False

        if not mt5.initialize():
            err = mt5.last_error()
            self._last_error = f"MT5 başlatılamadı: {err}"
            return False

        ai = mt5.account_info()
        if ai is None:
            mt5.shutdown()
            self._last_error = (
                "MT5 açık ama hesaba giriş yapılmamış. "
                "MT5'e login olun ve tekrar deneyin."
            )
            return False

        self._account_info = {
            "login": ai.login,
            "server": ai.server,
            "name": ai.name,
            "balance": float(ai.balance),
            "equity": float(ai.equity),
            "currency": ai.currency,
            "company": ai.company,
        }
        self._connected = True
        self._last_error = ""
        return True

    def disconnect(self) -> None:
        if mt5 is not None and self._connected:
            mt5.shutdown()
        self._connected = False
        self._account_info = None

    def detect_gold_symbol(self) -> Optional[str]:
        """Broker'daki XAUUSD/GOLD sembolünü otomatik bul.

        Hisse senedi (BarrickGold, Goldman Sachs vs.) filtrelenir —
        sadece SPOT METAL sembolü döner. Yaygın isimleri öncelikli sırada
        dener:  GOLD# → XAUUSD → XAUUSD.r → XAUUSDm → GOLDm# → GOLD ...

        Hiçbiri yoksa, isminde XAU+USD geçen ilk sembolü döner.
        """
        if mt5 is None or not self._connected:
            return None

        symbols = mt5.symbols_get()
        if symbols is None:
            return None
        available = {s.name for s in symbols}

        # Yaygın isimler (XM, IC, Pepperstone, FTMO, Exness, Robo)
        priority = [
            "GOLD#",       # XM Global
            "XAUUSD",      # IC Markets, FTMO, Pepperstone
            "XAUUSD.r",    # raw spread variants
            "XAUUSD.a",
            "XAUUSDm",     # Exness micro
            "GOLDm#",      # XM Micro
            "GOLD",        # bazi brokerler
            "GOLDb",
        ]
        for name in priority:
            if name in available:
                return name

        # Yedek: XAUUSD ile başlayan herhangi bir sembol
        for name in available:
            up = name.upper()
            if up.startswith("XAUUSD"):
                return name

        return None
