import socket
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QLocale, QTimer
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QPushButton, QCheckBox, QDoubleSpinBox, QRadioButton, QButtonGroup,
    QPlainTextEdit, QMessageBox, QDialog, QTableWidget, QTableWidgetItem,
    QComboBox, QHeaderView, QLineEdit, QScrollArea, QApplication
)

from core import license_store, settings as user_settings
from core.agent_worker import AgentWorker
from core.account_lock import bind as lock_bind, get_locked_info, is_bound, verify as lock_verify
from core.device_id import get_display_name, get_device_fingerprint
from core.kriptoly_client import KriptolyClient
from core.magic_map import (
    CARD_8T_LONG, CARD_8T_SHORT, CARD_GENIS, CARD_GOLDS, CARD_MICRO_S,
    CARD_MULTI100,
)
from core.mt5_connector import MT5Connector
from core.position_monitor import PositionMonitor
from core.strategy_engine import StrategyEngine
from core.trade_executor import TradeExecutor
from core.updater import check_and_update
from version import VERSION, APP_NAME


# Magic numara aralıkları (kart ↔ magic eşlemesi core/magic_map.py'de)
MAGIC_8T_LONG  = 20270001
MAGIC_8T_SHORT = 20270002
MULTI100_MAGICS = {20270011, 20270012, 20270013, 20270014}
MICRO_S_MAGICS  = {20270100 + i for i in range(1, 28)}  # 20270101..20270127
MAGIC_GOLDS    = 20270200
MAGIC_GENIS    = 20270300


BASE_DIR = Path(__file__).resolve().parent


DOT_OFF = "#8b949e"
DOT_ON = "#3fb950"
DOT_ERR = "#f85149"


STYLE = """
QMainWindow { background-color: #0d1117; }
QWidget { color: #e6edf3; font-family: 'Segoe UI', Arial; font-size: 13px; }

QFrame#TopStatus {
    background-color: #161b22;
    border: 1px solid #30363d;
    border-radius: 8px;
}
QLabel#StatusLabel { padding: 6px 12px; }
QLabel#StatusDot   { font-size: 16px; }

QFrame#StratCard {
    background-color: #161b22;
    border: 1px solid #30363d;
    border-radius: 10px;
}
QFrame#AvgBox {
    background-color: #0d1117;
    border: 1px solid #c9d1d9;
    border-radius: 8px;
}
QFrame#KasaBox {
    background-color: transparent;
    border: none;
}
QFrame#KasaInnerBox {
    background-color: #0d1117;
    border: 1px solid #30363d;
    border-radius: 8px;
}
QLabel#KasaRowLabel {
    color: #c9d1d9;
    font-weight: 600;
    padding-right: 8px;
}
QLabel#KasaHint {
    color: #8b949e;
    font-style: italic;
}
QCheckBox#StratCheckbox {
    font-size: 15px;
    font-weight: 600;
    spacing: 10px;
    color: #e6edf3;
}
QCheckBox#StratCheckbox::indicator {
    width: 20px;
    height: 20px;
    border: 1px solid #30363d;
    border-radius: 4px;
    background-color: #0d1117;
}
QCheckBox#StratCheckbox::indicator:checked {
    background-color: #238636;
    border-color: #2ea043;
    image: none;
}
QCheckBox#StratCheckbox::indicator:hover {
    border-color: #58a6ff;
}
QLabel#FieldLabel { color: #8b949e; }
QDoubleSpinBox#NumInput {
    background-color: #0d1117;
    border: 1px solid #30363d;
    border-radius: 6px;
    padding: 4px 8px;
    color: #e6edf3;
    min-width: 90px;
}
QDoubleSpinBox#NumInput:focus { border-color: #58a6ff; }
QRadioButton#AvgRadio {
    color: #c9d1d9;
    padding: 2px 6px;
    spacing: 6px;
}
QRadioButton#AvgRadio::indicator {
    width: 14px;
    height: 14px;
    border: 1px solid #30363d;
    border-radius: 7px;
    background-color: #0d1117;
}
QRadioButton#AvgRadio::indicator:checked {
    background-color: #238636;
    border-color: #2ea043;
}
QRadioButton#AvgRadio::indicator:hover { border-color: #58a6ff; }

/* Yeşil noktalı checkbox — Kasa paneli ON/OFF göstergesi */
QCheckBox#DotCheck {
    color: #c9d1d9;
    padding: 2px 6px;
    spacing: 6px;
}
QCheckBox#DotCheck::indicator {
    width: 14px;
    height: 14px;
    border: 1px solid #30363d;
    border-radius: 7px;
    background-color: #0d1117;
}
QCheckBox#DotCheck::indicator:checked {
    background-color: #238636;
    border-color: #2ea043;
}
QCheckBox#DotCheck::indicator:hover { border-color: #58a6ff; }

QPushButton {
    background-color: #21262d;
    border: 1px solid #30363d;
    border-radius: 6px;
    padding: 8px 18px;
    color: #c9d1d9;
}
QPushButton:hover    { background-color: #30363d; border-color: #58a6ff; }
QPushButton:pressed  { background-color: #1f6feb; }

QPushButton#StartBtn { background-color: #238636; border-color: #2ea043; color: white; }
QPushButton#StartBtn:hover { background-color: #2ea043; }
QPushButton#StopBtn  { background-color: #6e7681; border-color: #8b949e; color: white; }
QPushButton#ExitBtn  { background-color: #da3633; border-color: #f85149; color: white; }

QPlainTextEdit#LogText {
    background-color: #010409;
    color: #7d8590;
    border: 1px solid #21262d;
    border-radius: 6px;
    font-family: 'Consolas','Courier New',monospace;
    padding: 6px;
}
"""


def _spin(mn: float, mx: float, step: float, value: float, decimals: int = 2) -> QDoubleSpinBox:
    s = QDoubleSpinBox()
    s.setObjectName("NumInput")
    s.setLocale(QLocale.c())
    s.setDecimals(decimals)
    s.setRange(mn, mx)
    s.setSingleStep(step)
    s.setValue(value)
    s.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons)
    s.setAlignment(Qt.AlignmentFlag.AlignRight)
    return s


def _field_row(label_text: str, widget) -> QHBoxLayout:
    row = QHBoxLayout()
    row.setSpacing(8)
    lbl = QLabel(label_text)
    lbl.setObjectName("FieldLabel")
    lbl.setMinimumWidth(60)
    row.addWidget(lbl)
    row.addWidget(widget)
    row.addStretch(1)
    return row


