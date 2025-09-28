import os
import psycopg2
import pandas as pd
from datetime import datetime

DATABASE_URL = os.getenv("DATABASE_URL")

def fetch_sp500():
    # DataHub CSV (обновляется автоматически)
    url_csv = "https://datahub.io/core/s-and-p-500-companies/r/constituents.csv"
    df = pd.read_csv(url_csv)
    return df["Symbol"].dropna().tolist()

def fetch_nasdaq100():
    # Альтернативный CSV (NASDAQ listings)
    url_csv = "https://pkgstore.datahub.io/core/nasdaq-listings/nasdaq-listed_csv/data/nasdaq-listed_csv.csv"
    df = pd.read_csv(url_csv)
    return df["Symbol"].dropna().tolist()

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
