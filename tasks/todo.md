# GOLDSAM V2 v1.0.0 — İnşa Planı (Master Doküman)

> Bu dosya GOLDSAM V2'nin tam inşa planıdır. Kod yazılmadan ÖNCE okunup onaylanır.
> Her milestone tamamlandığında üstüne ✅ işaretlenir. Yarım kalanlar `## Yarım Kalanlar` altına gider.

---

## 1. Final Klasör Yapısı

```
GOLDSAM V2/
├── main.py                          # Entry — single-instance mutex + bootstrap
├── app.py                           # MainWindow (PySide6) — UI builder
├── config.py                        # settings.json + APPDATA yol yönetimi
├── logger.py                        # Dosya + konsol + Qt-sinyalli loglama
├── version.py                       # VERSION = "1.0.0"
├── requirements.txt
├── README.md
├── CLAUDE.md                        # Proje kuralları (bu klasörde, ayrı)
│
├── core/                            # Bot çekirdeği — UI'dan bağımsız
│   ├── __init__.py
│   ├── mt5_connector.py             # MT5 bağlantı + AutoTrading açma
│   ├── account_lock.py              # Hesap kilidi (AES-256, cihaz fingerprint) — YENİ
│   ├── device_id.py                 # MAC + CPU hash → fingerprint — YENİ
│   ├── trade_executor.py            # Market order gönderici
│   ├── lifecycle.py                 # Trailing ($1 → $0.50 ladder) [CYTHON]
│   ├── position_monitor.py          # Açık pozisyon takip + lifecycle bağlama
│   ├── trade_history.py             # SQLite işlem geçmişi
│   ├── strategy_engine.py           # Plugin loader + scheduler — YENİ
│   ├── bar_provider.py              # MT5 OHLCV bar çekme + cache — YENİ
│   └── agent_worker.py              # QThread → asyncio event loop
│
├── strategies/                      # Plugin tabanlı stratejiler — SADECE 2 ADET
│   ├── __init__.py
│   ├── base.py                      # Strategy abstract + Signal dataclass
│   ├── dengeli_8t.py                # 8T LONG+SHORT [CYTHON]
│   └── multi100/                    # MULTI100 paketi [CYTHON]
│       ├── __init__.py
│       ├── indicators.py            # RSI, ATR, BB, Heikin-Ashi
│       └── recipes.py               # S04, S11, S12, S17, S19, S22, S26, S30 × TF
│
├── ui/                              # PySide6 widget'ları
│   ├── __init__.py
│   ├── widgets/
│   │   ├── status_bar_top.py        # MT5 ✓ | Sinyal ✓ | Bot ✗ + Cihaz
│   │   ├── strategy_card.py         # checkbox + lot input + açıklama
│   │   ├── kasa_panel.py            # Bakiye preset + concurrent limit + Cuma
│   │   ├── log_panel.py             # Alt log paneli (QtLogHandler)
│   │   └── footer_bar.py            # Varlık $ + Kaydet/Başlat/Durdur/Test/Çıkış/Güncelle
│   └── styles.py                    # Tek yerde renkler/QSS
│
├── build/                           # Build pipeline
│   ├── setup_cython.py              # Cython compile (kritik .pyd dosyaları)
│   ├── GOLDSAM_V2.spec              # PyInstaller spec
│   └── build.py                     # bump version + cython + pyinstaller + smoke test
│
└── assets/
    ├── icon.ico
    └── alarm.wav
```

---

## 2. Modül Sorumlulukları

### `core/mt5_connector.py`
- **Görev:** `mt5.initialize()`, hesap/sembol bilgisi, order/modify/close, OHLCV çekme.
- **Pattern kaynağı:** `mt5-agent/core/mt5_connector.py:11-62` doğrudan referans (özellikle `_enable_autotrading`).
- **API:**
  - `initialize(path, login, password, server) -> bool`
  - `get_account_info() -> dict`
  - `get_positions(symbol=None) -> list`
  - `get_symbol_info(symbol) -> dict`
  - `send_order(symbol, side, lot, sl, tp, magic, comment) -> dict`
  - `close_position(ticket) -> dict`, `modify_position(ticket, sl, tp) -> dict`
  - `copy_rates(symbol, tf, count) -> list`

