import os
import psycopg2
import pandas as pd
import requests
from io import StringIO
from datetime import datetime

DATABASE_URL = os.getenv("DATABASE_URL")

def fetch_sp500():
    url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        html = requests.get(url, headers=headers, timeout=20).text
        table = pd.read_html(StringIO(html))[0]
        return table["Symbol"].tolist()
    except Exception as e:
        print(f"[WARN] Wikipedia S&P500 failed: {e}")
        # fallback to GitHub CSV
        url_csv = "https://datahub.io/core/s-and-p-500-companies/r/constituents.csv"
        df = pd.read_csv(url_csv)
        return df["Symbol"].tolist()

def fetch_nasdaq100():
    url = "https://en.wikipedia.org/wiki/NASDAQ-100"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        html = requests.get(url, headers=headers, timeout=20).text
        tables = pd.read_html(StringIO(html))
        # ищем таблицу с тикерами
        for tbl in tables:
            cols = [c.lower() for c in tbl.columns]
            if "ticker" in cols or "symbol" in cols:
                colname = "Ticker" if "Ticker" in tbl.columns else "Symbol"
                return tbl[colname].tolist()
        raise ValueError("Не найдена таблица с тикерами NASDAQ-100")
    except Exception as e:
        print(f"[WARN] Wikipedia NASDAQ100 failed: {e}")
        # fallback: статичный CSV (например nasdaqtrader.com)
        url_csv = "https://datahub.io/core/nasdaq-listings/r/nasdaq-listed.csv"
        df = pd.read_csv(url_csv)
        return df["Symbol"].tolist()

def save_to_db(sp500, nasdaq100):
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()

    # чистим старые тикеры
    cur.execute("DELETE FROM tickers")

    now = datetime.utcnow()
    for sym in sp500:
        cur.execute("INSERT INTO tickers (index_name, symbol, updated_at) VALUES (%s, %s, %s)",
                    ("SP500", sym, now))
    for sym in nasdaq100:
        cur.execute("INSERT INTO tickers (index_name, symbol, updated_at) VALUES (%s, %s, %s)",
                    ("NASDAQ100", sym, now))

    conn.commit()
    cur.close()
    conn.close()

    return {
        "sp500_count": len(sp500),
        "nasdaq100_count": len(nasdaq100),
        "examples_sp500": sp500[:5],
        "examples_nasdaq100": nasdaq100[:5],
        "timestamp": now.isoformat()
    }

if __name__ == "__main__":
    sp500 = fetch_sp500()
    nasdaq100 = fetch_nasdaq100()
    result = save_to_db(sp500, nasdaq100)
    print("✅ Обновлено:", result)
