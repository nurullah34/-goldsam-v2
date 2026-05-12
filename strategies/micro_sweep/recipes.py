"""Micro-Sweep — 27 bağımsız modül entry filter'ı.

Spec: STRATEGY_CATALOG.md
  PERFECT (11): MS-P01 → MS-P11
  ELITE   (7) : MS-E01 → MS-E07
  STRONG  (9) : MS-S01 → MS-S09

Her filtre `(ctx: dict) -> bool` döner.
Context keys (build by strategy.py):
  hour, s1, s3, s6, daily_bull, h1_bull, atr_pct, cum3, vol_ratio, recent_bear
"""
from __future__ import annotations

from typing import Callable, Dict


# ─── PERFECT TIER (%100 WR) ──────────────────────────────────────

def ms_p01(c: dict) -> bool:
    """UNION-7: hr∈{10,14,16,18} ∨ D_bull ∨ S3 ∨ atr_pct≤0.25"""
    return (
        c["hour"] in {10, 14, 16, 18}
        or c["daily_bull"]
        or c["s3"]
        or (c["atr_pct"] is not None and c["atr_pct"] <= 0.25)
    )


def ms_p02(c: dict) -> bool:
    """Daily-Bullish-Only"""
    return c["daily_bull"]


def ms_p03(c: dict) -> bool:
    """Hour 18 NY-PM"""
    return c["hour"] == 18


def ms_p04(c: dict) -> bool:
    """cum3 ≥ 0 ∧ D_bull"""
    return c["cum3"] >= 0 and c["daily_bull"]


def ms_p05(c: dict) -> bool:
    """Pure-S3 — sadece micro-sweep reclaim. Diğer setup'lar disable."""
    return c["s3"]


def ms_p06(c: dict) -> bool:
    """Hour 14 NY-Open"""
    return c["hour"] == 14


def ms_p07(c: dict) -> bool:
    """Hour 16 NY-Mid"""
    return c["hour"] == 16


def ms_p08(c: dict) -> bool:
    """TripleConfluence: hr∈[10..18] ∧ cum3≥0 ∧ (H1_bull ∨ D_bull)"""
    return (
        10 <= c["hour"] <= 18
        and c["cum3"] >= 0
        and (c["h1_bull"] or c["daily_bull"])
    )


def ms_p09(c: dict) -> bool:
    """LowVol-Only: atr_pct ≤ 0.25"""
    return c["atr_pct"] is not None and c["atr_pct"] <= 0.25


def ms_p10(c: dict) -> bool:
    """Hour 10 London-Mid"""
    return c["hour"] == 10


def ms_p11(c: dict) -> bool:
    """H1-Bullish-LowATR: H1_bull ∧ atr_pct ≤ 0.5"""
    return (
        c["h1_bull"]
        and c["atr_pct"] is not None
        and c["atr_pct"] <= 0.5
    )


# ─── ELITE TIER (%98.5+) ─────────────────────────────────────────

def ms_e01(c: dict) -> bool:
    """hr≥10 ∧ cum3≥0 ∧ tickV≥1.0×med20"""
    return c["hour"] >= 10 and c["cum3"] >= 0 and c["vol_ratio"] >= 1.0


def ms_e02(c: dict) -> bool:
    """hr∈[10..18] ∧ cum3≥0 ∧ tickV≥1.0"""
    return 10 <= c["hour"] <= 18 and c["cum3"] >= 0 and c["vol_ratio"] >= 1.0


def ms_e03(c: dict) -> bool:
    """(hr∈[10..18] ∨ S3 ∨ D_bull) ∧ ¬recent_bear"""
    return (
        (10 <= c["hour"] <= 18 or c["s3"] or c["daily_bull"])
        and not c["recent_bear"]
    )


def ms_e04(c: dict) -> bool:
    """hr≥10 ∧ tickV≥1.0"""
    return c["hour"] >= 10 and c["vol_ratio"] >= 1.0


def ms_e05(c: dict) -> bool:
    """(hr∈[10..18] ∧ cum3≥0) ∨ (D_bull ∧ ¬recent_bear)"""
    return (
        (10 <= c["hour"] <= 18 and c["cum3"] >= 0)
        or (c["daily_bull"] and not c["recent_bear"])
    )


