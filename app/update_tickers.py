import os
import pandas as pd
import psycopg2
from psycopg2.extras import execute_values


DB_URL = os.getenv("DATABASE_URL")


def fetch_sp500():
    """Загружаем список S&P 500 с Wikipedia"""
    url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
    df = pd.read_html(url)[0]
    return df["Symbol"].dropna().tolist()


def fetch_nasdaq100():
    """Загружаем список Nasdaq 100 с Wikipedia"""
    url = "https://en.wikipedia.org/wiki/NASDAQ-100"
    df = pd.read_html(url)[4]  # таблица с тикерами Nasdaq 100
    return df["Ticker"].dropna().tolist()


def update_tickers():
    """Обновляем таблицу tickers в PostgreSQL"""
    try:
        sp500 = fetch_sp500()
        nasdaq100 = fetch_nasdaq100()

        conn = psycopg2.connect(DB_URL)
        cur = conn.cursor()

        # создаём таблицу при первом запуске
        cur.execute("""
            CREATE TABLE IF NOT EXISTS tickers (
                symbol TEXT PRIMARY KEY,
                index_name TEXT
            )
        """)

        # очищаем перед вставкой
        cur.execute("TRUNCATE tickers")

        # объединяем тикеры с указанием индекса
        all_tickers = [(t, "SP500") for t in sp500] + [(t, "NASDAQ100") for t in nasdaq100]

        # массовая вставка
        execute_values(cur, "INSERT INTO tickers (symbol, index_name) VALUES %s", all_tickers)

        conn.commit()
        cur.close()
        conn.close()

        return {"status": "ok", "sp500": len(sp500), "nasdaq100": len(nasdaq100)}

    except Exception as e:
        return {"status": "error", "detail": str(e)}
