import os
import logging
from datetime import datetime

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware

import psycopg2
from psycopg2.extras import RealDictCursor

from update_tickers import update_tickers_from_sources
from build_portfolio import build_and_save_portfolio

# ---------------------------------------------------------
# Настройки
# ---------------------------------------------------------
DB_URL = os.getenv("DATABASE_URL")
API_KEY = os.getenv("API_KEY", "SuperSecret123")

app = FastAPI()

# Логирование
logging.basicConfig(level=logging.INFO)

# Разрешим CORS для фронта
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # для тестов можно оставить *
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------
# Вспомогательные функции
# ---------------------------------------------------------
def get_pg_connection():
    return psycopg2.connect(DB_URL)

def check_api_key(request: Request):
    key = request.headers.get("X-API-Key")
    if key != API_KEY:
        raise HTTPException(status_code=403, detail="Invalid API Key")

# ---------------------------------------------------------
# Эндпоинты
# ---------------------------------------------------------
@app.get("/")
async def root():
    return {"status": "ok", "message": "Wealth Dashboard API is running"}

@app.post("/update_tickers")
async def update_tickers(request: Request):
    check_api_key(request)
    try:
        stats = update_tickers_from_sources(DB_URL)
        logging.info(f"[UPDATE_TICKERS] ✅ {stats}")
        return {"status": "ok", **stats}
    except Exception as e:
        logging.error(f"[UPDATE_TICKERS] ❌ {e}")
        raise HTTPException(status_code=500, detail=f"Update failed: {e}")

@app.post("/portfolio/build")
async def build_portfolio(request: Request):
    check_api_key(request)
    try:
        portfolio = build_and_save_portfolio(DB_URL)
        logging.info(f"[BUILD_PORTFOLIO] ✅ {portfolio}")
        return {"status": "ok", "portfolio": portfolio}
    except Exception as e:
        logging.error(f"[BUILD_PORTFOLIO] ❌ {e}")
        raise HTTPException(status_code=500, detail=f"Build failed: {e}")

@app.get("/portfolio/holdings")
async def holdings(request: Request):
    check_api_key(request)
    try:
        conn = get_pg_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT id, symbol, weight, price, momentum, pattern, updated_at
            FROM portfolio_holdings
            ORDER BY id
        """)
        rows = cur.fetchall()
        cur.close()
        conn.close()

        return {"status": "ok", "holdings": rows}
    except Exception as e:
        logging.error(f"[HOLDINGS] ❌ {e}")
        raise HTTPException(status_code=500, detail=f"Holdings failed: {e}")
