"""GOLDSAM V2 — bot self-update (onedir mode, zip-based).

v2.1.0+ ile PyInstaller onefile yerine ONEDIR mode kullaniyoruz:
- Bot bir klasor (`GOLDSAM_V2/`) icinde calisir
- python312.dll + _internal/* DLL'leri exe yaninda durur
- %TEMP%\\_MEI extract YOK -> DLL load hatasi mimari olarak imkansiz

Self-update akisi:
  1. GitHub Releases API'den latest tag'i al
  2. Yeniyse: GOLDSAM_V2.zip indir (~70 MB)
  3. %TEMP%\\goldsam_update\\ klasorune extract et
  4. _update.bat olustur:
     - Bot process'i bitsin bekle (tasklist)
     - Eski klasor icerigini sil
     - %TEMP%'den dosyalari kopyala
     - Yeni exe'yi baslat
  5. Bot QApplication.quit -> bat devralir
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

RELEASE_API_URL = (
    f"https://api.github.com/repos/{GITHUB_USER}/{GITHUB_REPO}/releases/latest"
)
ASSET_NAME = "GOLDSAM_V2.zip"
ASSET_URL = (
    f"https://github.com/{GITHUB_USER}/{GITHUB_REPO}/releases/latest/download/{ASSET_NAME}"
)


def _ver_tuple(v: str) -> tuple[int, ...]:
    return tuple(int(x) for x in re.findall(r"\d+", v))


def fetch_remote_version(timeout: int = 10) -> Optional[str]:
    """GitHub Releases'tan en son tag_name (örn. 'v2.1.0' → '2.1.0')."""
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
    m = re.search(r"(\d+\.\d+\.\d+)", tag)
    return m.group(1) if m else None


def is_update_available(current: str, remote: str) -> bool:
    try:
        return _ver_tuple(remote) > _ver_tuple(current)
    except Exception:
        return False


def _running_as_exe() -> bool:
    return bool(getattr(sys, "frozen", False))


def _download_zip(target_path: Path, log: Callable[[str], None],
                  timeout: int = 180) -> bool:
    """ZIP'i indir."""
    log(f"Indiriliyor: {ASSET_URL}")
    try:
        req = urllib.request.Request(
            ASSET_URL, headers={"User-Agent": "GOLDSAM-V2-Updater"}
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            with open(target_path, "wb") as f:
                while True:
                    chunk = resp.read(1024 * 256)
                    if not chunk:
                        break
                    f.write(chunk)
            size_mb = target_path.stat().st_size / 1024 / 1024
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


def _extract_zip(zip_path: Path, dest_dir: Path,
                 log: Callable[[str], None]) -> bool:
    """ZIP'i hedef klasore extract et."""
    log(f"Extract ediliyor: {dest_dir}")
    try:
        import zipfile
        if dest_dir.exists():
            import shutil
            shutil.rmtree(dest_dir, ignore_errors=True)
        dest_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zip_path, "r") as z:
            z.extractall(dest_dir)
        return True
    except Exception as e:
        log(f"Extract HATA: {e}")
        return False


def _write_swap_bat(install_dir: Path, staged_dir: Path,
                    exe_name: str, bat_path: Path) -> None:
    """Helper bat: bot kapan bekle → eski klasor temizle → staged → kopyala
    → yeni exe baslat → kendini sil.
    """
    bat = f"""@echo off
:: GOLDSAM V2 - onedir update swap (auto-generated)
:: 1) Eski bot process bitmesini bekle (max 30 sn)
set /a WAIT=0
:wait_old
tasklist /FI "IMAGENAME eq {exe_name}" 2>NUL | find /I "{exe_name}" >NUL
if not errorlevel 1 (
    set /a WAIT=%WAIT%+1
    if %WAIT% GEQ 30 goto force
    timeout /t 1 /nobreak >NUL
    goto wait_old
)
:force

:: 2) Ek 2sn bekle (Windows file handle release)
timeout /t 2 /nobreak >NUL

:: 3) Staged klasordeki dosyalari install klasoru uzerine kopyala
:: /E: alt klasorler dahil, /Y: overwrite, /I: dest is dir, /K: read-only attr
xcopy /E /Y /I /Q "{staged_dir}" "{install_dir}" >NUL 2>NUL

:: 4) Staged klasoru temizle
rmdir /S /Q "{staged_dir}" 2>NUL

:: 5) Yeni exe'yi baslat
start "" "{install_dir}\\{exe_name}"

:: 6) Eski VBS kalintilarini temizle (v2.1.2'den)
del /q "{bat_path.with_suffix('.vbs')}" 2>NUL

:: 7) Bu bat'i sil
(goto) 2>nul & del "%~f0"
"""
    bat_path.write_text(bat, encoding="utf-8")
    with open(bat_path, "rb") as f:
        content = f.read()
    content = content.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
    with open(bat_path, "wb") as f:
        f.write(content)


