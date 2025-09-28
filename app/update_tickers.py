# app/update_tickers.py
import pandas as pd
import psycopg2
import os

DB_URL = os.getenv("DATABASE_URL")

# --- Функции для загрузки тикеров ---
def fetch_sp500_tickers():
    url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
    table = pd.read_html(url)[0]
    return table["Symbol"].tolist()

def fetch_nasdaq100_tickers():
    url = "https://en.wikipedia.org/wiki/NASDAQ-100"
    tables = pd.read_html(url)
    # таблица с тикерами обычно первая или вторая
    for t in tables:
        if "Ticker" in t.columns or "Symbol" in t.columns:
            col = "Ticker" if "Ticker" in t.columns else "Symbol"
            return t[col].dropna().tolist()
    return []

# --- Обновление базы ---
def update_tickers():
    sp500 = fetch_sp500_tickers()
    nasdaq100 = fetch_nasdaq100_tickers()

    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()

    # очищаем старые записи
    cur.execute("DELETE FROM tickers")

    # вставляем новые
    for sym in sp500:
        cur.execute("INSERT INTO tickers (index_name, symbol) VALUES (%s, %s)", ("SP500", sym.strip()))
    for sym in nasdaq100:
        cur.execute("INSERT INTO tickers (index_name, symbol) VALUES (%s, %s)", ("NASDAQ100", sym.strip()))

    conn.commit()
    cur.close()
    conn.close()

    return {
        "sp500_count": len(sp500),
        "nasdaq100_count": len(nasdaq100),
        "examples_sp500": sp500[:5],
        "examples_nasdaq100": nasdaq100[:5],
    }

if __name__ == "__main__":
    result = update_tickers()
    print("✅ Обновлено:", result)
