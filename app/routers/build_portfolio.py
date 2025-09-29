import os
import psycopg2
import yfinance as yf
import pandas as pd
import requests
from psycopg2.extras import RealDictCursor
from datetime import datetime

DB_URL = os.getenv("DATABASE_URL")
FMP_API_KEY = os.getenv("FMP_API_KEY")


# --- Подключение к БД ---
def get_pg_connection():
    return psycopg2.connect(DB_URL)


# --- Нормализация тикеров ---
def normalize_symbol(symbol: str) -> str:
    """
    YFinance использует дефисы вместо точек.
    Например: BRK.B → BRK-B, BF.B → BF-B
    """
    return symbol.replace(".", "-")


# --- Получение цены через FMP ---
def get_price_from_fmp(symbol: str):
    if not FMP_API_KEY:
        print(f"[FMP] ⚠️ Нет ключа FMP_API_KEY, пропускаю {symbol}")
        return None
    url = f"https://financialmodelingprep.com/api/v3/quote/{symbol}?apikey={FMP_API_KEY}"
    try:
        resp = requests.get(url, timeout=10)
        if resp.status_code != 200:
            print(f"[FMP] ❌ Ошибка API {resp.status_code} для {symbol}")
            return None
        data = resp.json()
        if not data:
            print(f"[FMP] ❌ Пустой ответ API для {symbol}")
            return None
        return data[0].get("price")
    except Exception as e:
        print(f"[FMP] ❌ Ошибка запроса для {symbol}: {e}")
        return None


# --- Построение портфеля ---
def build_and_save_portfolio():
    conn = get_pg_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    # 1. Берём тикеры из таблицы tickers (ограничим 50 для скорости)
    cur.execute("SELECT symbol FROM tickers LIMIT 50;")
    tickers = [row["symbol"] for row in cur.fetchall()]
    print(f"[PORTFOLIO] Загружено {len(tickers)} тикеров из БД")

    results = []

    # 2. Аналитика: цена, momentum, SMA-паттерн
    for sym in tickers:
        try:
            norm_sym = normalize_symbol(sym)

            # --- пробуем через Yahoo Finance ---
            try:
                data = yf.download(norm_sym, period="6mo", progress=False)
                if data.empty:
                    raise ValueError("Yahoo вернул пустые данные")
            except Exception as e:
                print(f"[YF] Ошибка для {norm_sym}: {e}, пробую FMP API...")

                # --- fallback через FMP ---
                price = get_price_from_fmp(norm_sym)
                if price is None:
                    print(f"[FMP] ❌ Нет данных для {norm_sym}, пропускаю")
                    continue
                else:
                    # создаём DataFrame с одной ценой
                    data = pd.DataFrame({"Close": [price]})

            # --- берём цену ---
            price = data["Close"].iloc[-1]

            # --- считаем momentum ---
            momentum = 0.0
            if len(data) > 1:
                momentum = (price / data["Close"].iloc[0]) - 1

            # --- определяем паттерн ---
            pattern = "Golden Cross" if momentum > 0 else "Normal"

            results.append({
                "symbol": sym,
                "price": float(price),
                "momentum": float(momentum),
                "pattern": pattern,
                "score": float(momentum)  # пока score = momentum
            })

            print(f"[OK] {norm_sym}: цена={price:.2f}, momentum={momentum:.2%}")

        except Exception as e:
            print(f"[ERROR] Не удалось обработать {sym}: {e}")
            continue

    # 3. Выбираем топ-5 по score
    top = sorted(results, key=lambda x: x["score"], reverse=True)[:5]
    print(f"[PORTFOLIO] Выбрано {len(top)} тикеров в портфель")

    # 4. Сохраняем в таблицу portfolio_holdings
    cur.execute("DELETE FROM portfolio_holdings;")
    for row in top:
        cur.execute("""
            INSERT INTO portfolio_holdings (symbol, price, momentum, pattern, weight, updated_at)
            VALUES (%s, %s, %s, %s, %s, NOW())
        """, (
            row["symbol"],
            row["price"],
            row["momentum"],
            row["pattern"],
            1 / len(top) if top else 0
        ))

    conn.commit()
    cur.close()
    conn.close()

    return {"status": "ok", "portfolio": top, "updated_at": datetime.utcnow().isoformat()}
