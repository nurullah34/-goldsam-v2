"""Bot worker — periyodik tick için QThread.

UI ana thread'ini dondurmaz. İki ayrı frekansta:
  - MONITOR_INTERVAL_MS (1 sn) → trailing SL güncelle (hızlı, lokal MT5 IPC)
  - SIGNAL_INTERVAL_MS  (5 sn) → server'dan sinyal poll (HTTP)

Trailing için 1 sn ideal — altın gibi hızlı pariteler için SL responsive
olur. Signal poll için 5 sn yeterli (sinyaller ortalama dakikada birkaç).
"""
from __future__ import annotations

from PySide6.QtCore import QThread, Signal

from core.position_monitor import PositionMonitor
from core.strategy_engine import StrategyEngine


class AgentWorker(QThread):
    log_message = Signal(str)
    status_changed = Signal(bool)
    error = Signal(str)

    # Trailing — 1 sn (hızlı: MT5 IPC, lokal)
    MONITOR_INTERVAL_MS = 1000
    # Signal poll — 5 sn (HTTP, server'a gereksiz yük olmasın)
    SIGNAL_INTERVAL_MS = 5000

    def __init__(self, engine: StrategyEngine, monitor: PositionMonitor,
                 parent=None) -> None:
        super().__init__(parent)
        self._engine = engine
        self._monitor = monitor
        self._running = False
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

        signal_every = self.SIGNAL_INTERVAL_MS // self.MONITOR_INTERVAL_MS  # 5
        counter = 0

        while self._running:
            try:
                # Her tick'te (1 sn): trailing — açık pozisyon SL'i ileri it
                self._monitor.tick(self._engine.active_magics())

                # 5 tick'te bir (5 sn): server sinyal poll
                if counter % signal_every == 0:
                    self._engine.tick()

                counter += 1
            except Exception as e:
                self.error.emit(f"tick hatası: {e}")

            self.msleep(self.MONITOR_INTERVAL_MS)

        self.status_changed.emit(False)
        self.log_message.emit("Bot durduruldu.")

    def stop(self) -> None:
        self._running = False