### `core/account_lock.py` — KRİTİK YENİ
- **Görev:** İlk başlatmada MT5 login/server'ı cihaz ID'siyle AES şifreleyip `%APPDATA%/GOLDSAM_V2/account.lock` dosyasına yazar. Sonraki açılışlarda decrypt edip karşılaştırır.
- **API:** `bind_or_verify(account_info: dict) -> tuple[bool, str]`, `is_bound() -> bool`, `unbind()`

### `core/device_id.py`
- **Görev:** MAC + CPU + Windows MachineGuid → SHA-256 → 32 byte sabit fingerprint.
- **API:** `get_device_id() -> bytes`, `get_display_name() -> str` ("DESKTOP-XXXXXXX")

### `core/strategy_engine.py` — YENİ MİMARİ KALBİ
- **Görev:** Aktif `Strategy` plugin'leri her döngüde tarar, sinyal döndüren stratejiyi `TradeExecutor`'a verir. Magic + aynı strateji tek poz + concurrent limit + Cuma blackout kontrolü burada.
- **Pattern:** `mt5-agent/core/agent_worker.py:429-520` + `multi100.py:330-416`.
- **API:** `register(strategy)`, `tick()`, `should_skip(strategy) -> bool`

### `core/lifecycle.py` [CYTHON]
- **Görev:** Trailing matematik — saf hesap, MT5 çağrısı yok. "Yeni SL ne olmalı" döndürür.
- **Pattern:** `mt5-agent/core/position_monitor.py:329-426` (`_apply_trailing`) + `backtest_may8_v2.py:79-162` (`simulate_exit_dollar`).
- **API:** `compute_new_sl(side, entry, current, current_sl, peak, lot, symbol, trail_activate_usd) -> float | None`

### `core/position_monitor.py`
- **Görev:** Her 3sn'de açık pozisyonları tarar, `lifecycle.compute_new_sl()` çağırır, `mt5.modify_position()` ile SL ileriye iter. Kapanan ticket'ları DB'ye yazar.
- **Pattern:** `mt5-agent/core/position_monitor.py` (sunucu kısımları çıkartılacak).

### `core/agent_worker.py`
- **Görev:** `QThread` içinde asyncio event loop. Task'lar: `strategy_engine.tick_loop`, `position_monitor.start`, `_mt5_reconnect_loop`. **WS yok.**
- **Pattern:** `mt5-agent/core/agent_worker.py:52-146` iskeleti. WS_Client + Reporter referansları silinir.
- **Qt sinyalleri:** `status_changed`, `account_updated`, `positions_updated`, `signal_received`, `trade_executed`, `error_occurred`.

### `strategies/base.py` — PLUGIN ARAYÜZÜ
```python
@dataclass
class Signal:
    side: str             # "buy" | "sell"
    symbol: str
    lot: float
    magic: int
    comment: str
    sl_usd: float = 75.0
    trail_activate_usd: float = 1.0

class Strategy(ABC):
    key: str              # "dengeli_8t"
    display: str          # "DENGELİ — 8T Sinyal"
    timeframes: list[str] # ["M1"] (8T), ["M30","H2","H3","H4"] (MULTI100)
    symbols: list[str]
    enabled: bool = False
    lot: float = 0.01

    @abstractmethod
    def check(self, bars_by_tf: dict[str, list]) -> Signal | None: ...
```

### `strategies/dengeli_8t.py`
- `detector.py` (8t-algorithm) kopyalanır, üstüne adapter yazılır. Cluster dedup `(side, dip_time)` set'iyle.

### `strategies/multi100/recipes.py`
- `multi100.py:77-129`'daki 8 fonksiyon + TF döngüsü = 32 kombinasyon.

---

## 3. AutoTrading common.ini Açma Yöntemi

`mt5-agent/core/mt5_connector.py:23-62`'den çıkarılan akış:

1. `mt5.initialize()` başarılı olduktan sonra `mt5.terminal_info()` çağrılır.
2. `ti.trade_allowed` False ise `ti.data_path` alınır.
3. `data_path + "/config/common.ini"` UTF-16 ile okunur (MT5 her zaman UTF-16 yazar).
4. `AutoTrading=` aranır → `0`'sa `1` yap; yoksa `[Common]` altına `AutoTrading=1` ekle.
5. UTF-16 ile geri yazılır.
6. `mt5.shutdown()` + `mt5.initialize()` ile MT5 reload.
7. `ti.trade_allowed` hâlâ False ise log warn + UI toast.

**UI bildirimi:** "AutoTrading otomatik açıldı, MT5 yeniden başlatılıyor..." 2sn'lik toast.

---

