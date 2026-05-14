@echo off
title GoldSam V2 Server (auto-restart + auto-pull)
cd /d "%~dp0"
chcp 65001 >NUL

:: Log dosyasi (her acilista append) — debug icin
if not exist logs mkdir logs

echo ================================================
echo   GoldSam V2 Server (stable mode)
echo ================================================
echo.

:: Pre-flight checks (Python + deps + MT5)
echo [1/4] Python kontrolu...
python --version 2>NUL
if errorlevel 1 (
    echo [HATA] Python bulunamadi. KUR.bat'i once calistir.
    pause
    exit /b 1
)

echo.
echo [2/4] Bagimliliklar...
python -c "import fastapi, uvicorn, MetaTrader5, pandas, numpy" 2>logs\preflight.log
if errorlevel 1 (
    echo [HATA] Bagimliliklar eksik. KUR.bat'i calistir.
    type logs\preflight.log
    pause
    exit /b 1
)
echo [OK]

echo.
echo [3/4] MT5...
python -c "import bar_provider; print('MT5:', bar_provider.is_connected(), 'Hesap:', bar_provider.account_info())" 2>logs\preflight.log
if errorlevel 1 (
    echo [HATA] MT5 baglanti hatasi:
    type logs\preflight.log
    pause
    exit /b 1
)

:: ── Auto-pull: GitHub'dan en yeni _server/ kodunu cek ─────────
:: Eger ag varsa otomatik gunceller. Yoksa local kodu kullanir.
echo.
echo [4/4] Son surum kontrol (GitHub'dan en yeni kod)...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "try { ^
     $url = 'https://github.com/nurullah34/-goldsam-v2/archive/refs/heads/main.zip'; ^
     $zip = Join-Path $env:TEMP 'goldsam_pull.zip'; ^
     $ext = Join-Path $env:TEMP 'goldsam_pull_extracted'; ^
     if (Test-Path $ext) { Remove-Item -Recurse -Force $ext }; ^
     Invoke-WebRequest -Uri $url -OutFile $zip -TimeoutSec 30 -UseBasicParsing; ^
     Expand-Archive -Path $zip -DestinationPath $ext -Force; ^
     $src = Get-ChildItem $ext -Directory | Select-Object -First 1; ^
     $serverFolder = Join-Path $src.FullName '_server'; ^
     Get-ChildItem $serverFolder -File ^| ForEach-Object { ^
       if ($_.Name -notin @('admin_token.txt')) { ^
         Copy-Item $_.FullName -Destination (Join-Path '%CD%' $_.Name) -Force; ^
       } ^
     }; ^
     Remove-Item $zip -Force -ErrorAction SilentlyContinue; ^
     Remove-Item -Recurse -Force $ext -ErrorAction SilentlyContinue; ^
     Write-Host '   [OK] En yeni kod indirildi' ^
   } catch { Write-Host '   [SKIP] GitHub erisilemedi, mevcut kod kullanilacak' }" 2>>logs\autopull.log

echo.
echo ================================================
echo   Server baslatiliyor (auto-restart + auto-pull)
echo   Pencereyi kapatma — server burada calisiyor.
echo   Log: logs\server.log
echo ================================================
echo.

:: Restart loop with exponential backoff (max 60sn)
set RESTART_COUNT=0
set BACKOFF=10

:LOOP
python server.py 2>>logs\server.log
set EXIT_CODE=%ERRORLEVEL%
echo.
echo [%date% %time%] Server cikti (exit=%EXIT_CODE%) — %BACKOFF% sn icinde restart...

:: Eger 5 kere arka arkaya patladiysa cooldown'u uzat (fast-fail loop koruma)
set /a RESTART_COUNT=%RESTART_COUNT%+1
if %RESTART_COUNT% GEQ 5 (
    set BACKOFF=60
    echo [UYARI] 5+ kez patladi. Cooldown 60 sn. Log: logs\server.log
)

timeout /t %BACKOFF% /nobreak >NUL
goto LOOP
