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


def _migrate_v1_to_v2(c) -> None:
    """Eski licenses tablosuna eksik kolonlari ekle."""
    cols = [r[1] for r in c.execute("PRAGMA table_info(licenses)").fetchall()]
    add = {
        "license_key":     "TEXT",
        "device_id":       "TEXT",
        "device_name":     "TEXT",
        "bound_at":        "TEXT",
        "customer_email":  "TEXT",
    }
    for name, typ in add.items():
        if name not in cols:
            try:
                c.execute(f"ALTER TABLE licenses ADD COLUMN {name} {typ}")
            except Exception:
                pass


def init_db() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with _conn() as c:
        # 1) Tablolari yarat (CREATE TABLE IF NOT EXISTS — eski tabloyu degistirmez)
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
            picked_at   TEXT,
            consumed_by TEXT
        );

        CREATE TABLE IF NOT EXISTS licenses (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            license_key     TEXT UNIQUE,
            agent_token     TEXT UNIQUE NOT NULL,
            mt5_login       INTEGER NOT NULL,
            mt5_server      TEXT,
            customer_name   TEXT,
            expires_at      TEXT,
            is_active       INTEGER NOT NULL DEFAULT 1,
            device_id       TEXT,
            device_name     TEXT,
            bound_at        TEXT,
            created_at      TEXT NOT NULL,
            last_heartbeat  TEXT
        );

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
        """)

        # 2) Migration — eski v1 tablosuna eksik kolonlari ekle (license_key,
        #    device_id, device_name, bound_at, customer_email). Index'lerden ONCE
        #    yapmali, yoksa "no such column: license_key" diye patlar.
        _migrate_v1_to_v2(c)

        # 3) Index'leri yarat — artik kolonlar kesin var
        c.executescript("""
        CREATE INDEX IF NOT EXISTS idx_signals_created ON signals(created_at);
        CREATE INDEX IF NOT EXISTS idx_signals_picked  ON signals(picked_at);
        CREATE INDEX IF NOT EXISTS idx_lic_token       ON licenses(agent_token);
        CREATE INDEX IF NOT EXISTS idx_lic_login       ON licenses(mt5_login);
        CREATE INDEX IF NOT EXISTS idx_lic_key         ON licenses(license_key);
        CREATE INDEX IF NOT EXISTS idx_tr_token        ON trade_reports(agent_token);
        CREATE INDEX IF NOT EXISTS idx_tr_signal       ON trade_reports(signal_id);
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


