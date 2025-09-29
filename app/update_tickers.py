import os
import psycopg2
import requests
from datetime import datetime

DATABASE_URL = os.getenv("DATABASE_URL")
FMP_API_KEY = os.getenv("FMP_API_KEY")  # добавьте в Railway Variables


def fetch_sp500():
    """
    Получаем список компаний S&P 500 через Financial Modeling Prep API
    """
    url = f"https://financialmodelingprep.com/api/v3/sp500_constituent?apikey={FMP_API_KEY}"
    resp = requests.get(url, timeout=20)
    resp.raise_for_status()
    data = resp.json()
    return [item["symbol"] for item in data if "symbol" in item]


def fetch_nasdaq100():
    """
    Получаем список компаний NASDAQ-100 через Financial Modeling Prep API
    """
    url = f"https://financialmodelingprep.com/api/v3/nasdaq_constituent?apikey={FMP_API_KEY}"
    resp = requests.get(url, timeout=20)
    resp.raise_for_status()
    data = resp.json()
    return [item["symbol"] for item in data if "symbol" in item]


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
