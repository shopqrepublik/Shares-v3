import os
import logging
from datetime import datetime

import pandas as pd
import yfinance as yf

import psycopg2
from psycopg2.extras import RealDictCursor
from sqlalchemy import create_engine, text

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware

# --------------------
# Логирование
# --------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DB_URL = os.getenv("DATABASE_URL")
API_KEY = os.getenv("API_KEY", "changeme")

app = FastAPI(title="Wealth Dashboard AI")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# --------------------
# Подключение к БД
# --------------------
def get_connection():
    """Автоматически выбирает psycopg2 или SQLAlchemy"""
    if "+psycopg2" in DB_URL:  # SQLAlchemy режим
        engine = create_engine(DB_URL)
        return engine.connect()
    else:  # Прямое подключение через psycopg2
        return psycopg2.connect(DB_URL)


def check_api_key(request: Request):
    api_key = request.headers.get("x-api-key")
    if api_key != API_KEY:
        raise HTTPException(status_code=403, detail="Forbidden")


# --------------------
# Обновление тикеров
# --------------------
def update_tickers_from_sources():
    """Загружаем тикеры SP500 и NASDAQ100"""
    all_tickers = []

    # SP500
    sp500_url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
    tables = pd.read_html(sp500_url)
    sp500 = tables[0]["Symbol"].tolist()
    for sym in sp500:
        all_tickers.append(("SP500", sym))

    # NASDAQ100
    nasdaq100_url = "https://en.wikipedia.org/wiki/NASDAQ-100"
    tables = pd.read_html(nasdaq100_url)
    nasdaq100 = tables[3]["Ticker"].tolist()
    for sym in nasdaq100:
        all_tickers.append(("NASDAQ100", sym))

    logger.info(f"[update_tickers] SP500={len(sp500)}, NASDAQ100={len(nasdaq100)}")

    conn = get_connection()
    if "+psycopg2" in DB_URL:
        conn.execute(text("TRUNCATE TABLE tickers;"))
        for idx, sym in all_tickers:
            conn.execute(
                text("INSERT INTO tickers (index_name, symbol, updated_at) VALUES (:idx, :sym, NOW())"),
                {"idx": idx, "sym": sym},
            )
        conn.commit()
        conn.close()
    else:
        cur = conn.cursor()
        cur.execute("TRUNCATE TABLE tickers;")
        for idx, sym in all_tickers:
            cur.execute(
                "INSERT INTO tickers (index_name, symbol, updated_at) VALUES (%s, %s, NOW())",
                (idx, sym),
            )
        conn.commit()
        conn.close()

    return {"status": "ok", "total": len(all_tickers), "sp500": len(sp500), "nasdaq100": len(nasdaq100)}


# --------------------
# Построение портфеля
# --------------------
def build_and_save_portfolio():
    conn = get_connection()

    # Читаем 50 тикеров SP500
    if "+psycopg2" in DB_URL:
        rows = conn.execute(text("SELECT symbol FROM tickers WHERE index_name='SP500' LIMIT 50;"))
        symbols = [r[0] for r in rows]
    else:
        cur = conn.cursor()
        cur.execute("SELECT symbol FROM tickers WHERE index_name='SP500' LIMIT 50;")
        symbols = [r[0] for r in cur.fetchall()]
        conn.close()

    portfolio = []

    for sym in symbols:
        try:
            data = yf.download(sym, period="6mo", interval="1d", progress=False)
            if len(data) < 30:
                continue

            price = data["Close"].iloc[-1]
            momentum = (price / data["Close"].iloc[0]) - 1

            sma50 = data["Close"].rolling(50).mean().iloc[-1]
            sma200 = data["Close"].rolling(200).mean().iloc[-1] if len(data) >= 200 else None
            pattern = "Golden Cross" if sma200 and sma50 > sma200 else "Normal"

            portfolio.append(
                {
                    "symbol": sym,
                    "price": float(price),
                    "momentum": float(momentum),
                    "pattern": pattern,
                    "score": float(momentum),
                }
            )
        except Exception as e:
            logger.warning(f"[build_portfolio] skip {sym}: {e}")

    # Топ-5
    top = sorted(portfolio, key=lambda x: x["score"], reverse=True)[:5]

    # Сохраняем
    conn = get_connection()
    if "+psycopg2" in DB_URL:
        conn.execute(text("TRUNCATE TABLE portfolio_holdings;"))
        for row in top:
            conn.execute(
                text(
                    """
                    INSERT INTO portfolio_holdings (symbol, price, momentum, pattern, weight, updated_at)
                    VALUES (:symbol, :price, :momentum, :pattern, :weight, NOW())
                    """
                ),
                {
                    "symbol": row["symbol"],
                    "price": row["price"],
                    "momentum": row["momentum"],
                    "pattern": row["pattern"],
                    "weight": 1 / len(top),
                },
            )
        conn.commit()
        conn.close()
    else:
        cur = conn.cursor()
        cur.execute("TRUNCATE TABLE portfolio_holdings;")
        for row in top:
            cur.execute(
                """
                INSERT INTO portfolio_holdings (symbol, price, momentum, pattern, weight, updated_at)
                VALUES (%s, %s, %s, %s, %s, NOW())
                """,
                (row["symbol"], row["price"], row["momentum"], row["pattern"], 1 / len(top)),
            )
        conn.commit()
        conn.close()

    return {"status": "ok", "portfolio": top}


# --------------------
# API эндпоинты
# --------------------
@app.get("/ping")
async def ping():
    return {"status": "ok", "time": datetime.utcnow().isoformat()}


@app.post("/update_tickers")
async def update_tickers(request: Request):
    check_api_key(request)
    return update_tickers_from_sources()


@app.post("/portfolio/build")
async def build_portfolio(request: Request):
    check_api_key(request)
    return build_and_save_portfolio()


@app.get("/portfolio/holdings")
async def get_holdings(request: Request):
    check_api_key(request)

    conn = get_connection()
    if "+psycopg2" in DB_URL:
        rows = conn.execute(text("SELECT id, symbol, price, momentum, pattern, weight, updated_at FROM portfolio_holdings ORDER BY id;")).fetchall()
        conn.close()
        return {"status": "ok", "holdings": [dict(r._mapping) for r in rows]}
    else:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT id, symbol, price, momentum, pattern, weight, updated_at FROM portfolio_holdings ORDER BY id;")
        rows = cur.fetchall()
        conn.close()
        return {"status": "ok", "holdings": rows}
