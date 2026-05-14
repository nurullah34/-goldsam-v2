# -*- mode: python ; coding: utf-8 -*-
"""GOLDSAM V2 — PyInstaller spec (tek dosya .exe, slim).

Cikti: dist/GOLDSAM_V2.exe (yaklasik 80-120 MB).
Build: python -m PyInstaller --clean --noconfirm GOLDSAM_V2.spec

Optimizasyon notu: PySide6 cok modullu (QtQuick, QtCharts, QtWebEngine,
QtMultimedia, QtPdf, Qt3D, vb.). Bot sadece QtCore + QtGui + QtWidgets
kullaniyor. Geri kalanini exclude ederek 249MB -> ~90MB indiriyoruz.
"""
from pathlib import Path
from PyInstaller.utils.hooks import collect_all

ROOT = Path(SPECPATH).resolve()

# certifi (HTTPS sertifikalari), cryptography (Fernet), MetaTrader5 — tam paket
datas = []
binaries = []
hiddenimports = []
for pkg in ("certifi", "cryptography", "MetaTrader5"):
    try:
        ds, bs, hs = collect_all(pkg)
        datas += ds
        binaries += bs
        hiddenimports += hs
    except Exception:
        pass

# MetaTrader5 — collect_all'in atladigi C extension binary'lerini manuel ekle
# _core.cp312-win_amd64.pyd MT5 paketinde olmazsa "MetaTrader5 yuklu degil" hatasi.
try:
    import MetaTrader5 as _mt5_mod
    _mt5_dir = Path(_mt5_mod.__file__).resolve().parent
    for _pyd in _mt5_dir.glob("*.pyd"):
        binaries.append((str(_pyd), "MetaTrader5"))
    for _dll in _mt5_dir.glob("*.dll"):
        binaries.append((str(_dll), "MetaTrader5"))
except Exception:
    pass

# PySide6 — sadece kullandigimiz modulleri elle ekle
hiddenimports += [
    "PySide6.QtCore",
    "PySide6.QtGui",
    "PySide6.QtWidgets",
    "shiboken6",
    # MT5 C extension'i acikca da ekle (yedek)
    "MetaTrader5",
    "MetaTrader5._core",
]


a = Analysis(
    [str(ROOT / "main.py")],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # VPS server kodu — bot exe'sine GIRMEMELI
        "_server",
        "strategies",
        # Test/dev paketleri
        "pytest", "pytest_qt", "hypothesis",
        # Gereksiz GUI framework'leri
        "tkinter",
        # PySide6 — bizim kullanmadigimiz buyuk modulleri ATLA
        "PySide6.QtQuick",
        "PySide6.QtQuick3D",
        "PySide6.QtQuickControls2",
        "PySide6.QtQuickWidgets",
        "PySide6.QtMultimedia",
        "PySide6.QtMultimediaWidgets",
        "PySide6.QtWebEngineCore",
        "PySide6.QtWebEngineWidgets",
        "PySide6.QtWebEngineQuick",
        "PySide6.QtWebChannel",
        "PySide6.QtWebSockets",
        "PySide6.QtWebView",
        "PySide6.QtCharts",
        "PySide6.QtDataVisualization",
        "PySide6.Qt3DCore",
        "PySide6.Qt3DRender",
        "PySide6.Qt3DInput",
        "PySide6.Qt3DLogic",
        "PySide6.Qt3DAnimation",
        "PySide6.Qt3DExtras",
        "PySide6.QtPdf",
        "PySide6.QtPdfWidgets",
        "PySide6.QtBluetooth",
        "PySide6.QtNfc",
        "PySide6.QtPositioning",
        "PySide6.QtLocation",
        "PySide6.QtSensors",
        "PySide6.QtSerialPort",
        "PySide6.QtSerialBus",
        "PySide6.QtSpatialAudio",
        "PySide6.QtTextToSpeech",
        "PySide6.QtRemoteObjects",
        "PySide6.QtScxml",
        "PySide6.QtStateMachine",
        "PySide6.QtHelp",
        "PySide6.QtDesigner",
        "PySide6.QtUiTools",
        "PySide6.QtSql",
        "PySide6.QtTest",
        "PySide6.QtXml",
        "PySide6.QtSvg",
        "PySide6.QtSvgWidgets",
        "PySide6.QtConcurrent",
        "PySide6.QtOpenGL",
        "PySide6.QtOpenGLWidgets",
        "PySide6.QtPrintSupport",
        "PySide6.QtHttpServer",
        "PySide6.QtGraphs",
    ],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="GOLDSAM_V2",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[
        # UPX bazi Qt DLL'lerinde calismayabiliyor — exclude (guvenli taraf)
        "Qt6Core.dll", "Qt6Gui.dll", "Qt6Widgets.dll", "Qt6Network.dll",
        "VCRUNTIME140.dll", "VCRUNTIME140_1.dll",
        "python312.dll",
    ],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
