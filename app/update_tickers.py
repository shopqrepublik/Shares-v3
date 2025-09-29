import os
import requests
import pandas as pd
import io
from datetime import datetime
import psycopg2
from psycopg2.extras import execute_values
import logging

# Настраиваем логи
logging.basicConfig(level=logging.INFO)

# Источники данных
NASDAQ_URL = "https://www.nasdaqtrader.com/dynamic/symdir/nasdaqlisted.txt"
OTHER_URL  = "https://www.nasdaqtrader.com/dynamic/symdir/otherlisted.txt"
SP500_URL  = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
NASDAQ100_URL = "https://en.wikipedia.org/wiki/NASDAQ-100"

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; PortfolioBot/1.0)"}

# Подключение к БД
def get_pg_connection():
    dsn = os.environ["DATABASE_URL"].replace("postgresql+psycopg2://", "postgresql://")
    return psycopg2.connect(dsn)

# Загрузка NASDAQ/OTHER
def fetch_tickers_from_url(url: str):
    resp = requests.get(url, headers=HEADERS)
    resp.raise_for_status()
    lines = resp.text.splitlines()
    symbols = []
    for line in lines[1:]:
        parts = line.split("|")
        if len(parts) > 1 and parts[0] not in ("Symbol", "File Creation Time", ""):
            symbols.append(parts[0].strip())
    return symbols

# Загрузка S&P500
def fetch_sp500():
    resp = requests.get(SP500_URL, headers=HEADERS)
    resp.raise_for_status()
    tables = pd.read_html(io.StringIO(resp.text))
    return tables[0]["Symbol"].tolist()

# Загрузка NASDAQ100
def fetch_nasdaq100():
    resp = requests.get(NASDAQ100_URL, headers=HEADERS)
    resp.raise_for_status()
    tables = pd.read_html(io.StringIO(resp.text))
    return tables[4]["Ticker"].tolist()

# Основная функция
def update_tickers():
    try:
        nasdaq = fetch_tickers_from_url(NASDAQ_URL)
        other  = fetch_tickers_from_url(OTHER_URL)
        sp500 = fetch_sp500()
        nasdaq100 = fetch_nasdaq100()

        all_symbols = set(nasdaq + other)
        data = []

        for sym in all_symbols:
            index_name = None
            if sym in sp500:
                index_name = "SP500"
            elif sym in nasdaq100:
                index_name = "NASDAQ100"
            data.append((index_name, sym, datetime.utcnow()))

        conn = get_pg_connection()
        with conn:
            with conn.cursor() as cur:
                # Очистка старых данных
                cur.execute("DELETE FROM tickers WHERE index_name IS NULL")
                cur.execute("DELETE FROM tickers WHERE index_name IN ('SP500','NASDAQ100')")
                # Вставка батчами
                execute_values(
                    cur,
                    "INSERT INTO tickers (index_name, symbol, updated_at) VALUES %s",
                    data,
                    page_size=500
                )
        conn.close()

        result = {
            "status": "ok",
            "total": len(data),
            "sp500_count": len(sp500),
            "nasdaq100_count": len(nasdaq100)
        }
        logging.info(f"[UPDATE_TICKERS] ✅ {result}")
        return result

    except Exception as e:
        logging.error(f"[UPDATE_TICKERS] ❌ {e}")
        return {"status": "error", "message": str(e)}
