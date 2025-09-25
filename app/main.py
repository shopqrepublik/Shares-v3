import logging
import sys
import os
import time
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, declarative_base, Session

# ---------------- LOGGING ----------------
logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)
logger = logging.getLogger(__name__)

# ---------------- FASTAPI ----------------
app = FastAPI(title="AI Portfolio Bot")

# CORS — ваш фронт
origins = [
    "https://wealth-dashboard-ai.lovable.app",
    "http://localhost:3000"
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------- DB ----------------
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./app.db")
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

try:
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    DB_READY = True
    DB_INIT_ERR = None
    logger.info("✅ DB initialized")
except Exception as e:
    DB_READY = False
    DB_INIT_ERR = str(e)
    logger.error(f"❌ DB init error: {e}")

# ---------------- AUTH ----------------
API_PASSWORD = "AI_German"

def check_api_key(request: Request):
    key = request.headers.get("x-api-key")
    if key != API_PASSWORD:
        logger.warning(f"Unauthorized request: x-api-key={key}")
        raise HTTPException(status_code=401, detail="Unauthorized")

# ---------------- HEALTH ----------------
@app.get("/ping")
def ping():
    return {"message": "pong"}

@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "ai-portfolio-bot",
        "db_ready": DB_READY,
        "db_error": (DB_INIT_ERR[:500] if DB_INIT_ERR else None),
    }

# ---------------- ONBOARDING ----------------
@app.post("/onboard")
async def onboard(request: Request):
    check_api_key(request)
    data = await request.json()
    budget = data.get("budget")
    risk = data.get("risk")
    goals = data.get("goals")
    logger.info(f"Onboarding received: {data}")
    return {"status": "ok", "saved": True, "data": data}

# ---------------- PORTFOLIO ----------------
@app.get("/portfolio/holdings")
def portfolio_holdings(request: Request):
    check_api_key(request)
    holdings = [
        {
            "ticker": "AAPL",
            "qty": 10,
            "avg_price": 150.0,
            "market_price": 155.0,
            "market_value": 1550.0,
            "ts": datetime.utcnow().isoformat()
        },
        {
            "ticker": "MSFT",
            "qty": 5,
            "avg_price": 300.0,
            "market_price": 305.0,
            "market_value": 1525.0,
            "ts": datetime.utcnow().isoformat()
        },
        {
            "ticker": "GOOG",
            "qty": 3,
            "avg_price": 140.0,
            "market_price": 142.5,
            "market_value": 427.5,
            "ts": datetime.utcnow().isoformat()
        }
    ]
    return {"holdings": holdings}
