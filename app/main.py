import os
import json
import logging
from typing import List, Dict, Any, Optional

import yfinance as yf
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import httpx
from openai import OpenAI

# ---------------- CONFIG ----------------
API_PASSWORD = os.getenv("API_PASSWORD", "SuperSecret123")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
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
    horizon: Optional[str] = None       # добавлено
    experience: Optional[str] = None    # добавлено

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
def build_candidates(limit: int = 100) -> List[Dict[str, Any]]:
    """
    Собираем список кандидатов из S&P500 через yfinance с метриками.
    """
    tickers = [
        "AAPL", "MSFT", "GOOG", "AMZN", "TSLA", "META", "NVDA", "JPM", "V", "JNJ",
        "PG", "HD", "DIS", "NFLX", "KO", "PEP", "XOM", "CVX", "BA", "IBM"
    ]
    candidates = []
    for sym in tickers[:limit]:
        try:
            data = yf.Ticker(sym)
            info = data.info
            hist = data.history(period="3mo")
            avg_vol = int(hist["Volume"].mean()) if not hist.empty else None
            candidates.append({
                "symbol": sym,
                "price": info.get("currentPrice"),
                "marketCap": info.get("marketCap"),
                "beta": info.get("beta"),
                "dividendYield": info.get("dividendYield"),
                "volume": avg_vol
            })
        except Exception as e:
            logging.warning(f"Ошибка для {sym}: {e}")
            continue
    return [c for c in candidates if c.get("price")]

def ai_select(candidates: List[Dict[str, Any]], profile: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Отправляем кандидатов в OpenAI → получаем 5 лучших + прогнозы.
    """
    prompt = f"""
    You are an investment AI.
    From the following {len(candidates)} candidate stocks with metrics:
    {json.dumps(candidates[:100], indent=2)}

    Select exactly 5 stocks fitting this profile:
    - Risk: {profile.get('risk_level')}
    - Goals: {profile.get('goals')}
    - Micro caps allowed: {profile.get('micro_caps')}
    - Horizon: {profile.get('horizon')}
    - Experience: {profile.get('experience')}

    For each stock, also forecast price at {profile.get('target_date')}.

    Return JSON:
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
    try:
        return json.loads(text)["selected"]
    except Exception as e:
        logging.error(f"AI parse error: {e}, raw: {text}")
        return []

# ---------------- ROUTES ----------------
@app.get("/ping")
async def ping():
    return {"message": "pong"}

@app.post("/onboard")
async def onboard(request: Request, body: OnboardRequest):
    check_api_key(request)
    user_profiles["profile"] = body.dict()
    return {"status": "ok", "profile": user_profiles["profile"]}

@app.post("/portfolio/build")
async def build_portfolio(request: Request):
    check_api_key(request)
    profile = user_profiles.get("profile")
    if not profile:
        raise HTTPException(status_code=400, detail="Run /onboard first")

    # 1. Кандидаты
    candidates = build_candidates(limit=100)

    # 2. AI выбор
    selected = ai_select(candidates, profile)

    # 3. Распределение бюджета
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
    return {"status": "ok", "portfolio": [p.dict() for p in positions]}

@app.get("/portfolio/holdings")
async def holdings(request: Request):
    check_api_key(request)
    portfolio = user_portfolios.get("portfolio", [])
    return {"holdings": [p.dict() for p in portfolio]}
