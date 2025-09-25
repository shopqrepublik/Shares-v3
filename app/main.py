import logging, sys, os
from datetime import datetime
from fastapi import FastAPI, Depends, HTTPException, Header
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import io

# ---------------- LOGGING ----------------
logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)
logging.debug("🚀 main.py started loading")

# ---------------- SECURITY ----------------
API_PASSWORD = "AI_German"

def verify_password(x_api_key: str = Header(None)):
    if x_api_key != API_PASSWORD:
        raise HTTPException(status_code=401, detail="Unauthorized")

# ---------------- DB SETUP ----------------
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./app.db")
Base = declarative_base()
engine = None
SessionLocal = None
DB_READY = False
DB_INIT_ERR = None

try:
    from sqlalchemy import create_engine
    engine = create_engine(DATABASE_URL)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    DB_READY = True
    logging.debug(f"✅ create_engine success, url={DATABASE_URL}")
except Exception as e:
    DB_INIT_ERR = str(e)
    logging.error(f"❌ create_engine failed: {e}")

class TradeLog(Base):
    __tablename__ = "trade_logs"
    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String, index=True)
    action = Column(String)
    shares = Column(Integer)
    price = Column(Float)
    timestamp = Column(DateTime, default=datetime.utcnow)

def init_db():
    global DB_READY, DB_INIT_ERR
    if engine:
        try:
            Base.metadata.create_all(bind=engine)
            DB_READY = True
            logging.debug("✅ DB initialized")
        except Exception as e:
            DB_INIT_ERR = str(e)
            logging.error(f"❌ DB init failed: {e}")

if engine:
    init_db()

# ---------------- FASTAPI APP ----------------
app = FastAPI(title="AI Portfolio Bot")

# ---------------- SCHEMAS ----------------
class OnboardRequest(BaseModel):
    budget: float
    risk_level: str
    goals: str

class PortfolioResponse(BaseModel):
    assets: list
    note: str

# ---------------- HEALTH ----------------
@app.get("/ping", tags=["health"])
def ping():
    return {"message": "pong"}

@app.get("/health", tags=["health"])
def health():
    return {
        "status": "ok",
        "service": "ai-portfolio-bot",
        "db_ready": DB_READY,
        "db_error": (DB_INIT_ERR[:500] if DB_INIT_ERR else None),
    }

@app.get("/", tags=["health"])
def root():
    return {"ok": True, "service": "ai-portfolio-bot"}

# ---------------- BUSINESS ENDPOINTS ----------------
@app.post("/onboard", dependencies=[Depends(verify_password)])
def onboard(req: OnboardRequest):
    return {
        "status": "ok",
        "saved": req.dict()
    }

@app.post("/portfolio/build", dependencies=[Depends(verify_password)])
def build_portfolio(risk: str):
    if risk == "low":
        assets = ["BND", "VNQ", "VOO"]
    elif risk == "medium":
        assets = ["VOO", "QQQ", "IWM"]
    else:
        assets = ["SPY", "ARKK", "TSLA", "NVDA"]
    return {"portfolio": assets}

@app.get("/portfolio/holdings", dependencies=[Depends(verify_password)])
def portfolio_holdings():
    return {"holdings": ["AAPL", "MSFT", "GOOG"]}

@app.post("/forecast/price", dependencies=[Depends(verify_password)])
def forecast_price(symbol: str, days: int = 5):
    # Lazy import heavy libs
    import pandas as pd
    import numpy as np
    import yfinance as yf
    from sklearn.linear_model import LinearRegression

    data = yf.download(symbol, period="6mo")
    if data.empty:
        raise HTTPException(status_code=400, detail="No data for symbol")
    data = data.reset_index()
    data["t"] = np.arange(len(data))
    X = data[["t"]]
    y = data["Close"]

    model = LinearRegression().fit(X, y)

    future_t = np.arange(len(data), len(data) + days).reshape(-1, 1)
    preds = model.predict(future_t)

    forecast = [{"day": i+1, "price": float(p)} for i, p in enumerate(preds)]
    return {"symbol": symbol, "forecast": forecast}

@app.get("/report/json", dependencies=[Depends(verify_password)])
def report_json():
    report = {"portfolio": ["AAPL", "TSLA"], "performance": {"return": 0.12, "volatility": 0.08}}
    return JSONResponse(content=report)

@app.get("/report/pdf", dependencies=[Depends(verify_password)])
def report_pdf():
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    c.drawString(100, 750, "Portfolio Report")
    c.drawString(100, 730, "Assets: AAPL, TSLA")
    c.drawString(100, 710, "Return: 12%  |  Volatility: 8%")
    c.save()

    buffer.seek(0)
    return StreamingResponse(buffer, media_type="application/pdf", headers={"Content-Disposition": "attachment; filename=report.pdf"})

@app.get("/advice/ai", dependencies=[Depends(verify_password)])
def advice_ai():
    # Пока без OpenAI, заглушка
    return {"advice": "Rebalance into more ETFs to reduce risk."}
