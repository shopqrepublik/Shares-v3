import os
import psycopg2
import pandas as pd
from psycopg2.extras import execute_values

DB_URL = os.getenv("DATABASE_URL")

def fetch_sp500():
    url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
    df = pd.read_html(url)[0]
    return df["Symbol"].dropna().tolist()

def fetch_nasdaq100():
    url = "https://en.wikipedia.org/wiki/NASDAQ-100"
    df = pd.read_html(url)[4]  # таблица с тикерами NASDAQ-100
    return df["Ticker"].dropna().tolist()

def save_to_db(sp500, nasdaq100):
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()

    # создаём таблицу если ещё не было
    cur.execute("""
        CREATE TABLE IF NOT EXISTS tickers (
            symbol TEXT PRIMARY KEY,
            index_name TEXT
        )
    """)

    # очищаем старые данные
    cur.execute("TRUNCATE tickers")

    # готовим данные для вставки
    values = [(t, "SP500") for t in sp500] + [(t, "NASDAQ100") for t in nasdaq100]
    execute_values(cur, "INSERT INTO tickers (symbol, index_name) VALUES %s", values)

    conn.commit()
    cur.close()
    conn.close()

def update_tickers():
    try:
        sp500 = fetch_sp500()
        nasdaq100 = fetch_nasdaq100()
        save_to_db(sp500, nasdaq100)
        return {"status": "ok", "sp500": len(sp500), "nasdaq100": len(nasdaq100)}
    except Exception as e:
        return {"status": "error", "detail": str(e)}
