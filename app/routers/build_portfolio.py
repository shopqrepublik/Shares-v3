import os
import pandas as pd
import yfinance as yf
import psycopg2
import requests
from datetime import datetime

# 🔑 API Keys
FMP_API_KEY = os.getenv("FMP_API_KEY")

# 📂 подключение к БД
DATABASE_URL = os.getenv("DATABASE_URL")

# === НОРМАЛИЗАЦИЯ ТИКЕРОВ ===
def normalize_symbol(symbol: str) -> str:
    """Нормализуем тикеры под Yahoo Finance"""
    if symbol.endswith(".B"):
        return symbol.replace(".B", "-B")  # BRK-B вместо BRK.B
    return symbol.strip()

# === FMP API ===
def get_price_from_fmp(symbol: str):
    try:
        url = f"https://financialmodelingprep.com/api/v3/quote/{symbol}?apikey={FMP_API_KEY}"
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            data = r.json()
            if data and "price" in data[0]:
                return data[0]["price"]
    except Exception as e:
        print(f"[FMP] Ошибка для {symbol}: {e}")
    return None

# === ПОДКЛЮЧЕНИЕ К БД ===
def get_db_connection():
    return psycopg2.connect(DATABASE_URL)

# === СОЗДАНИЕ ПОРТФЕЛЯ ===
def build_portfolio(tickers, risk_profile="Balanced"):
    portfolio = []

    for symbol in tickers:
        norm_sym = normalize_symbol(symbol)
        price = None
        momentum = None

        try:
            # --- 1️⃣ Пробуем через yfinance
            data = yf.download(norm_sym, period="6mo", progress=False)
            if data.empty:
                raise ValueError("Yahoo вернул пустые данные")
            price = float(data["Close"].iloc[-1])
            momentum = (price / data["Close"].iloc[0]) - 1

        except Exception as e:
            print(f"[YF] Ошибка для {norm_sym}: {e}, пробую FMP...")
            price = get_price_from_fmp(norm_sym)

        if price is None:
            print(f"[❌] Нет данных для {norm_sym}, пропускаю")
            continue

        portfolio.append({
            "symbol": norm_sym,
            "price": price,
            "momentum": momentum if momentum else 0.0,
            "weight": 1 / len(tickers),  # ⚖️ равные веса
            "pattern": None,
            "updated_at": datetime.utcnow()
        })

    # --- Сохраняем в БД ---
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("DELETE FROM portfolio_holdings;")  # очищаем старый портфель

    for row in portfolio:
        cur.execute(
            """
            INSERT INTO portfolio_holdings (symbol, price, momentum, weight, pattern, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (row["symbol"], row["price"], row["momentum"], row["weight"], row["pattern"], row["updated_at"])
        )

    conn.commit()
    cur.close()
    conn.close()

    print(f"[✅] Портфель построен: {len(portfolio)} тикеров")
    return portfolio


if __name__ == "__main__":
    # ⚡ Тестовый запуск
    tickers = ["AAPL", "MSFT", "GOOGL", "AMZN", "BRK-B"]
    build_portfolio(tickers)
