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

    def list_gold_symbols(self) -> list[str]:
        """Broker'daki altın sembollerini bul (GOLD/XAU içerenler)."""
        if mt5 is None or not self._connected:
            return []
        symbols = mt5.symbols_get()
        if symbols is None:
            return []
        out: list[str] = []
        for s in symbols:
            name = s.name.upper()
            if "GOLD" in name or "XAU" in name:
                out.append(s.name)
        # Yaygın isimleri başa al
        priority = ["GOLD#", "XAUUSD", "GOLD", "XAUUSD.r", "XAUUSDm", "GOLDm#"]
        ordered = [p for p in priority if p in out]
        ordered += [s for s in out if s not in priority]
        return ordered
