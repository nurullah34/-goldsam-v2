# GoldSam V2 Server — GitHub'dan son _server/ kodunu cek
# Kullanim: powershell -ExecutionPolicy Bypass -File autopull.ps1
# admin_token.txt ve data/ klasoru KORUNUR.

$ErrorActionPreference = "Stop"
$here   = Split-Path -Parent $MyInvocation.MyCommand.Path
$logDir = Join-Path $here "logs"
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir | Out-Null }
$logFile = Join-Path $logDir "autopull.log"

function Log { param($msg)
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "$ts  $msg" | Tee-Object -FilePath $logFile -Append
}

Log "Autopull baslatildi: $here"

$url = "https://github.com/nurullah34/-goldsam-v2/archive/refs/heads/main.zip"
$tmpZip = Join-Path $env:TEMP "goldsam_pull.zip"
$tmpExt = Join-Path $env:TEMP "goldsam_pull_ext"

if (Test-Path $tmpExt) { Remove-Item -Recurse -Force $tmpExt }

Log "Zip indiriliyor: $url"
try {
    Invoke-WebRequest -Uri $url -OutFile $tmpZip -TimeoutSec 60 -UseBasicParsing
    Log ("Zip indirildi: {0:N0} byte" -f (Get-Item $tmpZip).Length)
} catch {
    Log "HATA: indirme basarisiz: $_"
    exit 1
}

Log "Zip aciliyor: $tmpExt"
Expand-Archive -Path $tmpZip -DestinationPath $tmpExt -Force

# Extracted folder isimi GitHub'da: -goldsam-v2-main veya goldsam-v2-main
$srcRoot = Get-ChildItem $tmpExt -Directory | Select-Object -First 1
$serverSrc = Join-Path $srcRoot.FullName "_server"
if (-not (Test-Path $serverSrc)) {
    Log "HATA: $serverSrc bulunamadi"
    exit 1
}

# Dosyalari kopyala (admin_token.txt KORU)
$preserve = @("admin_token.txt", "logs", "data", "__pycache__")
$copied = 0
Get-ChildItem $serverSrc -File | ForEach-Object {
    if ($preserve -notcontains $_.Name) {
        Copy-Item -Path $_.FullName -Destination (Join-Path $here $_.Name) -Force
        $copied++
    }
}

# Alt klasorler (eger varsa, ornegin static/)
Get-ChildItem $serverSrc -Directory | ForEach-Object {
    if ($preserve -notcontains $_.Name) {
        $dest = Join-Path $here $_.Name
        if (Test-Path $dest) { Remove-Item -Recurse -Force $dest }
        Copy-Item -Path $_.FullName -Destination $dest -Recurse -Force
        $copied++
    }
}

Log "$copied dosya/klasor guncellendi"

# Temizlik
Remove-Item -Force $tmpZip -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force $tmpExt -ErrorAction SilentlyContinue

Log "Autopull tamamlandi"
Write-Host ""
Write-Host "[OK] $copied dosya/klasor guncellendi"
exit 0
