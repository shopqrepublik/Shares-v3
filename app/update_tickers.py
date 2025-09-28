import pandas as pd
import psycopg2
import os
from psycopg2.extras import execute_values

DB_URL = os.getenv("DATABASE_URL")

def fetch_sp500_tickers():
    url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
    table = pd.read_html(url)[0]
    return table["Symbol"].tolist()

def fetch_nasdaq100_tickers():
    url = "https://en.wikipedia.org/wiki/NASDAQ-100"
    table = pd.read_html(url)[3]
    return table["Ticker"].tolist()

def save_to_db(index_name, tickers):
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()
    cur.execute("DELETE FROM tickers WHERE index_name = %s", (index_name,))
    execute_values(
        cur,
        "INSERT INTO tickers (index_name, symbol) VALUES %s",
        [(index_name, t) for t in tickers]
    )
    conn.commit()
    cur.close()
    conn.close()

def update_tickers():
    sp500 = fetch_sp500_tickers()
    nasdaq = fetch_nasdaq100_tickers()

    save_to_db("SP500", sp500)
    save_to_db("NASDAQ100", nasdaq)

    return {
        "sp500": len(sp500),
        "nasdaq100": len(nasdaq),
        "examples": {
            "sp500": sp500[:5],
            "nasdaq100": nasdaq[:5]
        }
    }

if __name__ == "__main__":
    print(update_tickers())

