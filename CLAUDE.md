# GOLDSAM V2 — Claude Kuralları

## Proje Özeti
MT5 broker üzerinden çalışan, çoklu strateji destekli, profesyonel masaüstü trading botu.
Kullanıcının PC'sinde tamamen **lokal** çalışır — sunucu, websocket, dış bağımlılık YOK.

## Tech Stack
- **Python 3.12**
- **PySide6** — GUI (LGPL, ticari satış müsait)
- **MetaTrader5** — broker bağlantısı
- **pandas** — indikatör hesaplamaları (MULTI100 için)
- **cryptography** (Fernet) — hesap kilidi şifreleme
- **Cython** — kritik strateji dosyalarını `.pyd` derler (IP koruma)
- **PyInstaller** — tek dosya `.exe` paketleme

## Ana Klasörler
```
GOLDSAM V2/
├── main.py + app.py + config.py + logger.py    # Entry + UI bootstrap
├── core/        # Bot çekirdeği (MT5, kilit, lifecycle, engine)
├── strategies/  # Plugin tabanlı stratejiler (8T, MULTI100, Safe, Aggressive)
├── ui/widgets/  # PySide6 bileşenleri
├── build/       # PyInstaller + Cython build pipeline
├── assets/      # icon, sound
└── tasks/       # Çalışma planları (todo.md, lessons.md)
```

## Kritik Kurallar
1. **Stratejiler plugin pattern** — her biri `Strategy` abstract class'tan türer, `check(bars) → Signal | None` arayüzünü uygular. Yeni strateji eklemek = `strategies/` altında yeni dosya.
2. **MT5 hesap kilidi** — bot ilk başlatmada `mt5.account_info()` okur, cihaz ID'sıyla AES şifreleyip `account.lock`'a yazar. Sonraki açılışlarda doğrular, farklı hesapsa kapanır.
3. **Aynı stratejiden tek pozisyon** (default kural) — 8T LONG açıkken yeni 8T LONG sinyali REDDEDILIR.
4. **Concurrent limit kullanıcı seçimi** — UI'da 1-3 / 4-6 / 7-10 / sınırsız. Bot karışmaz.
5. **AutoTrading otomatik açılır** — `mt5.terminal_info().trade_allowed` False ise `common.ini`'i UTF-16 olarak okuyup `AutoTrading=1` yapar, MT5 restart eder.
6. **Trailing ortak motor** — Tüm stratejiler `core/lifecycle.compute_new_sl()` kullanır. $1 aktive → BE, sonra $0.50 ladder.
7. **Cython `.pyd` zorunlu** dosyalar: `core/lifecycle.py`, `strategies/dengeli_8t.py`, `strategies/multi100/recipes.py`. UI ve config `.py` kalır.
8. **Magic number ayrımı** — Her strateji unique magic. Format: `2027XXXX`:
   - 8T LONG: `20270001`, 8T SHORT: `20270002`
   - MULTI100 M30: `20270011`, H2: `20270012`, H3: `20270013`, H4: `20270014`

## Deployment
- Geliştirme: `python main.py`
- Test build: `python build/build.py --dev` (Cython skip)
- Release: `python build/build.py` → `dist/GOLDSAM_V2.exe` (tek dosya, ~25MB)
- Versiyon: `version.py` içinde `VERSION` — build script bunu okur.

## Versiyon Numaralandırma Kuralı (KESİN)
- Format: `MAJOR.MINOR.PATCH` — her hane tek basamaklı (0-9)
- Her küçük değişiklikte PATCH++ (1.0.0 → 1.0.1 → ... → 1.0.9)
- PATCH 9'a ulaşınca **MINOR++ ve PATCH=0** (1.0.9 → **1.1.0**) — ASLA 1.0.10 olmaz
- MINOR 9'a ulaşınca **MAJOR++ ve MINOR=0, PATCH=0** (1.9.9 → **2.0.0**)
- Major milestone bittiğinde ekstra olarak MINOR++ tetiklenebilir (örn. M2 bittiğinde 1.x.y → 1.(x+1).0)

## Geliştirme Sırası
1. Skelet + boş UI → PyInstaller smoke test
2. MT5 bağlantısı + AutoTrading otomatik aç
3. Hesap kilidi (ilk çalıştırmada bind, sonraki açılışlarda verify)
4. UI tamamlanır — 2 strateji kartı (8T + MULTI100), Kasa paneli, log, butonlar
5. Strategy engine + 8T entegrasyonu (sadece sinyal log)
6. Trade executor + lifecycle (gerçek emir)
7. Aynı strat tek poz + concurrent limit
8. MULTI100 entegrasyonu (8 strat × 4 TF = 32 kombinasyon)
9. Kasa Yönetimi davranışları (preset, Cuma blackout, manuel pozisyon trail)
10. Cython derlemesi + final paketleme
11. Smoke test → v1.0.0 release

## Session Log
→ `.claude/sessions/YYYY-MM-DD.md` dosyalarında tutulur

## Referans Projeler (bu klasör dışında, sadece pattern öğrenmek için)
- `C:\Users\nurul\OneDrive\Masaüstü\mt5-agent - Kopya\` — UI pattern, AutoTrading açma, build/spec
- `C:\Users\nurul\OneDrive\Masaüstü\8t-algorithm\detector.py` — 8T sinyal algoritması
- `C:\Users\nurul\OneDrive\Masaüstü\8T sinyal\backtest_may8_v2.py` — 8T lifecycle (SL/trail)
- `C:\Users\nurul\OneDrive\Masaüstü\MULTI100\multi100.py` — 8 strateji + 4 TF (S04..S30)