## 4. MT5 Hesap Kilidi Tasarımı

### Anahtar türetme
- `device_id_raw = MAC + CPU_info + MachineGuid` → SHA-256 → 32 byte
- AES key olarak doğrudan veya Fernet b64 ile

### Şifreleme
- `cryptography.fernet.Fernet` (AES-128 CBC + HMAC-SHA256)
- Built-in nonce + tamper detection — temiz

### Lock dosyası
- **Konum:** `%APPDATA%/GOLDSAM_V2/account.lock`
- **İçerik (encrypt before write):**
  ```json
  { "login": 12345678, "server": "XMGlobal-MT5", "bound_at": "2026-05-11T14:00:00", "version": 1 }
  ```

### Doğrulama akışı
```
on_app_start():
    if not lock_exists():
        mt5_info = connector.get_account_info()
        if not mt5_info: show_error("MT5 aç + login"); exit
        write_encrypted_lock(login=mt5_info.login, server=mt5_info.server)
        toast("Hesap kilitlendi: #{login} @ {server}")
        return OK

    locked = decrypt_lock()   # InvalidToken → tamper, sil ve yeniden bind
    current = connector.get_account_info()
    if current.login != locked.login OR current.server != locked.server:
        show_error("Bu bot başka hesaba kilitli (#{locked.login}). Yetkisiz hesap.")
        exit
    return OK
```

---

## 5. PyInstaller + Cython Hibrit Build Pipeline

### `.pyd` derlenecek (Cython)
- `core/lifecycle.py`
- `strategies/dengeli_8t.py` (+ inline detector)
- `strategies/multi100/recipes.py` + `indicators.py`
- (İleride) `strategies/safe_*.py`, `aggressive_*.py`

### `.py` kalacak
- `main.py`, `app.py`, `config.py`, `logger.py`, `version.py`
- Tüm `ui/`
- `core/mt5_connector.py`, `account_lock.py`, `strategy_engine.py`, `agent_worker.py`

### Build sırası (`build/build.py`)
1. `version.py` oku → "1.0.0"
2. Temizle: `dist/`, `build/`, `*.pyd`, `*.c`
3. `python build/setup_cython.py build_ext --inplace`
4. PyInstaller spec çağır (hiddenimports + datas + excludes)
5. Smoke test: `dist/GOLDSAM_V2.exe`'yi 8sn çalıştır, alive mı kontrol

### Spec dosyası kritik kısım
```python
a = Analysis(['../main.py'],
    hiddenimports=['core.lifecycle', 'strategies.dengeli_8t',
                   'strategies.multi100.recipes',
                   'strategies.multi100.indicators'],
    excludes=['detector_py_source'],
)
```

---

## 6. Geliştirme Sırası (Milestone'lar — her biri demo verilebilir)

- [ ] **M1.** İskelet + boş UI → exe açılır, "GOLDSAM V2 v1.0.0" başlık, boş pencere. Pipeline doğrulanır.
- [ ] **M2.** MT5 bağlantısı → "MT5 ✓" yeşil. "MT5 Test" butonu hesap bilgisini popup'la gösterir. AutoTrading otomatik açılır.
- [ ] **M3.** Hesap kilidi → İlk çalıştırmada `account.lock` oluşur. Farklı hesapla açılınca "Yetkisiz hesap" dialog → çıkış.
- [ ] **M4.** UI tamamlanır → Tüm paneller görünür. Kullanıcı UI'da gezinip ekran görüntüsü onayı verir.
- [ ] **M5.** Strategy engine + 8T → "DENGELİ — 8T" işaretli + "Başlat" → log'a `SİNYAL: 8T LONG @ 2412.50`. Emir HENÜZ yok.
- [ ] **M6.** Trade executor + lifecycle → Gerçek MT5 emri (XM demo). $1 kar → BE'ye SL. $0.50 ladder. Doğal kapanış log'lanır.
- [ ] **M7.** Aynı strat tek poz + concurrent limit → 4. emir kullanıcı limiti dolu ise RED.
- [ ] **M8.** MULTI100 entegrasyonu → S04..S30 × M30/H2/H3/H4 = 32 kombinasyon engine'e register. Her TF kendi magic'iyle açar.
- [ ] **M9.** Kasa Yönetimi → Bakiye preset radio lot doldurur, Cuma blackout, manuel pozisyon trail switch.
- [ ] **M10.** Cython derleme + final paketleme → tek `GOLDSAM_V2.exe` (~25MB), `.pyd`'ler gömülü.
- [ ] **M11.** Smoke test (temiz VM) → MT5 demo → 8T + MULTI100 trade aç/kapa → **v1.0.0 RELEASE**

