import os
import requests
import pandas as pd
import psycopg2
from fastapi import APIRouter

router = APIRouter()

# ✅ HTTPS вместо FTP
NASDAQ_URL = "https://www.nasdaqtrader.com/dynamic/symdir/nasdaqlisted.txt"
OTHER_URL = "https://www.nasdaqtrader.com/dynamic/symdir/otherlisted.txt"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; PortfolioBot/1.0; +https://example.com)"
}

def fetch_tickers_from_url(url: str):
    """Скачивает список тикеров с NASDAQ HTTP-зеркала"""
    print(f"[DEBUG] Fetching: {url}")
    resp = requests.get(url, headers=HEADERS)
    resp.raise_for_status()
    lines = resp.text.splitlines()
    symbols = []
    for line in lines[1:]:  # пропускаем заголовок
        parts = line.split("|")
        if len(parts) > 1 and parts[0] not in ("Symbol", "File Creation Time", ""):
            symbols.append(parts[0].strip())
    print(f"[DEBUG] {url} → {len(symbols)} tickers")
    return symbols

def fetch_sp500():
    url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
    print("[DEBUG] Fetching S&P500 from Wikipedia")
    tables = pd.read_html(url)
    symbols = tables[0]["Symbol"].tolist()
    print(f"[DEBUG] S&P500 → {len(symbols)} tickers")
    return symbols

def fetch_nasdaq100():
    url = "https://en.wikipedia.org/wiki/NASDAQ-100"
    print("[DEBUG] Fetching NASDAQ100 from Wikipedia")
    tables = pd.read_html(url)
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

        sp500 = fetch_sp500()
        nasdaq100 = fetch_nasdaq100()

        # Подключение к БД
        conn = psycopg2.connect(os.environ["DATABASE_URL"])
        cur = conn.cursor()

        # Создание таблицы
        cur.execute("""
        CREATE TABLE IF NOT EXISTS tickers (
            symbol TEXT PRIMARY KEY,
            index_name TEXT
        )
        """)

        # Чистим старые данные
        cur.execute("TRUNCATE tickers")

        # Записываем новые
        for sym in all_symbols:
            index_name = None
            if sym in sp500:
                index_name = "SP500"
            elif sym in nasdaq100:
                index_name = "NASDAQ100"
            cur.execute("INSERT INTO tickers (symbol, index_name) VALUES (%s, %s)", (sym, index_name))

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

