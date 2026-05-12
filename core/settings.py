"""Ayar persistence — settings.json APPDATA içinde."""
from __future__ import annotations

import json
import os
from copy import deepcopy
from pathlib import Path
from typing import Any


APP_DATA_DIR = Path(os.environ.get("APPDATA", str(Path.home()))) / "GOLDSAM_V2"
SETTINGS_FILE = APP_DATA_DIR / "settings.json"


_DEFAULT_STRAT = {
    "enabled":         False,
    "lot":             0.0,
    "sl_usd":          0.0,
    "avg_threshold_usd": None,   # None / 10 / 20 / 30 / 40
    "avg_lot":         None,
}

DEFAULTS: dict[str, Any] = {
    "version": 1,
    "strategies": {
        "8t_long":     deepcopy(_DEFAULT_STRAT),
        "8t_short":    deepcopy(_DEFAULT_STRAT),
        "multi100":    deepcopy(_DEFAULT_STRAT),
        "micro_sweep": deepcopy(_DEFAULT_STRAT),
    },
    "kasa": {
        "concurrent_limit":      999,    # 3 / 6 / 10 / 999=sınırsız
        "weekend_protection":    False,
        "manual_positions_trail": False,
        "trail_activate_usd":    1,      # 1 / 2 / 3 / 4 / 5
    },
}


def _merge_defaults(loaded: Any, defaults: Any) -> Any:
    """Eksik key'leri default'tan doldur — geriye dönük uyum."""
    if not isinstance(defaults, dict):
        return loaded if loaded is not None else defaults
    result = deepcopy(defaults)
    if not isinstance(loaded, dict):
        return result
    for k, v in loaded.items():
        if k in result:
            result[k] = _merge_defaults(v, result[k])
        else:
            result[k] = v
    return result


def load() -> dict:
    """settings.json'u oku. Yoksa veya bozuksa default döner."""
    if not SETTINGS_FILE.exists():
        return deepcopy(DEFAULTS)
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return _merge_defaults(data, DEFAULTS)
    except Exception:
        return deepcopy(DEFAULTS)


def save(settings: dict) -> tuple[bool, str]:
    """settings.json'a yaz. (success, msg) döner."""
    try:
        APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2, ensure_ascii=False)
        return True, str(SETTINGS_FILE)
    except Exception as e:
        return False, str(e)
