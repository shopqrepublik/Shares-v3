import os
import json
import logging
from datetime import datetime
from typing import List, Optional

import httpx
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.routers.portfolio import build_portfolio as build_core

# ----------------
# Конфигурация
# ----------------
logging.basicConfig(level=logging.INFO)

API_PASSWORD = os.getenv("API_PASSWORD", "SuperSecret123")
ALPACA_API_KEY = os.getenv("ALPACA_API_KEY", "")
ALPACA_API_SECRET = os.getenv("ALPACA_API_SECRET", "")

# ----------------
# FastAPI + CORS
# ----------------
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*", "https://wealth-dashboard-ai.lovable.app"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ----------------
# Модели
# ----------------
class OnboardRequest(BaseModel):
    budget: float
    risk_level: str
    goals: str
    horizon: str
    knowledge: str

USER_PROFILE: Optional[dict] = None
CURRENT_PORTFOLIO: List[dict] = []


# ----------------
# Утилиты
# ----------------
def check_api_key(request: Request):
    api_key = request.headers.get("X-API-Key")
    if api_key != API_PASSWORD:
        raise HTTPException(status_code=401, detail="Unauthorized")


# ----------------
# Маршруты
# ----------------
@app.get("/ping")
async def ping(request: Request):
    check_api_key(request)
    return {"message": "pong"}


@app.get("/check_keys")
async def check_keys(request: Request):
    check_api_key(request)
    return {
        "ALPACA_API_KEY": "set" if ALPACA_API_KEY else "missing",
        "ALPACA_API_SECRET": "set" if ALPACA_API_SECRET else "missing"
    }


@app.post("/onboard")
async def onboard(req: OnboardRequest, request: Request):
    check_api_key(request)
    global USER_PROFILE
    USER_PROFILE = req.dict()
    logging.info(f"[ONBOARD] {USER_PROFILE}")
    return {"status": "ok", "profile": USER_PROFILE}


@app.post("/portfolio/build")
async def build_portfolio(request: Request):
    check_api_key(request)
    global USER_PROFILE, CURRENT_PORTFOLIO
    if not USER_PROFILE:
        raise HTTPException(status_code=400, detail="User profile not set. Run /onboard first.")

    # Получаем базовые 5 бумаг из portfolio.py
    candidates = build_core(USER_PROFILE)

    # Здесь можно добавить AI-аннотации, сейчас просто обогащаем базовыми полями
    enriched = []
    budget = USER_PROFILE.get("budget", 1000)
    allocation = budget / len(candidates) if candidates else 0

    for c in candidates:
        enriched.append({
            "symbol": c["symbol"],
            "price": c.get("price", 100),
            "shares": round(allocation / c.get("price", 100), 2),
            "score": c.get("score"),
            "momentum": c.get("momentum"),
            "pattern": c.get("pattern"),
            "timestamp": datetime.utcnow().isoformat()
        })

    CURRENT_PORTFOLIO = enriched
    logging.info(f"[PORTFOLIO BUILT] {CURRENT_PORTFOLIO}")

    return {"data": enriched}


@app.get("/portfolio/holdings")
async def holdings(request: Request):
    check_api_key(request)
    global CURRENT_PORTFOLIO
    return {"data": CURRENT_PORTFOLIO}


# ----------------
# Отладка CORS
# ----------------
@app.options("/debug_cors")
async def debug_cors_options():
    return {"message": "CORS preflight ok"}

@app.get("/debug_cors")
async def debug_cors():
    return {"message": "CORS GET ok"}
