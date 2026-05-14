# GoldSam V2 Strategy Server

VPS'te koşan strateji engine + FastAPI sunucusu. Bot bu sunucuya bağlanır, sinyalleri çeker, MT5'te işlem açar.

## Kurulum (VPS Windows Server 2022)

1. Python 3.12 kur (https://www.python.org/downloads/ — "Add to PATH" işaretli).
2. Bu klasörü `C:\GoldSam_Server\` altına kopyala.
3. `KUR.bat` çift tık → bağımlılıkları kurar, DB init eder.
4. **MT5'i (metadinleme klasöründeki XM Demo)** açık tut, GOLD# sembolü Market Watch'ta olsun.
5. `BASLAT.bat` çift tık → sunucu 8000 portunda dinlemeye başlar.

## Endpoint'ler

### Public
- `GET /public/status` — sistem durumu (engine + MT5)
- `GET /public/signals/recent?limit=50` — son sinyaller (site dashboard için)

### Agent (Bot)
- `POST /v1/heartbeat` — bot durum bildirir (header: `X-Agent-Token`)
- `GET /v1/signals/pending?since_id=X&mt5_login=Y` — bekleyen sinyaller
- `POST /v1/trade_report` — trade sonuç raporu
- `GET /v1/license/check?mt5_login=Y` — lisans doğrulama

### Admin (`X-Admin-Token` header)
- `POST /admin/license/add` — yeni müşteri ekle
- `GET /admin/licenses` — tüm lisanslar
- `GET /admin/trade_reports` — trade raporları
- `POST /admin/engine/start` / `/stop` — engine kontrol
- `GET /admin/cleanup?days=30` — eski sinyalleri sil

## Müşteri Ekleme (Admin)

```bash
curl -X POST http://localhost:8000/admin/license/add \
  -H "X-Admin-Token: <data/admin_token.txt içeriği>" \
  -H "Content-Type: application/json" \
  -d '{"mt5_login": 148744, "mt5_server": "FundedTraderMarkets-Server", "customer_name": "Ali Veli", "expires_days": 365}'
```

Dönen `agent_token` müşterinin bot'una verilir.

## Strateji Listesi (Sunucu Tarafı, 6 Adet)

| Magic | Strateji | Yön |
|---|---|---|
| 20270001 | 8T LONG | BUY |
| 20270002 | 8T SHORT | SELL |
| 20270011-14 | MULTI100 (M30/H2/H3/H4) | BUY |
| 20270101-127 | MICRO-S (27 modül) | BUY |
| 20270200 | GOLDS (MEGA_B) | SELL |
| 20270300 | GENIS (LSVC-MTF) | BUY |

## DB

SQLite: `data/goldsam.sqlite`
- `signals` — üretilen sinyaller
- `licenses` — müşteriler
- `trade_reports` — bot raporları
