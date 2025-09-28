import os
import logging
import psycopg2
import yfinance as yf
import time
from datetime import datetime

DB_URL = os.getenv("DATABASE_URL")

# -------------------------
# Безопасная загрузка котировок
# -------------------------
def safe_download(ticker, period="6mo", interval="1d"):
    for attempt in range(3):
        try:
            data = yf.download(ticker, period=period, interval=interval, progress=False)
            if not data.empty:
                return data
        except Exception as e:
            logging.warning(f"[WARN] {ticker} attempt {attempt+1} failed: {e}")
            time.sleep(1)
    logging.error(f"[ERROR] {ticker} skipped (no data)")
    return None

# -------------------------
# Чтение тикеров из PostgreSQL
# -------------------------
def load_tickers(limit=50):
    if not DB_URL:
        raise RuntimeError("DATABASE_URL not set")

    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()
    cur.execute("SELECT symbol FROM tickers LIMIT %s;", (limit,))
    rows = cur.fetchall()
    cur.close()
    conn.close()

    tickers = [r[0].strip().upper() for r in rows]
    return tickers

# -------------------------
# Метрики по акциям
# -------------------------
def analyze_ticker(ticker):
    hist = safe_download(ticker)
    if hist is None:
        return None

    close = hist["Close"]
    momentum = (close.iloc[-1] - close.iloc[0]) / close.iloc[0] * 100
    score = round(momentum, 2)

    pattern = "uptrend" if score > 0 else "downtrend"

    return {
        "symbol": ticker,
        "price": round(close.iloc[-1], 2),
        "quantity": 1,  # пока просто 1 акция
        "score": score,
        "momentum": momentum,
        "pattern": pattern,
        "timestamp": datetime.utcnow().isoformat()
    }

# -------------------------
# Сборка портфеля
# -------------------------
def build_portfolio(profile):
    tickers = load_tickers(limit=50)
    logging.info(f"[TICKERS] Загружено {len(tickers)} тикеров из БД")

    portfolio = []
    skipped = []

    for t in tickers:
        res = analyze_ticker(t)
        if res:
            portfolio.append(res)
        else:
            skipped.append(t)

    # Сортируем по score и выбираем топ-5
    portfolio = sorted(portfolio, key=lambda x: x["score"], reverse=True)[:5]

    return portfolio, skipped
