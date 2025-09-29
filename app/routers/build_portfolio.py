import os
import psycopg2
import yfinance as yf
import pandas as pd
from fastapi import APIRouter
from datetime import datetime

router = APIRouter()

DATABASE_URL = os.getenv("DATABASE_URL")

def get_db_connection():
    return psycopg2.connect(DATABASE_URL)

@router.post("/portfolio/build")
async def build_portfolio():
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        # 1. Загружаем список тикеров (например, SP500)
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
                data = yf.download(sym, period="6mo", interval="1d", progress=False)
                if data.empty:
                    continue

                price = float(data["Close"].iloc[-1])
                momentum = (price - float(data["Close"].iloc[0])) / float(data["Close"].iloc[0])

                sma50 = data["Close"].rolling(50).mean().iloc[-1]
                sma200 = data["Close"].rolling(200).mean().iloc[-1]
                pattern = "Golden Cross" if sma50 > sma200 else "Normal"

                score = momentum * 100

                results.append({
                    "symbol": sym,
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

        # 3. Сортируем по score и выбираем топ-5
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
