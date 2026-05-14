"""GOLDSAM V2 — bot self-update (exe-tabanli).

v1.x'te Python source dosyalari indirilirdi (gomülü Python olduğu için).
v2.x ile PyInstaller onefile exe yapıyoruz. Çalışan exe kendi üzerine
yazamaz (Windows file lock). Çözüm: helper batch dosyası swap yapar.

Akış:
  1. GitHub Releases API'den latest release'ı al
  2. Eğer release version > current version:
     a. Asset (GOLDSAM_V2.exe) indir → sys.executable + ".new"
     b. _update.bat oluştur (swap mantığı)
     c. _update.bat'i detached process olarak başlat
     d. Bot kapanır (QApplication.quit)
     e. Bat 2 sn bekler → eski exe sil → yeni exe rename → çalıştır
     f. Bat kendini siler

GitHub Release sözleşmesi:
  - Tag: v2.0.2 (örn.) — version.py içindeki VERSION ile eşleşir
  - Asset adı: GOLDSAM_V2.exe (sabit isim)
  - URL formati: https://github.com/USER/REPO/releases/latest/download/GOLDSAM_V2.exe
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable, Optional

GITHUB_USER = "nurullah34"
GITHUB_REPO = "-goldsam-v2"

# GitHub Releases API — latest release JSON
RELEASE_API_URL = (
    f"https://api.github.com/repos/{GITHUB_USER}/{GITHUB_REPO}/releases/latest"
)
# Direct asset download — her release'de GOLDSAM_V2.exe sabit isim
ASSET_NAME = "GOLDSAM_V2.exe"
ASSET_URL = (
    f"https://github.com/{GITHUB_USER}/{GITHUB_REPO}/releases/latest/download/{ASSET_NAME}"
)


def _ver_tuple(v: str) -> tuple[int, ...]:
    """'2.0.1' → (2, 0, 1) — sürüm karşılaştırması."""
    return tuple(int(x) for x in re.findall(r"\d+", v))


def fetch_remote_version(timeout: int = 10) -> Optional[str]:
    """GitHub Releases'tan en son tag_name'i çek (örn. 'v2.0.2' → '2.0.2')."""
    try:
        req = urllib.request.Request(
            RELEASE_API_URL,
            headers={
                "User-Agent": "GOLDSAM-V2-Updater",
                "Accept": "application/vnd.github+json",
            },
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None
    tag = data.get("tag_name", "")
    # "v2.0.2" → "2.0.2"
    m = re.search(r"(\d+\.\d+\.\d+)", tag)
    return m.group(1) if m else None


def is_update_available(current: str, remote: str) -> bool:
    try:
        return _ver_tuple(remote) > _ver_tuple(current)
    except Exception:
        return False


def _running_as_exe() -> bool:
    """PyInstaller bundle olarak mi calisiyoruz? (sys.frozen)"""
    return bool(getattr(sys, "frozen", False))


def _download_exe(target_path: Path, log: Callable[[str], None],
                  timeout: int = 120) -> bool:
    """Yeni exe'yi indir (sys.executable + '.new' olarak)."""
    log(f"Indiriliyor: {ASSET_URL}")
    try:
        req = urllib.request.Request(
            ASSET_URL, headers={"User-Agent": "GOLDSAM-V2-Updater"}
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            total = 0
            with open(target_path, "wb") as f:
                while True:
                    chunk = resp.read(1024 * 256)  # 256 KB
                    if not chunk:
                        break
                    f.write(chunk)
                    total += len(chunk)
            size_mb = total / 1024 / 1024
            log(f"Indirme tamam: {size_mb:.1f} MB")
            return True
    except Exception as e:
        log(f"Indirme HATA: {e}")
        try:
            if target_path.exists():
                target_path.unlink()
        except Exception:
            pass
        return False


def _write_swap_bat(exe_path: Path, new_exe_path: Path, bat_path: Path) -> None:
    """Helper batch: bekle → eski exe sil → eski _MEI* temizle → yeni rename →
    calistir → bat kendini sil.

    Sorun: PyInstaller onefile exe %TEMP%\\_MEI<rand>\\python312.dll extract eder.
    Self-update sirasinda eski process tam kapanmazsa _MEI lock kalir, yeni exe
    "Failed to load Python DLL" hatasi verir. Cozum:
    1. 5 sn bekle (eski exe ve _MEI cleanup tamamlansin)
    2. Eski _MEI klasorlerini temizle (cache cakismasi onle)
    3. Sonra swap yap
    """
    exe_name = exe_path.name
    bat = f"""@echo off
:: GOLDSAM V2 - update swap (auto-generated)
:: 1) Eski exe process'ini bekle (TAMAMEN kapansin, atexit cleanup bitsin)
set /a WAIT=0
:wait_old
tasklist /FI "IMAGENAME eq {exe_name}" 2>NUL | find /I "{exe_name}" >NUL
if not errorlevel 1 (
    set /a WAIT=%WAIT%+1
    if %WAIT% GEQ 30 goto force_continue
    timeout /t 1 /nobreak >NUL
    goto wait_old
)
:force_continue

:: 2) Ek 2 sn bekle (atexit handler'i _MEI temizlesin)
timeout /t 2 /nobreak >NUL

:: 3) Tum %TEMP%\\_MEI* klasorlerini temizle (eski olanlar varsa)
for /d %%D in ("%TEMP%\\_MEI*") do rmdir /S /Q "%%D" 2>NUL

:: 4) Eski exe dosyasini sil (10 retry)
set /a RETRY=0
:retry_del
del /q "{exe_path}" 2>NUL
if exist "{exe_path}" (
    set /a RETRY=%RETRY%+1
    if %RETRY% GEQ 10 goto giveup
    timeout /t 1 /nobreak >NUL
    goto retry_del
)

:: 5) Yeni exe'yi yerine tasi
ren "{new_exe_path.name}" "{exe_name}" 2>NUL
if errorlevel 1 (
    move /Y "{new_exe_path}" "{exe_path}" >NUL
)

:: 6) Yeni exe'yi baslat
start "" "{exe_path}"
goto cleanup

:giveup
:: Eski exe silinemedi - yine de yeni exe'yi farkli isimle baslat
start "" "{new_exe_path}"

:cleanup
(goto) 2>nul & del "%~f0"
"""
    bat_path.write_text(bat, encoding="utf-8")
    # CRLF normalize (Windows batch dogru parse etsin)
    with open(bat_path, "rb") as f:
        content = f.read()
    content = content.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
    with open(bat_path, "wb") as f:
        f.write(content)


def _spawn_bat(bat_path: Path) -> bool:
    """Helper bat'i detached olarak baslat (bot kapanacak)."""
    try:
        DETACHED_PROCESS = 0x00000008
        CREATE_NEW_PROCESS_GROUP = 0x00000200
        CREATE_NO_WINDOW = 0x08000000

        subprocess.Popen(
            ["cmd", "/c", str(bat_path)],
            cwd=str(bat_path.parent),
            creationflags=(
                DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW
            ),
            close_fds=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return True
    except Exception:
        return False


def download_and_apply(
    base_dir: Path,
    log: Callable[[str], None],
) -> bool:
    """Yeni exe indir → swap bat oluştur + tetikle → bot çıkacak."""
    if not _running_as_exe():
        log("⚠ Bu özellik sadece kurulu exe'de çalışır (geliştirme modunda atlandı).")
        return False

    exe_path = Path(sys.executable).resolve()
    new_exe_path = exe_path.with_name(exe_path.name + ".new")
    bat_path = exe_path.with_name("_update.bat")

    # Önceki update kalintilarini temizle
    for stale in (new_exe_path, bat_path):
        try:
            if stale.exists():
                stale.unlink()
        except Exception:
            pass

    # 1. Yeni exe'yi indir
    if not _download_exe(new_exe_path, log):
        return False

    # 2. Helper bat oluştur
    try:
        _write_swap_bat(exe_path, new_exe_path, bat_path)
        log(f"Swap script yazildi: {bat_path.name}")
    except Exception as e:
        log(f"Swap script HATA: {e}")
        return False

    # 3. Bat'i baslat (detached) — bot kapanacak
    if not _spawn_bat(bat_path):
        log("Swap baslatilamadi.")
        return False

    log("✓ Güncelleme hazır. Bot kapanıyor, yeni sürüm 2-3 sn icinde acilacak...")
    return True


def check_and_update(
    base_dir: Path,
    current_version: str,
    log: Callable[[str], None],
) -> Optional[bool]:
    """True: güncellendi, bot kapatılmalı. False: zaten güncel. None: hata."""
    log("GitHub Releases kontrol ediliyor...")
    remote = fetch_remote_version()
    if remote is None:
        log("Uzak surum okunamadi (internet veya henuz release yok).")
        return None

    if not is_update_available(current_version, remote):
        log(f"Zaten guncel: v{current_version} (latest: v{remote})")
        return False

    log(f"Yeni surum bulundu: v{current_version} → v{remote}")
    if not _running_as_exe():
        log("⚠ Self-update sadece kurulu exe'de calisir. Su an Python kaynak modunda.")
        return None

    ok = download_and_apply(base_dir, log)
    return True if ok else None
