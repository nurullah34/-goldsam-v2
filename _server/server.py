"""GoldSam Server — FastAPI uygulaması.

Endpoint'ler:
  POST /v1/heartbeat              — bot durum bildirir
  GET  /v1/signals/pending        — bot yeni sinyalleri çeker
  POST /v1/trade_report           — bot trade sonucunu raporlar
  GET  /v1/license/check          — lisans doğrula
  GET  /public/signals/recent     — site dashboard için (anonim)
  GET  /public/status             — sistem durumu
  POST /admin/license/add         — yeni müşteri ekle (token korumalı)
  POST /admin/engine/start|stop   — engine kontrol
"""
from __future__ import annotations

import os
import secrets
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pathlib import Path
from pydantic import BaseModel

import db
from bar_provider import account_info, is_connected
from config import API_HOST, API_PORT
from engine import Engine


ADMIN_TOKEN = os.environ.get("GOLDSAM_ADMIN_TOKEN", "")
if not ADMIN_TOKEN:
    # Disk'e bak — varsa eski token'i kullan, YOKSA yeni uret + kaydet.
    # Eski mantikta her acilista yeni secrets.token_urlsafe() uretiliyordu;
    # eger DATA_DIR cwd-relative yanlis yerde olsaydi (config bug) yeni
    # token'i oraya yazip eskiyi okumuyordu. Su an DATA_DIR absolute (config.py).
    from config import DATA_DIR
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    token_path = DATA_DIR / "admin_token.txt"
    if token_path.exists():
        ADMIN_TOKEN = token_path.read_text(encoding="utf-8").strip()
    if not ADMIN_TOKEN:  # dosya yoktu veya bostu
        ADMIN_TOKEN = secrets.token_urlsafe(24)
        token_path.write_text(ADMIN_TOKEN, encoding="utf-8")


# ── Engine instance (global) ───────────────────────────────────
engine = Engine(log=print)


