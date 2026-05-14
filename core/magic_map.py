"""Magic numara ↔ kart mapping.

VPS sunucusu ``Signal(magic=X)`` gönderir. Bot magic'e bakıp hangi UI
kartının ayarlarını (lot/SL/trail) kullanacağını burada bulur.

Numaralandırma şeması (CLAUDE.md):
  8T LONG:    20270001
  8T SHORT:   20270002
  MULTI100:   20270011 (M30), 20270012 (H2), 20270013 (H3), 20270014 (H4)
  MICRO-S:    20270101..20270127  (MAGIC_BASE=20270100 + offset 1..27)
  GOLDS:      20270200
  GENIS:      20270300
"""
from __future__ import annotations


CARD_8T_LONG   = "8T_LONG"
CARD_8T_SHORT  = "8T_SHORT"
CARD_MULTI100  = "MULTI100"
CARD_MICRO_S   = "MICRO_S"
CARD_GOLDS     = "GOLDS"
CARD_GENIS     = "GENIS"


def card_for_magic(magic: int) -> str | None:
    """Magic numarasından kart id'sine eşle. Tanınmıyorsa None."""
    m = int(magic)
    if m == 20270001:
        return CARD_8T_LONG
    if m == 20270002:
        return CARD_8T_SHORT
    if 20270011 <= m <= 20270014:
        return CARD_MULTI100
    if 20270101 <= m <= 20270199:
        return CARD_MICRO_S
    if m == 20270200:
        return CARD_GOLDS
    if m == 20270300:
        return CARD_GENIS
    return None


def label_for_magic(magic: int) -> str:
    """Log için kısa etiket."""
    m = int(magic)
    if m == 20270001:
        return "8T LONG"
    if m == 20270002:
        return "8T SHORT"
    if 20270011 <= m <= 20270014:
        tf = {20270011: "M30", 20270012: "H2",
              20270013: "H3", 20270014: "H4"}.get(m, "?")
        return f"MULTI100 {tf}"
    if 20270101 <= m <= 20270199:
        return f"MICRO-S P{m - 20270100:02d}"
    if m == 20270200:
        return "GOLDS"
    if m == 20270300:
        return "GENIS"
    return f"magic={m}"
