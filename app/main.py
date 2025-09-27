import os
import logging
import json
from datetime import datetime
from fastapi import FastAPI, Request, HTTPException
from pydantic import BaseModel
from typing import Dict, Any, List

from app.routers.portfolio import build_portfolio as build_core
from openai import AsyncOpenAI

# Логирование
logging.basicConfig(level=logging.INFO)

# Инициализация
app = FastAPI()
client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Хранилище в памяти
USER_PROFILE: Dict[str, Any] = {}
CURRENT_PORTFOLIO: List[Dict[str, Any]] = []

# Конфиги
API_PASSWORD = os.getenv("API_PASSWORD", "SuperSecret123")

# -------------------- Модели --------------------

class OnboardRequest(BaseModel):
    budget: float
    risk_level: str
    goals: str
    horizon: str = ""
    experience: str = ""
    micro_caps: bool = False

# -------------------- Вспомогательные --------------------

def check_api_key(request: Request):
    api_key = request.headers.get("X-API-Key")
    if api_key != API_PASSWORD:
        raise HTTPException(status_code=401, detail="Unauthorized")

# -------------------- AI-аннотации --------------------

async def ai_annotate(candidates: List[Dict[str, Any]], profile: Dict[str, Any]):
    prompt = f"""
    Пользовательский профиль:
    - Бюджет: {profile.get("budget")}
    - Риск-профиль: {profile.get("risk_level")}
    - Цели: {profile.get("goals")}
    - Горизонт: {profile.get("horizon")}
    - Опыт: {profile.get("experience")}

    Вот список акций для портфеля:
    {json.dumps(candidates, indent=2, ensure_ascii=False)}

    Для каждой акции добавь:
    - reason: короткое объяснение (1–2 предложения)
    - forecast: JSON с target_date и ожидаемой ценой price

    Верни JSON-массив, пример:
    [
      {"symbol": "AAPL", "reason": "устойчивый рост", "forecast": {"target_date": "2025-12-31", "price": 250}}
    ]
    """

    try:
        resp = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Ты — финансовый аналитик."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3
        )
        text = resp.choices[0].message.content.strip()
        logging.info(f"[AI RAW OUTPUT] {text}")

        parsed = json.loads(text)
        if isinstance(parsed, list):
            enriched = []
            for cand in candidates:
                match = next((x for x in parsed if x.get("symbol") == cand["symbol"]), {})
                cand["reason"] = match.get("reason", "")
                cand["forecast"] = match.get("forecast", {})
                enriched.append(cand)
            logging.info(f"[AI PARSED] {enriched}")
            return enriched
    except Exception as e:
        logging.error(f"AI annotate failed: {e}")

    return candidates

# -------------------- Маршруты --------------------

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

    if not USER_PROFILE:
        raise HTTPException(status_code=400, detail="User profile not set. Run /onboard first.")

    profile = USER_PROFILE
    candidates = build_core(profile)
    logging.info(f"[CANDIDATES] {candidates}")

    enriched = await ai_annotate(candidates, profile)

    global CURRENT_PORTFOLIO
    CURRENT_PORTFOLIO = [
        {
            "symbol": c["symbol"],
            "shares": c.get("quantity", 0),
            "price": c.get("price", 0),
            "timestamp": datetime.utcnow().isoformat()
        }
        for c in enriched
    ]

    return {"data": CURRENT_PORTFOLIO}

@app.get("/portfolio/holdings")
async def get_holdings(request: Request):
    check_api_key(request)
    return {"data": CURRENT_PORTFOLIO}

@app.get("/check_keys")
async def check_keys(request: Request):
    check_api_key(request)
    return {
        "ALPACA_API_KEY": "set" if os.getenv("ALPACA_API_KEY") else "missing",
        "ALPACA_API_SECRET": "set" if os.getenv("ALPACA_API_SECRET") else "missing",
        "OPENAI_API_KEY": "set" if os.getenv("OPENAI_API_KEY") else "missing",
    }

@app.get("/ping")
async def ping():
    return {"status": "ok"}
