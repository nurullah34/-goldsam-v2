@echo off
title GOLDSAM V2 - Lokal zip sync
cd /d "%~dp0"
chcp 65001 >NUL

echo ================================================
echo   GOLDSAM V2 - Lokal zip'i en son release ile sync
echo ================================================
echo.

python sync_zip.py
set RC=%ERRORLEVEL%

echo.
if %RC% NEQ 0 (
    echo [HATA] Sync basarisiz.
) else (
    echo [OK] Sync tamamlandi.
)
echo.
pause