class ReportDialog(QDialog):
    """Detaylı işlem listesi — her trade için giriş/çıkış saati + strateji + P/L."""

    GROUPS = {
        "8T":       {20270001, 20270002},
        "MULTI100": {20270011, 20270012, 20270013, 20270014},
        "MICRO-S":  set(range(20270101, 20270128)),
        "GOLDS":    {20270200},
        "GENIS":    {20270300},
    }
    GROUPS["Hepsi"] = (
        GROUPS["8T"] | GROUPS["MULTI100"] | GROUPS["MICRO-S"]
        | GROUPS["GOLDS"] | GROUPS["GENIS"]
    )

    @staticmethod
    def _strategy_name(magic: int) -> str:
        if magic == 0:        return "MANUEL"
        if magic == 20270001: return "8T LONG"
        if magic == 20270002: return "8T SHORT"
        if magic == 20270011: return "MULTI100 M30"
        if magic == 20270012: return "MULTI100 H2"
        if magic == 20270013: return "MULTI100 H3"
        if magic == 20270014: return "MULTI100 H4"
        if 20270101 <= magic <= 20270127:
            off = magic - 20270100
            if 1 <= off <= 11:  return f"MS-P{off:02d}"
            if 12 <= off <= 18: return f"MS-E{off-11:02d}"
            if 19 <= off <= 27: return f"MS-S{off-18:02d}"
        if magic == 20270200: return "GOLDS"
        if magic == 20270300: return "GENIS"
        return f"#{magic}"

    def __init__(self, parent=None, default_period: int = 7,
                 default_group: str = "Hepsi") -> None:
        super().__init__(parent)
        self.setWindowTitle("Detaylı İşlem Raporu — İşlem Listesi")
        self.resize(960, 720)
        self.setStyleSheet(STYLE + """
            QDialog { background-color: #0d1117; }
            QTableWidget {
                background-color: #161b22;
                alternate-background-color: #1c2128;
                gridline-color: #30363d;
                color: #e6edf3;
                font-family: 'Consolas','Courier New',monospace;
                selection-background-color: #1f6feb;
                selection-color: #ffffff;
            }
            QTableCornerButton::section {
                background-color: #21262d;
                border: 1px solid #30363d;
            }
            QHeaderView::section {
                background-color: #21262d;
                color: #c9d1d9;
                padding: 4px;
                border: 1px solid #30363d;
                font-weight: 600;
            }
            QComboBox {
                background-color: #0d1117;
                border: 1px solid #30363d;
                border-radius: 6px;
                padding: 4px 8px;
                color: #e6edf3;
                min-width: 120px;
            }
            QComboBox:hover { border-color: #58a6ff; }
            QComboBox::drop-down {
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 22px;
                border-left: 1px solid #30363d;
            }
            QComboBox QAbstractItemView {
                background-color: #161b22;
                color: #e6edf3;
                selection-background-color: #1f6feb;
                selection-color: #ffffff;
                border: 1px solid #30363d;
                outline: 0;
            }
            QComboBox QAbstractItemView::item {
                min-height: 24px;
                padding: 4px 8px;
            }
            QComboBox QAbstractItemView::item:hover {
                background-color: #21262d;
            }
            QScrollBar:vertical {
                background-color: #0d1117;
                width: 12px;
                border: none;
            }
            QScrollBar::handle:vertical {
                background-color: #30363d;
                min-height: 24px;
                border-radius: 6px;
            }
            QScrollBar::handle:vertical:hover { background-color: #484f58; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
        """)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        # Filtre satırı
        flt = QHBoxLayout()
        flt.setSpacing(10)

        flt.addWidget(QLabel("Strateji:"))
        self.cb_group = QComboBox()
        # "Tümü" = bot + manuel, "Hepsi" = sadece bot, "Manuel" = sadece manuel
        for gname in ("Tümü", "Hepsi (Bot)", "8T", "MULTI100", "MICRO-S", "GOLDS", "GENIS", "Manuel"):
            self.cb_group.addItem(gname)
        # default_group eski isimle gelirse uyumlu kal
        compat = {"Hepsi": "Hepsi (Bot)"}.get(default_group, default_group)
        idx = self.cb_group.findText(compat)
        if idx < 0:
            idx = self.cb_group.findText("Tümü")
        self.cb_group.setCurrentIndex(max(idx, 0))
        flt.addWidget(self.cb_group)

        flt.addSpacing(20)
        flt.addWidget(QLabel("Periyod:"))
        self.period_group = QButtonGroup(self)
        period_options = [(1, "Bugün"), (7, "Bu Hafta"), (30, "Son 30 Gün"), (90, "Son 90 Gün")]
        for pid, txt in period_options:
            rb = QRadioButton(txt)
            rb.setObjectName("AvgRadio")
            if pid == default_period:
                rb.setChecked(True)
            self.period_group.addButton(rb, pid)
            flt.addWidget(rb)

        flt.addStretch(1)
        refresh_btn = QPushButton("Yenile")
        refresh_btn.clicked.connect(self._refresh)
        flt.addWidget(refresh_btn)
        root.addLayout(flt)

        # Başlık + özet
        self.summary_lbl = QLabel("—")
        self.summary_lbl.setStyleSheet(
            "color: #58a6ff; font-weight: 600; padding: 4px;"
        )
        root.addWidget(self.summary_lbl)

        # Her satır = bir trade — entry / exit / süre / strateji / magic / yön / lot / P/L
        self.table = QTableWidget(0, 8, self)
        self.table.setHorizontalHeaderLabels(
            ["Giriş", "Çıkış", "Süre", "Strateji", "Magic", "Yön", "Lot", "P/L ($)"]
        )
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(7, QHeaderView.ResizeMode.ResizeToContents)
        self.table.verticalHeader().setDefaultSectionSize(22)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)
        root.addWidget(self.table, stretch=1)

        # Buttonlar — yenile + kapat
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        close_btn = QPushButton("Kapat")
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        root.addLayout(btn_row)

        # Auto-refresh on selector change
        self.cb_group.currentTextChanged.connect(lambda _: self._refresh())
        self.period_group.idToggled.connect(
            lambda _id, checked: checked and self._refresh()
        )

        # İlk yükleme
        self._refresh()

    def _period_range(self) -> tuple[int, str]:
        import time as _time
        pid = self.period_group.checkedId()
        now = int(_time.time())
        if pid == 1:
            today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            return int(today.timestamp()), "Bugün"
        elif pid == 30:
            return now - 86400 * 30, "Son 30 Gün"
        elif pid == 90:
            return now - 86400 * 90, "Son 90 Gün"
        else:
            now_dt = datetime.now()
            monday = now_dt - timedelta(days=now_dt.weekday())
            monday = monday.replace(hour=0, minute=0, second=0, microsecond=0)
            return int(monday.timestamp()), "Bu Hafta"

    def _refresh(self) -> None:
        try:
            import MetaTrader5 as mt5_mod
        except ImportError:
            self.summary_lbl.setText("MT5 modülü yok.")
            return

        import time as _time
        from collections import defaultdict
        from PySide6.QtGui import QColor

        GREEN = QColor("#3fb950")
        RED   = QColor("#f85149")
        DIM   = QColor("#8b949e")

        gname = self.cb_group.currentText()
        bot_magics = self.GROUPS["Hepsi"]  # tüm bot magics

        def _accept(mg: int) -> bool:
            if gname == "Tümü":
                return True
            if gname == "Hepsi (Bot)":
                return mg in bot_magics
            if gname == "Manuel":
                return mg not in bot_magics  # bot dışı her şey (genelde magic=0)
            # Belirli grup (8T / MULTI100 / MICRO-S)
            return mg in self.GROUPS.get(gname, set())

        start, label = self._period_range()
        now = int(_time.time())

        # Geniş aralık çek (entry ile exit farklı günlerde olabilir) — sonra filtrele
        try:
            deals = mt5_mod.history_deals_get(
                max(0, start - 86400 * 7), now + 60
            )
        except Exception:
            deals = None
        if deals is None:
            deals = []

        # position_id bazlı grupla — TÜM deal'lar dahil (magic filter SONRA).
        # SL ile kapanan OUT deal'ların magic'i 0 olabiliyor → IN deal'ın
        # magic'ini ve/veya comment prefix'ini kullan.
        per_pos: dict[int, dict] = defaultdict(
            lambda: {"entry": None, "exit": None, "pnl_sum": 0.0,
                     "magic": 0, "comment": "", "side": "?", "volume": 0.0}
        )

        for d in deals:
            try:
                pid = int(d.position_id)
            except Exception:
                continue
            mg = int(getattr(d, "magic", 0) or 0)
            cmt = str(getattr(d, "comment", "") or "")
            entry_type = getattr(d, "entry", None)
            try:
                t = datetime.fromtimestamp(int(d.time))
            except Exception:
                continue

            rec = per_pos[pid]
            # Magic ve comment: IN deal'dan al; yoksa herhangi non-zero magic
            if entry_type == mt5_mod.DEAL_ENTRY_IN:
                rec["magic"] = mg
                if cmt:
                    rec["comment"] = cmt
            elif rec["magic"] == 0 and mg != 0:
                rec["magic"] = mg
            if not rec["comment"] and cmt:
                rec["comment"] = cmt

            if rec["volume"] == 0.0:
                rec["volume"] = float(getattr(d, "volume", 0) or 0)

            if entry_type == mt5_mod.DEAL_ENTRY_IN:
                dtype = int(getattr(d, "type", -1))
                rec["entry"] = t
                rec["side"] = (
                    "BUY"  if dtype == mt5_mod.DEAL_TYPE_BUY  else
                    "SELL" if dtype == mt5_mod.DEAL_TYPE_SELL else "?"
                )
            elif entry_type in (mt5_mod.DEAL_ENTRY_OUT, mt5_mod.DEAL_ENTRY_INOUT):
                if rec["exit"] is None or t > rec["exit"]:
                    rec["exit"] = t

            # MT5 "Profit" kolonu ile birebir olsun: sadece profit (komisyon + swap hariç)
            rec["pnl_sum"] += float(getattr(d, "profit", 0) or 0)

        # Magic fallback'i (comment'ten çıkar) — sonra _accept ile filtre
        def _resolve_magic(mg: int, cmt: str) -> int:
            if mg != 0:
                return mg
            if cmt.startswith("8T_LONG"):  return 20270001
            if cmt.startswith("8T_SHORT"): return 20270002
            if cmt.startswith("M100_M30"): return 20270011
            if cmt.startswith("M100_H2"):  return 20270012
            if cmt.startswith("M100_H3"):  return 20270013
            if cmt.startswith("M100_H4"):  return 20270014
            if cmt.startswith(("MS-", "MS_")):
                head = cmt.split("_", 1)[0]
                try:
                    tier = head[3]
                    num = int(head[4:6])
                    if tier == "P" and 1 <= num <= 11: return 20270100 + num
                    if tier == "E" and 1 <= num <= 7:  return 20270100 + 11 + num
                    if tier == "S" and 1 <= num <= 9:  return 20270100 + 18 + num
                except Exception:
                    pass
                return 20270101  # generic MICRO-S
            if cmt.startswith("GS_"):     return 20270200
            if cmt.startswith("GENIS_"):  return 20270300
            return 0

        for pid, rec in per_pos.items():
            rec["magic"] = _resolve_magic(rec["magic"], rec["comment"])

        # Şimdi user filter'ını uygula — magic doğru sınıflandırılmış pozisyonlar
        per_pos = {pid: rec for pid, rec in per_pos.items() if _accept(rec["magic"])}

        # Period başlangıç/bitiş datetime (local TZ-naive)
        period_start_dt = datetime.fromtimestamp(start)
        period_end_dt = datetime.fromtimestamp(now + 60)

        trades = []
        for pid, rec in per_pos.items():
            if rec["entry"] is None or rec["exit"] is None:
                continue
            # Kapanış zamanı periyod içinde olmalı (genel beklenti)
            if not (period_start_dt <= rec["exit"] <= period_end_dt):
                continue
            trades.append({
                "pid": pid,
                "entry": rec["entry"],
                "exit": rec["exit"],
                "duration_s": int((rec["exit"] - rec["entry"]).total_seconds()),
                "strategy": self._strategy_name(rec["magic"]),
                "magic": int(rec["magic"]),
                "side": rec["side"],
                "volume": rec["volume"],
                "pnl": rec["pnl_sum"],
                "open": False,
            })

        # AÇIK POZİSYONLAR — mt5.positions_get
        try:
            open_positions = mt5_mod.positions_get()
        except Exception:
            open_positions = None
        if open_positions:
            now_dt = datetime.fromtimestamp(now)
            for p in open_positions:
                mg = int(getattr(p, "magic", 0) or 0)
                if not _accept(mg):
                    continue
                try:
                    p_time = datetime.fromtimestamp(int(p.time))
                except Exception:
                    p_time = now_dt
                side = "BUY" if int(p.type) == mt5_mod.ORDER_TYPE_BUY else "SELL"
                pnl_open = float(getattr(p, "profit", 0) or 0)
                trades.append({
                    "pid": int(p.ticket),
                    "entry": p_time,
                    "exit": now_dt,  # şu an, henüz kapanmadı
                    "duration_s": int((now_dt - p_time).total_seconds()),
                    "strategy": self._strategy_name(mg),
                    "magic": mg,
                    "side": side,
                    "volume": float(getattr(p, "volume", 0) or 0),
                    "pnl": pnl_open,
                    "open": True,
                })

        trades.sort(key=lambda t: t["entry"], reverse=True)  # en yeni üstte

        # Özet — kapalı vs açık ayrımı
        closed_trades = [t for t in trades if not t.get("open")]
        open_trades = [t for t in trades if t.get("open")]
        n_closed = len(closed_trades)
        w_total = sum(1 for t in closed_trades if t["pnl"] > 0.001)
        l_total = sum(1 for t in closed_trades if t["pnl"] < -0.001)
        net_total = sum(t["pnl"] for t in closed_trades)
        wr_total = (100.0 * w_total / n_closed) if n_closed > 0 else 0.0
        sign = "+" if net_total >= 0 else ""
        open_pnl = sum(t["pnl"] for t in open_trades)
        open_sign = "+" if open_pnl >= 0 else ""
        open_part = (
            f"   |   🟢 Açık: {len(open_trades)} pozisyon  ({open_sign}${open_pnl:,.2f})"
            if open_trades else ""
        )
        self.summary_lbl.setText(
            f"📊 {gname} — {label}  |  {n_closed} kapalı işlem  |  "
            f"{w_total}W  {l_total}L  |  Net {sign}${net_total:,.2f}  |  "
            f"WR %{wr_total:.2f}{open_part}"
        )

        # Tablo doldur
        def _dur_text(secs: int) -> str:
            if secs < 0:
                return "—"
            if secs < 60:
                return f"{secs}sn"
            mins = secs // 60
            if mins < 60:
                return f"{mins}dk"
            h = mins // 60
            rem = mins % 60
            return f"{h}sa {rem:02d}dk"

        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(trades))
        from PySide6.QtGui import QBrush
        OPEN_BG = QBrush(QColor("#1f2d3d"))  # açık pozisyon için hafif farklı zemin

        for row, t in enumerate(trades):
            is_open = bool(t.get("open"))
            entry_str = t["entry"].strftime("%Y-%m-%d %H:%M:%S")
            exit_str  = "🟢 AÇIK" if is_open else t["exit"].strftime("%Y-%m-%d %H:%M:%S")
            dur_str   = _dur_text(t["duration_s"]) + (" (sürüyor)" if is_open else "")
            pnl_sign  = "+" if t["pnl"] >= 0 else ""
            pnl_label = f"{pnl_sign}${t['pnl']:,.2f}"
            pnl_str   = f"{pnl_label} ●" if is_open else pnl_label
            vol_str   = f"{t['volume']:.2f}"

            magic_str = str(t.get("magic", 0))
            cells = [
                (entry_str, Qt.AlignmentFlag.AlignCenter, None),
                (exit_str,  Qt.AlignmentFlag.AlignCenter,
                    GREEN if is_open else None),
                (dur_str,   Qt.AlignmentFlag.AlignCenter, DIM),
                (t["strategy"],
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, None),
                (magic_str, Qt.AlignmentFlag.AlignCenter, DIM),
                (t["side"], Qt.AlignmentFlag.AlignCenter,
                    GREEN if t["side"] == "BUY" else (RED if t["side"] == "SELL" else None)),
                (vol_str, Qt.AlignmentFlag.AlignCenter, DIM),
                (pnl_str,
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                    GREEN if t["pnl"] > 0.001 else (RED if t["pnl"] < -0.001 else None)),
            ]
            for col, (val, align, color) in enumerate(cells):
                it = QTableWidgetItem(val)
                it.setTextAlignment(align)
                if color is not None:
                    it.setForeground(color)
                if is_open:
                    it.setBackground(OPEN_BG)
                self.table.setItem(row, col, it)
        self.table.setSortingEnabled(True)
        # Varsayılan: Giriş'e göre azalan (en yeni üstte)
        self.table.sortItems(0, Qt.SortOrder.DescendingOrder)


