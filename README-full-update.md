# AI Portfolio Bot — Full Update (Guardrails + SELL/BUY + Logging)

Что добавлено:
- `app/guardrails.py` — конфиг из ENV, SELL/BUY ребаланс с учётом текущих позиций, лимиты на сделку/позицию.
- `app/models.py` — SQLAlchemy таблицы: trades, positions_snapshots, metrics_daily.
- `app/reporting.py` — логирование превью/сделок, снимок позиций, ежедневные метрики (equity, benchmark).
- `app/main.py` — эндпоинт `/rebalance?budget=1000&submit=true|false`; инициализация БД; снимок позиций.

ENV параметры (см. .env.example):
- MAX_WEIGHT_STOCK, MAX_WEIGHT_ETF, MAX_WEIGHT_MICROCAP_TOTAL
- MIN_PRICE, MIN_ADV_USD, CASH_BUFFER, MARKET_HOURS_ONLY, ALLOW_SHORTS
- MAX_ORDER_USD, MAX_POSITION_USD

Поток:
1) POST /onboard → allocations
2) POST /rebalance?budget=...&submit=false → превью + проверки
3) POST /rebalance?budget=...&submit=true  → отправка SELL/BUY в Alpaca (если валидация пройдена и рынок открыт)
