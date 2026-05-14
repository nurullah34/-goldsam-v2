"""GoldSell — 10 filtre (config'e göre uygulanır).

Spec: goldsell deneme1/STRATEGY_SPEC.md §4
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

import pandas as pd


# Konfig sabitleri (configs.json'dan port)
GOLDEN_HOURS = {4, 5, 6, 8, 11, 12, 16, 17, 18, 21}  # UTC
PEAK_HOURS   = {16, 17, 18, 21}

WHITE_BROAD = {
    "PEC", "BSL_AR", "BSL_AR+RFAH", "RFAH+PEC", "RFAH+SCST",
    "MWA+SCST", "RFAH+MWA+SCST", "RFAH+SCST+PEC", "MWA+PEC",
    "BSL_AR+RFAH+SCST", "RFAH+BSL_AR", "BSL_AR+SCST",
}
WHITE_NARROW = {"PEC", "BSL_AR", "BSL_AR+RFAH", "RFAH+SCST", "RFAH+PEC"}

NAMED_HOUR_SETS = {"GOLDEN_HOURS": GOLDEN_HOURS, "PEAK_HOURS": PEAK_HOURS}
NAMED_WHITE_SETS = {"WHITE_BROAD": WHITE_BROAD, "WHITE_NARROW": WHITE_NARROW}


def hour_filter(bar_time_iso: str, allow_set_name: Optional[str]) -> bool:
    if not allow_set_name:
        return True
    allow = NAMED_HOUR_SETS.get(allow_set_name)
    if allow is None:
        return True
    try:
        h = datetime.fromisoformat(bar_time_iso).hour
    except Exception:
        return False
    return h in allow


def atr_filter(atr20_val: Optional[float], atr_min: Optional[float] = None,
               atr_max: Optional[float] = None) -> bool:
    if atr20_val is None:
        return False
    if atr_min is not None and atr20_val < atr_min:
        return False
    if atr_max is not None and atr20_val > atr_max:
        return False
    return True


def confluence_filter(triggered: list[str], conf_min: int = 1) -> bool:
    return len(triggered) >= conf_min


def whitelist_filter(composite_name: str, allowed_name: Optional[str]) -> bool:
    if not allowed_name:
        return True
    allowed = NAMED_WHITE_SETS.get(allowed_name)
    if allowed is None:
        return True
    return composite_name in allowed


def spread_filter(spread_points: int, max_points: int = 20) -> bool:
    return spread_points <= max_points


def range_z_filter(range_z50_val: Optional[float], min_z: float = 1.0) -> bool:
    if range_z50_val is None:
        return False
    return range_z50_val >= min_z


def vol_expansion_filter(atr5_val: Optional[float], atr50_val: Optional[float],
                         min_ratio: float = 1.3) -> bool:
    if atr5_val is None or atr50_val is None or atr50_val <= 0:
        return False
    return (atr5_val / atr50_val) >= min_ratio


def close_strength_filter(bar: dict, min_cs: float = 0.4) -> bool:
    rng = bar["high"] - bar["low"]
    if rng <= 0:
        return False
    cs = (bar["high"] - bar["close"]) / rng
    return cs >= min_cs


def setup_only_filter(composite: str, exact: str) -> bool:
    return composite == exact


def dow_filter(bar_time_iso: str, allowed_dows: Optional[list[int]]) -> bool:
    if not allowed_dows:
        return True
    try:
        return datetime.fromisoformat(bar_time_iso).weekday() in set(allowed_dows)
    except Exception:
        return False


# ───── Config — config dict'ten tüm filtreleri sırayla uygula ────

def pass_all_filters(bar_dict: dict, triggered: list[str], composite: str,
                     atr5: Optional[float], atr20: Optional[float],
                     atr50: Optional[float], range_z50: Optional[float],
                     spread_points: int, cfg: dict) -> bool:
    f = cfg.get("filters", {})

    if "allow_hours" in f and not hour_filter(bar_dict["time"], f["allow_hours"]):
        return False
    if "atr_min" in f or "atr_max" in f:
        if not atr_filter(atr20, f.get("atr_min"), f.get("atr_max")):
            return False
    if "conf_min" in f and not confluence_filter(triggered, int(f["conf_min"])):
        return False
    if "whitelist_combos" in f and not whitelist_filter(composite, f["whitelist_combos"]):
        return False
    if "spread_max_pts" in f and not spread_filter(spread_points, int(f["spread_max_pts"])):
        return False
    if "range_z_min" in f and not range_z_filter(range_z50, float(f["range_z_min"])):
        return False
    if "vol_expansion" in f and not vol_expansion_filter(atr5, atr50, float(f["vol_expansion"])):
        return False
    if "close_strength_min" in f and not close_strength_filter(bar_dict, float(f["close_strength_min"])):
        return False
    if "setup_only" in f and not setup_only_filter(composite, str(f["setup_only"])):
        return False
    if "dow_allow" in f and not dow_filter(bar_dict["time"], list(f["dow_allow"])):
        return False
    return True
