import logging
import sys
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, Depends, Request, Response, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, declarative_base, Session
import os
import time

# ---------------- LOGGING ----------------
logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)
logger = logging.getLogger(__name__)

# ---------------- FASTAPI ----------------
app = FastAPI(title="AI Portfolio Bot")

# CORS — укажите ваш фронт
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

# ---------------- MIDDLEWARE: LOG ----------------
@app.middleware("http")
async def log_requests(request: Request, call_next):
    idem = f"{request.method} {request.url.path}"
    start_time = time.time()
    try:
        response = await call_next(request)
        process_time = (time.time() - start_time) * 1000
        logger.info(f"{idem} completed_in={process_time:.2f}ms status={response.status_code}")
        return response
    except Exception as e:
        logger.exception(f"ERROR in {idem}: {e}")
        raise

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

def verify_password(x_api_key: Optional[str] = None):
    if x_api_key != API_PASSWORD:
        raise HTTPException(status_code=401, detail="Unauthorized")

@app.post("/auth/check")
def auth_check(payload: dict):
    password = payload.get("password")
    if password == API_PASSWORD:
        return {"ok": True}
    return {"ok": False}

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
@app.post("/onboard", dependencies=[Depends(verify_password)])
def onboard(data: dict, db: Session = Depends(SessionLocal)):
    budget = data.get("budget")
    risk = data.get("risk")
    goals = data.get("goals")
    logger.info(f"Onboarding: budget={budget}, risk={risk}, goals={goals}")
    # тут можно сохранить в таблицу users
    return {"status": "ok", "saved": True}

# ---------------- PORTFOLIO ----------------
@app.get("/portfolio/holdings", dependencies=[Depends(verify_password)])
def portfolio_holdings():
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

# ---------------- METRICS ----------------
@app.post("/metrics/refresh", dependencies=[Depends(verify_password)])
def metrics_refresh():
    return {"status": "ok", "refreshed_at": datetime.utcnow().isoformat()}

# ---------------- FORECAST ----------------
@app.post("/forecast/price", dependencies=[Depends(verify_password)])
def forecast_price(data: dict):
    symbol = data.get("symbol", "AAPL")
    days = data.get("days", 5)
    forecast = [{"day": i+1, "predicted_price": 150 + i} for i in range(days)]
    return {"symbol": symbol, "forecast": forecast}

# ---------------- ADVICE ----------------
@app.post("/advice/ai", dependencies=[Depends(verify_password)])
def advice_ai(data: dict):
    return {
        "advice": f"Based on your risk profile '{data.get('risk','medium')}', diversify into AAPL, MSFT, and GOOG."
    }

# ---------------- REPORT ----------------
@app.get("/report/json", dependencies=[Depends(verify_password)])
def report_json():
    return {"portfolio": []}
