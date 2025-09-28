import os
import logging
import json
import httpx
import subprocess
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from datetime import datetime
from types import SimpleNamespace

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
        "OPENAI_API_KEY": "set" if OPENAI_API_KEY else "missing"
    }

@app.post("/update_tickers")
async def update_tickers(request: Request):
    check_api_key(request)
    try:
        result = subprocess.run(
            ["python", "app/update_tickers.py"],
            capture_output=True,
            text=True,
            check=True
        )
        logging.info(f"[UPDATE_TICKERS] {result.stdout}")
        return {"status": "ok", "output": result.stdout}
    except subprocess.CalledProcessError as e:
        logging.error(f"Update tickers failed: {e.stderr}")
        raise HTTPException(status_code=500, detail=f"Update failed: {e.stderr}")

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

