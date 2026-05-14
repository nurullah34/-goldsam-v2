@echo off
title GoldSam V2 - Guncelle
cd /d "%~dp0"
chcp 65001 >NUL

echo ================================================
echo   GoldSam V2 Server - GitHub'dan guncelle
echo ================================================
echo.
echo Mevcut _server kodu GitHub main branch ile degistirilecek.
echo admin_token.txt KORUNUR. data\ klasoru KORUNUR.
echo.
pause

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0autopull.ps1"
set RC=%ERRORLEVEL%
if %RC% NEQ 0 (
    echo.
    echo HATA: Guncelleme basarisiz. Bkz: logs\autopull.log
    pause
    exit /b 1
)

echo.
echo ================================================
echo   OK - Yeni kod indirildi
echo   Eger server acik calisiyorsa kapatip BASLAT.bat ile tekrar ac.
echo ================================================
pause
