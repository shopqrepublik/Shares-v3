import logging, sys, os
from fastapi import FastAPI
from pydantic import BaseModel
from typing import List
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker

# ---------------- LOGGING ----------------
logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)
logging.debug("🚀 main.py started loading")

# ---------------- DB SETUP ----------------
Base = declarative_base()
engine = None
SessionLocal = None
DB_READY = False
DB_INIT_ERR = None

try:
    DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./app.db")
    engine = create_engine(DATABASE_URL, echo=False, future=True)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    DB_READY = True
    logging.debug(f"✅ create_engine success, url={DATABASE_URL}")
except Exception as e:
    DB_INIT_ERR = str(e)
    logging.error(f"❌ create_engine failed: {e}")

# ---------------- MODELS ----------------
class TradeLog(Base):
    __tablename__ = "trade_logs"
    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String, index=True)
    action = Column(String)  # buy/sell
    qty = Column(Float)
    price = Column(Float)
    timestamp = Column(DateTime)

# ---------------- APP ----------------
app = FastAPI(title="AI Portfolio Bot", version="0.3.1")

# ---------------- SCHEMAS ----------------
class OnboardRequest(BaseModel):
    budget: float
    risk_level: str
    goals: List[str]

class PortfolioResponse(BaseModel):
    portfolio: dict
    message: str

# ---------------- ROUTES ----------------
@app.get("/ping", tags=["health"])
def ping():
    logging.debug("✅ /ping called")
    return {"message": "pong"}

@app.get("/health", tags=["health"])
def health():
    logging.debug("✅ /health called")
    return {
        "status": "ok",
        "service": "ai-portfolio-bot",
        "db_ready": DB_READY,
        "db_error": DB_INIT_ERR[:200] if DB_INIT_ERR else None
    }

@app.get("/", tags=["health"])
def root():
    logging.debug("✅ / called")
    return {"ok": True, "service": "ai-portfolio-bot"}

@app.post("/onboard", response_model=PortfolioResponse, tags=["demo"])
def onboard(req: OnboardRequest):
    logging.debug(f"✅ /onboard called with risk_level={req.risk_level}")
    if req.risk_level == "low":
        portfolio = {"ETF": "BND", "Stocks": "AAPL"}
    elif req.risk_level == "medium":
        portfolio = {"ETF": "VOO", "Stocks": "MSFT"}
    else:
        portfolio = {"ETF": "QQQ", "Stocks": "TSLA"}

    return PortfolioResponse(
        portfolio=portfolio,
        message=f"Portfolio built for risk level {req.risk_level}"
    )
    
