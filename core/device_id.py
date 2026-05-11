"""Cihaz fingerprint — MAC + CPU + Windows MachineGuid → SHA-256.

Bu fingerprint hem hesap kilidinin AES anahtarını türetir, hem de UI'da
"Cihaz: DESKTOP-XXXX" şeklinde gösterilir.
"""
from __future__ import annotations

import base64
import hashlib
import platform
import socket
import sys
import uuid


def _windows_machine_guid() -> str:
    """Windows MachineGuid — registry'den oku."""
    if sys.platform != "win32":
        return ""
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Cryptography",
            0,
            winreg.KEY_READ | winreg.KEY_WOW64_64KEY,
        )
        try:
            value, _ = winreg.QueryValueEx(key, "MachineGuid")
            return str(value)
        finally:
            winreg.CloseKey(key)
    except Exception:
        return ""


def get_device_fingerprint() -> bytes:
    """32-byte SHA-256 hash of (MAC + CPU + MachineGuid).

    Aynı cihazda hep aynı sonucu döner. Cihaz/donanım değişirse değişir.
    """
    parts = [
        str(uuid.getnode()),       # MAC adresi (integer)
        platform.processor() or "unknown_cpu",
        _windows_machine_guid(),   # Windows için sabit
        platform.system(),
    ]
    raw = "|".join(parts).encode("utf-8")
    return hashlib.sha256(raw).digest()


def get_fernet_key() -> bytes:
    """32 byte fingerprint → Fernet için urlsafe-base64 key."""
    return base64.urlsafe_b64encode(get_device_fingerprint())


def get_display_name() -> str:
    """UI'da gösterilecek cihaz adı (hostname)."""
    return socket.gethostname()
