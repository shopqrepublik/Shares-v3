import logging, sys
from fastapi import FastAPI
from pydantic import BaseModel
from typing import List

# ---------------- LOGGING ----------------
logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)
logging.debug("🚀 main.py started loading")

# ---------------- APP ----------------
app = FastAPI(title="AI Portfolio Bot", version="0.3")

# ---------------- SQLALCHEMY (models only) ----------------
from sqlalchemy import Column, Integer, String, Float, DateTime, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
import os

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./app.db")

Base = declarative_base()

class TradeLog(Base):
    __tablename__ = "trade_logs"
    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String, index=True)
    action = Column(String)       # buy/sell
    qty = Column(Float)
    price = Column(Float)
    timestamp = Column(DateTime)

# ВАЖНО: engine и SessionLocal объявлены, но init_db() не вызывается
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

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
    return {"message": "pong"}

@app.get("/health", tags=["health"])
def health():
    return {
        "status": "ok",           # Railway всегда получит "ok"
        "service": "ai-portfolio-bot",
        "db_ready": False,        # пока инициализацию не включали
        "db_error": None
    }

@app.get("/", tags=["health"])
def root():
    return {"ok": True, "service": "ai-portfolio-bot"}

# ----- Demo endpoint: Onboarding -----
@app.post("/onboard", response_model=PortfolioResponse, tags=["demo"])
def onboard(req: OnboardRequest):
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
