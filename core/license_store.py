"""Lisans tokeni şifreli saklama — cihaz fingerprint AES anahtarı ile.

Bot ilk açılışta kullanıcıdan lisans kodu + MT5 hesap no ister, server'a
POST /v1/login atar, dönen agent_token'ı buraya yazar. Sonraki açılışlarda
agent_token okunur, server'a heartbeat / signals poll'ünde kullanılır.

Lock dosyası başka cihaza kopyalansa cihaz fingerprint farklı olduğu için
decrypt patlar (tamper algılanır) — bot tekrar lisans sorar.
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken

from core.device_id import get_fernet_key


APP_DATA_DIR = Path(os.environ.get("APPDATA", str(Path.home()))) / "GOLDSAM_V2"
LICENSE_FILE = APP_DATA_DIR / "license.dat"
LICENSE_VERSION = 1


def save(agent_token: str, license_key: str, mt5_login: int,
         customer_name: str = "", expires_at: Optional[str] = None,
         days_remaining: Optional[int] = None,
         customer_email: str = "") -> bool:
    """Lisansı şifreleyip diske yaz."""
    APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "agent_token":     agent_token,
        "license_key":     license_key,
        "mt5_login":       int(mt5_login),
        "customer_name":   customer_name or "",
        "customer_email":  customer_email or "",
        "expires_at":      expires_at,
        "days_remaining":  days_remaining,
        "saved_at":        datetime.now().isoformat(timespec="seconds"),
        "version":         LICENSE_VERSION,
    }
    try:
        fernet = Fernet(get_fernet_key())
        encrypted = fernet.encrypt(json.dumps(payload).encode("utf-8"))
        LICENSE_FILE.write_bytes(encrypted)
        return True
    except Exception:
        return False


def load() -> Optional[dict]:
    """Diskteki lisansı oku (decrypt edilemezse None)."""
    if not LICENSE_FILE.exists():
        return None
    try:
        fernet = Fernet(get_fernet_key())
        decrypted = fernet.decrypt(LICENSE_FILE.read_bytes())
        return json.loads(decrypted)
    except (InvalidToken, Exception):
        return None


def clear() -> bool:
    """Lisansı sil (kullanıcı 'çıkış' yapınca veya server reject ederse)."""
    if LICENSE_FILE.exists():
        try:
            LICENSE_FILE.unlink()
            return True
        except OSError:
            return False
    return False


def update_meta(days_remaining: Optional[int] = None,
                expires_at: Optional[str] = None) -> None:
    """Heartbeat sonrası süre bilgisini güncelle (tokeni değiştirmez)."""
    cur = load()
    if not cur:
        return
    if days_remaining is not None:
        cur["days_remaining"] = days_remaining
    if expires_at is not None:
        cur["expires_at"] = expires_at
    try:
        fernet = Fernet(get_fernet_key())
        encrypted = fernet.encrypt(json.dumps(cur).encode("utf-8"))
        LICENSE_FILE.write_bytes(encrypted)
    except Exception:
        pass
