@echo off
title GoldSam V2 Server
cd /d "%~dp0"
chcp 65001 >NUL
if not exist logs mkdir logs

echo ================================================
echo   GoldSam V2 Server
echo ================================================
echo.

echo [1/3] Python kontrolu...
python --version 2>NUL
if errorlevel 1 (
    echo HATA: Python bulunamadi. KUR.bat'i once calistir.
    pause
    exit /b 1
)

echo.
echo [2/3] Bagimliliklar...
python -c "import fastapi, uvicorn, MetaTrader5, pandas, numpy" 2>logs\preflight.log
if errorlevel 1 (
    echo HATA: Bagimliliklar eksik. KUR.bat'i calistir.
    type logs\preflight.log
    pause
    exit /b 1
)

echo.
echo [3/3] MT5 baglantisi...
python -c "import bar_provider; print('MT5:', bar_provider.is_connected())" 2>logs\preflight.log
if errorlevel 1 (
    echo HATA: MT5 baglanti.
    type logs\preflight.log
    pause
    exit /b 1
)

echo.
echo ================================================
echo   Server baslatiliyor (auto-restart)
echo   Pencereyi kapatma. Log: logs\server.log
echo ================================================
echo.

set RESTART_COUNT=0

:LOOP
python server.py
set EXIT_CODE=%ERRORLEVEL%
echo.
echo [%date% %time%] Server cikti (exit=%EXIT_CODE%) - restart...
set /a RESTART_COUNT=%RESTART_COUNT%+1
if %RESTART_COUNT% GEQ 5 (
    echo [UYARI] 5+ kez patladi, 60 sn cooldown.
    timeout /t 60 /nobreak >NUL
    set RESTART_COUNT=0
) else (
    timeout /t 10 /nobreak >NUL
)
goto LOOP