def pending_signals(since_id: int = 0, limit: int = 50,
                    max_age_sec: int = 300) -> list[dict]:
    """Bot için bekleyen sinyaller.

    DEGISIM (v1.1.10): picked_at filter KALDIRILDI. Her bot kendi
    since_id'sini takip eder, aynı sinyal birden cok bot tarafindan
    alinabilir (VPS master bot + musteri botlari aynı pattern'i alir,
    her biri kendi MT5 hesabinda emir acar).

    max_age_sec: 5 dakikadan eski sinyaller pending degil (bot kapanip
    acilirsa eski sinyaller dirilmesin).
    """
    from datetime import timedelta
    cutoff = (datetime.utcnow() - timedelta(seconds=max_age_sec)).isoformat(timespec="seconds")
    with _conn() as c:
        rows = c.execute(
            "SELECT * FROM signals WHERE id > ? AND created_at > ? "
            "ORDER BY id ASC LIMIT ?",
            (since_id, cutoff, limit),
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

def _gen_license_key() -> str:
    """10-char kullanici-dostu kod: K7M-3P9-X2L (carmasik karakterler dahil)."""
    import secrets
    # I,O,0,1 karistirmayi onlemek icin sadece sade harf/rakam
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    parts = []
    for _ in range(3):
        parts.append("".join(secrets.choice(alphabet) for _ in range(3)))
    return "-".join(parts)  # ornek: K7M-3P9-X2L (11 char with dashes, 9 alphanumeric)


def add_license(mt5_login: int, mt5_server: str = "",
                customer_name: str = "", customer_email: str = "",
                expires_days: Optional[int] = None,
                license_key: Optional[str] = None,
                agent_token: Optional[str] = None) -> dict:
    """Yeni lisans olustur. license_key + agent_token otomatik uretilir."""
    import secrets as _s
    now = datetime.utcnow().isoformat(timespec="seconds")
    exp = None
    if expires_days:
        exp = (datetime.utcnow() + timedelta(days=expires_days)).isoformat(timespec="seconds")
    # Otomatik uretim
    if not license_key:
        # Cakisma kontrolu ile uniqe kod
        for _ in range(10):
            cand = _gen_license_key()
            with _conn() as c:
                row = c.execute("SELECT 1 FROM licenses WHERE license_key=?", (cand,)).fetchone()
                if not row:
                    license_key = cand
                    break
        if not license_key:
            license_key = _gen_license_key()  # fallback
    if not agent_token:
        agent_token = "gs_" + _s.token_urlsafe(24)

    with _conn() as c:
        cur = c.execute(
            "INSERT INTO licenses (license_key, agent_token, mt5_login, mt5_server, "
            "customer_name, customer_email, expires_at, is_active, created_at) "
            "VALUES (?,?,?,?,?,?,?,1,?)",
            (license_key, agent_token, mt5_login, mt5_server,
             customer_name, customer_email, exp, now),
        )
        lic_id = int(cur.lastrowid)
    return {
        "id":            lic_id,
        "license_key":   license_key,
        "agent_token":   agent_token,
        "mt5_login":     mt5_login,
        "mt5_server":    mt5_server,
        "customer_name": customer_name,
        "customer_email": customer_email,
        "expires_at":    exp,
    }


def get_license(agent_token: str) -> Optional[dict]:
    with _conn() as c:
        row = c.execute(
            "SELECT * FROM licenses WHERE agent_token=? AND is_active=1",
            (agent_token,),
        ).fetchone()
        return dict(row) if row else None


def get_license_by_key(license_key: str) -> Optional[dict]:
    with _conn() as c:
        row = c.execute(
            "SELECT * FROM licenses WHERE license_key=? AND is_active=1",
            (license_key,),
        ).fetchone()
        return dict(row) if row else None


def bind_device(license_id: int, device_id: str, device_name: str) -> None:
    now = datetime.utcnow().isoformat(timespec="seconds")
    with _conn() as c:
        c.execute(
            "UPDATE licenses SET device_id=?, device_name=?, bound_at=? WHERE id=?",
            (device_id, device_name, now, license_id),
        )


def license_login(license_key: str, mt5_login: int,
                  device_id: str, device_name: str,
                  customer_email: str = "") -> tuple[bool, str, Optional[dict]]:
    """Bot login: license_key + MT5 hesabi + cihaz ID -> agent_token.

    Ilk login'de cihaz bind edilir. Sonraki login'lerde device_id ayniysa OK,
    farkliysa REDDEDIL (1 cihaz kurali).

    Email opsiyonel — verilirse lisans kaydindaki email ile eslesmek zorunda
    (case-insensitive). Bu sayede kullanici "ben kimim" diye email yazip
    sifre yerine lisans kodunu girer; iki adim onay.
    """
    lic = get_license_by_key(license_key)
    if not lic:
        return False, "Gecersiz lisans kodu", None

    if not lic.get("is_active"):
        return False, "Lisans pasif", None

    # MT5 hesap eslesmeli
    if int(lic["mt5_login"]) != int(mt5_login):
        return False, (
            f"Bu lisans #{lic['mt5_login']} MT5 hesabina bagli, "
            f"sen #{mt5_login} ile baglandin"
        ), None

    # Email kontrolu (opsiyonel — sadece her ikisi de doluysa karsilastir)
    if customer_email and lic.get("customer_email"):
        if customer_email.strip().lower() != lic["customer_email"].strip().lower():
            return False, (
                f"E-posta lisans kayda eslemiyor. "
                f"Lisansin sahibi farkli bir e-postaya tanimli."
            ), None

    # Sure kontrolu
    if lic.get("expires_at"):
        try:
            exp = datetime.fromisoformat(lic["expires_at"])
            if datetime.utcnow() > exp:
                return False, f"Lisans suresi dolmus ({lic['expires_at']})", None
        except Exception:
            pass

    # Cihaz bind kontrolu
    bound = lic.get("device_id")
    if bound:
        if bound != device_id:
            return False, (
                f"Lisans baska bir cihaza bagli ({lic.get('device_name', 'bilinmiyor')}). "
                f"Yeni cihazda kullanmak icin admin'den lisans sifirlat."
            ), None
    else:
        # Ilk login - cihaza bind et
        bind_device(int(lic["id"]), device_id, device_name)
        lic["device_id"] = device_id
        lic["device_name"] = device_name

    return True, "Login basarili", lic


def license_valid(agent_token: str, mt5_login: int) -> tuple[bool, str]:
    """Bot sinyal isterken auth check (eski API, agent_token bazli)."""
    lic = get_license(agent_token)
    if not lic:
        return False, "Gecersiz veya pasif lisans"
    if lic["mt5_login"] != mt5_login:
        return False, (
            f"Lisans #{lic['mt5_login']} hesabina bagli, "
            f"gonderilen #{mt5_login}"
        )
    if lic.get("expires_at"):
        try:
            exp = datetime.fromisoformat(lic["expires_at"])
            if datetime.utcnow() > exp:
                return False, f"Lisans suresi doldu ({lic['expires_at']})"
        except Exception:
            pass
    return True, "OK"


def days_remaining(lic: dict) -> Optional[int]:
    """Lisanstan kac gun kaldi (None = sinirsiz)."""
    if not lic.get("expires_at"):
        return None
    try:
        exp = datetime.fromisoformat(lic["expires_at"])
        diff = exp - datetime.utcnow()
        return max(0, diff.days)
    except Exception:
        return None


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


def delete_license(license_id: int) -> bool:
    with _conn() as c:
        cur = c.execute("DELETE FROM licenses WHERE id=?", (license_id,))
        return cur.rowcount > 0


def update_license(license_id: int, **fields) -> bool:
    """Lisans gunceller (extend, deactivate, reset_device, vs.)."""
    allowed = {"customer_name", "customer_email", "expires_at", "is_active",
               "device_id", "device_name", "bound_at"}
    sets = []
    vals = []
    for k, v in fields.items():
        if k in allowed:
            sets.append(f"{k}=?")
            vals.append(v)
    if not sets:
        return False
    vals.append(license_id)
    with _conn() as c:
        cur = c.execute(
            f"UPDATE licenses SET {', '.join(sets)} WHERE id=?",
            vals,
        )
        return cur.rowcount > 0


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
