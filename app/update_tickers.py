import os
import psycopg2
from psycopg2.extras import execute_values
import pandas as pd
import requests
import io

DB_URL = os.getenv("DATABASE_URL")

FTP_BASE = "ftp://ftp.nasdaqtrader.com/symboldirectory/"

NASDAQ_FILE = "nasdaqlisted.txt"
OTHER_FILE = "otherlisted.txt"

WIKI_SP500_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
WIKI_NASDAQ100_URL = "https://en.wikipedia.org/wiki/NASDAQ-100"


def fetch_ftp_tickers():
    """
    Скачивает тикеры через FTP файлы NASDAQ и Other, возвращает список тикеров.
    """
    tickers = set()

    # Helper to fetch a text file via FTP-over-HTTP
    def fetch_txt(filename):
        url = FTP_BASE + filename
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        return resp.text

    # NASDAQ-listed
    text = fetch_txt(NASDAQ_FILE)
    # Файл обычно содержится в CSV-подобном формате, первая строка заголовков
    df = pd.read_csv(io.StringIO(text), sep="|")
    if "Symbol" in df.columns:
        tickers.update(df["Symbol"].dropna().tolist())

    # Other-listed (NYSE и др.)
    text2 = fetch_txt(OTHER_FILE)
    df2 = pd.read_csv(io.StringIO(text2), sep="|")
    if "ACT Symbol" in df2.columns:
        tickers.update(df2["ACT Symbol"].dropna().tolist())

    return list(tickers)


def fetch_sp500():
    df = pd.read_html(WIKI_SP500_URL)[0]
    return df["Symbol"].dropna().tolist()


def fetch_nasdaq100():
    df = pd.read_html(WIKI_NASDAQ100_URL)[4]
    return df["Ticker"].dropna().tolist()


def update_tickers():
    try:
        all_tickers = fetch_ftp_tickers()
        sp500 = set(fetch_sp500())
        nasdaq100 = set(fetch_nasdaq100())

        conn = psycopg2.connect(DB_URL)
        cur = conn.cursor()

        # Создаём таблицу если нет
        cur.execute("""
            CREATE TABLE IF NOT EXISTS tickers (
                symbol TEXT PRIMARY KEY,
                index_name TEXT
            )
        """)
        cur.execute("TRUNCATE tickers")

        rows = []
        for sym in all_tickers:
            label = None
            if sym in sp500:
                label = "SP500"
            elif sym in nasdaq100:
                label = "NASDAQ100"
            rows.append((sym, label))

        execute_values(cur, "INSERT INTO tickers (symbol, index_name) VALUES %s", rows)

        conn.commit()
        cur.close()
        conn.close()

        return {
            "status": "ok",
            "total": len(all_tickers),
            "sp500_count": len(sp500),
            "nasdaq100_count": len(nasdaq100),
        }
    except Exception as e:
        return {"status": "error", "detail": str(e)}
