@echo off
title GoldSam V2 Server - Kurulum
chcp 65001 >NUL
cd /d "%~dp0"

echo ================================================
echo   GoldSam V2 Server - Kurulum
echo ================================================
echo.

python --version >NUL 2>&1
if errorlevel 1 (
    echo [HATA] Python bulunamadi.
    echo https://www.python.org/downloads/ ile Python 3.12 kur,
    echo "Add to PATH" secenegini isaretle.
    pause
    exit /b 1
)

echo [OK] Python bulundu.
echo.
echo [..] Python paketleri kuruluyor...
python -m pip install --upgrade pip --quiet
python -m pip install -r requirements.txt --quiet
if errorlevel 1 (
    echo [HATA] Paket kurulumu basarisiz.
    pause
    exit /b 1
)
echo [OK] Paketler hazir.

echo.
echo [..] DB ilk init...
python -c "import db; db.init_db(); print('DB hazir')"
if errorlevel 1 (
    echo [HATA] DB init basarisiz.
    pause
    exit /b 1
)

echo.
echo ================================================
echo   Kurulum tamam. BASLAT.bat ile sunucuyu calistir.
echo ================================================
echo.
pause
