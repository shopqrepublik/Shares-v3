import os
import json
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta, timezone

import requests
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from openai import OpenAI

# ---------------- CONFIG ----------------
API_PASSWORD = os.getenv("API_PASSWORD", "SuperSecret123")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
ALPACA_API_KEY = os.getenv("ALPACA_API_KEY", "")
ALPACA_API_SECRET = os.getenv("ALPACA_API_SECRET", "")
ALPACA_API_URL = "https://paper-api.alpaca.markets"
ALPACA_DATA_URL = "https://data.alpaca.markets/v2"

client = OpenAI(api_key=OPENAI_API_KEY)
logging.basicConfig(level=logging.INFO)

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------- AUTH ----------------
def check_api_key(request: Request):
    api_key = request.headers.get("x-api-key")
    if api_key != API_PASSWORD:
        raise HTTPException(status_code=401, detail="Unauthorized")

# ---------------- DATA MODELS ----------------
class OnboardRequest(BaseModel):
    budget: float
    risk_level: str
    goals: str
    micro_caps: bool = False
    target_date: str = "2026-01-01"
    horizon: Optional[str] = None
    experience: Optional[str] = None

class Position(BaseModel):
    symbol: str
    quantity: int
    price: float
    allocation: float
    forecast: Dict[str, Any] = None

# ---------------- MEMORY STORAGE ----------------
user_profiles: Dict[str, Any] = {}
user_portfolios: Dict[str, List[Position]] = {}

# ---------------- HELPERS ----------------
def get_assets(limit: int = 50) -> List[str]:
    """Берём список активных торгуемых активов с Alpaca"""
    try:
        r = requests.get(
            f"{ALPACA_API_URL}/v2/assets",
            headers={
                "APCA-API-KEY-ID": ALPACA_API_KEY,
                "APCA-API-SECRET-KEY": ALPACA_API_SECRET
            },
            timeout=20
        )
        r.raise_for_status()
        assets = r.json()
        syms = [a["symbol"] for a in assets if a["tradable"] and a["status"] == "active"]
        return syms[:limit]
    except Exception as e:
        logging.warning(f"Assets fetch failed: {e}")
        return ["AAPL", "MSFT", "SPY", "QQQ"]  # fallback

def get_last_price(symbol: str) -> float:
    """Последняя цена через Alpaca Market Data v2"""
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=5)
    url = f"{ALPACA_DATA_URL}/stocks/{symbol}/bars"
    params = {
        "timeframe": "1Day",
        "start": start.isoformat(),
        "end": end.isoformat(),
        "limit": 5
    }
    try:
        r = requests.get(url, headers={
            "APCA-API-KEY-ID": ALPACA_API_KEY,
            "APCA-API-SECRET-KEY": ALPACA_API_SECRET
        }, params=params, timeout=20)
        if r.status_code == 200:
            bars = r.json().get("bars", [])
            if bars:
                return float(bars[-1]["c"])
    except Exception as e:
        logging.warning(f"Price fetch failed for {symbol}: {e}")
    return 100.0

def build_candidates(limit: int = 20) -> List[Dict[str, Any]]:
    """Собираем кандидатов с Alpaca + последняя цена"""
    tickers = get_assets(limit=limit)
    candidates = []
    for sym in tickers:
        price = get_last_price(sym)
        if price:
            candidates.append({
                "symbol": sym,
                "price": price,
                "marketCap": None,
                "beta": None,
                "dividendYield": None,
                "volume": None
            })
    logging.info(f"[CANDIDATES] {len(candidates)} tickers fetched")
    return candidates

def ai_select(candidates: List[Dict[str, Any]], profile: Dict[str, Any]) -> List[Dict[str, Any]]:
    """AI отбирает 5 лучших бумаг"""
    prompt = f"""
    You are an investment AI.
    From the following {len(candidates)} candidate stocks:
    {json.dumps(candidates[:50], indent=2)}

    Select exactly 5 stocks fitting this profile:
    - Risk: {profile.get('risk_level')}
    - Goals: {profile.get('goals')}
    - Micro caps allowed: {profile.get('micro_caps')}
    - Horizon: {profile.get('horizon')}
    - Experience: {profile.get('experience')}

    For each stock, also forecast price at {profile.get('target_date')}.

    Return ONLY valid JSON, no markdown or text:
    {{
      "selected": [
        {{
          "symbol": "AAPL",
          "reason": "Strong large-cap growth",
          "forecast": {{"target_date":"{profile.get('target_date')}","price":210}}
        }}
      ]
    }}
    """
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2
    )
    text = resp.choices[0].message.content.strip()
    logging.info(f"[AI RAW OUTPUT] {text}")
    try:
        # удаляем возможные markdown-блоки
        if text.startswith("```"):
            text = text.strip("`")
            if text.lower().startswith("json"):
                text = text[4:].strip()
        parsed = json.loads(text)["selected"]
        logging.info(f"[AI PARSED] {parsed}")
        return parsed
    except Exception as e:
        logging.error(f"AI parse error: {e}, raw: {text}")
        return []

# ---------------- ROUTES ----------------
@app.get("/ping")
async def ping():
    return {"message": "pong"}

@app.get("/check_keys")
async def check_keys(request: Request):
    check_api_key(request)
    return {
        "ALPACA_API_KEY": "set" if ALPACA_API_KEY else "missing",
        "ALPACA_API_SECRET": "set" if ALPACA_API_SECRET else "missing"
    }

@app.post("/onboard")
async def onboard(request: Request, body: OnboardRequest):
    check_api_key(request)
    user_profiles["profile"] = body.dict()
    logging.info(f"[ONBOARD] {user_profiles['profile']}")
    return {"status": "ok", "profile": user_profiles["profile"]}

@app.post("/portfolio/build")
async def build_portfolio(request: Request):
    check_api_key(request)
    profile = user_profiles.get("profile")
    if not profile:
        raise HTTPException(status_code=400, detail="Run /onboard first")

    candidates = build_candidates(limit=20)
    selected = ai_select(candidates, profile)

    budget = profile["budget"]
    if not selected:
        return {"status": "error", "message": "AI did not return selection"}

    alloc = budget / len(selected)
    positions = []
    for s in selected:
        price = next((c["price"] for c in candidates if c["symbol"] == s["symbol"]), 100)
        qty = int(alloc // price) if price else 0
        positions.append(Position(
            symbol=s["symbol"],
            quantity=qty,
            price=price,
            allocation=round(alloc/budget, 2),
            forecast=s.get("forecast")
        ))
    user_portfolios["portfolio"] = positions
    logging.info(f"[PORTFOLIO BUILT] {positions}")
    return {"status": "ok", "portfolio": [p.dict() for p in positions]}

@app.get("/portfolio/holdings")
async def holdings(request: Request):
    check_api_key(request)
    portfolio = user_portfolios.get("portfolio", [])
    return {"holdings": [p.dict() for p in portfolio]}
