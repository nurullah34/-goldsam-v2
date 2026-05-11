"""MT5 hesap kilidi — bot bir hesaba bağlanır, başka hesapla çalışmaz.

İlk açılışta MT5'in account_info'sundan login + server alınır, cihaz
fingerprint'inden türetilmiş AES anahtarı ile şifrelenip APPDATA'ya yazılır.

Sonraki açılışlarda dosya decrypt edilir, mevcut MT5 ile karşılaştırılır.
Eşleşmezse bot kapanır. Lock dosyası başka cihaza kopyalansa bile cihaz
fingerprint değiştiği için decrypt patlar (tamper algılanır).
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

from core.device_id import get_fernet_key


APP_DATA_DIR = Path(os.environ.get("APPDATA", str(Path.home()))) / "GOLDSAM_V2"
LOCK_FILE = APP_DATA_DIR / "account.lock"
LOCK_VERSION = 1


def is_bound() -> bool:
    """Lock dosyası var mı?"""
    return LOCK_FILE.exists()


def bind(account_info: dict) -> tuple[bool, str]:
    """İlk açılış — bu MT5 hesabına kilitle.

    Dönen: (success, message)
    """
    APP_DATA_DIR.mkdir(parents=True, exist_ok=True)

    payload = {
        "login":    int(account_info.get("login", 0)),
        "server":   str(account_info.get("server", "")),
        "company":  str(account_info.get("company", "")),
        "bound_at": datetime.now().isoformat(timespec="seconds"),
        "version":  LOCK_VERSION,
    }

    try:
        fernet = Fernet(get_fernet_key())
        encrypted = fernet.encrypt(json.dumps(payload).encode("utf-8"))
        LOCK_FILE.write_bytes(encrypted)
    except Exception as e:
        return False, f"Lock yazılamadı: {e}"

    return True, (
        f"Hesap kilitlendi: #{payload['login']} @ {payload['server']} "
        f"({payload['company']})"
    )


def verify(account_info: dict) -> tuple[bool, str]:
    """Mevcut MT5 hesabı, kilitli hesapla eşleşiyor mu?

    Dönen: (ok, message)
      ok = True  → eşleşti, bot çalışabilir
      ok = False → eşleşmedi (yetkisiz hesap) veya lock bozuk
    """
    if not LOCK_FILE.exists():
        return False, "Lock dosyası yok"

    try:
        fernet = Fernet(get_fernet_key())
        decrypted = fernet.decrypt(LOCK_FILE.read_bytes())
    except InvalidToken:
        return False, (
            "Lock dosyası bu cihaza ait değil veya bozulmuş. "
            "Eğer cihaz/donanım değiştiyseniz lock'u sıfırlamak gerekir."
        )
    except Exception as e:
        return False, f"Lock okuma hatası: {e}"

    try:
        data = json.loads(decrypted)
    except Exception:
        return False, "Lock içeriği geçersiz"

    current_login = int(account_info.get("login", 0))
    current_server = str(account_info.get("server", ""))

    if data.get("login") != current_login:
        return False, (
            f"Bu bot #{data.get('login')} hesabına kilitli, "
            f"mevcut hesap #{current_login}. Yetkisiz hesap."
        )

    if data.get("server") != current_server:
        return False, (
            f"Bu bot '{data.get('server')}' sunucusuna kilitli, "
            f"mevcut sunucu '{current_server}'. Yetkisiz sunucu."
        )

    return True, f"Hesap doğrulandı: #{current_login} @ {current_server}"


def get_locked_info() -> dict | None:
    """Mevcut lock dosyasının içeriğini döndür (decrypt edilebiliyorsa)."""
    if not LOCK_FILE.exists():
        return None
    try:
        fernet = Fernet(get_fernet_key())
        decrypted = fernet.decrypt(LOCK_FILE.read_bytes())
        return json.loads(decrypted)
    except Exception:
        return None


def unbind() -> bool:
    """Lock dosyasını sil — sadece test/debug için."""
    if LOCK_FILE.exists():
        LOCK_FILE.unlink()
        return True
    return False
