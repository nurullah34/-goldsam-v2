"""GoldSam Server — config sabitleri."""
from __future__ import annotations

import os
from pathlib import Path

# MT5 master (XM Demo — bar verisi için)
MT5_PATH = os.environ.get("MT5_PATH", r"C:\Program Files\metadinleme\terminal64.exe")
SYMBOL = os.environ.get("SYMBOL", "GOLD#")

# Engine
TICK_INTERVAL_SEC = int(os.environ.get("TICK_INTERVAL_SEC", "5"))
SIGNAL_TTL_SEC = int(os.environ.get("SIGNAL_TTL_SEC", "60"))  # eski sinyaller pending'den düşer

# API
API_HOST = os.environ.get("API_HOST", "0.0.0.0")
API_PORT = int(os.environ.get("API_PORT", "8000"))

# Server-side trail (lokal bot'un mevcut lifecycle'ı ile uyumlu)
DEFAULT_TRAIL_ACTIVATE_USD = 1.0
DEFAULT_SL_USD = 75.0

# DB
DATA_DIR = Path(os.environ.get("DATA_DIR", "data"))
DB_PATH = DATA_DIR / "goldsam.sqlite"
