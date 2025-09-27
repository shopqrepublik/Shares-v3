import os
import logging
import json
import httpx
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from datetime import datetime

from app.routers.portfolio import build_portfolio as build_core

# -------------------------
# Настройка FastAPI
# -------------------------
app = FastAPI()

# ✅ Разрешаем CORS для фронта
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # можно заменить на ["https://wealth-dashboard-ai.lovable.app"]
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -------------------------
# Переменные окружения
# -------------------------
ALPACA_API_KEY = os.getenv("ALPACA_API_KEY", "")
ALPACA_API_SECRET = os.getenv("ALPACA_API_SECRET", "")
API_PASSWORD = os.getenv("API_PASSWORD", "SuperSecret123")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

USER_PROFILE = None
CURRENT_PORTFOLIO = []

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
    Верни JSON {"{"}"symbols":[{{"symbol":"AAPL","reason":"...","forecast":{"target_date":"2025-12-01","price":200}}}]{ "}"}.
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

            parsed = json.loads(raw.replace("```json", "").replace("```", ""))
            ai_map = {item["symbol"]: item for item in parsed.get("symbols", [])}

            for c in candidates:
                sym = c["symbol"]
                if sym in ai_map:
                    c["reason"] = ai_map[sym].get("reason", "")
                    c["forecast"] = ai_map[sym].get("forecast", {})
            return candidates
    except Exception as e:
        logging.error(f"AI annotation failed: {e}")
        return candidates

# -------------------------
# Роуты
# -------------------------
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

    candidates = build_core(USER_PROFILE)
    enriched = await ai_annotate(candidates, USER_PROFILE)

    global CURRENT_PORTFOLIO
    CURRENT_PORTFOLIO = [
        {
            "symbol": c["symbol"],
            "shares": c.get("quantity", 0),
            "price": c.get("price", 0.0),
            "score": c.get("score", 0),
            "momentum": c.get("momentum"),
            "pattern": c.get("pattern"),
            "reason": c.get("reason"),
            "forecast": c.get("forecast"),
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
        "ALPACA_API_KEY": "set" if ALPACA_API_KEY else "missing",
        "ALPACA_API_SECRET": "set" if ALPACA_API_SECRET else "missing",
        "OPENAI_API_KEY": "set" if OPENAI_API_KEY else "missing"
    }

@app.get("/ping")
async def ping():
    return {"status": "ok", "time": datetime.utcnow().isoformat()}
