import os
import time
import json
import logging
from typing import Optional

import httpx
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from openai import AsyncOpenAI

# ---------------------------------------
# Логирование
# ---------------------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------------------------------------
# Конфиг
# ---------------------------------------
API_PASSWORD = os.getenv("API_PASSWORD") or os.getenv("VITE_API_KEY") or "AI_German"
ALPACA_API_KEY = os.getenv("ALPACA_API_KEY")
ALPACA_SECRET_KEY = os.getenv("ALPACA_SECRET_KEY")
ALPACA_BASE_URL = os.getenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
client_ai = AsyncOpenAI(api_key=OPENAI_API_KEY)

# ---------------------------------------
# FastAPI init
# ---------------------------------------
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------
# Авторизация
# ---------------------------------------
def check_api_key(request: Request):
    key = request.headers.get("x-api-key")
    if key != API_PASSWORD:
        logger.warning(f"Unauthorized request: x-api-key={key}")
        raise HTTPException(status_code=401, detail="Unauthorized")

# ---------------------------------------
# Кэш тикеров
# ---------------------------------------
ASSETS_CACHE = {"symbols": [], "last_update": 0}

async def get_symbols_from_alpaca(headers):
    global ASSETS_CACHE
    now = time.time()
    if ASSETS_CACHE["symbols"] and (now - ASSETS_CACHE["last_update"] < 86400):
        return ASSETS_CACHE["symbols"]

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{ALPACA_BASE_URL}/v2/assets",
            headers=headers,
            timeout=30,
        )
        if resp.status_code != 200:
            logger.error(f"Alpaca assets error {resp.status_code}: {resp.text}")
            raise HTTPException(status_code=500, detail="Failed to fetch assets")

        assets = resp.json()
        symbols = [a["symbol"] for a in assets if a["status"] == "active" and a["tradable"]]
        ASSETS_CACHE = {"symbols": symbols, "last_update": now}
        logger.info(f"Fetched {len(symbols)} symbols from Alpaca")
        return symbols

# ---------------------------------------
# Хелперы
# ---------------------------------------
async def get_snapshots(headers, symbols):
    """Берем цены по части тикеров (например топ-200)"""
    symbols = symbols[:200]
    joined = ",".join(symbols)
    url = f"{ALPACA_BASE_URL.replace('paper-api','data')}/v2/stocks/snapshots?symbols={joined}"

    async with httpx.AsyncClient() as client:
        resp = await client.get(url, headers=headers, timeout=30)
        if resp.status_code != 200:
            logger.error(f"Alpaca snapshots error {resp.status_code}: {resp.text}")
            raise HTTPException(status_code=500, detail="Failed to fetch snapshots")
        data = resp.json()
        prices = {}
        for sym, val in data.items():
            try:
                prices[sym] = val["latestQuote"]["ap"]
            except Exception:
                continue
        return prices

async def ask_openai_for_portfolio(budget, risk, goals, prices: dict):
    symbols_subset = dict(list(prices.items())[:50])  # ограничим топ-50 для скорости

    prompt = f"""
You are an investment assistant.
Task: Build a stock portfolio and provide forecast returns.

Budget: {budget} USD
Risk profile: {risk}
Goals: {goals}

Available symbols and prices (JSON): {json.dumps(symbols_subset)}

Return JSON only in this format:
{{
  "portfolio":[{{"symbol":"AAPL","shares":5,"avg_price":170}}],
  "forecast":{{"3m":"+5%","6m":"+12%","12m":"+25%"}}
}}
"""
    resp = await client_ai.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "You are an expert financial analyst."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.3,
        max_tokens=800,
    )
    content = resp.choices[0].message.content.strip()
    try:
        data = json.loads(content)
    except Exception:
        logger.warning(f"Failed to parse AI response: {content}")
        raise HTTPException(status_code=500, detail="AI response parse error")
    return data

# ---------------------------------------
# Эндпоинты
# ---------------------------------------
@app.get("/ping")
async def ping():
    return {"message": "pong"}

@app.get("/portfolio/holdings")
async def holdings(request: Request):
    check_api_key(request)
    return {"holdings": ["AAPL", "MSFT", "GOOG"]}

# --- фиксы для совместимости ---
@app.get("/onboard")
async def onboard_get(request: Request):
    check_api_key(request)
    return {
        "status": "ok",
        "message": "GET /onboard is deprecated, please use POST /onboard",
        "compat": True,
    }

@app.post("/onboard")
async def onboard_post(request: Request):
    check_api_key(request)
    body = await request.json()
    budget = body.get("budget", 1000)
    risk = body.get("risk", "balanced")
    goals = body.get("goals", "growth")
    horizon = body.get("horizon", "6m")
    knowledge = body.get("knowledge", "novice")

    return {
        "status": "ok",
        "input": {
            "budget": budget,
            "risk": risk,
            "goals": goals,
            "horizon": horizon,
            "knowledge": knowledge,
        },
    }

@app.post("/portfolio/build")
async def build_portfolio(request: Request):
    check_api_key(request)
    body = await request.json()
    budget = body.get("budget", 10000)
    risk = body.get("risk", "balanced")
    goals = body.get("goals", "growth")

    headers = {
        "APCA-API-KEY-ID": ALPACA_API_KEY,
        "APCA-API-SECRET-KEY": ALPACA_SECRET_KEY,
    }

    symbols = await get_symbols_from_alpaca(headers)
    prices = await get_snapshots(headers, symbols)
    ai_result = await ask_openai_for_portfolio(budget, risk, goals, prices)

    return {
        "status": "ok",
        "input": {"budget": budget, "risk": risk, "goals": goals},
        "portfolio": ai_result.get("portfolio", []),
        "forecast": ai_result.get("forecast", {}),
    }