---

## 7. mt5-agent'tan ÖĞRENİLECEK ama TAŞINMAYACAK Kısımlar

| Modül | Karar | Neden |
|---|---|---|
| `core/ws_client.py` | **SİL** | GOLDSAM V2 tamamen lokal. |
| `core/reporter.py` | **SİL** | Sunucu yok. |
| `login_dialog.py` (kriptoly.com) | **SİL** | Yeni model "hesap kilidi". |
| `core/decision_engine.py` | **DÖNÜŞTÜR** | Risk kontrol mantığı `strategy_engine`'e taşınır. `Decision` → `Signal`. |
| `app.py` (1709 satır tek dosya) | **PARÇALA** | `ui/widgets/*` altına böl. |
| `truststore` / `certifi` SSL hack | **SİL** | HTTPS yok. |
| `_check_single_instance` (mutex) | **TAŞI** | Birebir kopyalanabilir, sağlam. |
| `_show_first_run_notice` (SmartScreen uyarısı) | **TAŞI** | Aynı pattern gerekli. |
| `_cleanup_update_files` | **BASİTLEŞTİR** | `_MEI*` temp temizlik kalsın. |

---

## 8. Risk / Uyarı Noktaları

1. **UTF-16 common.ini**: MT5 her zaman UTF-16 LE yazar. BOM olmayabilir — `errors="ignore"` ekle.
2. **Restart sonrası trailing fallback**: Bot kapanıp açılınca `_tracked` boşalır. Persistent `_tracked.json` ile sağlamlaştır.
3. **Phantom close bug** (`position_monitor.py:217-251`): MT5 bağlantısı kekemelik yapınca `get_positions()` boş döner ve bot "kapandı" sanır. `get_deal_close_info` doğrulaması ŞART. **KRİTİK.**
4. **Magic number çakışması**: GOLDSAM V2'de tek namespace `2027XXXX`:
   - DENGELİ 8T LONG: `20270001`, SHORT: `20270002`
   - MULTI100 M30: `20270011`, H2: `20270012`, H3: `20270013`, H4: `20270014`
5. **Sembol farkı broker'a göre**: `GOLD#`, `XAUUSD`, `GOLDm#`... `config.py:get_symbol_map` pattern'i + UI'da "manuel sembol seç" fallback.
6. **`mt5.symbol_select(symbol, True)`**: Sembol Market Watch'a eklenmemişse `symbol_info` None döner. Her `get_bars` ve `send_order` öncesi çağrılır.
7. **PyInstaller `--onefile` 3-5sn açılış** (anti-virüsle 15sn'ye çıkar): Splash screen mt5-agent'ta yok — GOLDSAM V2 için `--splash assets/splash.png` ekle.
8. **Cython + PyInstaller hidden import**: `.pyd` dosyaları PyInstaller bazen bulamaz — `hiddenimports` elle listele.
9. **`app.py` parçalama tuzağı**: mt5-agent'ın 1709 satırlık tek dosyasını kopyalayıp parçalamak yerine, en başından `ui/widgets/` altına parçalayarak yaz. Kopyalama tuzağına düşme.
10. **`record_close` çift-INSERT**: `mt5-agent/core/trade_history.py:64` `INSERT OR REPLACE`. Daha temiz: SELECT → varsa UPDATE, yoksa INSERT.

---

## 9. Kullanıcı Onay Notu

**Bu plan onaylandıktan sonra** koda geçilir.
Kullanıcının onay bekleyen noktalar:
- [ ] Klasör yapısı kabul mi?
- [ ] Milestone sırası (M1→M12) doğru mu? Demo noktaları mantıklı mı?
- [ ] Magic number şeması (2027XXXX) kabul mi?
- [ ] PySide6 + Cython + Fernet kombinasyonu net mi?
- [ ] Mt5-agent'tan SİLİNECEK listesi doğru mu? (özellikle `ws_client`, `reporter`, `login_dialog`)
- [ ] M1'den başlamak için yeşil ışık?

---

## Review Section (her milestone sonunda doldurulur)

### M1 — İskelet
*Henüz başlanmadı.*

### M2 — MT5 bağlantısı
*Henüz başlanmadı.*

... (M12'ye kadar)

---

## Yarım Kalanlar
*(Şu an boş.)*
