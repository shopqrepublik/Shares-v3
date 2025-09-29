import psycopg2
from psycopg2.extras import execute_values
from datetime import datetime
import yfinance as yf
import os
import re

DB_URL = os.getenv("DATABASE_URL")

def get_pg_connection():
    """Подключение к БД с исправлением формата URI"""
    dsn = re.sub(r"\+psycopg2", "", DB_URL)
    return psycopg2.connect(dsn)

def build_portfolio_yf(limit: int = 100):
    """
    Формирует портфель ТОЛЬКО через yfinance.
    Берёт тикеры из таблицы tickers, считает momentum и SMA, сохраняет в БД.
    """
    conn = get_pg_connection()
    cur = conn.cursor()

    # берем список тикеров
    cur.execute("SELECT symbol FROM tickers LIMIT %s;", (limit,))
    rows = cur.fetchall()
    symbols = [r[0] for r in rows]

    portfolio = []
    for sym in symbols:
        try:
            data = yf.Ticker(sym).history(period="6mo")
            if data.empty:
                continue
            price = float(data["Close"].iloc[-1])
            momentum = (price / float(data["Close"].iloc[0])) - 1
            sma50 = data["Close"].rolling(50).mean().iloc[-1]
            sma200 = data["Close"].rolling(200).mean().iloc[-1]
            pattern = "Golden Cross" if sma50 > sma200 else "Normal"
            score = momentum
            portfolio.append({
                "symbol": sym,
                "price": price,
                "momentum": momentum,
                "pattern": pattern,
                "score": score
            })
        except Exception as e:
            print(f"[YF ERROR] {sym}: {e}")

    # сортировка и топ-5
    portfolio = sorted(portfolio, key=lambda x: x["score"], reverse=True)[:5]

    # сохраняем в БД
    cur.execute("DELETE FROM portfolio_holdings;")
    values = [(p["symbol"], p["price"], p["momentum"], p["pattern"],
               1/len(portfolio), datetime.utcnow()) for p in portfolio]
    execute_values(
        cur,
        """
        INSERT INTO portfolio_holdings (symbol, price, momentum, pattern, weight, updated_at)
        VALUES %s
        """,
        values
    )
    conn.commit()
    cur.close()
    conn.close()

    return portfolio
