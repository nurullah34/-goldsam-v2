from __future__ import annotations

import os
from typing import Optional

try:
    import MetaTrader5 as mt5
except ImportError:
    mt5 = None


def _scan_mt5_paths() -> list[str]:
    """Windows'ta yüklü tüm MT5 instance'larını bul (terminal64.exe arar).

    `Program Files` + `Program Files (x86)` altındaki tüm üst klasörlerde
    `terminal64.exe` var mı diye bakar. Birden fazla MT5 kurulu olduğunda
    (örn. VPS'te master demo + müşteri trade hesabı) hepsini listeler.
    """
    candidates: set[str] = set()
    bases = [
        os.environ.get("ProgramFiles", r"C:\Program Files"),
        os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
    ]
    for base in bases:
        if not base or not os.path.isdir(base):
            continue
        try:
            for d in os.listdir(base):
                full_d = os.path.join(base, d)
                if not os.path.isdir(full_d):
                    continue
                exe = os.path.join(full_d, "terminal64.exe")
                if os.path.isfile(exe):
                    candidates.add(exe)
        except (OSError, PermissionError):
            pass
    return sorted(candidates)


class MT5Connector:
    """MT5 terminaline bağlanıp hesap bilgisini okur.

    Birden fazla MT5 instance varsa (VPS'te master demo + trade hesabı gibi)
    kilitli hesabı (`account.lock`) içeren MT5'i otomatik bulur.
    """

    def __init__(self) -> None:
        self._connected: bool = False
        self._account_info: Optional[dict] = None
        self._last_error: str = ""
        self._active_path: Optional[str] = None  # hangi MT5'e bağlandık

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
        """MT5'i başlat ve hesap bilgisini oku.

        Çoklu MT5 desteği: birden fazla terminal64.exe açıksa, kilitli hesabı
        (account.lock) içeren MT5'i otomatik bulur. Eğer lock yoksa, ilk
        bağlanan MT5'i kullanır (ilk bind için).
        """
        if mt5 is None:
            self._last_error = "MetaTrader5 paketi yüklü değil."
            return False

        # Hedef login (kilitli hesap)
        target_login: Optional[int] = None
        try:
            from core.account_lock import get_locked_info
            locked = get_locked_info()
            if locked and locked.get("login"):
                target_login = int(locked["login"])
        except Exception:
            pass

        # Önce default (no path), sonra scan'den gelen path'ler
        paths_to_try: list[Optional[str]] = [None]
        for p in _scan_mt5_paths():
            if p not in paths_to_try:
                paths_to_try.append(p)

        seen_logins: list[int] = []

        for path in paths_to_try:
            try:
                mt5.shutdown()
            except Exception:
                pass
            try:
                init_ok = mt5.initialize(path=path) if path else mt5.initialize()
            except Exception:
                continue
            if not init_ok:
                continue
            ai = mt5.account_info()
            if ai is None:
                try:
                    mt5.shutdown()
                except Exception:
                    pass
                continue

            seen_logins.append(int(ai.login))

            # Lock varsa, hedef hesaba eşleşmeli; yoksa ilk geçerli MT5 yeter
            if target_login is None or int(ai.login) == target_login:
                self._account_info = {
                    "login":    ai.login,
                    "server":   ai.server,
                    "name":     ai.name,
                    "balance":  float(ai.balance),
                    "equity":   float(ai.equity),
                    "currency": ai.currency,
                    "company":  ai.company,
                }
                self._connected = True
                self._active_path = path
                self._last_error = ""
                return True

        # Hiçbir MT5'te hedef hesap yok
        if target_login is not None:
            found_str = ", ".join(f"#{x}" for x in seen_logins) if seen_logins else "YOK"
            self._last_error = (
                f"Bot #{target_login} hesabına kilitli. "
                f"Açık MT5'lerde bulunan hesaplar: {found_str}. "
                f"Doğru hesabı MT5'te aç ve tekrar dene."
            )
        else:
            self._last_error = (
                "Hiçbir MT5 açık değil veya hesaba giriş yapılmamış. "
                "MT5'i aç, hesaba bağlan, tekrar dene."
            )
        return False

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
