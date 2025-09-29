import os
import psycopg2
import pandas as pd
import requests
from psycopg2.extras import RealDictCursor

# =========================
# Настройки
# =========================
DATABASE_URL = os.getenv("DATABASE_URL")
FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY")

# =========================
# Функция для подключения к БД
# =========================
def get_db_connection():
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)

# =========================
# Получение цены из Finnhub
# =========================
def get_price_from_finnhub(symbol):
    try:
        url = f"https://finnhub.io/api/v1/quote?symbol={symbol}&token={FINNHUB_API_KEY}"
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        data = r.json()

        # Ответ Finnhub:
        # {
        #   "c": 261.74,   # Current price
        #   "h": 263.31,   # High price of the day
        #   "l": 260.68,   # Low price of the day
        #   "o": 261.07,   # Open price of the day
        #   "pc": 259.45   # Previous close price
        # }

        if "c" in data and data["c"] > 0:
            return data["c"]
        else:
            print(f"[FINNHUB] Пустой ответ для {symbol}: {data}")
            return None

    except Exception as e:
        print(f"[FINNHUB] Ошибка получения цены для {symbol}: {e}")
        return None

# =========================
# Построение портфеля
# =========================
def build_portfolio(risk_profile="Balanced"):
    conn = get_db_connection()
    cur = conn.cursor()

    # Забираем тикеры из таблицы tickers
    cur.execute("SELECT symbol FROM tickers WHERE index_name IN ('SP500', 'NASDAQ100') LIMIT 50;")
    rows = cur.fetchall()
    symbols = [row["symbol"] for row in rows]

    portfolio = []
    weight = 1 / len(symbols) if symbols else 0

    for symbol in symbols:
        price = get_price_from_finnhub(symbol)
        if price:
            portfolio.append({"symbol": symbol, "price": price, "weight": weight})
            # сохраняем в holdings
            cur.execute(
                """
                INSERT INTO portfolio_holdings (symbol, weight, last_price, updated_at)
                VALUES (%s, %s, %s, NOW())
                ON CONFLICT (symbol) DO UPDATE
                SET weight = EXCLUDED.weight,
                    last_price = EXCLUDED.last_price,
                    updated_at = NOW();
                """,
                (symbol, weight, price),
            )

    conn.commit()
    cur.close()
    conn.close()

    return portfolio

# =========================
# Запуск для теста
# =========================
if __name__ == "__main__":
    portfolio = build_portfolio("Balanced")
    print(pd.DataFrame(portfolio))
