"""Auto-update — GitHub'dan en son sürümü çekip kendini günceller.

Mt5-agent pattern'i:
  1. GitHub raw'dan version.py'yi çek → uzak VERSION.
  2. Yerel VERSION ile karşılaştır.
  3. Yeniyse: main branch'i zip indir → bellek üzerinde aç.
  4. Her dosyayı doğrudan base_dir'a yaz (.py dosyaları lock değil).
  5. subprocess.Popen ile yeni Python process'i başlat (detached).
  6. Eski bot QApplication.quit() ile kapanır.

Batch file YOK. Geçici klasör YOK. _update.bat YOK. Tertemiz.
"""
from __future__ import annotations

import io
import os
import re
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path
from typing import Callable, Optional

GITHUB_USER = "nurullah34"
GITHUB_REPO = "-goldsam-v2"
BRANCH = "main"

RAW_VERSION_URL = (
    f"https://raw.githubusercontent.com/{GITHUB_USER}/{GITHUB_REPO}/{BRANCH}/version.py"
)
ZIP_URL = (
    f"https://github.com/{GITHUB_USER}/{GITHUB_REPO}/archive/refs/heads/{BRANCH}.zip"
)


def _ver_tuple(v: str) -> tuple[int, ...]:
    """'1.4.8' → (1, 4, 8) — sürüm karşılaştırması."""
    return tuple(int(x) for x in re.findall(r"\d+", v))


def fetch_remote_version(timeout: int = 10) -> Optional[str]:
    """GitHub'daki version.py'den VERSION değerini çek."""
    try:
        req = urllib.request.Request(
            RAW_VERSION_URL,
            headers={"User-Agent": "GOLDSAM-V2-Updater"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            text = resp.read().decode("utf-8")
    except Exception:
        return None
    match = re.search(r'VERSION\s*=\s*["\']([0-9.]+)["\']', text)
    return match.group(1) if match else None


def is_update_available(current: str, remote: str) -> bool:
    try:
        return _ver_tuple(remote) > _ver_tuple(current)
    except Exception:
        return False


# Bot tarafında SİLİNMEMESİ gereken kullanıcıya özel dosyalar
PRESERVE_NAMES = {
    ".app.pid",
    ".gitignore",
    ".update_tmp",
    "_update.bat",
}


def download_and_apply(
    base_dir: Path,
    log: Callable[[str], None],
) -> bool:
    """Zip indir → bellekten dosyaları yaz → yeni Python process'i başlat."""
    # 1. Zip indir
    try:
        log(f"Güncelleme indiriliyor: {ZIP_URL}")
        req = urllib.request.Request(
            ZIP_URL, headers={"User-Agent": "GOLDSAM-V2-Updater"}
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            zip_bytes = resp.read()
        log(f"İndirme tamam ({len(zip_bytes)/1024:.1f} KB)")
    except Exception as e:
        log(f"İndirme başarısız: {e}")
        return False

    # 2. Zip'i bellek üzerinde aç, dosyaları doğrudan base_dir'a yaz
    written = 0
    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
            for name in z.namelist():
                if name.endswith("/"):
                    continue
                # Path: "-goldsam-v2-main/core/lifecycle.py"
                # İlk component'i at (repo+branch klasörü)
                if "/" not in name:
                    continue
                rel = name.split("/", 1)[1]
                if not rel:
                    continue

                # Korunan dosyaları atla
                first_part = rel.split("/", 1)[0]
                if first_part in PRESERVE_NAMES:
                    continue

                dst = base_dir / rel
                try:
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    with z.open(name) as src, open(dst, "wb") as out:
                        shutil.copyfileobj(src, out)
                    written += 1
                except Exception as e:
                    log(f"  ⚠️ {rel} yazılamadı: {e}")
    except Exception as e:
        log(f"Zip açma hatası: {e}")
        return False

    log(f"✓ {written} dosya güncellendi.")

    # 3. Yeni Python process'i başlat — detach + stdin/out/err DEVNULL
    #    Sebep: parent kapanınca child'ın stdio handle'ları kopabiliyor;
    #    DEVNULL ile bağlı handle yok, yeni Qt pencere bağımsız açılır.
    main_path = base_dir / "main.py"
    if not main_path.exists():
        log(f"❌ {main_path} bulunamadı — yeniden başlatılamaz.")
        return False

    exe = sys.executable
    log(f"Yeni sürüm fırlatılıyor: {exe} {main_path}")
    try:
        DETACHED_PROCESS = 0x00000008
        CREATE_NEW_PROCESS_GROUP = 0x00000200
        CREATE_NO_WINDOW = 0x08000000

        proc = subprocess.Popen(
            [exe, str(main_path)],
            cwd=str(base_dir),
            creationflags=(
                DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW
            ),
            close_fds=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        log(f"✓ Yeni process PID={proc.pid} başlatıldı, eski bot kapanıyor...")
        return True
    except Exception as e:
        log(f"❌ Yeni process başlatma hatası: {e}")
        # Fallback: os.startfile ile dene (Windows shell üzerinden)
        try:
            import os
            os.startfile(str(main_path))
            log("✓ Fallback (os.startfile) ile yeni sürüm açıldı.")
            return True
        except Exception as e2:
            log(f"❌ Fallback da başarısız: {e2}")
            return False


def check_and_update(
    base_dir: Path,
    current_version: str,
    log: Callable[[str], None],
) -> Optional[bool]:
    """True: güncellendi, bot kapatılmalı. False: zaten güncel. None: hata."""
    log("GitHub kontrol ediliyor...")
    remote = fetch_remote_version()
    if remote is None:
        log("Uzak sürüm okunamadı (internet / repo erişimi?).")
        return None

    if not is_update_available(current_version, remote):
        log(f"Zaten güncel: v{current_version} (uzak: v{remote})")
        return False

    log(f"Yeni sürüm bulundu: v{current_version} → v{remote}")
    ok = download_and_apply(base_dir, log)
    return True if ok else None
