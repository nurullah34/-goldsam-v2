import atexit
import os
import shutil
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from app import MainWindow
from version import APP_NAME

BASE_DIR = Path(__file__).resolve().parent
PID_FILE = BASE_DIR / ".app.pid"
UPDATE_BAT = BASE_DIR / "_update.bat"
UPDATE_TMP = BASE_DIR / ".update_tmp"


def _cleanup_update_artifacts() -> None:
    """Önceki güncellemeden kalmış _update.bat ve .update_tmp'yi sil."""
    try:
        if UPDATE_BAT.exists():
            UPDATE_BAT.unlink()
    except OSError:
        pass
    try:
        if UPDATE_TMP.exists():
            shutil.rmtree(UPDATE_TMP, ignore_errors=True)
    except OSError:
        pass


def _kill_previous_instance() -> None:
    """Önceki çalışan instance varsa kapat — single-instance kuralı."""
    if not PID_FILE.exists():
        return
    try:
        old_pid = int(PID_FILE.read_text().strip())
    except (ValueError, OSError):
        return
    if old_pid == os.getpid():
        return
    try:
        if sys.platform == "win32":
            os.system(f"taskkill /F /PID {old_pid} >NUL 2>&1")
        else:
            os.kill(old_pid, 15)
    except OSError:
        pass


def _write_pid() -> None:
    try:
        PID_FILE.write_text(str(os.getpid()))
    except OSError:
        pass


def _cleanup_pid() -> None:
    try:
        if PID_FILE.exists():
            current = PID_FILE.read_text().strip()
            if current == str(os.getpid()):
                PID_FILE.unlink()
    except OSError:
        pass


def main() -> int:
    _kill_previous_instance()
    _cleanup_update_artifacts()
    _write_pid()
    atexit.register(_cleanup_pid)

    qt = QApplication(sys.argv)
    qt.setApplicationName(APP_NAME)
    qt.setOrganizationName("GOLDSAM")

    win = MainWindow()
    win.show()
    return qt.exec()


if __name__ == "__main__":
    sys.exit(main())