def ms_e06(c: dict) -> bool:
    """(hr∈[10..18] ∨ D_bull) ∧ cum3≥0"""
    return (10 <= c["hour"] <= 18 or c["daily_bull"]) and c["cum3"] >= 0


def ms_e07(c: dict) -> bool:
    """(hr∈[10..18] ∧ cum3≥0) ∨ S3"""
    return (10 <= c["hour"] <= 18 and c["cum3"] >= 0) or c["s3"]


# ─── STRONG TIER (%98-98.5) ──────────────────────────────────────

def ms_s01(c: dict) -> bool:
    """(hr∈[10..18] ∨ S3) ∧ ¬recent_bear"""
    return (10 <= c["hour"] <= 18 or c["s3"]) and not c["recent_bear"]


def ms_s02(c: dict) -> bool:
    """hr∈[10..18] ∧ ¬recent_bear"""
    return 10 <= c["hour"] <= 18 and not c["recent_bear"]


def ms_s03(c: dict) -> bool:
    """hr∈[10..18] ∧ (cum3≥0 ∨ S3)"""
    return 10 <= c["hour"] <= 18 and (c["cum3"] >= 0 or c["s3"])


def ms_s04(c: dict) -> bool:
    """hr∈[11..18] ∧ ¬recent_bear"""
    return 11 <= c["hour"] <= 18 and not c["recent_bear"]


def ms_s05(c: dict) -> bool:
    """hr∈[10..18] ∨ S3   (R22 — en yüksek trade sayısı)"""
    return 10 <= c["hour"] <= 18 or c["s3"]


def ms_s06(c: dict) -> bool:
    """¬recent_bear ∧ (H1_bull ∨ D_bull)"""
    return (not c["recent_bear"]) and (c["h1_bull"] or c["daily_bull"])


def ms_s07(c: dict) -> bool:
    """(hr∈[10..18] ∧ cum3≥0) ∨ (S3 ∧ ¬recent_bear)"""
    return (
        (10 <= c["hour"] <= 18 and c["cum3"] >= 0)
        or (c["s3"] and not c["recent_bear"])
    )


def ms_s08(c: dict) -> bool:
    """(hr∈[10..18] ∨ S3) ∧ cum3≥0"""
    return (10 <= c["hour"] <= 18 or c["s3"]) and c["cum3"] >= 0


def ms_s09(c: dict) -> bool:
    """hr∈[10..18] ∧ cum3≥0   (en basit kural)"""
    return 10 <= c["hour"] <= 18 and c["cum3"] >= 0


# ─── Modül kaydı — priority order: PERFECT → ELITE → STRONG ──────
# Engine her tick'te bu sırayla tarar ve İLK eşleşen modülü işletir.

ModuleFn = Callable[[Dict], bool]


# (module_id, magic_offset, filter_fn)
# magic = MAGIC_BASE + offset. Her modüle benzersiz magic.
MODULES: list[tuple[str, int, ModuleFn]] = [
    # PERFECT (1-11)
    ("MS-P01", 1,  ms_p01),
    ("MS-P02", 2,  ms_p02),
    ("MS-P03", 3,  ms_p03),
    ("MS-P04", 4,  ms_p04),
    ("MS-P05", 5,  ms_p05),
    ("MS-P06", 6,  ms_p06),
    ("MS-P07", 7,  ms_p07),
    ("MS-P08", 8,  ms_p08),
    ("MS-P09", 9,  ms_p09),
    ("MS-P10", 10, ms_p10),
    ("MS-P11", 11, ms_p11),
    # ELITE (12-18)
    ("MS-E01", 12, ms_e01),
    ("MS-E02", 13, ms_e02),
    ("MS-E03", 14, ms_e03),
    ("MS-E04", 15, ms_e04),
    ("MS-E05", 16, ms_e05),
    ("MS-E06", 17, ms_e06),
    ("MS-E07", 18, ms_e07),
    # STRONG (19-27)
    ("MS-S01", 19, ms_s01),
    ("MS-S02", 20, ms_s02),
    ("MS-S03", 21, ms_s03),
    ("MS-S04", 22, ms_s04),
    ("MS-S05", 23, ms_s05),
    ("MS-S06", 24, ms_s06),
    ("MS-S07", 25, ms_s07),
    ("MS-S08", 26, ms_s08),
    ("MS-S09", 27, ms_s09),
]
