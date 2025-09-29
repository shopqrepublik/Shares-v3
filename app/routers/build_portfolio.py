import os
import psycopg2
import yfinance as yf
import requests
from fastapi import APIRouter
from datetime import datetime

router = APIRouter()

DATABASE_URL = os.getenv("DATABASE_URL")
FMP_API_KEY = os.getenv("FMP_API_KEY")  # ключ хранится в Railway → Variables

def get_db_connection():
    return psycopg2.connect(DATABASE_URL)

def normalize_symbol(symbol: str) -> str:
    """
    YFinance использует дефисы вместо точек.
    Например: BRK.B → BRK-B, BF.B → BF-B
    """
    return symbol.replace(".", "-")

def get_price_from_fmp(symbol: str) -> float | None:
    """
    Получить цену через FMP (fallback, если yfinance не сработал).
    """
    if not FMP_API_KEY:
        print("⚠️ Нет ключа FMP_API_KEY")
        return None

    try:
        url = f"https://financialmodelingprep.com/api/v3/quote/{symbol}?apikey={FMP_API_KEY}"
        resp = requests.get(url, timeout=10)
        data = resp.json()
        if isinstance(data, list) and len(data) > 0 and "price" in data[0]:
            return float(data[0]["price"])
        else:
            print(f"❌ Ошибка API для {symbol}: пустой ответ {data}")
    except Exception as e:
        print(f"[FMP] Ошибка по {symbol}: {e}")
    return None

@router.post("/portfolio/build")
async def build_portfolio():
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        # 1. Берём тикеры из базы (SP500)
        cur.execute("""
            SELECT symbol 
            FROM tickers 
            WHERE index_name = 'SP500'
            LIMIT 50;
        """)
        tickers = [row[0] for row in cur.fetchall()]

        if not tickers:
            return {"status": "error", "message": "Нет доступных тикеров"}

        results = []

        # 2. Аналитика: цена, momentum, SMA-паттерн
        for sym in tickers:
            try:
                norm_sym = normalize_symbol(sym)
                data = yf.download(norm_sym, period="6mo", interval="1d", progress=False)

                if not data.empty:
                    price = float(data["Close"].iloc[-1])
                    momentum = (price - float(data["Close"].iloc[0])) / float(data["Close"].iloc[0])
                    sma50 = data["Close"].rolling(50).mean().iloc[-1]
                    sma200 = data["Close"].rolling(200).mean().iloc[-1]
                    pattern = "Golden Cross" if sma50 > sma200 else "Normal"
                else:
                    # fallback через FMP
                    price = get_price_from_fmp(sym)
                    if not price:
                        print(f"⚠️ Нет данных для {sym}")
                        continue
                    momentum, sma50, sma200, pattern = 0.0, 0.0, 0.0, "FMP"

                score = momentum * 100

                results.append({
                    "symbol": sym,  # сохраняем оригинальный тикер
                    "price": round(price, 2),
                    "momentum": round(momentum, 3),
                    "pattern": pattern,
                    "score": round(score, 2)
                })

            except Exception as e:
                print(f"Ошибка по {sym}: {e}")
                continue

        if not results:
            return {"status": "error", "message": "Не удалось рассчитать метрики"}

        # 3. Сортируем по score и берём топ-5
        top = sorted(results, key=lambda x: x["score"], reverse=True)[:5]

        # 4. Чистим старый портфель
        cur.execute("DELETE FROM portfolio_holdings;")

        # 5. Сохраняем новый портфель
        weight = 1 / len(top)
        for row in top:
            cur.execute(
                """
                INSERT INTO portfolio_holdings (symbol, weight, price, momentum, pattern, updated_at)
                VALUES (%s, %s, %s, %s, %s, NOW())
                """,
                (row["symbol"], weight, row["price"], row["momentum"], row["pattern"])
            )

        conn.commit()
        cur.close()
        conn.close()

        return {
            "status": "success",
            "portfolio": top
        }

    except Exception as e:
        return {"status": "error", "message": str(e)}
