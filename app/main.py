import os
import json
import logging
from typing import List, Dict, Any, Optional
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from openai import OpenAI

# ---------------- CONFIG ----------------
API_PASSWORD = os.getenv("API_PASSWORD", "SuperSecret123")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
ALPACA_API_KEY = os.getenv("ALPACA_API_KEY", "")
ALPACA_API_SECRET = os.getenv("ALPACA_API_SECRET", "")

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

# ---------------- MEMORY STORAGE ----------------
user_profiles: Dict[str, Any] = {}
user_portfolios: Dict[str, List[Dict[str, Any]]] = {}

# ---------------- AI ANNOTATION ----------------
def ai_annotate(selected: List[Dict[str, Any]], profile: Dict[str, Any]) -> List[Dict[str, Any]]:
    """AI добавляет прогноз и объяснение к уже выбранным акциям"""
    prompt = f"""
    You are an investment assistant.
    For the following 5 selected stocks:
    {json.dumps(selected, indent=2)}

    User profile:
    - Risk: {profile.get('risk_level')}
    - Goals: {profile.get('goals')}
    - Horizon: {profile.get('horizon')}
    - Experience: {profile.get('experience')}

    For each stock, provide:
    - reason (short explanation why it fits profile)
    - forecast (expected price at {profile.get('target_date')})

    Return ONLY valid JSON:
    {{
      "annotated": [
        {{
          "symbol": "AAPL",
          "reason": "Large-cap stability with growth",
          "forecast": {{"target_date": "{profile.get('target_date')}", "price": 210}}
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
        if text.startswith("```"):
            text = text.strip("`")
            if text.lower().startswith("json"):
                text = text[4:].strip()
        parsed = json.loads(text)["annotated"]
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

    # 1. Берём готовый top-5 из app/routers/portfolio.py
    from app.routers.portfolio import build_portfolio as build_core
    holdings_resp = build_core()
    selected = holdings_resp["data"]

    if not selected:
        return {"status": "error", "message": "No holdings built"}

    logging.info("[METRICS RESULT] Отобранные бумаги по метрикам:")
    for s in selected:
        logging.info(f"  {s['symbol']} — price={s['price']}, score={s.get('score')}")

    # 2. Обогащаем через AI (reason + forecast)
    annotated = ai_annotate(selected, profile)

    logging.info("[AI ANNOTATION] Прогнозы AI:")
    for a in annotated:
        logging.info(f"  {a['symbol']} — reason={a.get('reason')}, forecast={a.get('forecast')}")

    # 3. Объединяем данные
    budget = profile["budget"]
    alloc = budget / len(selected)

    enriched = []
    for s in selected:
        extra = next((a for a in annotated if a["symbol"] == s["symbol"]), {})
        qty = int(alloc // s["price"]) if s["price"] else 0
        enriched.append({
            "symbol": s["symbol"],
            "price": s["price"],
            "score": s.get("score"),
            "momentum": s.get("momentum"),
            "forecast_metric": s.get("forecast"),
            "pattern": s.get("pattern"),
            "quantity": qty,
            "allocation": round(alloc/budget, 2),
            "reason": extra.get("reason"),
            "forecast": extra.get("forecast")
        })

    user_portfolios["portfolio"] = enriched
    logging.info("[PORTFOLIO BUILT] Итоговый портфель:")
    for p in enriched:
        logging.info(f"  {p['symbol']} — qty={p['quantity']}, alloc={p['allocation']}, score={p['score']}")

    return {"status": "ok", "portfolio": enriched}

@app.get("/portfolio/holdings")
async def holdings(request: Request):
    check_api_key(request)
    portfolio = user_portfolios.get("portfolio", [])
    return {"holdings": portfolio}

