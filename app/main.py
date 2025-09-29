import os
import psycopg2
from psycopg2.extras import RealDictCursor, execute_values
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime
import pandas as pd
import yfinance as yf

# Папка с CSV (для fallback)
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")

# DB URL
DB_URL = os.getenv("DATABASE_URL")
API_KEY = os.getenv("API_KEY", "changeme")

# --- Подключение к БД ---
import re

def get_pg_connection():
    """
    Создаёт подключение к PostgreSQL.
    Если DATABASE_URL содержит '+psycopg2', убираем его,
    потому что psycopg2 не понимает такой формат.
    """
    dsn = re.sub(r"\+psycopg2", "", DB_URL)
    return psycopg2.connect(dsn)

# --- FastAPI ---
app = FastAPI()

# --- CORS ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Проверка API ключа ---
def check_api_key(request: Request):
    key = request.headers.get("X-API-Key")
    if key != API_KEY:
        raise HTTPException(status_code=403, detail="Forbidden")

# --- Healthcheck ---
@app.get("/ping")
async def ping():
    return {"status": "ok", "time": datetime.utcnow().isoformat()}


# --- Update tickers ---
def update_tickers_from_sources():
    sp500_url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
    nasdaq100_url = "https://en.wikipedia.org/wiki/NASDAQ-100"

    try:
        # 1️⃣ Загружаем с Википедии
        sp500 = pd.read_html(sp500_url)[0]["Symbol"].tolist()
        nasdaq100 = pd.read_html(nasdaq100_url)[3]["Ticker"].tolist()
        print(f"[TICKERS] Успешно загружено с Википедии: SP500={len(sp500)}, NASDAQ100={len(nasdaq100)}")
    except Exception as e:
        # 2️⃣ Fallback CSV
        print(f"[TICKERS] Ошибка Википедии: {e}")
        sp500 = pd.read_csv(os.path.join(DATA_DIR, "tickers_sp500.csv"))["Symbol"].tolist()
        nasdaq100 = pd.read_csv(os.path.join(DATA_DIR, "tickers_nasdaq100.csv"))["Symbol"].tolist()
        print(f"[TICKERS] Загружено из CSV: SP500={len(sp500)}, NASDAQ100={len(nasdaq100)}")

    # Подготовка данных
    now = datetime.utcnow()
    all_tickers = []
    for sym in sp500:
        all_tickers.append(("SP500", sym, now))
    for sym in nasdaq100:
        all_tickers.append(("NASDAQ100", sym, now))

    # Запись в БД
    conn = get_pg_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM tickers WHERE index_name IN ('SP500','NASDAQ100') OR index_name IS NULL;")
    execute_values(
        cur,
        "INSERT INTO tickers (index_name, symbol, updated_at) VALUES %s",
        all_tickers,
        page_size=500
    )
    conn.commit()
    cur.close()
    conn.close()

    print(f"[TICKERS] ✅ Обновление завершено: всего {len(all_tickers)}, SP500={len(sp500)}, NASDAQ100={len(nasdaq100)}")

    return {
        "status": "ok",
        "total": len(all_tickers),
        "sp500_count": len(sp500),
        "nasdaq100_count": len(nasdaq100)
    }

@app.post("/update_tickers")
async def update_tickers(request: Request):
    check_api_key(request)
    return update_tickers_from_sources()


# --- Build portfolio ---
@app.post("/portfolio/build")
async def build_portfolio(request: Request):
    check_api_key(request)

    # 1️⃣ Берём тикеры SP500
    conn = get_pg_connection()
    cur = conn.cursor()
    cur.execute("SELECT symbol FROM tickers WHERE index_name='SP500' LIMIT 50;")
    rows = cur.fetchall()
    cur.close()
    conn.close()
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
            print(f"[PORTFOLIO] Ошибка для {sym}: {e}")

    # 2️⃣ Сортировка и выбор топ-5
    portfolio = sorted(portfolio, key=lambda x: x["score"], reverse=True)[:5]

    # 3️⃣ Запись в БД
    conn = get_pg_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM portfolio_holdings;")
    values = [(p["symbol"], p["price"], p["momentum"], p["pattern"], 1/len(portfolio), datetime.utcnow()) for p in portfolio]
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

    print(f"[PORTFOLIO] ✅ Сохранено {len(portfolio)} тикеров в portfolio_holdings")

    return {"status": "ok", "portfolio": portfolio}


# --- Get portfolio holdings ---
@app.get("/portfolio/holdings")
async def holdings(request: Request):
    check_api_key(request)
    conn = get_pg_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT id, symbol, weight, price, momentum, pattern, updated_at FROM portfolio_holdings ORDER BY id;")
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return {"status": "ok", "holdings": rows}
