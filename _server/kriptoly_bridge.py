"""Kriptoly.com köprü — VPS server agent olarak kayıtlı, sürekli heartbeat atar.

Engine her tick'te (5 sn) heartbeat gönderir. Böylece kriptoly admin paneli
VPS-V2-PROD agent'ını "online" olarak gösterir.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from datetime import datetime
from typing import Optional

# Kriptoly bağlantı bilgileri — env vars ile override edilebilir
KRIPTOLY_URL = os.environ.get("KRIPTOLY_URL", "https://kriptoly.com")
AGENT_TOKEN = os.environ.get(
    "KRIPTOLY_AGENT_TOKEN",
    "mt5_GEP_0i9iryTXsW3Qp6V3t05WS3bsjJGfBqmgzdp20aU",  # VPS-V2-PROD
)


def send_heartbeat(
    mt5_login: int,
    mt5_server: str,
    broker_name: str,
    mt5_connected: bool,
    account_balance: float,
    account_equity: float,
    open_positions: int = 0,
    error_message: Optional[str] = None,
) -> bool:
    """Kriptoly'a heartbeat gönder. Başarı/başarısızlık döndürür."""
    if not AGENT_TOKEN:
        return False
    url = f"{KRIPTOLY_URL.rstrip('/')}/api/mt5/heartbeat"
    payload = {
        "mt5_login":       int(mt5_login),
        "mt5_server":      str(mt5_server),
        "broker_name":     str(broker_name),
        "mt5_connected":   bool(mt5_connected),
        "open_positions":  int(open_positions),
        "account_balance": float(account_balance),
        "account_equity":  float(account_equity),
    }
    if error_message:
        payload["error_message"] = str(error_message)

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "X-Agent-Token": AGENT_TOKEN,
            "User-Agent":    "GoldSam-V2-Server/1.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError):
        return False
    except Exception:
        return False
