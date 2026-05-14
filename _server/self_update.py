"""Server self-update — GitHub'dan yeni _server/ kodunu indirip kendini günceller.

Akış:
  1. GitHub main branch zip'i indir
  2. ZIP'i belleğe aç, sadece `_server/` altındaki dosyaları çıkar
  3. Mevcut server dosyalarının üstüne yaz (data/ ve admin_token.txt KORUNUR)
  4. sys.exit(0) — BASLAT.bat restart döngüsü yeni kodu yükler
"""
from __future__ import annotations

import io
import os
import shutil
import sys
import zipfile
import urllib.request
from datetime import datetime
from pathlib import Path

GITHUB_REPO_ZIP = "https://github.com/nurullah34/-goldsam-v2/archive/refs/heads/main.zip"

# Server dosyalarının bulunduğu klasör (config + db + engine + bar_provider + server vs.)
SERVER_DIR = Path(__file__).resolve().parent

# ZIP içindeki kök: "-goldsam-v2-main/_server/..." → bunun "_server/" kısmını alacağız
ZIP_SERVER_PREFIX = "_server/"

# KORUNACAK dosyalar (override edilmez)
PRESERVE = {
    "data",                  # SQLite DB + admin_token.txt
    "admin_token.txt",
    "__pycache__",
}


def _download_zip() -> bytes:
    req = urllib.request.Request(
        GITHUB_REPO_ZIP,
        headers={"User-Agent": "GoldSam-Server-Updater"},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read()


def perform_update(log_fn=print) -> dict:
    """Self-update — yeni kodu çek, dosyaları override et. dict sonuç döner."""
    started = datetime.utcnow().isoformat(timespec="seconds")
    log_fn(f"[UPDATE] Başladı {started}")

    try:
        log_fn(f"[UPDATE] ZIP indiriliyor: {GITHUB_REPO_ZIP}")
        zip_bytes = _download_zip()
        log_fn(f"[UPDATE] ZIP indirildi: {len(zip_bytes)/1024:.1f} KB")
    except Exception as e:
        return {"ok": False, "error": f"İndirme hatası: {e}"}

    # ZIP içindeki _server/ klasöründeki dosyaları çıkar
    written = 0
    errors: list[str] = []
    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
            for name in z.namelist():
                if name.endswith("/"):
                    continue
                # name örn: "-goldsam-v2-main/_server/engine.py"
                parts = name.split("/", 1)
                if len(parts) < 2:
                    continue
                rel = parts[1]   # "_server/engine.py"
                if not rel.startswith(ZIP_SERVER_PREFIX):
                    continue
                rel = rel[len(ZIP_SERVER_PREFIX):]  # "engine.py"
                if not rel:
                    continue

                # PRESERVE kontrol — kök seviyede korunan klasör/dosyalar
                first = rel.split("/", 1)[0]
                if first in PRESERVE:
                    continue

                target = SERVER_DIR / rel
                try:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with z.open(name) as src, open(target, "wb") as out:
                        shutil.copyfileobj(src, out)
                    written += 1
                except Exception as e:
                    errors.append(f"{rel}: {e}")
    except Exception as e:
        return {"ok": False, "error": f"ZIP açma: {e}"}

    log_fn(f"[UPDATE] {written} dosya güncellendi. Restart için exit ediliyor...")

    # Restart trigger dosyası yaz — BASLAT.bat döngüsü loop'tan çıkmasın
    restart_flag = SERVER_DIR / "_restart.flag"
    try:
        restart_flag.write_text(datetime.utcnow().isoformat(), encoding="utf-8")
    except Exception:
        pass

    return {
        "ok": True,
        "files_written": written,
        "errors": errors,
        "started_at": started,
        "finished_at": datetime.utcnow().isoformat(timespec="seconds"),
    }


def schedule_exit(delay_sec: float = 2.0) -> None:
    """Belirli süre sonra process'i kapat — uvicorn'un response göndermesi için bekler."""
    import threading
    def _bye():
        import time
        time.sleep(delay_sec)
        os._exit(0)
    threading.Thread(target=_bye, daemon=True).start()
