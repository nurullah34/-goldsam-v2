@echo off
title GOLDSAM V2 - Kurulum
chcp 65001 >NUL
echo ================================================
echo   GOLDSAM V2 - Kurulum
echo ================================================
echo.

:: Python kurulu mu?
python --version >NUL 2>&1
if %errorlevel%==0 (
    echo [OK] Python kurulu.
) else (
    echo [!] Python bulunamadi.
    echo     https://www.python.org/downloads/ adresinden Python 3.12 indir
    echo     ve "Add Python to PATH" secenegini isaretle.
    pause
    exit /b 1
)

echo.
echo [..] Gerekli paketler yukleniyor (PySide6, MetaTrader5, pandas, cryptography)
echo     Bu islem 2-5 dakika surebilir...
python -m pip install --upgrade pip --quiet
python -m pip install -r requirements.txt --quiet
if %errorlevel% NEQ 0 (
    echo [!] Paket kurulumu basarisiz.
    pause
    exit /b 1
)
echo [OK] Paketler hazir.

echo.
echo ================================================
echo   Kurulum tamamlandi.
echo.
echo   1. MT5 terminalini ac ve hesabina giris yap
echo   2. BASLAT.bat ile botu calistir
echo   3. Sembol kutusundan dogru sembolu sec (GOLD#, XAUUSD vb.)
echo ================================================
echo.
pause
