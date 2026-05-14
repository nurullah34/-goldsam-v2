@echo off
title GoldSam V2 Server
cd /d "%~dp0"
chcp 65001 >NUL
echo ================================================
echo   GoldSam V2 Server
echo ================================================
echo.

echo [1/4] Python kontrolu...
python --version 2>NUL
if errorlevel 1 (
    echo [HATA] Python bulunamadi. KUR.bat'i once calistir.
    pause
    exit /b 1
)

echo.
echo [2/4] Bagimlilik testi...
python -c "import fastapi, uvicorn, MetaTrader5, pandas, numpy" 2>tmp_err.txt
if errorlevel 1 (
    echo [HATA] Bagimliliklar eksik.
    type tmp_err.txt
    del tmp_err.txt
    echo.
    echo Cozum: KUR.bat'i once calistir.
    pause
    exit /b 1
)
del tmp_err.txt
echo [OK]

echo.
echo [3/4] MT5 + bar verisi testi...
python -c "import bar_provider; ok = bar_provider.is_connected(); print('MT5:', ok); info = bar_provider.account_info(); print('Hesap:', info)" 2>tmp_err.txt
if errorlevel 1 (
    echo [HATA] MT5 baglanti hatasi.
    type tmp_err.txt
    del tmp_err.txt
    echo.
    echo Cozum: 'C:\Program Files\metadinleme\terminal64.exe' yolundaki MT5'i ac
    echo ve XMGlobal demo hesabina giris yap.
    pause
    exit /b 1
)
del tmp_err.txt
echo [OK]

echo.
echo [4/4] Sunucu baslatiliyor (port 8000)...
echo ================================================
echo   Logu izle. Kapatmak icin pencereyi kapat.
echo   Admin token: data\admin_token.txt
echo   Public URL: http://%COMPUTERNAME%:8000/public/status
echo ================================================
echo.
python server.py
echo.
echo Sunucu durdu. Pencere kapanmadi — hata mesaji yukarida.
pause
