import os
import requests
import pandas as pd
import psycopg2
from psycopg2.extras import execute_values
from fastapi import APIRouter

router = APIRouter()

# Источники
NASDAQ_URL = "https://www.nasdaqtrader.com/dynamic/symdir/nasdaqlisted.txt"
OTHER_URL = "https://www.nasdaqtrader.com/dynamic/symdir/otherlisted.txt"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; PortfolioBot/1.0; +https://example.com)"
}

def get_pg_connection():
    """Создание подключения к БД, автоматически убираем '+psycopg2'"""
    raw_dsn = os.environ["DATABASE_URL"]
    if raw_dsn.startswith("postgresql+psycopg2://"):
        raw_dsn = raw_dsn.replace("postgresql+psycopg2://", "postgresql://", 1)
    return psycopg2.connect(raw_dsn)

def fetch_tickers_from_url(url: str):
    print(f"[DEBUG] Fetching: {url}")
    resp = requests.get(url, headers=HEADERS)
    resp.raise_for_status()
    lines = resp.text.splitlines()
    symbols = []
    for line in lines[1:]:
        parts = line.split("|")
        if len(parts) > 1 and parts[0] not in ("Symbol", "File Creation Time", ""):
            symbols.append(parts[0].strip())
    print(f"[DEBUG] {url} → {len(symbols)} tickers")
    return symbols

def fetch_sp500():
    url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
    print("[DEBUG] Fetching S&P500 from Wikipedia")
    resp = requests.get(url, headers=HEADERS)
    resp.raise_for_status()
    tables = pd.read_html(resp.text)
    symbols = tables[0]["Symbol"].tolist()
    print(f"[DEBUG] S&P500 → {len(symbols)} tickers")
    return symbols

def fetch_nasdaq100():
    url = "https://en.wikipedia.org/wiki/NASDAQ-100"
    print("[DEBUG] Fetching NASDAQ100 from Wikipedia")
    resp = requests.get(url, headers=HEADERS)
    resp.raise_for_status()
    tables = pd.read_html(resp.text)
    symbols = tables[4]["Ticker"].tolist()
    print(f"[DEBUG] NASDAQ100 → {len(symbols)} tickers")
    return symbols

@router.post("/update_tickers")
def update_tickers():
    try:
        # Получаем данные
        nasdaq = fetch_tickers_from_url(NASDAQ_URL)
        other = fetch_tickers_from_url(OTHER_URL)
        all_symbols = set(nasdaq + other)

        sp500 = set(fetch_sp500())
        nasdaq100 = set(fetch_nasdaq100())

        # Готовим список для вставки
        rows = []
        for sym in all_symbols:
            index_name = None
            if sym in sp500:
                index_name = "SP500"
            elif sym in nasdaq100:
                index_name = "NASDAQ100"
            rows.append((sym, index_name))

        # Подключение к БД
        conn = get_pg_connection()
        cur = conn.cursor()

        # Создание таблицы
        cur.execute("""
        CREATE TABLE IF NOT EXISTS tickers (
            id SERIAL PRIMARY KEY,
            symbol TEXT UNIQUE,
            index_name TEXT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)

        # Чистим старые данные
        cur.execute("TRUNCATE tickers RESTART IDENTITY")

        # ⚡ Вставляем пачкой
        execute_values(
            cur,
            "INSERT INTO tickers (symbol, index_name) VALUES %s",
            rows,
            page_size=500
        )

        conn.commit()
        cur.close()
        conn.close()

        result = {
            "status": "ok",
            "total": len(all_symbols),
            "sp500_count": len(sp500),
            "nasdaq100_count": len(nasdaq100)
        }
        print(f"[DEBUG] Update complete: {result}")
        return result

    except Exception as e:
        print(f"[ERROR] update_tickers failed: {e}")
        return {"status": "error", "detail": str(e)}
