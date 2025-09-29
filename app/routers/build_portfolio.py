import os
import psycopg2
import requests
from psycopg2.extras import RealDictCursor
from datetime import datetime

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
# Нормализация тикеров для Finnhub
# =========================
def normalize_symbol(symbol: str) -> str:
    """
    Приводим тикеры к формату, который принимает Finnhub.
    Например: BRK-B → BRK.B, BF-B → BF.B
    """
    mapping = {
        "BRK-B": "BRK.B",
        "BF-B": "BF.B"
    }
    return mapping.get(symbol, symbol)

# =========================
# Получение цены акции через Finnhub
# =========================
def get_price_from_finnhub(symbol: str):
    try:
        url = f"https://finnhub.io/api/v1/quote?symbol={symbol}&token={FINNHUB_API_KEY}"
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        data = r.json()
        if "c" in data and data["c"] > 0:
            return data["c"]
        else:
            print(f"[Finnhub] Нет цены для {symbol}, ответ={data}")
    except Exception as e:
        print(f"[Finnhub] Ошибка для {symbol}: {e}")
    return None

# =========================
# Построение портфеля
# =========================
def build_portfolio():
    conn = get_pg_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    # Загружаем список тикеров (берем до 50 для теста)
    cur.execute("SELECT symbol FROM tickers LIMIT 50;")
    symbols = [row["symbol"] for row in cur.fetchall()]

    portfolio = []
    weight = round(1 / len(symbols), 6) if symbols else 0

    for symbol in symbols:
        norm_symbol = normalize_symbol(symbol)  # нормализуем для Finnhub
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
