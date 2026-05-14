"""VPS strateji sunucusu HTTP client.

Bot artık lokal strateji çalıştırmıyor — sinyaller VPS'teki engine'den
gelir. Bu modül:
  - login(license_key, mt5_login, device_id, device_name) → agent_token
  - poll_signals(since_id) → list of Signal
  - heartbeat(mt5_login, equity, ...)
  - trade_report(ticket, status, pnl, ...)

Network hataları sessiz/loglu — UI'ı kilitlemez.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Callable, Optional

from core.types import Signal


# VPS sunucu adresi — bot doğrudan VPS'e gider (mixed content yok, exe çalışıyor)
DEFAULT_SERVER_URL = "http://185.185.83.48:8000"

# HTTP timeout (saniye)
TIMEOUT_LOGIN = 15
TIMEOUT_NORMAL = 10
TIMEOUT_HEARTBEAT = 8


def _post(url: str, body: dict, headers: Optional[dict] = None,
          timeout: float = TIMEOUT_NORMAL) -> tuple[int, dict]:
    """POST JSON → (status_code, response_dict).

    Network hatası → (0, {"error": str(e)})
    """
    data = json.dumps(body).encode("utf-8")
    hdrs = {"Content-Type": "application/json"}
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(url, data=data, headers=hdrs, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        try:
            err_body = json.loads(e.read().decode("utf-8"))
        except Exception:
            err_body = {"detail": str(e)}
        return e.code, err_body
    except urllib.error.URLError as e:
        return 0, {"error": f"Sunucuya ulaşılamıyor: {e.reason}"}
    except Exception as e:
        return 0, {"error": str(e)}


def _get(url: str, headers: Optional[dict] = None,
         timeout: float = TIMEOUT_NORMAL) -> tuple[int, dict]:
    req = urllib.request.Request(url, headers=headers or {}, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        try:
            err_body = json.loads(e.read().decode("utf-8"))
        except Exception:
            err_body = {"detail": str(e)}
        return e.code, err_body
    except urllib.error.URLError as e:
        return 0, {"error": f"Sunucuya ulaşılamıyor: {e.reason}"}
    except Exception as e:
        return 0, {"error": str(e)}


class KriptolyClient:
    """VPS strateji sunucusu için HTTP client."""

    def __init__(self, server_url: str = DEFAULT_SERVER_URL,
                 log: Optional[Callable[[str], None]] = None) -> None:
        self.server_url = server_url.rstrip("/")
        self.log = log or (lambda m: None)
        # Yan durum
        self._agent_token: Optional[str] = None
        self._mt5_login: Optional[int] = None
        self._last_signal_id: int = 0

    # ───── Auth ────────────────────────────────────────────────

    def set_credentials(self, agent_token: str, mt5_login: int) -> None:
        self._agent_token = agent_token
        self._mt5_login = int(mt5_login)

    def has_credentials(self) -> bool:
        return bool(self._agent_token and self._mt5_login)

    def login(self, license_key: str, mt5_login: int,
              device_id: str, device_name: str,
              customer_email: str = "") -> tuple[bool, str, dict]:
        """POST /v1/login → agent_token + meta.

        Email opsiyonel — verilirse server tarafında lisans kaydındaki
        email ile eşleşmek zorunda. Boş bırakılırsa eski davranış (sadece
        kod + MT5 hesap).

        Dönen: (success, message, body)
        """
        status, body = _post(
            f"{self.server_url}/v1/login",
            {
                "license_key":    license_key.strip().upper(),
                "mt5_login":      int(mt5_login),
                "device_id":      device_id,
                "device_name":    device_name or "",
                "customer_email": (customer_email or "").strip(),
            },
            timeout=TIMEOUT_LOGIN,
        )
        if status == 0:
            return False, body.get("error", "Sunucuya ulaşılamadı"), {}
        if status != 200 or not body.get("ok"):
            return False, body.get("detail") or body.get("msg") or "Lisans reddedildi", body

        token = body.get("agent_token", "")
        if not token:
            return False, "Sunucudan boş token döndü", body
        self.set_credentials(token, mt5_login)
        return True, body.get("msg", "Login başarılı"), body

    # ───── Heartbeat ───────────────────────────────────────────

    def heartbeat(self, mt5_server: str, open_positions: int,
                  balance: float, equity: float) -> tuple[bool, dict]:
        """POST /v1/heartbeat — bot canlılık + durum bildirir."""
        if not self.has_credentials():
            return False, {"error": "Token yok"}
        status, body = _post(
            f"{self.server_url}/v1/heartbeat",
            {
                "mt5_login":       int(self._mt5_login),
                "mt5_server":      mt5_server or "",
                "open_positions":  int(open_positions),
                "account_balance": float(balance),
                "account_equity":  float(equity),
            },
            headers={"X-Agent-Token": self._agent_token},
            timeout=TIMEOUT_HEARTBEAT,
        )
        return (status == 200 and body.get("ok") == True), body

    # ───── Signal Polling ──────────────────────────────────────

    def poll_signals(self) -> list[dict]:
        """GET /v1/signals/pending — yeni sinyalleri çek.

        Dönen: list of raw signal dicts (server format):
          {id, strategy, side, symbol, lot, magic, sl_usd, comment,
           trail_activate_usd, created_at, picked_at}
        """
        if not self.has_credentials():
            return []
        url = (
            f"{self.server_url}/v1/signals/pending"
            f"?since_id={self._last_signal_id}&limit=50"
            f"&mt5_login={self._mt5_login}"
        )
        status, body = _get(
            url,
            headers={"X-Agent-Token": self._agent_token},
            timeout=TIMEOUT_NORMAL,
        )
        if status != 200:
            # 403 → token süresi/lisans pasif (caller hallesin)
            if status in (401, 403):
                self.log(f"Lisans reddedildi: {body.get('detail', '')}")
            return []
        sigs = body.get("signals", []) or []
        # since_id'yi en yüksek ID ile güncelle
        if sigs:
            self._last_signal_id = max(int(s.get("id", 0)) for s in sigs)
        return sigs

    # ───── Trade Report ────────────────────────────────────────

    def trade_report(self, **fields) -> bool:
        """POST /v1/trade_report — emir sonucu (opsiyonel, fire-and-forget)."""
        if not self.has_credentials():
            return False
        status, _ = _post(
            f"{self.server_url}/v1/trade_report",
            fields,
            headers={"X-Agent-Token": self._agent_token},
            timeout=TIMEOUT_NORMAL,
        )
        return status == 200


def signal_from_server(raw: dict, lot_override: float, sl_override: float,
                       trail_override: float) -> Signal:
    """Server'dan gelen sinyal dict'i + UI kart ayarları → Signal.

    Server lot/sl_usd'yi 0 placeholder olarak gönderir; bot kartların
    UI değerlerini koyar.
    """
    return Signal(
        side=raw["side"],
        symbol=raw["symbol"],
        lot=float(lot_override),
        magic=int(raw["magic"]),
        sl_usd=float(sl_override),
        comment=raw.get("comment", "")[:31],
        trail_activate_usd=float(trail_override),
        server_signal_id=int(raw.get("id", 0)),
        strategy_name=raw.get("strategy", ""),
    )
