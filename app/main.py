import logging, sys, os
from fastapi import FastAPI
from pydantic import BaseModel
from typing import List

# ---------------- LOGGING ----------------
logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)
logging.debug("🚀 main.py started loading")

# ---------------- APP ----------------
app = FastAPI(title="AI Portfolio Bot", version="0.4")

# ---------------- SQLALCHEMY ----------------
from sqlalchemy import Column, Integer, String, Float, DateTime, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./app.db")
SKIP_DB_INIT = os.getenv("SKIP_DB_INIT", "0") == "1"

Base = declarative_base()

class TradeLog(Base):
    __tablename__ = "trade_logs"
    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String, index=True)
    action = Column(String)       # buy/sell
    qty = Column(Float)
    price = Column(Float)
    timestamp = Column(DateTime)

# engine и SessionLocal определяем всегда
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# ---------------- INIT DB ----------------
DB_READY = False
DB_INIT_ERR = None

def init_db():
    global DB_READY, DB_INIT_ERR
    try:
        Base.metadata.create_all(bind=engine)
        DB_READY = True
        logging.info("✅ init_db() completed successfully")
    except Exception as e:
        DB_INIT_ERR = str(e)
        DB_READY = False
        logging.error(f"❌ init_db() failed: {e}")

if not SKIP_DB_INIT:
    logging.info("🔧 Calling init_db()...")
    init_db()
else:
    logging.info("⏩ SKIP_DB_INIT=1 → пропускаем init_db()")

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
        "status": "ok",           # Railway всегда получает ok
        "service": "ai-portfolio-bot",
        "db_ready": DB_READY,
        "db_error": DB_INIT_ERR
    }

@app.get("/", tags=["health"])
def root():
    return {"ok": True, "service": "ai-portfolio-bot"}

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
