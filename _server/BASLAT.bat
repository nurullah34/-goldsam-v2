@echo off
title GoldSam V2 Server (auto-restart)
cd /d "%~dp0"
chcp 65001 >NUL

echo ================================================
echo   GoldSam V2 Server (auto-restart enabled)
echo ================================================
echo.

:: Pre-flight check
echo [1/3] Python kontrolu...
python --version 2>NUL
if errorlevel 1 (
    echo [HATA] Python bulunamadi. KUR.bat'i once calistir.
    pause
    exit /b 1
)

echo.
echo [2/3] Bagimliliklar...
python -c "import fastapi, uvicorn, MetaTrader5, pandas, numpy" 2>tmp_err.txt
if errorlevel 1 (
    echo [HATA] Bagimliliklar eksik. KUR.bat'i calistir.
    type tmp_err.txt
    del tmp_err.txt
    pause
    exit /b 1
)
del tmp_err.txt
echo [OK]

echo.
echo [3/3] MT5...
python -c "import bar_provider; print('MT5:', bar_provider.is_connected(), 'Hesap:', bar_provider.account_info())" 2>tmp_err.txt
if errorlevel 1 (
    echo [HATA] MT5 baglanti hatasi.
    type tmp_err.txt
    del tmp_err.txt
    pause
    exit /b 1
)
del tmp_err.txt

echo.
echo ================================================
echo   Server baslatiliyor (auto-restart on)
echo   Cikinca otomatik geri acilir (self-update vs.)
echo   Tamamen durdurmak icin pencereyi kapat.
echo ================================================
echo.

:LOOP
python server.py
echo.
echo [%date% %time%] Server cikti, 3 sn icinde restart...
timeout /t 3 /nobreak >NUL
goto LOOP