def _spawn_bat(bat_path: Path) -> bool:
    """Bat'i guvenilir bir sekilde baslat. 4 farkli yontem fallback ile.

    Kullanici raporu: PowerShell zinciri bazen tetiklenmiyor (_update.bat
    klasorde duruyor, hic calismamis). Daha agresif: birden cok yontem
    dene, biri tutarsa devam.

    Yontemler (sirayla):
    1. Win32 ShellExecuteW (en guvenilir, Defender'a takilmaz)
    2. os.startfile (Windows shell)
    3. cmd start /B (yeni pencere acmaz)
    4. subprocess.Popen direkt (son care)
    """
    DETACHED_PROCESS = 0x00000008
    CREATE_NO_WINDOW = 0x08000000
    bat_str = str(bat_path)
    cwd_str = str(bat_path.parent)

    # YONTEM 1: Win32 API ShellExecuteW (SW_HIDE = 0)
    try:
        import ctypes
        result = ctypes.windll.shell32.ShellExecuteW(
            None,           # hwnd
            "open",         # operation
            bat_str,        # file
            None,           # parameters
            cwd_str,        # working dir
            0,              # SW_HIDE
        )
        # ShellExecuteW > 32 ise basari
        if int(result) > 32:
            return True
    except Exception:
        pass

    # YONTEM 2: os.startfile (Windows shell handler)
    try:
        import os
        os.startfile(bat_str)
        return True
    except Exception:
        pass

    # YONTEM 3: cmd start /B (yeni pencere acmaz)
    try:
        subprocess.Popen(
            f'start "" /B "{bat_str}"',
            shell=True,
            cwd=cwd_str,
            creationflags=DETACHED_PROCESS | CREATE_NO_WINDOW,
            close_fds=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return True
    except Exception:
        pass

    # YONTEM 4: subprocess.Popen direkt (pencere acabilir ama calisir)
    try:
        subprocess.Popen(
            [bat_str],
            cwd=cwd_str,
            creationflags=DETACHED_PROCESS | CREATE_NO_WINDOW,
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
    """Zip indir → extract → swap bat tetikle → bot kapan."""
    if not _running_as_exe():
        log("⚠ Bu özellik sadece kurulu exe'de çalışır.")
        return False

    exe_path = Path(sys.executable).resolve()
    install_dir = exe_path.parent           # GOLDSAM_V2/ klasoru
    exe_name = exe_path.name                # GOLDSAM_V2.exe

    # Staging: %TEMP%\goldsam_update — geçici extract yeri
    import tempfile
    tmp_root = Path(tempfile.gettempdir()) / "goldsam_update"
    tmp_zip = tmp_root / "update.zip"
    tmp_extract = tmp_root / "extracted"
    staged_dir = tmp_root / "staged"

    # Temizle önceki kalıntıları
    if tmp_root.exists():
        import shutil
        shutil.rmtree(tmp_root, ignore_errors=True)
    tmp_root.mkdir(parents=True, exist_ok=True)

    # 1. ZIP indir
    if not _download_zip(tmp_zip, log):
        return False

    # 2. Extract
    if not _extract_zip(tmp_zip, tmp_extract, log):
        return False

    # 3. Extracted icindeki "GOLDSAM_V2/" klasorunu bul → staged'a koy
    # GHA workflow: Compress-Archive dist/GOLDSAM_V2 → zip içeriği "GOLDSAM_V2/..."
    candidates = list(tmp_extract.glob("GOLDSAM_V2"))
    if candidates and candidates[0].is_dir():
        # zip içeriği: GOLDSAM_V2/exe + dll + _internal
        import shutil
        shutil.move(str(candidates[0]), str(staged_dir))
    else:
        # zip direkt root'ta dosyalar: GOLDSAM_V2.exe, python312.dll, _internal/
        import shutil
        shutil.move(str(tmp_extract), str(staged_dir))

    log(f"Staged: {staged_dir}")

    # 4. Helper bat oluştur (install_dir cwd'sinden çalışır)
    bat_path = install_dir / "_update.bat"
    if bat_path.exists():
        try:
            bat_path.unlink()
        except Exception:
            pass
    try:
        _write_swap_bat(install_dir, staged_dir, exe_name, bat_path)
        log(f"Swap script: {bat_path.name}")
    except Exception as e:
        log(f"Swap script HATA: {e}")
        return False

    # 5. Bat'i baslat (detached) — bot kapanacak
    if not _spawn_bat(bat_path):
        log("Swap baslatilamadi.")
        return False

    log("✓ Güncelleme hazır. Bot kapanıyor, yeni sürüm 3-5 sn icinde acilacak...")
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
        log("⚠ Self-update sadece kurulu exe'de calisir.")
        return None

    ok = download_and_apply(base_dir, log)
    return True if ok else None
