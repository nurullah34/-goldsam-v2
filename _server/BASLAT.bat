@echo off
title GoldSam V2 Server
cd /d "%~dp0"
echo ================================================
echo   GoldSam V2 Server baslatiliyor...
echo   Port: 8000  |  MT5: metadinleme  |  Sembol: GOLD#
echo ================================================
echo.
echo Loglar asagida — kapatmak icin pencereyi kapat.
echo Admin token: data\admin_token.txt
echo.
python server.py
pause
