import os
import logging
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from openai import OpenAI

from app.update_tickers import update_tickers as update_tickers_job

# --- Logging ---
logging.basicConfig(level=logging.INFO)

# --- API keys ---
API_KEY = os.getenv("API_KEY", "SuperSecret123")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
DB_URL = os.getenv("DATABASE_URL", "")

# --- OpenAI client ---
client = OpenAI(api_key=OPENAI_API_KEY)

# --- FastAPI app ---
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


# --- Models ---
class OnboardRequest(BaseModel):
    budget: float
    risk_level: str
    goals: str
    horizon: str
    knowledge: str


# --- Helpers ---
def check_api_key(request: Request):
    api_key = request.headers.get("X-API-Key")
    if api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")


# --- Routes ---
@app.get("/ping")
async def ping():
    return {"status": "ok"}


@app.get("/health")
async def health():
    return {"status": "healthy"}


@app.post("/onboard")
async def onboard(req: OnboardRequest, request: Request):
    check_api_key(request)
    # Здесь можно сохранить профиль в базу, пока просто возвращаем
    return {"status": "ok", "profile": req.dict()}


@app.post("/portfolio/build")
async def build_portfolio(request: Request):
    check_api_key(request)
    body = await request.json()

    budget = body.get("budget", "Not specified")
    risk = body.get("risk", "Not specified")
    goals = body.get("goals", "Not specified")
    horizon = body.get("horizon", "Not specified")
    knowledge = body.get("knowledge", "Not specified")

    messages = [
        {"role": "system", "content": "You are an AI financial advisor."},
        {"role": "user", "content": f"""
        Build an investment portfolio for the following profile:
        Budget: {budget}
        Risk level: {risk}
        Goals: {goals}
        Horizon: {horizon}
        Knowledge: {knowledge}
        """}
    ]

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            temperature=0.7,
            max_tokens=500
        )
        content = response.choices[0].message.content
        return {"status": "ok", "portfolio": content}
    except Exception as e:
        logging.error(f"[BUILD_PORTFOLIO] ❌ {e}")
        raise HTTPException(status_code=500, detail=f"Failed to build portfolio: {str(e)}")


@app.get("/portfolio/holdings")
async def holdings(request: Request):
    check_api_key(request)
    # TODO: достать из базы список тикеров или сохранённый портфель
    return {"status": "ok", "holdings": []}


@app.get("/check_keys")
async def check_keys(request: Request):
    check_api_key(request)
    return {
        "status": "ok",
        "api_key_set": bool(API_KEY),
        "openai_key_set": bool(OPENAI_API_KEY),
        "db_url_set": bool(DB_URL),
    }


@app.post("/update_tickers")
async def update_tickers_endpoint(request: Request):
    check_api_key(request)

    if not DB_URL:
        raise HTTPException(status_code=500, detail="DATABASE_URL not set")

    result = update_tickers_job()
    if result["status"] == "error":
        logging.error(f"[UPDATE_TICKERS] ❌ {result['detail']}")
        raise HTTPException(status_code=500, detail=f"Update failed: {result['detail']}")

    logging.info(f"[UPDATE_TICKERS] ✅ {result}")
    return result
