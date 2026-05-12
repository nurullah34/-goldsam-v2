import socket
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QLocale, QTimer
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QPushButton, QCheckBox, QDoubleSpinBox, QRadioButton, QButtonGroup,
    QPlainTextEdit, QMessageBox, QDialog, QTableWidget, QTableWidgetItem,
    QComboBox, QHeaderView
)

from core import settings as user_settings
from core.agent_worker import AgentWorker
from core.account_lock import bind as lock_bind, get_locked_info, is_bound, verify as lock_verify
from core.device_id import get_display_name
from core.mt5_connector import MT5Connector
from core.position_monitor import PositionMonitor
from core.strategy_engine import StrategyEngine
from core.trade_executor import TradeExecutor
from core.updater import check_and_update
from strategies.dengeli_8t import Dengeli8T
from strategies.multi100.strategy import Multi100Strategy
from strategies.micro_sweep.strategy import MicroSweepStrategy
from version import VERSION, APP_NAME


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
    }
    GROUPS["Hepsi"] = (
        GROUPS["8T"] | GROUPS["MULTI100"] | GROUPS["MICRO-S"]
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
        for gname in ("Tümü", "Hepsi (Bot)", "8T", "MULTI100", "MICRO-S", "Manuel"):
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

        # Her satır = bir trade — entry / exit / süre / strateji / yön / lot / P/L
        self.table = QTableWidget(0, 7, self)
        self.table.setHorizontalHeaderLabels(
            ["Giriş", "Çıkış", "Süre", "Strateji", "Yön", "Lot", "P/L ($)"]
        )
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)
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

        # position_id bazlı grupla — entry + exit deal'ları birleştir
        per_pos: dict[int, dict] = defaultdict(
            lambda: {"entry": None, "exit": None, "pnl_sum": 0.0,
                     "magic": 0, "side": "?", "volume": 0.0}
        )

        for d in deals:
            mg = int(getattr(d, "magic", 0) or 0)
            if not _accept(mg):
                continue
            try:
                pid = int(d.position_id)
            except Exception:
                continue
            entry_type = getattr(d, "entry", None)
            try:
                t = datetime.fromtimestamp(int(d.time))
            except Exception:
                continue

            rec = per_pos[pid]
            rec["magic"] = mg
            if rec["volume"] == 0.0:
                rec["volume"] = float(getattr(d, "volume", 0) or 0)

            if entry_type == mt5_mod.DEAL_ENTRY_IN:
                rec["entry"] = t
                dtype = int(getattr(d, "type", -1))
                rec["side"] = (
                    "BUY"  if dtype == mt5_mod.DEAL_TYPE_BUY  else
                    "SELL" if dtype == mt5_mod.DEAL_TYPE_SELL else "?"
                )
            elif entry_type in (mt5_mod.DEAL_ENTRY_OUT, mt5_mod.DEAL_ENTRY_INOUT):
                if rec["exit"] is None or t > rec["exit"]:
                    rec["exit"] = t

            # MT5 "Profit" kolonu ile birebir olsun: sadece profit (komisyon + swap hariç)
            rec["pnl_sum"] += float(getattr(d, "profit", 0) or 0)

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
                "side": rec["side"],
                "volume": rec["volume"],
                "pnl": rec["pnl_sum"],
            })
        trades.sort(key=lambda t: t["entry"], reverse=True)  # en yeni üstte

        # Özet
        n_total = len(trades)
        w_total = sum(1 for t in trades if t["pnl"] > 0.001)
        l_total = sum(1 for t in trades if t["pnl"] < -0.001)
        net_total = sum(t["pnl"] for t in trades)
        wr_total = (100.0 * w_total / n_total) if n_total > 0 else 0.0
        sign = "+" if net_total >= 0 else ""
        self.summary_lbl.setText(
            f"📊 {gname} — {label}  |  {n_total} işlem  |  "
            f"{w_total}W  {l_total}L  |  Net {sign}${net_total:,.2f}  |  WR %{wr_total:.2f}"
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
        for row, t in enumerate(trades):
            entry_str = t["entry"].strftime("%Y-%m-%d %H:%M:%S")
            exit_str  = t["exit"].strftime("%Y-%m-%d %H:%M:%S")
            dur_str   = _dur_text(t["duration_s"])
            pnl_sign  = "+" if t["pnl"] >= 0 else ""
            pnl_str   = f"{pnl_sign}${t['pnl']:,.2f}"
            vol_str   = f"{t['volume']:.2f}"

            cells = [
                (entry_str, Qt.AlignmentFlag.AlignCenter, None),
                (exit_str,  Qt.AlignmentFlag.AlignCenter, None),
                (dur_str,   Qt.AlignmentFlag.AlignCenter, DIM),
                (t["strategy"],
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, None),
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
        self.engine.on_signal = lambda sig, strat: self.executor.execute(sig)
        self.worker: Optional[AgentWorker] = None
        self._account_locked: bool = False  # Lock doğrulamadan bot başlamaz

        # Strateji kartları
        self.card_8t_long = StrategyCard("8T LONG")
        self.card_8t_short = StrategyCard("8T SHORT")
        self.card_multi = StrategyCard("MULTI100")
        self.card_micro = StrategyCard("MICRO-S")

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
        self._kasa_manuel_chk: Optional[QCheckBox] = None
        self._kasa_trail_group: Optional[QButtonGroup] = None
        # Stats + varlık paneli
        self._stats_8t: Optional[QLabel] = None
        self._stats_multi: Optional[QLabel] = None
        self._stats_micro: Optional[QLabel] = None
        self._stats_manual: Optional[QLabel] = None
        self._stats_header: Optional[QLabel] = None
        self._stats_period_group: Optional[QButtonGroup] = None
        self._varlik_label: Optional[QLabel] = None
        self._stats_timer: Optional[QTimer] = None

        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)
        self.setCentralWidget(root)

        layout.addWidget(self._build_top_status())
        layout.addWidget(self._build_strategies_row())
        layout.addWidget(self._build_kasa_panel())
        layout.addWidget(self._build_stats_panel())
        layout.addWidget(self._build_log_panel(), stretch=1)
        layout.addLayout(self._build_footer())

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
            self._verify_account_lock(ai)
        else:
            self._set_dot(self._dot_mt5, DOT_ERR)
            self._log_msg(f"MT5 BAĞLANTI HATASI: {self.mt5.last_error}")

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

        if not self._detected_symbol:
            self._log_msg("🚫 Sembol tespit edilemedi — bot başlatılamaz.")
            return

        # Kartlardan ayarları topla, stratejileri register et
        self.engine.reset()
        active_count = 0
        trail = self._kasa_trail_value()
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

        for card, direction, label in (
            (self.card_8t_long, "long", "8T LONG"),
            (self.card_8t_short, "short", "8T SHORT"),
        ):
            s = card.settings()
            if not s["enabled"]:
                continue
            if s["lot"] <= 0:
                self._log_msg(f"{label}: lot 0 — strateji başlatılamadı.")
                continue
            strat = Dengeli8T(direction=direction, symbol=symbol)
            strat.apply_settings(
                enabled=True,
                lot=s["lot"],
                sl_usd=s["sl_usd"],
                trail_activate_usd=trail,
                avg_threshold_usd=s["avg_threshold_usd"],
                avg_lot=s["avg_lot"],
            )
            self.engine.register(strat)
            active_count += 1
            self._log_msg(f"{label} aktif | {symbol} | lot={s['lot']} SL=${s['sl_usd']}")

        smulti = self.card_multi.settings()
        if smulti["enabled"]:
            if smulti["lot"] <= 0:
                self._log_msg("MULTI100: lot 0 — strateji başlatılamadı.")
            else:
                for tf in Multi100Strategy.all_timeframes():
                    strat = Multi100Strategy(timeframe=tf, symbol=symbol)
                    strat.apply_settings(
                        enabled=True,
                        lot=smulti["lot"],
                        sl_usd=smulti["sl_usd"],
                        trail_activate_usd=trail,
                        avg_threshold_usd=smulti["avg_threshold_usd"],
                        avg_lot=smulti["avg_lot"],
                    )
                    self.engine.register(strat)
                    active_count += 1
                self._log_msg(
                    f"MULTI100 aktif | {symbol} | lot={smulti['lot']} SL=${smulti['sl_usd']}"
                )

        smicro = self.card_micro.settings()
        if smicro["enabled"]:
            if smicro["lot"] <= 0:
                self._log_msg("MICRO-S: lot 0 — strateji başlatılamadı.")
            else:
                strat = MicroSweepStrategy(symbol=symbol)
                strat.apply_settings(
                    enabled=True,
                    lot=smicro["lot"],
                    sl_usd=smicro["sl_usd"],
                    trail_activate_usd=trail,
                    avg_threshold_usd=smicro["avg_threshold_usd"],
                    avg_lot=smicro["avg_lot"],
                )
                self.engine.register(strat)
                active_count += 1
                self._log_msg(
                    f"MICRO-S aktif | {symbol} | lot={smicro['lot']} SL=${smicro['sl_usd']}"
                )

        if active_count == 0:
            self._log_msg("Hiç strateji aktif değil — kartlardan en az 1 tane seç.")
            return

        # Monitor ayarları (Kasa panelinden)
        self.monitor.set_trail_activate(trail)
        self.monitor.set_manage_manual(
            bool(self._kasa_manuel_chk and self._kasa_manuel_chk.isChecked())
        )

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

    def _kasa_trail_value(self) -> float:
        if self._kasa_trail_group is None:
            return 1.0
        cid = self._kasa_trail_group.checkedId()
        return float(cid) if cid >= 1 else 1.0

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
        # Manual positions trail
        if self._kasa_manuel_chk is not None:
            self._kasa_manuel_chk.setChecked(bool(kasa.get("manual_positions_trail", False)))
        # Trail activate USD
        ta = int(kasa.get("trail_activate_usd", 1))
        if self._kasa_trail_group is not None:
            for btn in self._kasa_trail_group.buttons():
                if self._kasa_trail_group.id(btn) == ta:
                    btn.setChecked(True)
                    break

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
            },
            "kasa": {
                "concurrent_limit":       self._kasa_concurrent_limit(),
                "weekend_protection":     (self._kasa_weekend_chk.isChecked()
                                           if self._kasa_weekend_chk else False),
                "manual_positions_trail": (self._kasa_manuel_chk.isChecked()
                                           if self._kasa_manuel_chk else False),
                "trail_activate_usd":     int(self._kasa_trail_value()),
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
        frame = QFrame()
        v = QVBoxLayout(frame)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(10)

        # Üst satır: 8T LONG | 8T SHORT
        top = QHBoxLayout()
        top.setSpacing(14)
        top.addWidget(self.card_8t_long)
        top.addWidget(self.card_8t_short)
        v.addLayout(top)

        # Alt satır: MULTI100 | Micro-Sweep
        bot = QHBoxLayout()
        bot.setSpacing(14)
        bot.addWidget(self.card_multi)
        bot.addWidget(self.card_micro)
        v.addLayout(bot)
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

        # Hafta sonu koruması
        self._kasa_weekend_chk = QCheckBox(
            "Cuma 17:00 - 23:59 arası yeni işlem alma (açık işlemler etkilenmez)"
        )
        v.addLayout(self._kasa_row(
            "Hafta sonu\nkoruması", self._wrap_widget(self._kasa_weekend_chk)
        ))

        # İç kutu: Manuel + Trailing
        inner = QFrame()
        inner.setObjectName("KasaInnerBox")
        inner_v = QVBoxLayout(inner)
        inner_v.setContentsMargins(10, 8, 10, 8)
        inner_v.setSpacing(6)

        self._kasa_manuel_chk = QCheckBox("Bot dışı açık işlemleri de trailing ile yönet")
        inner_v.addLayout(self._kasa_row(
            "Manuel\nişlemler", self._wrap_widget(self._kasa_manuel_chk)
        ))

        self._kasa_trail_group = QButtonGroup(box)
        trail_hbox = QHBoxLayout()
        trail_hbox.setSpacing(4)
        for amount in [1, 2, 3, 4, 5]:
            rb = QRadioButton(f"${amount}")
            rb.setObjectName("AvgRadio")
            if amount == 1:
                rb.setChecked(True)
            self._kasa_trail_group.addButton(rb, amount)
            trail_hbox.addWidget(rb)
        trail_hbox.addSpacing(12)
        hint = QLabel("Kara ulaşınca Kar takibi devreye girer ($0.50 adımlarla ilerler)")
        hint.setObjectName("KasaHint")
        trail_hbox.addWidget(hint)
        trail_hbox.addStretch(1)
        inner_v.addLayout(self._kasa_row("Trailing\nbaşlangıç", trail_hbox))

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
        self._stats_manual = QLabel("MANUEL   :  —")
        for lbl in (self._stats_8t, self._stats_multi, self._stats_micro, self._stats_manual):
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
        }
        bot_all = groups["8T"] | groups["MULTI100"] | groups["MICRO-S"]
        stats = {k: {"n": 0, "w": 0, "l": 0, "net": 0.0}
                 for k in list(groups.keys()) + ["MANUEL"]}

        for d in deals:
            try:
                if d.entry not in (mt5_mod.DEAL_ENTRY_OUT, mt5_mod.DEAL_ENTRY_INOUT):
                    continue
            except Exception:
                continue
            mg = int(getattr(d, "magic", 0) or 0)
            # MT5 "Profit" kolonu ile birebir
            pnl = float(getattr(d, "profit", 0) or 0)
            target = None
            if mg in bot_all:
                for gname, gset in groups.items():
                    if mg in gset:
                        target = gname
                        break
            else:
                target = "MANUEL"
            if target is None:
                continue
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
