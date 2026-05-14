"""Lisans + MT5 hesap kilidi giriş dialog'u.

Bot ilk açılışta (veya lisans bozulduğunda) bu dialog'u gösterir.
Kullanıcı 10-haneli lisans kodunu girer, MT5 hesap no otomatik dolu
(MT5'e bağlanıldıysa). 'Doğrula' tuşuna basınca:
  → kriptoly_client.login() server'a POST /v1/login atar
  → başarılıysa agent_token diske şifreli kaydedilir
  → dialog accept (True) ile kapanır
  → başarısızsa hata mesajı gösterilir, tekrar denenebilir
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QFrame, QSizePolicy, QSpacerItem,
)

from core import license_store
from core.device_id import get_device_fingerprint, get_display_name
from core.kriptoly_client import KriptolyClient


# Aynı palette (app.py STYLE bloğu ile uyumlu)
DIALOG_STYLE = """
QDialog { background-color: #0d1117; }
QWidget { color: #e6edf3; font-family: 'Segoe UI', Arial; font-size: 13px; }
QFrame#Card {
    background-color: #161b22;
    border: 1px solid #30363d;
    border-radius: 10px;
}
QLabel#Title {
    color: #f0b429;
    font-size: 18px;
    font-weight: 700;
}
QLabel#Subtitle {
    color: #8b949e;
    font-size: 12px;
}
QLabel#FieldLabel {
    color: #c9d1d9;
    font-size: 12px;
    font-weight: 600;
}
QLineEdit {
    background-color: #0d1117;
    border: 1px solid #30363d;
    border-radius: 6px;
    padding: 8px 10px;
    color: #e6edf3;
    font-size: 13px;
    selection-background-color: #1f6feb;
}
QLineEdit:focus { border: 1px solid #1f6feb; }
QLineEdit#LicenseInput {
    font-family: 'Consolas', 'Courier New', monospace;
    font-size: 16px;
    font-weight: 700;
    letter-spacing: 2px;
}
QPushButton#PrimaryBtn {
    background-color: #2ea043;
    color: white;
    border: none;
    border-radius: 6px;
    padding: 10px 18px;
    font-weight: 600;
    font-size: 13px;
}
QPushButton#PrimaryBtn:hover  { background-color: #3fb950; }
QPushButton#PrimaryBtn:pressed { background-color: #238636; }
QPushButton#PrimaryBtn:disabled { background-color: #444; color: #8b949e; }
QPushButton#CancelBtn {
    background-color: #21262d;
    color: #c9d1d9;
    border: 1px solid #30363d;
    border-radius: 6px;
    padding: 10px 18px;
    font-weight: 500;
}
QPushButton#CancelBtn:hover { background-color: #30363d; }
QLabel#ErrLabel {
    color: #f85149;
    background-color: rgba(248, 81, 73, 0.08);
    border: 1px solid rgba(248, 81, 73, 0.3);
    border-radius: 6px;
    padding: 8px 10px;
}
QLabel#OkLabel {
    color: #3fb950;
}
QLabel#DeviceLabel {
    color: #8b949e;
    font-size: 11px;
}
"""


class LicenseDialog(QDialog):
    """Lisans kodu + MT5 hesap no ile login dialog'u."""

    def __init__(self, client: KriptolyClient,
                 mt5_login_default: int = 0,
                 parent=None) -> None:
        super().__init__(parent)
        self._client = client
        self._mt5_login_default = int(mt5_login_default or 0)
        # Sonuç — accept'te doldurulur
        self.agent_token: Optional[str] = None
        self.customer_name: str = ""
        self.expires_at: Optional[str] = None
        self.days_remaining: Optional[int] = None

        self.setWindowTitle("GOLDSAM V2 — Lisans Doğrulama")
        self.setModal(True)
        self.setFixedWidth(440)
        self.setStyleSheet(DIALOG_STYLE)

        self._build_ui()

    # ───── UI ──────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(14)

        # Başlık
        title = QLabel("🔐 Lisans Doğrulama")
        title.setObjectName("Title")
        title.setAlignment(Qt.AlignCenter)
        root.addWidget(title)

        sub = QLabel("Botu kullanmak için size verilen lisans kodunu girin.")
        sub.setObjectName("Subtitle")
        sub.setAlignment(Qt.AlignCenter)
        sub.setWordWrap(True)
        root.addWidget(sub)

        # Form kartı
        card = QFrame()
        card.setObjectName("Card")
        form = QVBoxLayout(card)
        form.setContentsMargins(16, 16, 16, 16)
        form.setSpacing(12)

        # Lisans kodu
        lbl_key = QLabel("LİSANS KODU")
        lbl_key.setObjectName("FieldLabel")
        form.addWidget(lbl_key)
        self.input_key = QLineEdit()
        self.input_key.setObjectName("LicenseInput")
        self.input_key.setPlaceholderText("XXX-XXX-XXX")
        self.input_key.setMaxLength(16)  # 9 char + 2 dash = 11, +tolerans
        self.input_key.setAlignment(Qt.AlignCenter)
        self.input_key.textChanged.connect(self._on_key_changed)
        form.addWidget(self.input_key)

        # MT5 hesap no
        lbl_mt5 = QLabel("MT5 HESAP NO")
        lbl_mt5.setObjectName("FieldLabel")
        form.addWidget(lbl_mt5)
        self.input_mt5 = QLineEdit()
        self.input_mt5.setPlaceholderText("148744")
        if self._mt5_login_default > 0:
            self.input_mt5.setText(str(self._mt5_login_default))
            self.input_mt5.setReadOnly(True)
            self.input_mt5.setStyleSheet("color: #8b949e; background-color: #21262d;")
        form.addWidget(self.input_mt5)

        # Cihaz info
        dev = QLabel(f"Cihaz: {get_display_name()}  •  Bu cihaza özel bind edilir")
        dev.setObjectName("DeviceLabel")
        form.addWidget(dev)

        root.addWidget(card)

        # Hata satırı (başta gizli)
        self.err_label = QLabel("")
        self.err_label.setObjectName("ErrLabel")
        self.err_label.setWordWrap(True)
        self.err_label.hide()
        root.addWidget(self.err_label)

        # Butonlar
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        self.btn_cancel = QPushButton("İptal")
        self.btn_cancel.setObjectName("CancelBtn")
        self.btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(self.btn_cancel)

        btn_row.addItem(QSpacerItem(20, 0, QSizePolicy.Expanding, QSizePolicy.Minimum))

        self.btn_ok = QPushButton("✓ Doğrula")
        self.btn_ok.setObjectName("PrimaryBtn")
        self.btn_ok.clicked.connect(self._on_verify)
        self.btn_ok.setDefault(True)
        btn_row.addWidget(self.btn_ok)

        root.addLayout(btn_row)

        # Footer
        footer = QLabel("kriptoly.com  •  GOLDSAM V2")
        footer.setObjectName("DeviceLabel")
        footer.setAlignment(Qt.AlignCenter)
        root.addWidget(footer)

    # ───── Slots ───────────────────────────────────────────────

    def _on_key_changed(self, text: str) -> None:
        """Lisans kodunu büyük harfe çevir + hatayı temizle."""
        up = text.upper()
        if up != text:
            cursor_pos = self.input_key.cursorPosition()
            self.input_key.blockSignals(True)
            self.input_key.setText(up)
            self.input_key.setCursorPosition(cursor_pos)
            self.input_key.blockSignals(False)
        if self.err_label.isVisible():
            self.err_label.hide()

    def _on_verify(self) -> None:
        key = self.input_key.text().strip().upper()
        mt5_login_txt = self.input_mt5.text().strip()

        if not key:
            self._show_error("Lisans kodu boş olamaz.")
            return
        try:
            mt5_login = int(mt5_login_txt)
        except ValueError:
            self._show_error("MT5 hesap no sayısal olmalı.")
            return
        if mt5_login <= 0:
            self._show_error("Geçerli bir MT5 hesap no girin.")
            return

        # UI'yı kilitle ("yükleniyor" gösterimi)
        self.btn_ok.setEnabled(False)
        self.btn_ok.setText("Doğrulanıyor...")
        self.err_label.hide()
        # Qt event loop'un kilidi yansıtması için tekrar çiz
        self.repaint()

        device_id = get_device_fingerprint().hex()
        device_name = get_display_name()

        ok, msg, body = self._client.login(
            license_key=key,
            mt5_login=mt5_login,
            device_id=device_id,
            device_name=device_name,
        )

        if not ok:
            self.btn_ok.setEnabled(True)
            self.btn_ok.setText("✓ Doğrula")
            self._show_error(msg or "Lisans reddedildi.")
            return

        # Başarılı — token'ı diske kaydet
        self.agent_token = body.get("agent_token", "")
        self.customer_name = body.get("customer_name", "") or ""
        self.expires_at = body.get("expires_at")
        self.days_remaining = body.get("days_remaining")

        license_store.save(
            agent_token=self.agent_token,
            license_key=key,
            mt5_login=mt5_login,
            customer_name=self.customer_name,
            expires_at=self.expires_at,
            days_remaining=self.days_remaining,
        )

        self.accept()

    def _show_error(self, text: str) -> None:
        self.err_label.setText("⚠  " + text)
        self.err_label.show()
