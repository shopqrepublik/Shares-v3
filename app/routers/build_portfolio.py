import os
import psycopg2
import requests
import time
from psycopg2.extras import RealDictCursor
from datetime import datetime
from typing import Optional

# =========================
# Конфигурация
# =========================
DB_URL = os.getenv("DATABASE_URL")
FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY")

# =========================
# Подключение к базе
# =========================
def get_pg_connection():
    return psycopg2.connect(DB_URL)

# =========================
# Нормализация тикеров
# =========================
def normalize_symbol(symbol: str) -> str:
    mapping = {
        "BRK-B": "BRK.B",
        "BF-B": "BF.B"
    }
    return mapping.get(symbol, symbol)

# =========================
# Получение цены через Finnhub
# =========================
def get_price_from_finnhub(symbol: str) -> Optional[float]:
    url = f"https://finnhub.io/api/v1/quote?symbol={symbol}&token={FINNHUB_API_KEY}"
    try:
        resp = requests.get(url, timeout=10)
        if resp.status_code == 429:
            print(f"[RATE LIMIT] Too many requests. Pausing for 60s...")
            time.sleep(60)
            return None
        resp.raise_for_status()
        data = resp.json()
        if not data or "c" not in data:
            print(f"[EMPTY] {symbol}: {data}")
            return None
        if data["c"] and data["c"] > 0:
            return float(data["c"])
        else:
            print(f"[ZERO PRICE] {symbol}: {data}")
            return None
    except Exception as e:
        print(f"[ERROR] {symbol}: {e}")
        return None

# =========================
# Построение портфеля
# =========================
def build_portfolio():
    conn = get_pg_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    # Берем список тикеров (например 100 для теста)
    cur.execute("SELECT symbol FROM tickers LIMIT 100;")
    symbols = [row["symbol"] for row in cur.fetchall()]

    portfolio = []
    weight = round(1 / len(symbols), 6) if symbols else 0

    for i, symbol in enumerate(symbols, start=1):
        norm_symbol = normalize_symbol(symbol)
        price = get_price_from_finnhub(norm_symbol)
        if price:
            portfolio.append({"symbol": symbol, "price": price, "weight": weight})
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
        else:
            print(f"[❌] Нет данных для {symbol}")

        # троттлинг каждые 50 запросов
        if i % 50 == 0:
            print(f"[INFO] Processed {i} symbols, pausing for 60s to respect API limits")
            time.sleep(60)

    conn.commit()
    cur.close()
    conn.close()

    print(f"[PORTFOLIO] Построено {len(portfolio)} бумаг из {len(symbols)}")
    return portfolio

# =========================
# Запуск
# =========================
if __name__ == "__main__":
    build_portfolio()
