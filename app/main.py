import os
import logging
import json
import httpx
import psycopg2
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from datetime import datetime
from types import SimpleNamespace
import pandas as pd

# ✅ правильный импорт
from app.routers.portfolio import build_portfolio as build_core

# -------------------------
# Настройка FastAPI
# -------------------------
app = FastAPI()
logging.basicConfig(level=logging.INFO)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -------------------------
# Переменные окружения
# -------------------------
ALPACA_API_KEY = os.getenv("ALPACA_API_KEY", "")
ALPACA_API_SECRET = os.getenv("ALPACA_API_SECRET", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
API_PASSWORD = os.getenv("API_PASSWORD", "SuperSecret123")
DB_URL = os.getenv("DATABASE_URL")

USER_PROFILE = None
CURRENT_PORTFOLIO = []
SKIPPED_TICKERS = []

# -------------------------
# Проверка API ключа
# -------------------------
def check_api_key(request: Request):
    key = request.headers.get("X-API-Key")
    if not key or key != API_PASSWORD:
        raise HTTPException(status_code=401, detail="Unauthorized")

# -------------------------
# Pydantic модели
# -------------------------
class OnboardRequest(BaseModel):
    budget: float
    risk_level: str
    goals: str
    horizon: str
    knowledge: str

# -------------------------
# AI аннотации
# -------------------------
async def ai_annotate(candidates, profile):
    if not OPENAI_API_KEY:
        logging.warning("OPENAI_API_KEY not set, skipping AI annotation")
        return candidates

    prompt = f"""
    У тебя есть список акций: {candidates}.
    Для каждой бумаги добавь:
    - reason: объяснение выбора
    - forecast: JSON с target_date (6m) и target_price
    Профиль инвестора: {profile}.
    Верни JSON {{"symbols":[{{"symbol":"AAPL","reason":"...","forecast":{{"target_date":"2025-12-01","price":200}}}}]}}.
    """

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENAI_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "gpt-4o-mini",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.3,
                },
            )
            data = resp.json()
            raw = data["choices"][0]["message"]["content"]
            logging.info(f"[AI RAW OUTPUT] {raw}")

            raw = raw.strip().replace("```json", "").replace("```", "")

            try:
                parsed = json.loads(raw)
            except Exception:
                logging.error(f"AI response is not valid JSON: {raw}")
                return candidates

            ai_map = {}
            if isinstance(parsed, dict) and "symbols" in parsed:
                for item in parsed["symbols"]:
                    ai_map[item.get("symbol")] = item

            safe = []
            for c in candidates:
                if not isinstance(c, dict):
                    continue
                sym = c.get("symbol")
                if sym in ai_map:
                    c["reason"] = ai_map[sym].get("reason", "")
                    c["forecast"] = ai_map[sym].get("forecast", {})
                safe.append(c)

            return safe
    except Exception as e:
        logging.error(f"AI annotation failed: {e}")
        return candidates

# -------------------------
# Роуты
# -------------------------
@app.get("/ping")
async def ping():
    return {"status": "ok", "time": datetime.utcnow().isoformat()}

@app.post("/onboard")
async def onboard(req: OnboardRequest, request: Request):
    check_api_key(request)
    global USER_PROFILE
    USER_PROFILE = req.dict()
    logging.info(f"[ONBOARD] {USER_PROFILE}")
    return {"status": "ok", "profile": USER_PROFILE}

@app.post("/portfolio/build")
async def build_portfolio_api(request: Request):
    check_api_key(request)
    if not USER_PROFILE:
        raise HTTPException(status_code=400, detail="User profile not set. Run /onboard first.")

    profile_obj = SimpleNamespace(**USER_PROFILE)

    portfolio, skipped = build_core(profile_obj)
    enriched = await ai_annotate(portfolio, USER_PROFILE)

    global CURRENT_PORTFOLIO, SKIPPED_TICKERS
    CURRENT_PORTFOLIO = [
        {
            "symbol": c.get("symbol"),
            "shares": c.get("quantity", 0),
            "price": c.get("price", 0.0),
            "score": c.get("score", 0),
            "momentum": c.get("momentum"),
            "pattern": c.get("pattern"),
            "reason": c.get("reason"),
            "forecast": c.get("forecast"),
            "timestamp": datetime.utcnow().isoformat()
        }
        for c in enriched if isinstance(c, dict)
    ]
    SKIPPED_TICKERS = skipped

    return {
        "portfolio": CURRENT_PORTFOLIO,
        "skipped": SKIPPED_TICKERS,
        "timestamp": datetime.utcnow().isoformat()
    }

@app.get("/portfolio/holdings")
async def get_holdings(request: Request):
    check_api_key(request)
    return {"portfolio": CURRENT_PORTFOLIO, "skipped": SKIPPED_TICKERS}

@app.get("/check_keys")
async def check_keys(request: Request):
    check_api_key(request)
    return {
        "ALPACA_API_KEY": "set" if ALPACA_API_KEY else "missing",
        "ALPACA_API_SECRET": "set" if ALPACA_API_SECRET else "missing",
        "OPENAI_API_KEY": "set" if OPENAI_API_KEY else "missing",
        "DATABASE_URL": "set" if DB_URL else "missing"
    }

# -------------------------
# Update Tickers в PostgreSQL
# -------------------------
@app.post("/update_tickers")
async def update_tickers(request: Request):
    check_api_key(request)

    if not DB_URL:
        raise HTTPException(status_code=500, detail="DATABASE_URL not set")

    try:
        # Загружаем тикеры с Wikipedia
        sp500 = pd.read_html("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies")[0]["Symbol"].tolist()
        nasdaq_tables = pd.read_html("https://en.wikipedia.org/wiki/NASDAQ-100")
        nasdaq100 = []
        for t in nasdaq_tables:
            if "Ticker" in t.columns or "Symbol" in t.columns:
                col = "Ticker" if "Ticker" in t.columns else "Symbol"
                nasdaq100 = t[col].dropna().tolist()
                break

        conn = psycopg2.connect(DB_URL)
        cur = conn.cursor()
        cur.execute("DELETE FROM tickers")  # очищаем таблицу

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
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logging.error(f"Update tickers failed: {e}")
        raise HTTPException(status_code=500, detail=f"Update failed: {str(e)}")

# -------------------------
# CORS debug
# -------------------------
@app.options("/debug_cors")
async def debug_cors_options():
    return JSONResponse(
        content={"message": "CORS preflight OK"},
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            "Access-Control-Allow-Headers": "*",
        },
    )

@app.get("/debug_cors")
async def debug_cors_get():
    return JSONResponse(
        content={"message": "CORS GET OK"},
        headers={"Access-Control-Allow-Origin": "*"},
    )
