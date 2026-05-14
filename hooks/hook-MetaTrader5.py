"""Custom PyInstaller hook for MetaTrader5.

PyInstaller'in collect_all'i MT5 _core.cp312-win_amd64.pyd binary'sini
otomatik almiyor. Bu hook .pyd ve .dll dosyalarini binaries listesine
zorla ekler.
"""
from PyInstaller.utils.hooks import (
    collect_data_files,
    collect_dynamic_libs,
    collect_submodules,
)

datas = collect_data_files("MetaTrader5", include_py_files=True)
binaries = collect_dynamic_libs("MetaTrader5")
hiddenimports = collect_submodules("MetaTrader5") + ["MetaTrader5._core"]
