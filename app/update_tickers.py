import os
import psycopg2
import pandas as pd
from datetime import datetime

DATABASE_URL = os.getenv("DATABASE_URL")


def fetch_sp500():
    """
    Загружает список тикеров S&P 500 с Wikipedia.
    """
    url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
    df = pd.read_html(url, header=0)[0]
    return df["Symbol"].dropna().tolist()


def fetch_nasdaq100():
    """
    Загружает список тикеров NASDAQ-100 с Wikipedia.
    """
    url = "https://en.wikipedia.org/wiki/NASDAQ-100"
    # на странице несколько таблиц, таблица с тикерами обычно 4-я
    df = pd.read_html(url, header=0)[4]
    return df["Ticker"].dropna().tolist()


def save_to_db(sp500, nasdaq100):
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()

    # чистим старые тикеры
    cur.execute("DELETE FROM tickers")

    now = datetime.utcnow()
    for sym in sp500:
        cur.execute(
            "INSERT INTO tickers (index_name, symbol, updated_at) VALUES (%s, %s, %s)",
            ("SP500", sym, now),
        )
    for sym in nasdaq100:
        cur.execute(
            "INSERT INTO tickers (index_name, symbol, updated_at) VALUES (%s, %s, %s)",
            ("NASDAQ100", sym, now),
        )

    conn.commit()
    cur.close()
    conn.close()

    return {
        "sp500_count": len(sp500),
        "nasdaq100_count": len(nasdaq100),
        "examples_sp500": sp500[:5],
        "examples_nasdaq100": nasdaq100[:5],
        "timestamp": now.isoformat(),
    }


if __name__ == "__main__":
    sp500 = fetch_sp500()
    nasdaq100 = fetch_nasdaq100()
    result = save_to_db(sp500, nasdaq100)
    print("✅ Обновлено:", result)