def _watchdog_thread() -> None:
    """Dahili saglik kontrol thread'i — AGRESIF mod (max ~25 sn downtime):
    1. Her 10 sn MT5 check (5 sn timeout)
    2. 2 ardisik fail -> os._exit(1) -> BASLAT.bat goto LOOP restart
    3. Engine 60sn'den uzun cevapsizsa: exit

    Eski ayar 60sn cycle + 3 fail (max 3 dk) cok uzundu, kullanici 10sn
    istedi. Yeni ayar: ~25 sn worst case downtime.
    """
    import threading, time, os as _os
    from datetime import datetime as _dt

    CHECK_INTERVAL = 10   # sn
    MT5_TIMEOUT = 5       # sn (her check icin)
    FAIL_THRESHOLD = 2    # 2 ardisik fail -> restart
    ENGINE_STALE_SEC = 60 # 1 dk tick yoksa restart

    def _check_mt5_timeout(timeout=MT5_TIMEOUT):
        """MT5 cagrisini ayri thread'de calistir, timeout uygula."""
        finished = threading.Event()
        ok_box = [False]

        def _call():
            try:
                ti = bar_provider.is_connected()
                ok_box[0] = bool(ti)
            except Exception:
                ok_box[0] = False
            finally:
                finished.set()

        t = threading.Thread(target=_call, daemon=True)
        t.start()
        if not finished.wait(timeout=timeout):
            return False  # timeout
        return ok_box[0]

    consecutive_fail = 0
    while True:
        try:
            time.sleep(CHECK_INTERVAL)

            # 1) MT5 check
            mt5_ok = _check_mt5_timeout()
            if not mt5_ok:
                consecutive_fail += 1
                print(f"[WATCHDOG] MT5 cevap vermiyor ({consecutive_fail}/{FAIL_THRESHOLD})")
                if consecutive_fail >= FAIL_THRESHOLD:
                    print(f"[WATCHDOG] {FAIL_THRESHOLD}+ MT5 hata - server RESTART")
                    _os._exit(1)
            else:
                if consecutive_fail > 0:
                    print(f"[WATCHDOG] MT5 normalize oldu")
                consecutive_fail = 0

            # 2) Engine staleness check
            last = getattr(engine, "last_tick_at", None)
            if last:
                try:
                    last_dt = _dt.fromisoformat(last) if isinstance(last, str) else last
                    age_sec = (_dt.utcnow() - last_dt).total_seconds()
                    if age_sec > ENGINE_STALE_SEC:
                        print(f"[WATCHDOG] Engine tick {age_sec:.0f}sn cevapsiz - RESTART")
                        _os._exit(2)
                except Exception:
                    pass
        except Exception as e:
            print(f"[WATCHDOG] hata: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    print(f"GoldSam Server başlatıldı")
    print(f"Admin token: {ADMIN_TOKEN}")
    engine.start()
    # Watchdog thread'i baslat (daemon - process exit'inde otomatik kapanir)
    import threading
    wd = threading.Thread(target=_watchdog_thread, daemon=True, name="watchdog")
    wd.start()
    print("[WATCHDOG] Saglik kontrol thread'i aktif (60sn aralikla)")
    yield
    engine.stop()
    print("GoldSam Server kapandı")


app = FastAPI(
    title="GoldSam V2 Strategy Server",
    version="1.1.7",
    lifespan=lifespan,
)

# CORS — kriptoly.com'dan da çağrılabilsin
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ───── Models ────────────────────────────────────────────────

class HeartbeatIn(BaseModel):
    mt5_login: int
    mt5_server: Optional[str] = None
    open_positions: int = 0
    account_balance: float = 0.0
    account_equity: float = 0.0


class TradeReportIn(BaseModel):
    signal_id: Optional[int] = None
    ticket: Optional[int] = None
    symbol: Optional[str] = None
    side: Optional[str] = None
    lot: Optional[float] = None
    entry_price: Optional[float] = None
    exit_price: Optional[float] = None
    sl_price: Optional[float] = None
    opened_at: Optional[str] = None
    closed_at: Optional[str] = None
    pnl_usd: Optional[float] = None
    magic: Optional[int] = None
    comment: Optional[str] = None
    status: Optional[str] = None  # "opened", "closed", "rejected"


class LicenseAddIn(BaseModel):
    mt5_login: int
    mt5_server: Optional[str] = ""
    customer_name: Optional[str] = ""
    customer_email: Optional[str] = ""
    expires_days: Optional[int] = 30


class LicenseLoginIn(BaseModel):
    license_key: str
    mt5_login: int
    device_id: str
    device_name: Optional[str] = ""
    customer_email: Optional[str] = ""   # opsiyonel — verirse server'da match'lenir


class LicenseUpdateIn(BaseModel):
    customer_name: Optional[str] = None
    customer_email: Optional[str] = None
    expires_days: Optional[int] = None      # uzatma (mevcuda eklenir)
    is_active: Optional[bool] = None
    reset_device: Optional[bool] = False    # cihaz bind sifirlama


# ───── Auth helpers ──────────────────────────────────────────

def require_agent(x_agent_token: Optional[str] = Header(None)) -> dict:
    if not x_agent_token:
        raise HTTPException(status_code=401, detail="X-Agent-Token header eksik")
    lic = db.get_license(x_agent_token)
    if not lic:
        raise HTTPException(status_code=403, detail="Geçersiz token")
    return lic


def require_admin(x_admin_token: Optional[str] = Header(None)) -> None:
    if not x_admin_token or x_admin_token != ADMIN_TOKEN:
        raise HTTPException(status_code=403, detail="Yetkisiz: admin token yanlış")


# ───── Public ────────────────────────────────────────────────

@app.get("/")
def root():
    return {
        "service": "GoldSam V2 Strategy Server",
        "version": "1.1.7",
        "status": "running",
    }


# Static HTML — V2 Sinyaller dashboard sayfasi (kriptoly menusunde linkleyebilirsin)
@app.get("/v2-signals")
def v2_signals_page():
    html_path = Path(__file__).parent / "static" / "v2_signals.html"
    if not html_path.exists():
        raise HTTPException(status_code=404, detail="v2_signals.html bulunamadi")
    return FileResponse(html_path, media_type="text/html")


@app.get("/public/status")
def public_status():
    return {
        "engine": engine.status,
        "mt5": account_info() if is_connected() else None,
    }


@app.get("/healthz")
def healthz():
    """Stabilite kontrol — uptime + DB + MT5 + engine."""
    try:
        mt5_ok = is_connected()
    except Exception:
        mt5_ok = False
    try:
        from db import list_licenses
        lic_count = len(list_licenses())
        db_ok = True
    except Exception:
        lic_count = 0
        db_ok = False
    return {
        "ok": db_ok and mt5_ok,
        "version": "1.1.7",
        "mt5_connected": mt5_ok,
        "db_ok": db_ok,
        "license_count": lic_count,
        "engine_running": engine.status.get("running", False) if engine else False,
    }


@app.get("/public/signals/recent")
def public_signals_recent(limit: int = Query(50, ge=1, le=200)):
    """Site dashboard için son sinyaller (anonim)."""
    return {"signals": db.recent_signals(limit=limit)}


# ───── Agent (Bot) endpoints ─────────────────────────────────

@app.post("/v1/login")
def license_login(payload: LicenseLoginIn):
    """Bot login — license_key + MT5 hesap + cihaz ID → agent_token döner.
    İlk girişte cihaza bind edilir, sonraki girişlerde aynı cihaz olmalı.
    """
    ok, msg, lic = db.license_login(
        license_key=payload.license_key.strip().upper(),
        mt5_login=payload.mt5_login,
        device_id=payload.device_id,
        device_name=payload.device_name or "",
        customer_email=(payload.customer_email or "").strip(),
    )
    if not ok or lic is None:
        raise HTTPException(status_code=403, detail=msg)
    days_left = db.days_remaining(lic)
    return {
        "ok": True,
        "agent_token":  lic["agent_token"],
        "customer_name": lic.get("customer_name"),
        "mt5_login":    lic["mt5_login"],
        "expires_at":   lic.get("expires_at"),
        "days_remaining": days_left,
        "warn_expiry":  (days_left is not None and days_left <= 7),
        "msg": msg,
    }


@app.post("/v1/heartbeat")
def heartbeat(payload: HeartbeatIn, x_agent_token: str = Header(...)):
    lic = require_agent(x_agent_token)
    ok, msg = db.license_valid(x_agent_token, payload.mt5_login)
    if not ok:
        raise HTTPException(status_code=403, detail=msg)
    db.heartbeat_license(x_agent_token)
    days_left = db.days_remaining(lic)
    return {
        "ok":           True,
        "ts":           datetime.utcnow().isoformat(timespec="seconds"),
        "days_remaining": days_left,
        "warn_expiry":  (days_left is not None and days_left <= 7),
    }


@app.get("/v1/signals/pending")
def signals_pending(
    since_id: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    mt5_login: int = Query(...),
    x_agent_token: str = Header(...),
):
    """Bot bekleyen sinyalleri çeker, mark_picked atılır."""
    lic = require_agent(x_agent_token)
    ok, msg = db.license_valid(x_agent_token, mt5_login)
    if not ok:
        raise HTTPException(status_code=403, detail=msg)

    sigs = db.pending_signals(since_id=since_id, limit=limit)
    if sigs:
        db.mark_picked([s["id"] for s in sigs], x_agent_token)
    return {"signals": sigs, "count": len(sigs)}


@app.post("/v1/trade_report")
def trade_report(payload: TradeReportIn, x_agent_token: str = Header(...)):
    require_agent(x_agent_token)
    rid = db.save_trade_report(x_agent_token, payload.model_dump())
    return {"ok": True, "report_id": rid}


@app.get("/v1/license/check")
def license_check(mt5_login: int = Query(...), x_agent_token: str = Header(...)):
    lic = require_agent(x_agent_token)
    ok, msg = db.license_valid(x_agent_token, mt5_login)
    return {"ok": ok, "msg": msg, "license": lic if ok else None}


# ───── Admin endpoints ───────────────────────────────────────

@app.post("/admin/license/add")
def admin_license_add(payload: LicenseAddIn, x_admin_token: str = Header(...)):
    require_admin(x_admin_token)
    lic = db.add_license(
        mt5_login=payload.mt5_login,
        mt5_server=payload.mt5_server or "",
        customer_name=payload.customer_name or "",
        customer_email=payload.customer_email or "",
        expires_days=payload.expires_days,
    )
    return {"ok": True, **lic}


@app.get("/admin/licenses")
def admin_licenses(x_admin_token: str = Header(...)):
    require_admin(x_admin_token)
    licenses = db.list_licenses()
    for lic in licenses:
        lic["days_remaining"] = db.days_remaining(lic)
    return {"licenses": licenses}


@app.delete("/admin/license/{license_id}")
def admin_license_delete(license_id: int, x_admin_token: str = Header(...)):
    require_admin(x_admin_token)
    ok = db.delete_license(license_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Lisans bulunamadı")
    return {"ok": True}


@app.patch("/admin/license/{license_id}")
def admin_license_update(license_id: int, payload: LicenseUpdateIn,
                          x_admin_token: str = Header(...)):
    require_admin(x_admin_token)
    fields = {}
    if payload.customer_name is not None:
        fields["customer_name"] = payload.customer_name
    if payload.customer_email is not None:
        fields["customer_email"] = payload.customer_email
    if payload.is_active is not None:
        fields["is_active"] = 1 if payload.is_active else 0
    if payload.reset_device:
        fields["device_id"] = None
        fields["device_name"] = None
        fields["bound_at"] = None
    if payload.expires_days is not None and payload.expires_days > 0:
        # Mevcut süreye ekle (yoksa bugünden itibaren)
        existing = db.list_licenses()
        cur = next((l for l in existing if l["id"] == license_id), None)
        if cur:
            from datetime import datetime as _dt, timedelta as _td
            try:
                base = (_dt.fromisoformat(cur["expires_at"])
                        if cur.get("expires_at") else _dt.utcnow())
                if base < _dt.utcnow():
                    base = _dt.utcnow()
            except Exception:
                base = _dt.utcnow()
            fields["expires_at"] = (base + _td(days=payload.expires_days)).isoformat(timespec="seconds")
    ok = db.update_license(license_id, **fields)
    if not ok:
        raise HTTPException(status_code=404, detail="Lisans bulunamadı veya değişiklik yok")
    return {"ok": True}


@app.get("/admin/trade_reports")
def admin_trades(x_admin_token: str = Header(...), limit: int = Query(100, ge=1, le=500)):
    require_admin(x_admin_token)
    return {"reports": db.trade_reports(limit=limit)}


@app.post("/admin/engine/start")
def admin_engine_start(x_admin_token: str = Header(...)):
    require_admin(x_admin_token)
    engine.start()
    return {"ok": True, "status": engine.status}


@app.post("/admin/engine/stop")
def admin_engine_stop(x_admin_token: str = Header(...)):
    require_admin(x_admin_token)
    engine.stop()
    return {"ok": True, "status": engine.status}


@app.get("/admin/cleanup")
def admin_cleanup(days: int = Query(30, ge=1), x_admin_token: str = Header(...)):
    require_admin(x_admin_token)
    deleted = db.cleanup_old_signals(days=days)
    return {"ok": True, "deleted_signals": deleted}


@app.post("/admin/update")
def admin_update(x_admin_token: str = Header(...)):
    """Self-update — GitHub'dan yeni kod çek, restart et. BASLAT.bat loop devralacak."""
    require_admin(x_admin_token)
    import self_update
    result = self_update.perform_update(log_fn=print)
    if result.get("ok"):
        # 2sn sonra exit — response gönder, BASLAT.bat restart eder
        self_update.schedule_exit(delay_sec=2.0)
    return result


@app.get("/admin/version")
def admin_version():
    """Mevcut server versiyonu — kod hash'i (her güncellemede değişir)."""
    import hashlib
    from pathlib import Path
    code_dir = Path(__file__).parent
    hasher = hashlib.sha256()
    for f in sorted(code_dir.rglob("*.py")):
        if "__pycache__" in str(f):
            continue
        try:
            hasher.update(f.read_bytes())
        except Exception:
            pass
    return {
        "code_hash": hasher.hexdigest()[:12],
        "engine_status": engine.status,
    }


# ───── Entry ─────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "server:app",
        host=API_HOST,
        port=API_PORT,
        log_level="info",
        reload=False,
    )
