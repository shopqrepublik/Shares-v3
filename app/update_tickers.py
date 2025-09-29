import os
import requests
import psycopg2
from psycopg2.extras import execute_values

API_KEY = os.getenv("FMP_API_KEY")
DB_URL = os.getenv("DATABASE_URL")

def fetch_all_tickers():
    """
    Загружает все акции с FMP (Free Plan).
    Фильтрует только NYSE и NASDAQ, исключает нулевые цены.
    """
    url = f"https://financialmodelingprep.com/api/v3/stock/list?apikey={API_KEY}"
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    tickers = [
        item["symbol"]
        for item in data
        if item.get("exchangeShortName") in ("NYSE", "NASDAQ") and item.get("price", 0) > 0
    ]

    return tickers


def save_to_db(tickers):
    """
    Сохраняет тикеры в таблицу tickers.
    Полностью очищает таблицу перед вставкой новых данных.
    """
    if not DB_URL:
        raise RuntimeError("DATABASE_URL not set")

    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()

    # создаём таблицу если её нет
    cur.execute("""
        CREATE TABLE IF NOT EXISTS tickers (
            symbol TEXT PRIMARY KEY
        )
    """)

    # очищаем и вставляем новые
    cur.execute("TRUNCATE tickers")
    execute_values(cur, "INSERT INTO tickers (symbol) VALUES %s", [(t,) for t in tickers])

    conn.commit()
    cur.close()
    conn.close()
    print(f"[UPDATE_TICKERS] ✅ Inserted {len(tickers)} tickers")


def update_tickers():
    """
    Обновляет список тикеров: тянет с FMP и сохраняет в базу.
    """
    try:
        tickers = fetch_all_tickers()
        save_to_db(tickers)
        return {"status": "ok", "count": len(tickers)}
    except Exception as e:
        print(f"[UPDATE_TICKERS] ❌ {e}")
        return {"status": "error", "detail": str(e)}
