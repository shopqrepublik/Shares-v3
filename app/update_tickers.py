import os
import psycopg2
from psycopg2.extras import execute_values
import requests

DB_URL = os.getenv("DATABASE_URL")
MARKETSTACK_KEY = os.getenv("MARKETSTACK_KEY")

def fetch_tickers(exchange_code):
    url = "url = "https://api.marketstack.com/v1/tickers"
    params = {
        "access_key": MARKETSTACK_KEY,
        "exchange": exchange_code,
        "limit": 1000
    }
    resp = requests.get(url, params=params)
    resp.raise_for_status()
    data = resp.json().get("data", [])
    return [(item["symbol"], exchange_code) for item in data if "symbol" in item]

def update_tickers():
    if not DB_URL or not MARKETSTACK_KEY:
        return {"status": "error", "detail": "DATABASE_URL or MARKETSTACK_KEY not set"}

    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS tickers (
            symbol TEXT PRIMARY KEY,
            exchange TEXT
        )
    """)
    cur.execute("TRUNCATE tickers")

    tickers = []
    for exchange in ["XNAS", "XNYS"]:  # NASDAQ и NYSE
        tickers.extend(fetch_tickers(exchange))

    execute_values(cur, "INSERT INTO tickers (symbol, exchange) VALUES %s", tickers)
    conn.commit()
    cur.close()
    conn.close()

    return {"status": "ok", "total": len(tickers), "exchanges": ["XNAS", "XNYS"]}
