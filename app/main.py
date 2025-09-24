import logging, sys
from fastapi import FastAPI
from pydantic import BaseModel
from typing import List
from sqlalchemy.orm import declarative_base

# ---------------- LOGGING ----------------
logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)
logging.debug("🚀 main.py started loading")

# ---------------- APP ----------------
app = FastAPI(title="AI Portfolio Bot", version="0.3-test")

# ---------------- SQLALCHEMY (только Base и модель) ----------------
Base = declarative_base()

class TradeLog(Base):
    __tablename__ = "trade_logs"
    # Поля определены, но engine/SessionLocal не создаём
    from sqlalchemy import Column, Integer, String, Float, DateTime
    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String, index=True)
    action = Column(String)       # buy/sell
    qty = Column(Float)
    price = Column(Float)
    timestamp = Column(DateTime)

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
        "db_ready": False,   # пока база не используется
        "db_error": None
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
