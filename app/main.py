import os
import logging
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import openai

# Импорты из вашего update_tickers.py
from app.update_tickers import fetch_sp500, fetch_nasdaq100, save_to_db

# --- Logging ---
logging.basicConfig(level=logging.INFO)

# --- API Key ---
API_KEY = os.getenv("API_KEY", "SuperSecret123")
DB_URL = os.getenv("DATABASE_URL", "")

# --- OpenAI ---
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
if OPENAI_API_KEY:
    openai.api_key = OPENAI_API_KEY

# --- FastAPI app ---
app = FastAPI()

# --- CORS ---
origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "https://wealth-dashboard-ai.lovable.app",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Helpers ---
def check_api_key(request: Request):
    api_key = request.headers.get("X-API-Key")
    if api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")

# --- Models ---
class OnboardRequest(BaseModel):
    budget: float
    risk_level: str
    goals: str
    horizon: str
    knowledge: str

# --- Public endpoints ---
@app.get("/ping")
def ping():
    return {"status": "ok"}

@app.get("/health")
def health():
    return {"status": "healthy"}

# --- Protected endpoints ---
@app.post("/onboard")
async def onboard(request: Request, body: OnboardRequest):
    check_api_key(request)
    return {"status": "ok", "profile": body.dict()}

@app.post("/portfolio/build")
async def build_portfolio(request: Request, body: OnboardRequest):
    check_api_key(request)

    if not OPENAI_API_KEY:
        raise HTTPException(status_code=500, detail="OPENAI_API_KEY not set")

    prompt = f"""
    Build an investment portfolio for:
    - Budget: {body.budget}
    - Risk Level: {body.risk_level}
    - Goals: {body.goals}
    - Horizon: {body.horizon}
    - Knowledge: {body.knowledge}
    """

    try:
        response = openai.ChatCompletion.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
        )
        return {"portfolio": response.choices[0].message["content"].strip()}
    except Exception as e:
        logging.error(f"[BUILD_PORTFOLIO] ❌ {e}")
        raise HTTPException(status_code=500, detail=f"Portfolio build failed: {str(e)}")

@app.get("/portfolio/holdings")
async def get_holdings(request: Request):
    check_api_key(request)
    return {"holdings": []}  # Заглушка, можно заменить реальной логикой

@app.get("/check_keys")
async def check_keys(request: Request):
    check_api_key(request)
    return {
        "API_KEY": bool(API_KEY),
        "OPENAI_API_KEY": bool(OPENAI_API_KEY),
        "DATABASE_URL": bool(DB_URL),
    }

@app.post("/update_tickers")
async def update_tickers(request: Request):
    check_api_key(request)

    if not DB_URL:
        raise HTTPException(status_code=500, detail="DATABASE_URL not set")

    try:
        sp500 = fetch_sp500()
        nasdaq100 = fetch_nasdaq100()
        result = save_to_db(sp500, nasdaq100)
        logging.info(f"[UPDATE_TICKERS] ✅ {result}")
        return {"status": "ok", **result}
    except Exception as e:
        logging.error(f"[UPDATE_TICKERS] ❌ {e}")
        raise HTTPException(status_code=500, detail=f"Update failed: {str(e)}")

# --- Test CORS ---
@app.options("/{full_path:path}")
async def preflight_handler(full_path: str):
    return {}
