@echo off
title GoldSam Server - Tani
cd /d "%~dp0"
echo ============================================
echo   GoldSam Server Diagnostic
echo ============================================
echo.

echo [Klasor]: %CD%
echo.

echo [1] Python:
python --version
echo.

echo [2] Pip paketler:
python -m pip list 2>NUL | findstr /i "fastapi uvicorn metatrader5 pandas numpy"
echo.

echo [3] Dosyalar:
dir /b *.py *.bat *.txt
echo.

echo [4] MT5 baglanti testi:
python -c "import bar_provider; print('Connected:', bar_provider.is_connected()); print('Info:', bar_provider.account_info())"
echo.

echo [5] DB testi:
python -c "import db; db.init_db(); print('DB OK:', db.DB_PATH)"
echo.

echo [6] Server import testi:
python -c "import server; print('Server module OK')"
echo.

echo [7] Server kisa baslatma denemesi (5 sn):
echo Eger hata varsa asagida gorunur...
timeout /t 1 /nobreak >NUL
start /B python server.py
timeout /t 5 /nobreak >NUL
echo.
echo [8] Port 8000 test:
curl -s http://localhost:8000/ 2>&1 | head -c 300
echo.
echo.

echo ============================================
echo   Tani tamam. Yukaridaki ciktinin
echo   screenshot'unu paylas.
echo ============================================
pause
