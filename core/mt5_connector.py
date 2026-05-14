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

        Çoklu MT5 desteği:
        - Lock varsa: kilitli hesabı içeren MT5'i bul, ona bağlan.
        - Lock yoksa (ilk bind): tüm açık MT5'leri tara, GERÇEK hesabı
          DEMO'ya tercih et (trade_mode kontrolü).
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

        # Tüm path'leri dene, account bilgilerini topla
        # (path, account_info_dict, trade_mode)
        candidates: list[tuple[Optional[str], dict, int]] = []

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

            info = {
                "login":    ai.login,
                "server":   ai.server,
                "name":     ai.name,
                "balance":  float(ai.balance),
                "equity":   float(ai.equity),
                "currency": ai.currency,
                "company":  ai.company,
            }
            # trade_mode: 0=REAL, 1=CONTEST, 2=DEMO
            tmode = int(getattr(ai, "trade_mode", 2))
            candidates.append((path, info, tmode))

            # Lock varsa hemen eşleşeni döndür
            if target_login is not None and int(ai.login) == target_login:
                self._account_info = info
                self._connected = True
                self._active_path = path
                self._last_error = ""
                return True

        # Buraya gelirsek ya lock yok ya da kilitli hesap bulunamadı

        # Lock varsa hata mesajı
        if target_login is not None:
            seen = ", ".join(f"#{c[1]['login']}" for c in candidates) or "YOK"
            self._last_error = (
                f"Bot #{target_login} hesabına kilitli. "
                f"Açık MT5'lerde bulunan hesaplar: {seen}. "
                f"Doğru hesabı MT5'te aç ve tekrar dene."
            )
            return False

        # Lock yok — ilk bind. Önce REAL (trade_mode=0), sonra CONTEST, sonra DEMO
        if not candidates:
            self._last_error = (
                "Hiçbir MT5 açık değil veya hesaba giriş yapılmamış. "
                "MT5'i aç, hesaba bağlan, tekrar dene."
            )
            return False

        # Sırala: trade_mode (0=real önce, 2=demo en son), sonra path None önce
        candidates.sort(key=lambda c: (c[2], 0 if c[0] is None else 1))

        # Eğer birden fazla farklı login varsa ve karışıksa kullanıcıyı uyar
        unique_logins = {c[1]["login"] for c in candidates}
        if len(unique_logins) > 1:
            chosen_login = candidates[0][1]["login"]
            other_logins = [c[1]["login"] for c in candidates if c[1]["login"] != chosen_login]
            other_str = ", ".join(f"#{x}" for x in other_logins)
            self._last_error = (
                f"Birden fazla MT5 hesabı bulundu. "
                f"GERÇEK hesap tercih edildi: #{chosen_login}. "
                f"Diğerleri (DEMO): {other_str}."
            )

        # En iyi adayı seç
        path, info, _tmode = candidates[0]
        # Bu path'e tekrar bağlan (önceki shutdown'lar sonrası)
        try:
            mt5.shutdown()
        except Exception:
            pass
        try:
            ok = mt5.initialize(path=path) if path else mt5.initialize()
        except Exception:
            ok = False
        if not ok:
            self._last_error = f"Tercih edilen MT5'e bağlanılamadı: {path or 'default'}"
            return False
        ai = mt5.account_info()
        if ai is None:
            self._last_error = "MT5'e bağlanıldı ama hesap bilgisi okunamadı."
            return False
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
        # Lock yoksa hata mesajını sıfırla (uyarı yerine bilgi olarak göstereceğiz)
        # Ama _last_error'da uyarıyı tut, app.py log'lar
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