class StrategyCard(QFrame):
    """Bir stratejinin UI kartı + ayar okuma."""

    def __init__(self, title: str, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("StratCard")
        # 4 kart birebir aynı boyutta görünsün — fixed height (wrapped text dahil)
        self.setFixedHeight(130)

        self.chk = QCheckBox(title)
        self.chk.setObjectName("StratCheckbox")
        # Sabit genişlik — 4 kart hizalansın (en uzun başlık MULTI100)
        self.chk.setMinimumWidth(110)

        self.lot_input = _spin(0.00, 100.00, 0.01, 0.00)
        self.sl_input = _spin(0.00, 10000.00, 5.00, 0.00)
        self.avg_lot_input = _spin(0.00, 100.00, 0.01, 0.00)
        self.avg_group = QButtonGroup(self)

        self._build()

    def _build(self) -> None:
        h = QHBoxLayout(self)
        h.setContentsMargins(14, 10, 14, 10)
        h.setSpacing(14)

        # Chk vertical-center'a zorlanır (stretch'li wrapper)
        chk_wrap = QVBoxLayout()
        chk_wrap.setContentsMargins(0, 0, 0, 0)
        chk_wrap.addStretch(1)
        chk_wrap.addWidget(self.chk)
        chk_wrap.addStretch(1)
        h.addLayout(chk_wrap)
        h.addSpacing(12)

        left = QVBoxLayout()
        left.setSpacing(6)
        left.addStretch(1)
        left.addLayout(_field_row("Lot:", self.lot_input))
        left.addLayout(_field_row("SL ($):", self.sl_input))
        left.addStretch(1)
        h.addLayout(left)

        h.addSpacing(16)

        avg_box = QFrame()
        avg_box.setObjectName("AvgBox")
        right = QVBoxLayout(avg_box)
        right.setContentsMargins(10, 8, 10, 8)
        right.setSpacing(6)
        right.addStretch(1)

        avg_label = QLabel("Açılan işlemden kaç dolar düşerse bir işlem daha açılsın:")
        avg_label.setObjectName("FieldLabel")
        avg_label.setWordWrap(True)
        right.addWidget(avg_label)

        radio_row = QHBoxLayout()
        radio_row.setSpacing(4)
        for amount in [10, 20, 30, 40]:
            rb = QRadioButton(f"${amount}")
            rb.setObjectName("AvgRadio")
            self.avg_group.addButton(rb, amount)
            radio_row.addWidget(rb)
        radio_row.addSpacing(10)
        avg_lot_label = QLabel("Lot:")
        avg_lot_label.setObjectName("FieldLabel")
        radio_row.addWidget(avg_lot_label)
        radio_row.addWidget(self.avg_lot_input)
        radio_row.addStretch(1)
        right.addLayout(radio_row)
        right.addStretch(1)

        h.addWidget(avg_box, stretch=1)

    def settings(self) -> dict:
        avg_id = self.avg_group.checkedId()
        return {
            "enabled": self.chk.isChecked(),
            "lot": self.lot_input.value(),
            "sl_usd": self.sl_input.value(),
            "avg_threshold_usd": float(avg_id) if avg_id > 0 else None,
            "avg_lot": self.avg_lot_input.value() if self.avg_lot_input.value() > 0 else None,
        }

    def load_settings(self, data: dict) -> None:
        """Kaydedilmiş ayardan widget'ları doldur (settings.json'dan açılışta)."""
        self.chk.setChecked(bool(data.get("enabled", False)))
        self.lot_input.setValue(float(data.get("lot", 0.0) or 0.0))
        self.sl_input.setValue(float(data.get("sl_usd", 0.0) or 0.0))
        self.avg_lot_input.setValue(float(data.get("avg_lot", 0.0) or 0.0))
        avg_thr = data.get("avg_threshold_usd")
        if avg_thr in (10, 20, 30, 40, 10.0, 20.0, 30.0, 40.0):
            target_id = int(avg_thr)
            for btn in self.avg_group.buttons():
                if self.avg_group.id(btn) == target_id:
                    btn.setChecked(True)
                    break


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} v{VERSION}")
        self.resize(900, 780)
        self.setStyleSheet(STYLE)

        # Backend
        self.mt5 = MT5Connector()
        self.executor = TradeExecutor(log=self._log_msg)
        self.monitor = PositionMonitor(log=self._log_msg, symbol="GOLD#")
        self.engine = StrategyEngine(log=self._log_msg)
        self.client = KriptolyClient(log=self._log_msg)
        self.engine.set_client(self.client)
        self.engine.on_signal = lambda sig, strat: self.executor.execute(sig)
        self.worker: Optional[AgentWorker] = None
        self._account_locked: bool = False  # Lock doğrulamadan bot başlamaz
        self._license_ok: bool = False      # Lisans doğrulanmadan bot başlamaz
        # Heartbeat — 60 sn'de bir VPS'e durum bildir
        self._hb_timer: Optional[QTimer] = None

        # Strateji kartları
        self.card_8t_long = StrategyCard("8T LONG")
        self.card_8t_short = StrategyCard("8T SHORT")
        self.card_multi = StrategyCard("MULTI100")
        self.card_micro = StrategyCard("MICRO-S")
        self.card_goldsell = StrategyCard("GOLDS")
        self.card_genis = StrategyCard("GENIS")

        # UI element referansları
        self._dot_mt5: Optional[QLabel] = None
        self._dot_bot: Optional[QLabel] = None
        self._log: Optional[QPlainTextEdit] = None
        self._start_btn: Optional[QPushButton] = None
        self._stop_btn: Optional[QPushButton] = None
        self._symbol_label: Optional[QLabel] = None
        self._detected_symbol: Optional[str] = None
        self._kasa_concurrent_group: Optional[QButtonGroup] = None
        self._kasa_weekend_chk: Optional[QCheckBox] = None
        self._kasa_trail_long_chk: Optional[QCheckBox] = None
        self._kasa_trail_short_chk: Optional[QCheckBox] = None
        self._kasa_trail_long_input: Optional[QDoubleSpinBox] = None
        self._kasa_trail_short_input: Optional[QDoubleSpinBox] = None
        # Stats + varlık paneli
        self._stats_8t: Optional[QLabel] = None
        self._stats_multi: Optional[QLabel] = None
        self._stats_micro: Optional[QLabel] = None
        self._stats_goldsell: Optional[QLabel] = None
        self._stats_genis: Optional[QLabel] = None
        self._stats_manual: Optional[QLabel] = None
        self._stats_header: Optional[QLabel] = None
        self._stats_period_group: Optional[QButtonGroup] = None
        self._varlik_label: Optional[QLabel] = None
        self._stats_timer: Optional[QTimer] = None

        # Ana içerik (root) — küçük ekranlarda scroll yapacak QScrollArea içine
        # konuluyor ki 6 kart yan yana sığmazsa kullanıcı kaydırabilsin.
        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        scroll = QScrollArea()
        scroll.setWidget(root)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("QScrollArea { background-color: #0d1117; border: none; }")
        self.setCentralWidget(scroll)

        layout.addWidget(self._build_top_status())
        layout.addWidget(self._build_strategies_row())
        layout.addWidget(self._build_kasa_panel())
        layout.addWidget(self._build_stats_panel())
        layout.addWidget(self._build_log_panel(), stretch=1)
        layout.addLayout(self._build_footer())

        # Pencere boyutu küçük tutulur, sonra maximize ile ekranı kaplar.
        # Kullanıcı pencereyi küçültürse en az 700x520 (kartlar tek sütun
        # düzende, scroll otomatik).
        self.resize(900, 700)
        self.setMinimumSize(700, 520)
        # Ekran ne kadar küçük olursa olsun pencere maximized — her kart
        # rahat görünür, scroll'la kaydırılır.
        self.showMaximized()

        # Önce kaydedilmiş ayarları yükle (UI dolsun)
        QTimer.singleShot(50, self._load_all_settings)
        QTimer.singleShot(400, self._try_connect_mt5)
        # Varlık + stats periyodik yenile (2 sn)
        self._stats_timer = QTimer(self)
        self._stats_timer.timeout.connect(self._refresh_stats)
        self._stats_timer.start(2000)

    # ─── log + status ─────────────────────────────────────────
    def _log_msg(self, text: str) -> None:
        if self._log is None:
            return
        ts = datetime.now().strftime("%H:%M:%S")
        self._log.appendPlainText(f"[{ts}] {text}")

    def _set_dot(self, dot: Optional[QLabel], color: str) -> None:
        if dot is not None:
            dot.setStyleSheet(f"color: {color};")

    def _set_bot_running(self, running: bool) -> None:
        self._set_dot(self._dot_bot, DOT_ON if running else DOT_OFF)
        if self._start_btn is not None:
            self._start_btn.setEnabled(not running)
        if self._stop_btn is not None:
            self._stop_btn.setEnabled(running)

    # ─── MT5 bağlantı ─────────────────────────────────────────
    def _try_connect_mt5(self) -> None:
        self._log_msg("MT5'e bağlanılıyor...")
        ok = self.mt5.connect()
        if ok:
            ai = self.mt5.account_info or {}
            self._set_dot(self._dot_mt5, DOT_ON)
            self._log_msg(
                f"MT5 bağlandı: #{ai.get('login')} @ {ai.get('server')} "
                f"| {ai.get('company')} | Bakiye ${ai.get('balance'):.2f}"
            )
            self._populate_symbols()
            # 1) Lisans kontrolü (lokal kayıt → server doğrulama → dialog)
            self._verify_license(ai)
            # 2) MT5 hesap kilidi (lokal AES)
            self._verify_account_lock(ai)
            # 3) Heartbeat timer (sadece lisans varsa)
            self._start_heartbeat_timer(ai)
        else:
            self._set_dot(self._dot_mt5, DOT_ERR)
            self._log_msg(f"MT5 BAĞLANTI HATASI: {self.mt5.last_error}")

    # ─── Lisans doğrulama (server) ────────────────────────────
    def _verify_license(self, account_info: dict) -> None:
        """Lisansı server'da doğrula. Geçersizse LicenseDialog aç.

        Akış:
          1. license_store.load() → varsa client'a set
          2. heartbeat ile server'a doğrula
          3. başarısızsa lokal token'ı sil + dialog aç
          4. dialog kabulde token kaydedilmiş olur → client.set_credentials
        """
        from ui.license_dialog import LicenseDialog

        mt5_login = int(account_info.get("login", 0))
        mt5_server = str(account_info.get("server", ""))
        balance = float(account_info.get("balance", 0.0))
        equity = float(account_info.get("equity", 0.0))

        # Lokal token varsa yükle
        saved = license_store.load()
        if saved:
            # Aynı MT5 hesabı mı? (lisans MT5 hesabına bağlı)
            if int(saved.get("mt5_login", 0)) != mt5_login:
                self._log_msg(
                    f"⚠ Lisans #{saved.get('mt5_login')} hesabına bağlı, "
                    f"şu an #{mt5_login} ile bağlısın. Yeni lisans isteniyor..."
                )
                license_store.clear()
            else:
                self.client.set_credentials(saved["agent_token"], mt5_login)
                # Server doğrulaması
                ok, body = self.client.heartbeat(
                    mt5_server=mt5_server, open_positions=0,
                    balance=balance, equity=equity,
                )
                if ok:
                    self._license_ok = True
                    days = body.get("days_remaining")
                    name = saved.get("customer_name") or "—"
                    self._log_msg(
                        f"🔐 Lisans doğrulandı | Müşteri: {name} | "
                        f"Kalan: {days if days is not None else '∞'} gün"
                    )
                    if body.get("warn_expiry"):
                        self._log_msg(
                            f"⚠ DİKKAT: Lisans süresinin dolmasına {days} gün kaldı. "
                            "Yenileme için yöneticinizle iletişime geçin."
                        )
                    license_store.update_meta(days_remaining=days)
                    return
                # Server reddettiyse → kayıtlı tokenı sil, dialog'a düş
                self._log_msg(
                    "🚫 Lisans server tarafından reddedildi — yeniden giriş gerekiyor."
                )
                license_store.clear()

        # Dialog aç
        dlg = LicenseDialog(self.client, mt5_login_default=mt5_login, parent=self)
        if dlg.exec() != QDialog.Accepted:
            self._license_ok = False
            self._log_msg("🚫 Lisans girilmedi — bot başlatılamaz.")
            QMessageBox.critical(
                self, "Lisans Gerekli",
                "Botu kullanmak için geçerli bir lisans kodu gerekli.\n"
                "Lisans için yöneticinizle iletişime geçin.",
            )
            return

        self._license_ok = True
        days = dlg.days_remaining
        name = dlg.customer_name or "—"
        self._log_msg(
            f"🔐 Lisans doğrulandı | Müşteri: {name} | "
            f"Kalan: {days if days is not None else '∞'} gün"
        )

    # ─── Heartbeat timer ──────────────────────────────────────
    def _start_heartbeat_timer(self, account_info: dict) -> None:
        if not self._license_ok or not self.client.has_credentials():
            return
        if self._hb_timer is not None:
            return
        self._hb_timer = QTimer(self)
        self._hb_timer.setInterval(60_000)  # 60 sn
        self._hb_timer.timeout.connect(self._send_heartbeat)
        self._hb_timer.start()

    def _send_heartbeat(self) -> None:
        if not self.client.has_credentials():
            return
        ai = (self.mt5.account_info or {}) if self.mt5.connected else {}
        try:
            import MetaTrader5 as mt5  # type: ignore
            positions = mt5.positions_get() or []
            open_count = len(positions)
        except Exception:
            open_count = 0
        ok, body = self.client.heartbeat(
            mt5_server=str(ai.get("server", "")),
            open_positions=open_count,
            balance=float(ai.get("balance", 0.0)),
            equity=float(ai.get("equity", 0.0)),
        )
        if ok:
            days = body.get("days_remaining")
            if days is not None:
                license_store.update_meta(days_remaining=days)
            if body.get("warn_expiry") and days is not None and days <= 7:
                self._log_msg(
                    f"⚠ Lisans uyarısı: {days} gün kaldı"
                )
        else:
            # Server reddederse → lisans iptal/expired olmuş olabilir
            detail = body.get("detail") or body.get("error") or ""
            if detail:
                self._log_msg(f"⚠ Heartbeat reddi: {detail}")

    def _verify_account_lock(self, account_info: dict) -> None:
        """İlk açılışsa kilitle, değilse doğrula."""
        if not is_bound():
            ok, msg = lock_bind(account_info)
            if ok:
                self._account_locked = True
                self._log_msg(f"🔐 {msg}")
                self._log_msg("⚠️  Bu bot artık SADECE bu hesapta çalışır. Başka MT5 hesabıyla açılırsa kapanır.")
            else:
                self._log_msg(f"LOCK HATASI: {msg}")
            return

        ok, msg = lock_verify(account_info)
        if ok:
            self._account_locked = True
            locked = get_locked_info() or {}
            bound_at = locked.get("bound_at", "?")
            self._log_msg(f"🔐 {msg}  (bind: {bound_at})")
        else:
            self._account_locked = False
            self._log_msg(f"🚫 YETKİSİZ HESAP: {msg}")
            QMessageBox.critical(
                self,
                "Yetkisiz Hesap",
                f"{msg}\n\nDoğru MT5 hesabını açıp tekrar deneyin.\n"
                f"Bot 'Botu Başlat' tuşu DEVRE DIŞI bırakıldı."
            )
            if self._start_btn is not None:
                self._start_btn.setEnabled(False)

    def _populate_symbols(self) -> None:
        """MT5'ten otomatik olarak gold sembolünü tespit et + UI'ya yaz."""
        detected = self.mt5.detect_gold_symbol()
        if detected:
            self._detected_symbol = detected
            if self._symbol_label is not None:
                self._symbol_label.setText(detected)
            self._log_msg(f"💠 Sembol otomatik tespit edildi: {detected}")
        else:
            self._detected_symbol = None
            if self._symbol_label is not None:
                self._symbol_label.setText("YOK!")
                self._symbol_label.setStyleSheet(
                    "color: #f85149; font-weight: 600; padding: 2px 10px; "
                    "background-color: #0d1117; border: 1px solid #f85149; border-radius: 4px;"
                )
            self._log_msg(
                "❌ XAUUSD/GOLD sembolü bulunamadı. Broker'ın Market Watch'ında "
                "altın sembolü olduğundan emin ol."
            )

    def _current_symbol(self) -> str:
        return self._detected_symbol or "GOLD#"

    # ─── Bot başlat/durdur ────────────────────────────────────
    def _start_bot(self) -> None:
        if self.worker is not None and self.worker.isRunning():
            self._log_msg("Bot zaten çalışıyor.")
            return

        if not self.mt5.connected:
            self._log_msg("ÖNCE MT5'e bağlanılmalı (MT5 Test ile dene).")
            return

        if not self._account_locked:
            self._log_msg("🚫 Hesap kilidi doğrulanmadı — bot başlatılamaz.")
            return

        if not self._license_ok or not self.client.has_credentials():
            self._log_msg("🚫 Lisans doğrulanmadı — bot başlatılamaz.")
            return

        if not self._detected_symbol:
            self._log_msg("🚫 Sembol tespit edilemedi — bot başlatılamaz.")
            return

        # Kartlardan ayarları topla, stratejileri register et
        self.engine.reset()
        active_count = 0
        trail_long = self._kasa_trail_long()
        trail_short = self._kasa_trail_short()
        symbol = self._current_symbol()
        concurrent = self._kasa_concurrent_limit()
        self.monitor.symbol = symbol
        self.engine.symbol = symbol
        self.engine.max_concurrent = concurrent

        if concurrent < 999:
            self._log_msg(f"⚙️ Eşzamanlı pozisyon limiti: max {concurrent}")
        else:
            self._log_msg("⚙️ Eşzamanlı pozisyon limiti: SINIRSIZ")

        # M9: Hafta sonu koruması
        weekend = bool(self._kasa_weekend_chk and self._kasa_weekend_chk.isChecked())
        self.engine.weekend_protection = weekend
        if weekend:
            self._log_msg("⚙️ Hafta sonu koruması: AÇIK (Cuma 17:00-23:59 yeni emir yok)")

        # Kartlardan ayarları magic numaralarıyla register et — sinyal VPS'ten
        # gelince, magic'e bakıp ilgili kartın lot/SL/trail değerini kullanırız.
        for card, card_id, magics, trail_val, label in (
            (self.card_8t_long,   CARD_8T_LONG,  MAGIC_8T_LONG,  trail_long,  "8T LONG"),
            (self.card_8t_short,  CARD_8T_SHORT, MAGIC_8T_SHORT, trail_short, "8T SHORT"),
            (self.card_multi,     CARD_MULTI100, MULTI100_MAGICS, trail_long,  "MULTI100"),
            (self.card_micro,     CARD_MICRO_S,  MICRO_S_MAGICS,  trail_long,  "MICRO-S"),
            (self.card_goldsell,  CARD_GOLDS,    MAGIC_GOLDS,    trail_short, "GOLDS"),
            (self.card_genis,     CARD_GENIS,    MAGIC_GENIS,    trail_long,  "GENIS"),
        ):
            s = card.settings()
            if not s["enabled"]:
                continue
            if s["lot"] <= 0:
                self._log_msg(f"{label}: lot 0 — strateji başlatılamadı.")
                continue
            self.engine.register_card(
                card_id=card_id,
                label=label,
                magics=magics,
                lot=s["lot"],
                sl_usd=s["sl_usd"],
                trail_activate_usd=trail_val,
            )
            active_count += 1
            self._log_msg(f"{label} aktif | {symbol} | lot={s['lot']} SL=${s['sl_usd']}")

        if active_count == 0:
            self._log_msg("Hiç strateji aktif değil — kartlardan en az 1 tane seç.")
            return

        # Monitor ayarları (Kasa panelinden)
        long_on = bool(self._kasa_trail_long_chk and self._kasa_trail_long_chk.isChecked())
        short_on = bool(self._kasa_trail_short_chk and self._kasa_trail_short_chk.isChecked())
        self.monitor.set_trail_activate(trail_long, trail_short)
        self.monitor.set_trail_enabled(long_on, short_on)
        # Manuel pozisyonlar da LONG/SHORT açıkken otomatik trail edilir
        self.monitor.set_manage_manual(True)
        if not long_on:
            self._log_msg("⚠️ LONG trailing KAPALI — BUY pozisyonlar trailing yapılmayacak.")
        if not short_on:
            self._log_msg("⚠️ SHORT trailing KAPALI — SELL pozisyonlar trailing yapılmayacak.")

        # Worker'ı başlat
        self.worker = AgentWorker(self.engine, self.monitor)
        self.worker.log_message.connect(self._log_msg)
        self.worker.status_changed.connect(self._set_bot_running)
        self.worker.error.connect(lambda e: self._log_msg(f"WORKER HATA: {e}"))
        self.worker.start()

    def _stop_bot(self) -> None:
        if self.worker is None or not self.worker.isRunning():
            self._log_msg("Bot zaten durmuş.")
            return
        self._log_msg("Bot durduruluyor...")
        self.worker.stop()
        self.worker.wait(8000)

    def _kasa_trail_long(self) -> float:
        if self._kasa_trail_long_input is None:
            return 1.0
        v = float(self._kasa_trail_long_input.value())
        return v if v >= 1.0 else 1.0

    def _kasa_trail_short(self) -> float:
        if self._kasa_trail_short_input is None:
            return 1.0
        v = float(self._kasa_trail_short_input.value())
        return v if v >= 1.0 else 1.0

    def _kasa_concurrent_limit(self) -> int:
        if self._kasa_concurrent_group is None:
            return 999
        cid = self._kasa_concurrent_group.checkedId()
        return cid if cid >= 1 else 999

    # ─── Settings persistence (M9) ────────────────────────────
    def _load_all_settings(self) -> None:
        """settings.json'dan UI'yı doldur."""
        s = user_settings.load()
        strats = s.get("strategies", {})
        self.card_8t_long.load_settings(strats.get("8t_long", {}))
        self.card_8t_short.load_settings(strats.get("8t_short", {}))
        self.card_multi.load_settings(strats.get("multi100", {}))
        self.card_micro.load_settings(strats.get("micro_sweep", {}))
        self.card_goldsell.load_settings(strats.get("goldsell", {}))
        self.card_genis.load_settings(strats.get("genis", {}))

        kasa = s.get("kasa", {})
        # Concurrent limit
        cl = int(kasa.get("concurrent_limit", 999))
        if self._kasa_concurrent_group is not None:
            for btn in self._kasa_concurrent_group.buttons():
                if self._kasa_concurrent_group.id(btn) == cl:
                    btn.setChecked(True)
                    break
        # Weekend protection
        if self._kasa_weekend_chk is not None:
            self._kasa_weekend_chk.setChecked(bool(kasa.get("weekend_protection", False)))
        # LONG / SHORT trailing enabled (yeşil göstergeler)
        if self._kasa_trail_long_chk is not None:
            self._kasa_trail_long_chk.setChecked(bool(kasa.get("trail_long_enabled", True)))
        if self._kasa_trail_short_chk is not None:
            self._kasa_trail_short_chk.setChecked(bool(kasa.get("trail_short_enabled", True)))
        # Trail activate USD — LONG ve SHORT ayrı (eski tek değer geriye uyum)
        def _read_trail(key: str, fallback: float = 1.0) -> float:
            try:
                v = float(kasa.get(key, fallback) or fallback)
                return max(1.0, min(9999.0, v))
            except (TypeError, ValueError):
                return fallback
        # Eski "trail_activate_usd" tek değerse her ikisine de uygula
        legacy = _read_trail("trail_activate_usd", 1.0)
        tl = _read_trail("trail_activate_long_usd", legacy)
        ts = _read_trail("trail_activate_short_usd", legacy)
        if self._kasa_trail_long_input is not None:
            self._kasa_trail_long_input.setValue(tl)
        if self._kasa_trail_short_input is not None:
            self._kasa_trail_short_input.setValue(ts)

        self._log_msg(f"📂 Ayarlar yüklendi ({user_settings.SETTINGS_FILE.name})")

    def _save_all_settings(self) -> None:
        """UI'dan ayarları al, settings.json'a yaz."""
        data = {
            "version": 1,
            "strategies": {
                "8t_long":     self.card_8t_long.settings(),
                "8t_short":    self.card_8t_short.settings(),
                "multi100":    self.card_multi.settings(),
                "micro_sweep": self.card_micro.settings(),
                "goldsell":    self.card_goldsell.settings(),
                "genis":       self.card_genis.settings(),
            },
            "kasa": {
                "concurrent_limit":       self._kasa_concurrent_limit(),
                "weekend_protection":     (self._kasa_weekend_chk.isChecked()
                                           if self._kasa_weekend_chk else False),
                "trail_long_enabled":  (self._kasa_trail_long_chk.isChecked()
                                        if self._kasa_trail_long_chk else True),
                "trail_short_enabled": (self._kasa_trail_short_chk.isChecked()
                                        if self._kasa_trail_short_chk else True),
                "trail_activate_long_usd":  float(self._kasa_trail_long()),
                "trail_activate_short_usd": float(self._kasa_trail_short()),
            },
        }
        ok, msg = user_settings.save(data)
        if ok:
            self._log_msg(f"💾 Ayarlar kaydedildi: {msg}")
        else:
            self._log_msg(f"❌ Ayarlar kaydedilemedi: {msg}")

    def _check_update(self) -> None:
        """Güncelle butonu — GitHub'dan en son sürümü kontrol et + uygula."""
        # Bot çalışıyorsa önce durdur (worker thread temiz kapansın)
        if self.worker is not None and self.worker.isRunning():
            self._log_msg("Önce botu durduruyorum (güncelleme için)...")
            self.worker.stop()
            self.worker.wait(8000)

        # MT5 bağlantısını da kapat (yeni process açacak)
        if self.mt5.connected:
            try:
                self.mt5.disconnect()
            except Exception:
                pass

        result = check_and_update(BASE_DIR, VERSION, self._log_msg)
        if result is True:
            self._log_msg("Yeni sürüm açıldı, eski pencere 3 sn içinde kapanacak...")
            # 3 sn bekle — yeni process'in Qt penceresi açılmaya zaman bulsun
            QTimer.singleShot(3000, self.close)

    # ─── UI BUILD ─────────────────────────────────────────────
    def _build_top_status(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("TopStatus")
        h = QHBoxLayout(frame)
        h.setContentsMargins(12, 6, 12, 6)

        self._dot_mt5 = QLabel("●")
        self._dot_mt5.setObjectName("StatusDot")
        self._dot_mt5.setStyleSheet(f"color: {DOT_OFF};")
        mt5_label = QLabel("MT5")
        mt5_label.setObjectName("StatusLabel")
        h.addWidget(self._dot_mt5)
        h.addWidget(mt5_label)
        h.addSpacing(12)

        self._dot_bot = QLabel("●")
        self._dot_bot.setObjectName("StatusDot")
        self._dot_bot.setStyleSheet(f"color: {DOT_OFF};")
        bot_label = QLabel("Bot")
        bot_label.setObjectName("StatusLabel")
        h.addWidget(self._dot_bot)
        h.addWidget(bot_label)

        h.addSpacing(20)
        sym_caption = QLabel("Sembol:")
        sym_caption.setStyleSheet("color: #8b949e;")
        h.addWidget(sym_caption)
        self._symbol_label = QLabel("—")
        self._symbol_label.setStyleSheet(
            "color: #e6edf3; font-weight: 600; padding: 2px 10px; "
            "background-color: #0d1117; border: 1px solid #30363d; border-radius: 4px;"
        )
        self._symbol_label.setMinimumWidth(120)
        self._symbol_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        h.addWidget(self._symbol_label)

        h.addStretch(1)
        cihaz = QLabel(f"Cihaz: {get_display_name()}")
        cihaz.setStyleSheet("color: #8b949e;")
        h.addWidget(cihaz)
        return frame

    def _build_strategies_row(self) -> QFrame:
        """6 kart TEK SÜTUN — kucuk laptop ekranlarda yan yana 2 sütun
        sigmiyor, kartlar saga taşıyordu. Üst üste düzen scroll ile her
        ekrana sıgar."""
        frame = QFrame()
        v = QVBoxLayout(frame)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(10)
        for card in (
            self.card_8t_long,
            self.card_8t_short,
            self.card_multi,
            self.card_micro,
            self.card_goldsell,
            self.card_genis,
        ):
            v.addWidget(card)
        return frame

    def _build_kasa_panel(self) -> QFrame:
        box = QFrame()
        box.setObjectName("KasaBox")
        v = QVBoxLayout(box)
        v.setContentsMargins(4, 4, 4, 4)
        v.setSpacing(8)

        # Aynı anda açık işlem sayısı — id direkt limit değeri (3,6,10,999=sınırsız)
        self._kasa_concurrent_group = QButtonGroup(box)
        concurrent_hb = QHBoxLayout()
        concurrent_hb.setSpacing(6)
        concurrent_options = [(3, "1-3"), (6, "4-6"), (10, "7-10"), (999, "Sınırsız")]
        for limit_val, txt in concurrent_options:
            rb = QRadioButton(txt)
            rb.setObjectName("AvgRadio")
            if limit_val == 999:
                rb.setChecked(True)
            self._kasa_concurrent_group.addButton(rb, limit_val)
            concurrent_hb.addWidget(rb)
        concurrent_hb.addStretch(1)
        v.addLayout(self._kasa_row("Aynı anda açık\nişlem sayısı", concurrent_hb))

        # Hafta sonu koruması — yeşil noktalı (DotCheck)
        self._kasa_weekend_chk = QCheckBox(
            "Cuma 17:00 - 23:59 arası yeni işlem alma (açık işlemler etkilenmez)"
        )
        self._kasa_weekend_chk.setObjectName("DotCheck")
        v.addLayout(self._kasa_row(
            "Hafta sonu\nkoruması", self._wrap_widget(self._kasa_weekend_chk)
        ))

        # İç kutu: Trailing (LONG + SHORT)
        inner = QFrame()
        inner.setObjectName("KasaInnerBox")
        inner_v = QVBoxLayout(inner)
        inner_v.setContentsMargins(10, 8, 10, 8)
        inner_v.setSpacing(6)

        # Bilgi notu — LONG/SHORT trailing açıkken bot dışı pozisyonlar da yönetilir
        info_lbl = QLabel("ℹ️  Bot dışı açık işlemler de trailing ile yönetilir (LONG/SHORT açıkken)")
        info_lbl.setStyleSheet("color: #c9d1d9; padding: 2px 4px;")
        inner_v.addWidget(info_lbl)

        # LONG Trailing — 8T LONG, MULTI100, MICRO-S, GENIS için
        self._kasa_trail_long_chk = QCheckBox("")
        self._kasa_trail_long_chk.setObjectName("DotCheck")
        self._kasa_trail_long_chk.setChecked(True)
        self._kasa_trail_long_input = _spin(1.0, 9999.0, 1.0, 1.0, decimals=2)
        long_hbox = QHBoxLayout()
        long_hbox.setSpacing(8)
        long_hbox.addWidget(self._kasa_trail_long_chk)
        long_dollar = QLabel("$")
        long_dollar.setStyleSheet("color: #c9d1d9; font-weight: 600;")
        long_hbox.addWidget(long_dollar)
        long_hbox.addWidget(self._kasa_trail_long_input)
        long_hbox.addSpacing(12)
        long_hint = QLabel("BUY trade'leri (8T LONG, MULTI100, MICRO-S, GENIS) — $0.50 adımlarla ilerler")
        long_hint.setObjectName("KasaHint")
        long_hbox.addWidget(long_hint)
        long_hbox.addStretch(1)
        inner_v.addLayout(self._kasa_row("LONG\nTrailing", long_hbox))

        # SHORT Trailing — 8T SHORT, GOLDS için
        self._kasa_trail_short_chk = QCheckBox("")
        self._kasa_trail_short_chk.setObjectName("DotCheck")
        self._kasa_trail_short_chk.setChecked(True)
        self._kasa_trail_short_input = _spin(1.0, 9999.0, 1.0, 1.0, decimals=2)
        short_hbox = QHBoxLayout()
        short_hbox.setSpacing(8)
        short_hbox.addWidget(self._kasa_trail_short_chk)
        short_dollar = QLabel("$")
        short_dollar.setStyleSheet("color: #c9d1d9; font-weight: 600;")
        short_hbox.addWidget(short_dollar)
        short_hbox.addWidget(self._kasa_trail_short_input)
        short_hbox.addSpacing(12)
        short_hint = QLabel("SELL trade'leri (8T SHORT, GOLDS) — $0.50 adımlarla ilerler")
        short_hint.setObjectName("KasaHint")
        short_hbox.addWidget(short_hint)
        short_hbox.addStretch(1)
        inner_v.addLayout(self._kasa_row("SHORT\nTrailing", short_hbox))

        v.addWidget(inner)
        return box

    def _kasa_row(self, label_text, right_layout_or_widget):
        row = QHBoxLayout()
        row.setSpacing(10)
        lbl = QLabel(label_text)
        lbl.setObjectName("KasaRowLabel")
        lbl.setMinimumWidth(140)
        row.addWidget(lbl, alignment=Qt.AlignmentFlag.AlignTop)
        if isinstance(right_layout_or_widget, QHBoxLayout):
            row.addLayout(right_layout_or_widget, stretch=1)
        else:
            row.addWidget(right_layout_or_widget, stretch=1)
        return row

    def _wrap_widget(self, w) -> QHBoxLayout:
        hb = QHBoxLayout()
        hb.setContentsMargins(0, 0, 0, 0)
        hb.addWidget(w)
        hb.addStretch(1)
        return hb

    def _build_log_panel(self) -> QPlainTextEdit:
        self._log = QPlainTextEdit()
        self._log.setObjectName("LogText")
        self._log.setReadOnly(True)
        self._log.setMaximumBlockCount(2000)
        self._log_msg(f"{APP_NAME} v{VERSION} başlatıldı.")
        return self._log

    def _build_footer(self) -> QHBoxLayout:
        h = QHBoxLayout()
        h.setSpacing(8)

        save_btn = QPushButton("Kaydet")
        save_btn.setObjectName("SaveBtn")
        save_btn.setMinimumHeight(36)
        save_btn.clicked.connect(self._save_all_settings)
        h.addWidget(save_btn)

        self._start_btn = QPushButton("Botu Başlat")
        self._start_btn.setObjectName("StartBtn")
        self._start_btn.setMinimumHeight(36)
        self._start_btn.clicked.connect(self._start_bot)
        h.addWidget(self._start_btn)

        self._stop_btn = QPushButton("Botu Durdur")
        self._stop_btn.setObjectName("StopBtn")
        self._stop_btn.setMinimumHeight(36)
        self._stop_btn.setEnabled(False)
        self._stop_btn.clicked.connect(self._stop_bot)
        h.addWidget(self._stop_btn)

        test_btn = QPushButton("MT5 Test")
        test_btn.setObjectName("TestBtn")
        test_btn.setMinimumHeight(36)
        test_btn.clicked.connect(self._try_connect_mt5)
        h.addWidget(test_btn)

        update_btn = QPushButton("Güncelle")
        update_btn.setObjectName("UpdateBtn")
        update_btn.setMinimumHeight(36)
        update_btn.clicked.connect(self._check_update)
        h.addWidget(update_btn)

        exit_btn = QPushButton("Çıkış")
        exit_btn.setObjectName("ExitBtn")
        exit_btn.setMinimumHeight(36)
        exit_btn.clicked.connect(self.close)
        h.addWidget(exit_btn)

        h.addStretch(1)
        self._varlik_label = QLabel("Varlık: —")
        self._varlik_label.setStyleSheet(
            "color: #e6edf3; padding-right: 6px; font-weight: 600;"
        )
        h.addWidget(self._varlik_label)
        return h

    def _build_stats_panel(self) -> QFrame:
        """3 strateji grubu için P/L analizi (8T / MULTI100 / MICRO-S) + periyod seçici."""
        box = QFrame()
        box.setObjectName("StatsPanel")
        box.setStyleSheet(
            "QFrame#StatsPanel { background-color: #161b22; border: 1px solid #30363d; "
            "border-radius: 8px; } "
            "QLabel#StatsRow { color: #c9d1d9; "
            "font-family: 'Consolas','Courier New',monospace; font-size: 12px; "
            "padding: 2px 6px; }"
        )
        v = QVBoxLayout(box)
        v.setContentsMargins(10, 6, 10, 6)
        v.setSpacing(2)

        # Üst satır: başlık + periyod seçici
        top = QHBoxLayout()
        top.setSpacing(10)
        self._stats_header = QLabel("📊 İşlem Analizi — Bu Hafta")
        self._stats_header.setStyleSheet(
            "color: #58a6ff; font-weight: 600; padding: 2px 4px; font-size: 12px;"
        )
        top.addWidget(self._stats_header)
        top.addStretch(1)

        self._stats_period_group = QButtonGroup(box)
        period_options = [(1, "Bugün"), (7, "Bu Hafta"), (30, "Son 30 Gün")]
        for pid, txt in period_options:
            rb = QRadioButton(txt)
            rb.setObjectName("AvgRadio")
            if pid == 7:  # default
                rb.setChecked(True)
            self._stats_period_group.addButton(rb, pid)
            top.addWidget(rb)
        self._stats_period_group.idToggled.connect(
            lambda _id, checked: checked and self._refresh_stats()
        )
        # Detaylı rapor butonu (saat dağılımı)
        report_btn = QPushButton("📋 Detaylı Rapor")
        report_btn.setStyleSheet(
            "QPushButton { background-color: #21262d; border: 1px solid #30363d; "
            "border-radius: 4px; padding: 3px 10px; color: #c9d1d9; font-weight: 600; } "
            "QPushButton:hover { background-color: #30363d; border-color: #58a6ff; }"
        )
        report_btn.clicked.connect(self._open_report_dialog)
        top.addSpacing(8)
        top.addWidget(report_btn)
        v.addLayout(top)

        self._stats_8t = QLabel("8T       :  —")
        self._stats_multi = QLabel("MULTI100 :  —")
        self._stats_micro = QLabel("MICRO-S  :  —")
        self._stats_goldsell = QLabel("GOLDS    :  —")
        self._stats_genis = QLabel("GENIS    :  —")
        self._stats_manual = QLabel("MANUEL   :  —")
        for lbl in (self._stats_8t, self._stats_multi, self._stats_micro,
                    self._stats_goldsell, self._stats_genis, self._stats_manual):
            lbl.setObjectName("StatsRow")
            v.addWidget(lbl)
        return box

    def _open_report_dialog(self) -> None:
        """Detaylı saat dağılımı raporunu aç."""
        pid = self._stats_period_group.checkedId() if self._stats_period_group else 7
        dlg = ReportDialog(self, default_period=pid, default_group="Hepsi")
        dlg.exec()

    def _stats_period_range(self) -> tuple[int, str]:
        """Seçilen periyod için (start_unix, label) döner."""
        import time as _time
        pid = self._stats_period_group.checkedId() if self._stats_period_group else 7
        now = int(_time.time())
        if pid == 1:
            # Bugün: yerel 00:00
            today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            return int(today.timestamp()), "Bugün"
        elif pid == 30:
            return now - 86400 * 30, "Son 30 Gün"
        else:
            # Bu Hafta: bu haftanın Pazartesi 00:00
            now_dt = datetime.now()
            monday = now_dt - timedelta(days=now_dt.weekday())
            monday = monday.replace(hour=0, minute=0, second=0, microsecond=0)
            return int(monday.timestamp()), "Bu Hafta"

    # ─── Periyodik stats + varlık yenileme ────────────────────
    def _refresh_stats(self) -> None:
        """2 sn'de bir: account_info'dan varlık + history_deals_get'ten 3 grup için P/L."""
        try:
            import MetaTrader5 as mt5_mod
        except ImportError:
            return
        if not self.mt5.connected:
            return

        # Varlık (balance + equity + aktif kar)
        try:
            info = mt5_mod.account_info()
        except Exception:
            info = None
        if info is not None and self._varlik_label is not None:
            balance = float(info.balance)
            equity = float(info.equity)
            profit = float(info.profit)
            sign = "+" if profit >= 0 else ""
            color = "#3fb950" if profit > 0 else ("#f85149" if profit < -0.001 else "#e6edf3")
            self._varlik_label.setText(
                f"Bakiye: <b>${balance:,.2f}</b>  |  Sermaye: <b>${equity:,.2f}</b>  |  "
                f"Açık: <span style='color: {color};'><b>{sign}${profit:,.2f}</b></span>"
            )
            self._varlik_label.setTextFormat(Qt.TextFormat.RichText)

        # Seçilen periyot için deal'ları çek
        import time as _time
        now = int(_time.time())
        period_start, period_label = self._stats_period_range()
        if self._stats_header is not None:
            self._stats_header.setText(f"📊 İşlem Analizi — {period_label}")
        try:
            deals = mt5_mod.history_deals_get(period_start, now + 60)
        except Exception:
            deals = None
        if deals is None:
            deals = []

        groups = {
            "8T":       {20270001, 20270002},
            "MULTI100": {20270011, 20270012, 20270013, 20270014},
            "MICRO-S":  set(range(20270101, 20270128)),
            "GOLDS":    {20270200},
            "GENIS":    {20270300},
        }
        bot_all = (groups["8T"] | groups["MULTI100"] | groups["MICRO-S"]
                   | groups["GOLDS"] | groups["GENIS"])
        stats = {k: {"n": 0, "w": 0, "l": 0, "net": 0.0}
                 for k in list(groups.keys()) + ["MANUEL"]}

        # position_id bazlı grupla — SL ile kapanan deal'ların magic'i 0 olabiliyor,
        # bu yüzden IN deal'dan magic'i al, OUT/INOUT deal'lardan P/L'i topla.
        from collections import defaultdict
        per_pos = defaultdict(
            lambda: {"magic": 0, "comment": "", "pnl": 0.0, "has_close": False}
        )
        for d in deals:
            try:
                pid = int(d.position_id)
            except Exception:
                continue
            rec = per_pos[pid]
            mg = int(getattr(d, "magic", 0) or 0)
            cmt = str(getattr(d, "comment", "") or "")
            entry_type = getattr(d, "entry", None)

            # Magic'i bul: önce IN deal'dan, yoksa herhangi non-zero
            if entry_type == mt5_mod.DEAL_ENTRY_IN:
                rec["magic"] = mg
                if cmt:
                    rec["comment"] = cmt
            elif rec["magic"] == 0 and mg != 0:
                rec["magic"] = mg

            # P/L sadece kapanış deal'larından
            if entry_type in (mt5_mod.DEAL_ENTRY_OUT, mt5_mod.DEAL_ENTRY_INOUT):
                rec["pnl"] += float(getattr(d, "profit", 0) or 0)
                rec["has_close"] = True

        def _classify(mg: int, cmt: str) -> Optional[str]:
            if mg in bot_all:
                for gname, gset in groups.items():
                    if mg in gset:
                        return gname
            # Fallback: magic kaybolduysa comment prefix'inden
            if cmt.startswith("8T_"):     return "8T"
            if cmt.startswith("M100_"):   return "MULTI100"
            if cmt.startswith("MS-"):     return "MICRO-S"
            if cmt.startswith("MS_"):     return "MICRO-S"  # underscore varyant
            if cmt.startswith("GS_"):     return "GOLDS"
            if cmt.startswith("GENIS_"):  return "GENIS"
            return "MANUEL"

        for pid, rec in per_pos.items():
            if not rec["has_close"]:
                continue
            target = _classify(rec["magic"], rec["comment"])
            if target is None:
                continue
            pnl = rec["pnl"]
            stats[target]["n"] += 1
            stats[target]["net"] += pnl
            if pnl > 0.001:
                stats[target]["w"] += 1
            elif pnl < -0.001:
                stats[target]["l"] += 1

        def _fmt(gname: str, s: dict) -> str:
            head = f"{gname:<8s} :"
            if s["n"] == 0:
                return f"{head}  henüz işlem yok"
            wr = 100.0 * s["w"] / s["n"]
            sign = "+" if s["net"] >= 0 else ""
            return (
                f"{head}  {s['n']:>3d} işlem  |  "
                f"{s['w']:>3d}W {s['l']:>3d}L  |  "
                f"Net {sign}${s['net']:,.2f}  |  WR %{wr:5.1f}"
            )

        if self._stats_8t is not None:
            self._stats_8t.setText(_fmt("8T", stats["8T"]))
        if self._stats_multi is not None:
            self._stats_multi.setText(_fmt("MULTI100", stats["MULTI100"]))
        if self._stats_micro is not None:
            self._stats_micro.setText(_fmt("MICRO-S", stats["MICRO-S"]))
        if self._stats_goldsell is not None:
            self._stats_goldsell.setText(_fmt("GOLDS", stats["GOLDS"]))
        if self._stats_genis is not None:
            self._stats_genis.setText(_fmt("GENIS", stats["GENIS"]))
        if self._stats_manual is not None:
            self._stats_manual.setText(_fmt("MANUEL", stats["MANUEL"]))

    def closeEvent(self, event) -> None:  # noqa: N802
        # Açık pozisyon uyarısı (bot çalışıyorken kullanıcı X'e basarsa)
        if self.worker is not None and self.worker.isRunning():
            self._log_msg("👋 Pencere kapanıyor — bot durduruluyor, açık pozisyonlar broker'da kalır.")
            self.worker.stop()
            self.worker.wait(5000)
        if self.mt5.connected:
            self.mt5.disconnect()
        super().closeEvent(event)
