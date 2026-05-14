# -*- mode: python ; coding: utf-8 -*-
"""GOLDSAM V2 — PyInstaller spec (tek dosya .exe, slim).

Cikti: dist/GOLDSAM_V2.exe (yaklasik 80-120 MB).
Build: python -m PyInstaller --clean --noconfirm GOLDSAM_V2.spec
"""
from pathlib import Path
from PyInstaller.utils.hooks import collect_all, collect_dynamic_libs

ROOT = Path(SPECPATH).resolve()

datas = []
binaries = []
hiddenimports = []

# certifi (HTTPS sertifikalari), cryptography (Fernet), numpy (MT5 dependency)
# numpy KRITIK: MT5 paketi numpy ile compile edilmis, eksik olursa
# ImportError: numpy._core.multiarray failed to import
for pkg in ("certifi", "cryptography", "numpy"):
    try:
        ds, bs, hs = collect_all(pkg)
        datas += ds
        binaries += bs
        hiddenimports += hs
    except Exception:
        pass

# MetaTrader5 — MANUEL paketleme (collect_all _core.pyd'yi atlar)
# .pyd ve .dll dosyalarini binaries'e ekle, paket klasorunun tum icerigi
# datas'a (collect_data_files include_py_files=True).
try:
    import MetaTrader5 as _mt5_mod
    _mt5_dir = Path(_mt5_mod.__file__).resolve().parent

    # Tum .py dosyalari (init dahil)
    for _py in _mt5_dir.glob("*.py"):
        datas.append((str(_py), "MetaTrader5"))

    # Tum .pyd C extension'lar (KRITIK!)
    for _pyd in _mt5_dir.glob("*.pyd"):
        binaries.append((str(_pyd), "MetaTrader5"))

    # Yan DLL'ler varsa
    for _dll in _mt5_dir.glob("*.dll"):
        binaries.append((str(_dll), "MetaTrader5"))

    print(f"[SPEC] MetaTrader5 klasoru: {_mt5_dir}")
    print(f"[SPEC] .py: {len(list(_mt5_dir.glob('*.py')))}, "
          f".pyd: {len(list(_mt5_dir.glob('*.pyd')))}, "
          f".dll: {len(list(_mt5_dir.glob('*.dll')))}")
except Exception as _e:
    print(f"[SPEC] MT5 paketleme HATA: {_e}")

# PySide6 — sadece kullandigimiz modulleri elle ekle
hiddenimports += [
    "PySide6.QtCore",
    "PySide6.QtGui",
    "PySide6.QtWidgets",
    "shiboken6",
    "MetaTrader5",
    "MetaTrader5._core",
    # numpy 2.x'in C extension katmanlari
    "numpy",
    "numpy._core",
    "numpy._core.multiarray",
    "numpy._core.umath",
    "numpy._core._methods",
    "numpy._core._multiarray_umath",
    "numpy._core._exceptions",
    "numpy._core._dtype",
    "numpy._core._add_newdocs",
    "numpy._core._add_newdocs_scalars",
    "numpy._core._asarray",
    "numpy._core._type_aliases",
    "numpy._core.numeric",
]


a = Analysis(
    [str(ROOT / "main.py")],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[str(ROOT / "hooks")],   # custom hook'lar (hook-MetaTrader5.py)
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "_server",
        "strategies",
        "pytest", "pytest_qt", "hypothesis",
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

# ONEDIR MODE: tek dosya yerine dist/GOLDSAM_V2/ klasoru olusturur.
# - DLL'ler exe yaninda durur (python312.dll, _internal/...)
# - %TEMP%\_MEI extract YOK -> "Failed to load Python DLL" hatasi MIMARI
#   olarak imkansiz
# - Aciliş çok hızlı (extract yok)
# - Self-update: zip-based (klasor icerigi degistir)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,   # KRITIK: binaries COLLECT'e gider, exe içine değil
    name="GOLDSAM_V2",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,               # onedir'de UPX'e gerek yok (klasor zaten ayri)
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="GOLDSAM_V2",   # klasor adi: dist/GOLDSAM_V2/
)
