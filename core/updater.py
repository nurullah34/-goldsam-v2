"""Auto-update — GitHub'dan en son sürümü çekip kendini günceller.

Akış:
  1. GitHub raw'dan version.py'yi çek, VERSION'ı parse et.
  2. Mevcut VERSION ile karşılaştır.
  3. Yeniyse: main branch'ini zip olarak indir, geçici klasöre extract et.
  4. Bir update.bat oluştur:
       - 3 saniye bekle (bot kapansın)
       - yeni dosyaları kopyala
       - pythonw main.py ile yeniden başlat
  5. update.bat'ı arka planda çalıştır, bot'u kapat.
"""
from __future__ import annotations

import io
import os
import re
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
    """'1.3.4' → (1, 3, 4) — sürüm karşılaştırması için."""
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


def download_and_apply(
    base_dir: Path,
    log: Callable[[str], None],
) -> bool:
    """Zip indir → extract → update.bat oluştur → bot'u kapat."""
    try:
        log(f"Güncelleme indiriliyor: {ZIP_URL}")
        req = urllib.request.Request(
            ZIP_URL, headers={"User-Agent": "GOLDSAM-V2-Updater"}
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            zip_bytes = resp.read()
        log(f"İndirme tamam ({len(zip_bytes)/1024:.1f} KB), açılıyor...")
    except Exception as e:
        log(f"İndirme başarısız: {e}")
        return False

    tmp_dir = base_dir / ".update_tmp"
    if tmp_dir.exists():
        # Eski geçici dosyaları temizle
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)
    tmp_dir.mkdir(exist_ok=True)

    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
            z.extractall(tmp_dir)
    except Exception as e:
        log(f"Zip açılamadı: {e}")
        return False

    # Zip içinde tek alt-klasör var: "{repo}-{branch}"
    inner = list(tmp_dir.iterdir())
    if not inner:
        log("Zip içeriği boş.")
        return False
    src_dir = inner[0]
    log(f"Yeni sürüm klasörü: {src_dir.name}")

    # update.bat oluştur — bot kapandıktan sonra dosyaları yer değiştirir
    # ve sonunda KENDİ KENDİNİ siler (self-delete pattern).
    update_bat = base_dir / "_update.bat"
    update_bat.write_text(
        "@echo off\r\n"
        "chcp 65001 >NUL\r\n"
        "title GOLDSAM V2 - Update\r\n"
        "echo Bot kapanıyor, 3 saniye bekleniyor...\r\n"
        "timeout /t 3 /nobreak >NUL\r\n"
        f'xcopy "{src_dir}\\*" "{base_dir}" /E /Y /Q\r\n'
        f'rmdir /S /Q "{tmp_dir}"\r\n'
        f'del "{base_dir}\\.app.pid" 2>NUL\r\n'
        "echo Güncelleme tamam. Bot yeniden başlatılıyor...\r\n"
        "timeout /t 1 /nobreak >NUL\r\n"
        f'cd /d "{base_dir}"\r\n'
        f'start "" pythonw "{base_dir}\\main.py"\r\n'
        # Self-delete — yeni cmd başlat, 3 sn bekle, _update.bat'ı sil.
        # Bu sırada mevcut bat çıkmış olur, dosya unlock olur.
        f'start "" /B cmd /c "timeout /t 3 /nobreak >NUL & del /Q \\"{update_bat}\\""\r\n'
        "exit\r\n",
        encoding="utf-8",
    )
    log("Update script hazır, bot 3 saniye içinde yeniden başlayacak.")

    # update.bat'ı arka planda başlat — yeni bir konsol açar ama anında detach olur
    DETACHED_PROCESS = 0x00000008
    CREATE_NEW_PROCESS_GROUP = 0x00000200
    subprocess.Popen(
        ["cmd", "/c", str(update_bat)],
        creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP,
        close_fds=True,
    )
    return True


def check_and_update(
    base_dir: Path,
    current_version: str,
    log: Callable[[str], None],
) -> Optional[bool]:
    """True: güncellendi, bot kapatılmalı.
    False: güncel zaten.
    None: hata oldu, hiçbir şey yapılmadı."""
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
    if not ok:
        return None
    return True
