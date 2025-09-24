import logging, sys
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker
import os

# ---------------- LOGGING ----------------
logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)
logging.debug("🚀 main.py started loading")

# ---------------- DB ----------------
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./app.db")

Base = declarative_base()
DB_READY, DB_INIT_ERR = False, None

class TradeLog(Base):
    __tablename__ = "trade_logs"
    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String, index=True)
    action = Column(String)
    shares = Column(Integer)
    price = Column(Float)
    timestamp = Column(DateTime, default=datetime.utcnow)

try:
    engine = create_engine(DATABASE_URL)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(engine)
    DB_READY = True
    logging.debug("✅ DB initialized")
except Exception as e:
    DB_INIT_ERR = str(e)
    logging.error(f"❌ DB init failed: {DB_INIT_ERR}")

# ---------------- FASTAPI ----------------
app = FastAPI(title="AI Portfolio Bot", version="0.7")

# ---------------- SCHEMAS ----------------
class OnboardRequest(BaseModel):
    budget: float
    risk_level: str
    goals: str | None = None

class PortfolioResponse(BaseModel):
    symbol: str
    shares: int
    allocation: float

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
        "db_error": DB_INIT_ERR,
    }

@app.get("/", tags=["health"])
def root():
    return {"ok": True, "service": "ai-portfolio-bot"}

@app.post("/onboard", response_model=list[PortfolioResponse])
def onboard(req: OnboardRequest):
    if req.risk_level.lower() == "low":
        return [{"symbol": "BND", "shares": 10, "allocation": 0.7},
                {"symbol": "AAPL", "shares": 5, "allocation": 0.3}]
    if req.risk_level.lower() == "high":
        return [{"symbol": "TSLA", "shares": 8, "allocation": 0.6},
                {"symbol": "NVDA", "shares": 6, "allocation": 0.4}]
    return [{"symbol": "VOO", "shares": 7, "allocation": 1.0}]

@app.get("/report/json")
def report_json():
    data = {"timestamp": datetime.utcnow().isoformat(), "portfolio": ["AAPL", "TSLA", "NVDA"]}
    return data

@app.get("/report/pdf")
def report_pdf():
    from io import BytesIO
    from reportlab.pdfgen import canvas
    from fastapi.responses import StreamingResponse

    buffer = BytesIO()
    p = canvas.Canvas(buffer)
    p.drawString(100, 750, "Portfolio Report")
    p.drawString(100, 730, f"Generated at: {datetime.utcnow().isoformat()}")
    p.showPage()
    p.save()
    buffer.seek(0)

    return StreamingResponse(buffer, media_type="application/pdf",
                             headers={"Content-Disposition": "inline; filename=report.pdf"})

@app.post("/forecast/price")
def forecast_price(req: ForecastRequest):
    try:
        import yfinance as yf
        import numpy as np
        from sklearn.linear_model import LinearRegression

        data = yf.download(req.symbol, period="6mo")
        if data.empty:
            raise HTTPException(status_code=404, detail="No data found")

        data = data.reset_index()
        data["day"] = np.arange(len(data))
        X = data["day"].values.reshape(-1, 1)
        y = data["Close"].values

        model = LinearRegression().fit(X, y)
        future_days = np.arange(len(data), len(data) + req.days).reshape(-1, 1)
        forecast = model.predict(future_days)

        return {"symbol": req.symbol,
                "forecast": [{"day": i+1, "price": round(float(p), 2)}
                             for i, p in enumerate(forecast)]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Forecast error: {str(e)}")
