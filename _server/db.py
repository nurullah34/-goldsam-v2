"""SQLite — signals + licenses + trade reports."""
from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Any, Optional

from config import DB_PATH, DATA_DIR


_LOCK = threading.Lock()


def init_db() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with _conn() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS signals (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            strategy    TEXT NOT NULL,
            side        TEXT NOT NULL,
            symbol      TEXT NOT NULL,
            lot         REAL NOT NULL,
            magic       INTEGER NOT NULL,
            sl_usd      REAL NOT NULL,
            comment     TEXT,
            trail_activate_usd REAL NOT NULL DEFAULT 1.0,
            created_at  TEXT NOT NULL,
            picked_at   TEXT,        -- bot tarafindan alindi
            consumed_by TEXT          -- agent_token
        );
        CREATE INDEX IF NOT EXISTS idx_signals_created ON signals(created_at);
        CREATE INDEX IF NOT EXISTS idx_signals_picked ON signals(picked_at);

        CREATE TABLE IF NOT EXISTS licenses (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_token     TEXT UNIQUE NOT NULL,
            mt5_login       INTEGER NOT NULL,
            mt5_server      TEXT,
            customer_name   TEXT,
            expires_at      TEXT,
            is_active       INTEGER NOT NULL DEFAULT 1,
            created_at      TEXT NOT NULL,
            last_heartbeat  TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_lic_token ON licenses(agent_token);
        CREATE INDEX IF NOT EXISTS idx_lic_login ON licenses(mt5_login);

        CREATE TABLE IF NOT EXISTS trade_reports (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_token TEXT NOT NULL,
            signal_id   INTEGER,
            ticket      INTEGER,
            symbol      TEXT,
            side        TEXT,
            lot         REAL,
            entry_price REAL,
            exit_price  REAL,
            sl_price    REAL,
            opened_at   TEXT,
            closed_at   TEXT,
            pnl_usd     REAL,
            magic       INTEGER,
            comment     TEXT,
            status      TEXT,
            created_at  TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_tr_token ON trade_reports(agent_token);
        CREATE INDEX IF NOT EXISTS idx_tr_signal ON trade_reports(signal_id);
        """)


@contextmanager
def _conn():
    """Thread-safe SQLite connection."""
    with _LOCK:
        con = sqlite3.connect(str(DB_PATH))
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA journal_mode=WAL")
        try:
            yield con
            con.commit()
        finally:
            con.close()


# ───── Signals ───────────────────────────────────────────────

def insert_signal(strategy: str, side: str, symbol: str, lot: float,
                  magic: int, sl_usd: float, comment: str = "",
                  trail_activate_usd: float = 1.0) -> int:
    now = datetime.utcnow().isoformat(timespec="seconds")
    with _conn() as c:
        cur = c.execute(
            "INSERT INTO signals (strategy, side, symbol, lot, magic, sl_usd, "
            "comment, trail_activate_usd, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (strategy, side, symbol, lot, magic, sl_usd, comment,
             trail_activate_usd, now),
        )
        return int(cur.lastrowid)


def pending_signals(since_id: int = 0, limit: int = 50) -> list[dict]:
    """Bot için bekleyen sinyaller (picked_at IS NULL ve > since_id)."""
    with _conn() as c:
        rows = c.execute(
            "SELECT * FROM signals WHERE picked_at IS NULL AND id > ? "
            "ORDER BY id ASC LIMIT ?",
            (since_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]


def mark_picked(signal_ids: list[int], agent_token: str) -> int:
    if not signal_ids:
        return 0
    now = datetime.utcnow().isoformat(timespec="seconds")
    placeholders = ",".join("?" * len(signal_ids))
    with _conn() as c:
        cur = c.execute(
            f"UPDATE signals SET picked_at=?, consumed_by=? WHERE id IN ({placeholders}) "
            f"AND picked_at IS NULL",
            (now, agent_token, *signal_ids),
        )
        return cur.rowcount


def recent_signals(limit: int = 50, since_iso: Optional[str] = None) -> list[dict]:
    """Site dashboard için son sinyaller (public)."""
    with _conn() as c:
        if since_iso:
            rows = c.execute(
                "SELECT * FROM signals WHERE created_at >= ? "
                "ORDER BY id DESC LIMIT ?",
                (since_iso, limit),
            ).fetchall()
        else:
            rows = c.execute(
                "SELECT * FROM signals ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]


def cleanup_old_signals(days: int = 30) -> int:
    """30 gün önceki sinyalleri sil."""
    cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat(timespec="seconds")
    with _conn() as c:
        cur = c.execute("DELETE FROM signals WHERE created_at < ?", (cutoff,))
        return cur.rowcount


# ───── Licenses ──────────────────────────────────────────────

def add_license(agent_token: str, mt5_login: int, mt5_server: str = "",
                customer_name: str = "", expires_days: Optional[int] = None) -> int:
    now = datetime.utcnow().isoformat(timespec="seconds")
    exp = None
    if expires_days:
        exp = (datetime.utcnow() + timedelta(days=expires_days)).isoformat(timespec="seconds")
    with _conn() as c:
        cur = c.execute(
            "INSERT INTO licenses (agent_token, mt5_login, mt5_server, customer_name, "
            "expires_at, is_active, created_at) VALUES (?,?,?,?,?,1,?)",
            (agent_token, mt5_login, mt5_server, customer_name, exp, now),
        )
        return int(cur.lastrowid)


def get_license(agent_token: str) -> Optional[dict]:
    with _conn() as c:
        row = c.execute(
            "SELECT * FROM licenses WHERE agent_token=? AND is_active=1",
            (agent_token,),
        ).fetchone()
        return dict(row) if row else None


def license_valid(agent_token: str, mt5_login: int) -> tuple[bool, str]:
    lic = get_license(agent_token)
    if not lic:
        return False, "Geçersiz veya pasif lisans"
    if lic["mt5_login"] != mt5_login:
        return False, (
            f"Lisans #{lic['mt5_login']} hesabına bağlı, "
            f"gönderilen #{mt5_login}"
        )
    if lic.get("expires_at"):
        try:
            exp = datetime.fromisoformat(lic["expires_at"])
            if datetime.utcnow() > exp:
                return False, f"Lisans süresi doldu ({lic['expires_at']})"
        except Exception:
            pass
    return True, "OK"


def heartbeat_license(agent_token: str) -> None:
    now = datetime.utcnow().isoformat(timespec="seconds")
    with _conn() as c:
        c.execute(
            "UPDATE licenses SET last_heartbeat=? WHERE agent_token=?",
            (now, agent_token),
        )


def list_licenses() -> list[dict]:
    with _conn() as c:
        rows = c.execute("SELECT * FROM licenses ORDER BY id DESC").fetchall()
        return [dict(r) for r in rows]


# ───── Trade Reports ─────────────────────────────────────────

def save_trade_report(agent_token: str, payload: dict) -> int:
    now = datetime.utcnow().isoformat(timespec="seconds")
    with _conn() as c:
        cur = c.execute(
            "INSERT INTO trade_reports (agent_token, signal_id, ticket, symbol, "
            "side, lot, entry_price, exit_price, sl_price, opened_at, closed_at, "
            "pnl_usd, magic, comment, status, created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                agent_token,
                payload.get("signal_id"),
                payload.get("ticket"),
                payload.get("symbol"),
                payload.get("side"),
                payload.get("lot"),
                payload.get("entry_price"),
                payload.get("exit_price"),
                payload.get("sl_price"),
                payload.get("opened_at"),
                payload.get("closed_at"),
                payload.get("pnl_usd"),
                payload.get("magic"),
                payload.get("comment"),
                payload.get("status"),
                now,
            ),
        )
        return int(cur.lastrowid)


def trade_reports(limit: int = 100) -> list[dict]:
    with _conn() as c:
        rows = c.execute(
            "SELECT * FROM trade_reports ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]
