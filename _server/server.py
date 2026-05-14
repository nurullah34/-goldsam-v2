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
from pydantic import BaseModel

import db
from bar_provider import account_info, is_connected
from config import API_HOST, API_PORT
from engine import Engine


ADMIN_TOKEN = os.environ.get("GOLDSAM_ADMIN_TOKEN", "")
if not ADMIN_TOKEN:
    ADMIN_TOKEN = secrets.token_urlsafe(24)
    # Disk'e yaz (ilk açılışta üret + persistent)
    from config import DATA_DIR
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    token_path = DATA_DIR / "admin_token.txt"
    if token_path.exists():
        ADMIN_TOKEN = token_path.read_text(encoding="utf-8").strip()
    else:
        token_path.write_text(ADMIN_TOKEN, encoding="utf-8")


# ── Engine instance (global) ───────────────────────────────────
engine = Engine(log=print)


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    print(f"GoldSam Server başlatıldı")
    print(f"Admin token: {ADMIN_TOKEN}")
    engine.start()
    yield
    engine.stop()
    print("GoldSam Server kapandı")


app = FastAPI(
    title="GoldSam V2 Strategy Server",
    version="1.0.0",
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
    expires_days: Optional[int] = 365


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
        "version": "1.0.0",
        "status": "running",
    }


@app.get("/public/status")
def public_status():
    return {
        "engine": engine.status,
        "mt5": account_info() if is_connected() else None,
    }


@app.get("/public/signals/recent")
def public_signals_recent(limit: int = Query(50, ge=1, le=200)):
    """Site dashboard için son sinyaller (anonim)."""
    return {"signals": db.recent_signals(limit=limit)}


# ───── Agent (Bot) endpoints ─────────────────────────────────

@app.post("/v1/heartbeat")
def heartbeat(payload: HeartbeatIn, x_agent_token: str = Header(...)):
    lic = require_agent(x_agent_token)
    ok, msg = db.license_valid(x_agent_token, payload.mt5_login)
    if not ok:
        raise HTTPException(status_code=403, detail=msg)
    db.heartbeat_license(x_agent_token)
    return {"ok": True, "ts": datetime.utcnow().isoformat(timespec="seconds")}


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
    new_token = "gs_" + secrets.token_urlsafe(24)
    lic_id = db.add_license(
        agent_token=new_token,
        mt5_login=payload.mt5_login,
        mt5_server=payload.mt5_server or "",
        customer_name=payload.customer_name or "",
        expires_days=payload.expires_days,
    )
    return {
        "ok": True,
        "license_id": lic_id,
        "agent_token": new_token,
        "mt5_login": payload.mt5_login,
        "customer_name": payload.customer_name,
        "expires_days": payload.expires_days,
    }


@app.get("/admin/licenses")
def admin_licenses(x_admin_token: str = Header(...)):
    require_admin(x_admin_token)
    return {"licenses": db.list_licenses()}


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
