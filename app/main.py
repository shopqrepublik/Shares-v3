import logging, sys, os
from datetime import datetime
from io import BytesIO

from fastapi import FastAPI
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime
from sqlalchemy.orm import sessionmaker, declarative_base
from reportlab.pdfgen import canvas

# ---------------- LOGGING ----------------
logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)
logging.debug("🚀 main.py started loading")

# ---------------- DATABASE ----------------
DB_URL = os.getenv("DATABASE_URL", "sqlite:///./app.db")
DB_READY = False
DB_INIT_ERR = None

Base = declarative_base()
engine = None
SessionLocal = None

try:
    engine = create_engine(DB_URL, pool_pre_ping=True)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    DB_READY = True
    logging.debug(f"✅ create_engine success, url={DB_URL}")
except Exception as e:
    DB_INIT_ERR = str(e)
    logging.error(f"❌ create_engine failed: {e}")

# ---------------- MODELS ----------------
class TradeLog(Base):
    __tablename__ = "trade_logs"
    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String, index=True)
    action = Column(String)
    shares = Column(Integer)
    price = Column(Float)
    timestamp = Column(DateTime, default=datetime.utcnow)

# ---------------- INIT DB ----------------
def init_db():
    global DB_READY, DB_INIT_ERR
    try:
        Base.metadata.create_all(bind=engine)
        DB_READY = True
        logging.info("✅ DB initialized")
    except Exception as e:
        DB_INIT_ERR = str(e)
        DB_READY = False
        logging.error(f"❌ DB init failed: {e}")

if DB_READY:
    init_db()

# ---------------- FASTAPI APP ----------------
app = FastAPI(title="AI Portfolio Bot", version="0.6")

# ---------------- Pydantic Schemas ----------------
class OnboardRequest(BaseModel):
    budget: float
    risk_level: str
    goals: str

class PortfolioResponse(BaseModel):
    assets: list[str]
    allocation: list[float]
    expected_return: float

class ForecastRequest(BaseModel):
    symbol: str
    days: int = 5

# ---------------- ROUTES ----------------
@app.get("/ping", tags=["health"])
def ping():
    return {"message": "pong"}

@app.get("/health", tags=["health"])
def health():
    return {
        "status": "ok",
        "service": "ai-portfolio-bot",
        "db_ready": DB_READY,
        "db_error": (DB_INIT_ERR[:200] if DB_INIT_ERR else None),
    }

@app.get("/", tags=["health"])
def root():
    return {"ok": True, "service": "ai-portfolio-bot"}

@app.post("/onboard", response_model=PortfolioResponse)
def onboard(req: OnboardRequest):
    if req.risk_level == "low":
        assets, alloc, exp_ret = ["BND", "VOO"], [0.7, 0.3], 0.05
    elif req.risk_level == "high":
        assets, alloc, exp_ret = ["TSLA", "NVDA", "BTC"], [0.4, 0.4, 0.2], 0.20
    else:
        assets, alloc, exp_ret = ["AAPL", "MSFT", "BND"], [0.4, 0.4, 0.2], 0.10
    return PortfolioResponse(assets=assets, allocation=alloc, expected_return=exp_ret)

# ---------------- REPORTS ----------------
@app.get("/report/json")
def report_json():
    report = {
        "generated_at": datetime.utcnow().isoformat(),
        "portfolio": [
            {"symbol": "AAPL", "allocation": 0.4, "expected_return": 0.12},
            {"symbol": "MSFT", "allocation": 0.4, "expected_return": 0.10},
            {"symbol": "BND", "allocation": 0.2, "expected_return": 0.03},
        ]
    }
    return JSONResponse(content=report)

@app.get("/report/pdf")
def report_pdf():
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer)
    pdf.setFont("Helvetica", 12)
    pdf.drawString(100, 800, "Portfolio Report")
    pdf.drawString(100, 780, f"Generated at: {datetime.utcnow().isoformat()}")
    pdf.drawString(100, 750, "AAPL - 40% - Expected return: 12%")
    pdf.drawString(100, 730, "MSFT - 40% - Expected return: 10%")
    pdf.drawString(100, 710, "BND  - 20% - Expected return: 3%")
    pdf.showPage()
    pdf.save()
    buffer.seek(0)
    return StreamingResponse(buffer, media_type="application/pdf", headers={
        "Content-Disposition": "inline; filename=report.pdf"
    })

# ---------------- AI FORECAST ----------------
@app.post("/forecast/price")
def forecast_price(req: ForecastRequest):
    try:
        import pandas as pd
        import yfinance as yf
        from sklearn.linear_model import LinearRegression
        import numpy as np

        logging.info(f"Fetching data for {req.symbol}")
        data = yf.download(req.symbol, period="6mo", interval="1d")
        if data.empty:
            return {"error": f"No data for {req.symbol}"}

        # Подготовка данных
        data = data.reset_index()
        data["Day"] = np.arange(len(data))
        X = data[["Day"]].values
        y = data["Close"].values

        model = LinearRegression()
        model.fit(X, y)

        # Прогноз на req.days дней вперёд
        future_days = np.arange(len(data), len(data) + req.days).reshape(-1, 1)
        preds = model.predict(future_days)

        forecast = [
            {"day": int(len(data) + i), "predicted_price": float(pred)}
            for i, pred in enumerate(preds)
        ]

        return {
            "symbol": req.symbol,
            "generated_at": datetime.utcnow().isoformat(),
            "forecast_days": req.days,
            "forecast": forecast,
        }

    except Exception as e:
        logging.error(f"❌ Forecast failed: {e}")
        return {"error": str(e)}
