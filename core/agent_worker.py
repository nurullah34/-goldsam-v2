"""Bot worker — periyodik tick için QThread.

UI ana thread'ini dondurmaz. Her tick:
  1. PositionMonitor → açık pozisyonların SL'ini trail et
  2. StrategyEngine → yeni sinyal var mı tara (bulursa executor çağrılır)
"""
from __future__ import annotations

from typing import Iterable

from PySide6.QtCore import QThread, Signal

from core.position_monitor import PositionMonitor
from core.strategy_engine import StrategyEngine


class AgentWorker(QThread):
    log_message = Signal(str)
    status_changed = Signal(bool)
    error = Signal(str)

    TICK_INTERVAL_MS = 5000

    def __init__(self, engine: StrategyEngine, monitor: PositionMonitor,
                 parent=None) -> None:
        super().__init__(parent)
        self._engine = engine
        self._monitor = monitor
        self._running = False
        # Engine ve monitor log'larını bizim sinyalimize bağla
        self._engine.log = self.log_message.emit
        self._monitor.log = self.log_message.emit

    def run(self) -> None:
        self._running = True
        self.status_changed.emit(True)
        self.log_message.emit("Bot başlatıldı — sinyaller taranıyor.")
        self.log_message.emit(
            "⏳ Warm-up: geçmiş paternler 'görünmüş' sayıldı. "
            "Sadece bot start sonrası OLUŞAN yeni paternler tetiklenecek."
        )

        while self._running:
            try:
                # Önce trailing (açık pozisyonların SL'ini ileri it)
                self._monitor.tick(self._engine.active_magics())
                # Sonra yeni sinyal taraması
                self._engine.tick()
            except Exception as e:
                self.error.emit(f"tick hatası: {e}")
            self.msleep(self.TICK_INTERVAL_MS)

        self.status_changed.emit(False)
        self.log_message.emit("Bot durduruldu.")

    def stop(self) -> None:
        self._running = False
