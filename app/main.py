import os
import logging
from datetime import datetime
from types import SimpleNamespace

import psycopg2
import httpx
import pandas as pd
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.portfolio import build_portfolio as build_core
from app.update_tickers import fetch_sp500, fetch_nasdaq100

# --- Логирование ---
logging.basicConfig(level=logging.INFO)

# --- Переменные окружения ---
API_KEY = os.getenv("API_KEY", "SuperSecret123")
DB_URL = os.getenv("DATABASE_URL", "")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
ALPACA_API_KEY = os.getenv("ALPACA_API_KEY", "")
ALPACA_API_SECRET = os.getenv("ALPACA_API_SECRET", "")

# --- FastAPI ---
app = FastAPI()

# --- CORS ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://wealth-dashboard-ai.lovable.app",  # фронт
        "http://localhost:5173",                   # локальная разработка
        "http://127.0.0.1:5173"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Глобальные ---
USER_PROFILE = {}
CURRENT_PORTFOLIO = []
SKIPPED_TICKERS = []

# --- Модели ---
class OnboardRequest(BaseModel):
    budget: float
    risk_level: str
    goals: str
    horizon: str = "6m"
    knowledge: str = "beginner"

# --- Мидлваря для API-ключа ---
PUBLIC_PATHS = {"/health", "/ping", "/docs", "/openapi.json", "/redoc"}

@app.middleware("http")
async def verify_api_key(request: Request, call_next):
    if request.url.path in PUBLIC_PATHS:
        return await call_next(request)
    key = request.headers.get("X-API-Key")
    if key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing X-API-Key")
    return await call_next(request)

# --- Хелперы ---
async def ai_annotate(portfolio):
    """AI-аннотации через OpenAI"""
    if not OPENAI_API_KEY:
        return portfolio

    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}"}
    async with httpx.AsyncClient(timeout=20) as client:
        for stock in portfolio:
            prompt = f"""
            Компания: {stock['symbol']}
            Score={stock['score']}, Momentum={stock['momentum']}, Pattern={stock['pattern']}
            Объясни в 1–2 предложениях, почему эта акция в портфеле,
            и сделай прогноз на 6 месяцев.
            """
            try:
                resp = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers=headers,
                    json={
                        "model": "gpt-4o-mini",
                        "messages": [
                            {"role": "system", "content": "Ты финансовый аналитик."},
                            {"role": "user", "content": prompt},
                        ],
                        "max_tokens": 120,
                        "temperature": 0.7,
                    },
                )
                text = resp.json()["choices"][0]["message"]["content"].strip()
                stock["reason"] = text.split("\n")[0]
                stock["forecast"] = text.split("\n")[-1]
            except Exception as e:
                logging.error(f"[AI] Ошибка аннотации {stock['symbol']}: {e}")
                stock["reason"] = "—"
                stock["forecast"] = "—"
    return portfolio

# --- Публичные маршруты ---
@app.get("/health")
def health():
    return {"status": "ok", "time": datetime.utcnow().isoformat()}

@app.get("/ping")
async def ping():
    return {"status": "ok", "time": datetime.utcnow().isoformat()}

# --- Защищённые маршруты ---
@app.post("/onboard")
async def onboard(data: OnboardRequest):
    global USER_PROFILE
    USER_PROFILE = data.dict()
    logging.info(f"[ONBOARD] {USER_PROFILE}")
    return {"status": "ok", "profile": USER_PROFILE}

@app.post("/portfolio/build")
async def build_portfolio_api(request: Request):
    data = await request.json()
    profile_obj = SimpleNamespace(**data)

    logging.info(f"[BUILD] Profile: {data}")

    global CURRENT_PORTFOLIO, SKIPPED_TICKERS
    CURRENT_PORTFOLIO, SKIPPED_TICKERS = build_core(profile_obj)

    if CURRENT_PORTFOLIO and OPENAI_API_KEY:
        CURRENT_PORTFOLIO = await ai_annotate(CURRENT_PORTFOLIO)

    return {
        "portfolio": CURRENT_PORTFOLIO,
        "skipped": SKIPPED_TICKERS,
        "timestamp": datetime.utcnow().isoformat(),
    }

@app.get("/portfolio/holdings")
async def portfolio_holdings():
    return {
        "portfolio": CURRENT_PORTFOLIO,
        "skipped": SKIPPED_TICKERS,
    }

@app.get("/check_keys")
async def check_keys():
    return {
        "OPENAI_API_KEY": "set" if OPENAI_API_KEY else "missing",
        "ALPACA_API_KEY": "set" if ALPACA_API_KEY else "missing",
        "ALPACA_API_SECRET": "set" if ALPACA_API_SECRET else "missing",
        "DATABASE_URL": "set" if DB_URL else "missing",
    }

@app.post("/update_tickers")
async def update_tickers():
    if not DB_URL:
        raise HTTPException(status_code=500, detail="DATABASE_URL not set")

    try:
        sp500 = fetch_sp500()
        nasdaq100 = fetch_nasdaq100()

        conn = psycopg2.connect(DB_URL)
        cur = conn.cursor()
        cur.execute("DELETE FROM tickers")

        for sym in sp500:
            cur.execute("INSERT INTO tickers (index_name, symbol) VALUES (%s, %s)", ("SP500", sym.strip()))
        for sym in nasdaq100:
            cur.execute("INSERT INTO tickers (index_name, symbol) VALUES (%s, %s)", ("NASDAQ100", sym.strip()))

        conn.commit()
        cur.close()
        conn.close()

        logging.info(f"[UPDATE_TICKERS] ✅ S&P500={len(sp500)}, NASDAQ100={len(nasdaq100)}")

        return {
            "status": "ok",
            "sp500_count": len(sp500),
            "nasdaq100_count": len(nasdaq100),
            "examples_sp500": sp500[:5],
            "examples_nasdaq100": nasdaq100[:5],
            "timestamp": datetime.utcnow().isoformat(),
        }

    except Exception as e:
        logging.error(f"[UPDATE_TICKERS] ❌ {e}")
        raise HTTPException(status_code=500, detail=f"Update failed: {str(e)}")

# --- CORS debug ---
@app.get("/test-cors")
async def test_cors():
    return {"message": "CORS OK"}

@app.options("/{rest_of_path:path}")
async def preflight_handler(rest_of_path: str = None):
    return {}
