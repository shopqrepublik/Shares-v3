import logging, sys
from datetime import datetime
from io import BytesIO
import os

from fastapi import FastAPI
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)
logging.debug("🚀 main.py started loading")

# ---------- База данных ----------
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./app.db")
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()


class TradeLog(Base):
    __tablename__ = "trade_logs"
    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String, index=True)
    action = Column(String)
    shares = Column(Integer)
    price = Column(Float)
    timestamp = Column(DateTime, default=datetime.utcnow)


class UserPref(Base):
    __tablename__ = "user_prefs"
    id = Column(Integer, primary_key=True)
    budget = Column(Float, default=10000.0)
    goal = Column(String, default="growth")
    risk = Column(String, default="medium")
    horizon_years = Column(Integer, default=5)
    created_at = Column(DateTime, default=datetime.utcnow)


class PortfolioHolding(Base):
    __tablename__ = "portfolio_holdings"
    id = Column(Integer, primary_key=True)
    symbol = Column(String, index=True)
    weight = Column(Float)
    qty = Column(Float, default=0.0)
    last_price = Column(Float, default=0.0)
    updated_at = Column(DateTime, default=datetime.utcnow)


class MetricsDaily(Base):
    __tablename__ = "metrics_daily"
    id = Column(Integer, primary_key=True)
    ts = Column(DateTime, default=datetime.utcnow, index=True)
    equity = Column(Float)
    pnl_day = Column(Float)
    pnl_total = Column(Float)
    benchmark_value = Column(Float)
    note = Column(String, nullable=True)


try:
    Base.metadata.create_all(bind=engine)
    logging.debug("✅ DB initialized")
    DB_READY = True
    DB_INIT_ERR = None
except Exception as e:
    logging.error(f"❌ DB init failed: {e}")
    DB_READY = False
    DB_INIT_ERR = str(e)

# ---------- FastAPI ----------
app = FastAPI()


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


# ---------- Модели запросов ----------
class OnboardRequest(BaseModel):
    budget: float
    risk_level: str
    goals: str


class ForecastRequest(BaseModel):
    symbol: str
    days: int = 5


# ---------- Эндпоинты ----------
@app.post("/onboard")
def onboard(req: OnboardRequest):
    db = SessionLocal()
    try:
        pref = db.query(UserPref).first()
        if not pref:
            pref = UserPref()
            db.add(pref)
        pref.budget = req.budget
        pref.goal = req.goals
        pref.risk = req.risk_level
        pref.horizon_years = 5
        db.commit()
        return {"saved": True, "pref": {
            "budget": pref.budget,
            "goal": pref.goal,
            "risk": pref.risk,
            "horizon_years": pref.horizon_years
        }}
    finally:
        db.close()


@app.post("/portfolio/build")
def build_portfolio(risk: str = "medium"):
    db = SessionLocal()
    try:
        db.query(PortfolioHolding).delete()  # очистить старый портфель
        if risk == "low":
            holdings = [("SPY", 0.7), ("AGG", 0.3)]
        elif risk == "medium":
            holdings = [("SPY", 0.5), ("QQQ", 0.3), ("IWM", 0.2)]
        else:  # high
            holdings = [("QQQ", 0.5), ("IWM", 0.3), ("XYZM", 0.2)]  # XYZM = micro-cap demo
        for sym, w in holdings:
            h = PortfolioHolding(symbol=sym, weight=w, qty=0.0)
            db.add(h)
        db.commit()
        return {"ok": True, "holdings": holdings}
    finally:
        db.close()


@app.get("/portfolio/holdings")
def get_portfolio():
    db = SessionLocal()
    try:
        holds = db.query(PortfolioHolding).all()
        return [{"symbol": h.symbol, "weight": h.weight, "qty": h.qty, "last_price": h.last_price} for h in holds]
    finally:
        db.close()


@app.post("/metrics/refresh")
def refresh_metrics():
    import yfinance as yf
    db = SessionLocal()
    try:
        holds = db.query(PortfolioHolding).all()
        if not holds:
            return {"error": "no holdings"}
        total = 0.0
        for h in holds:
            try:
                price = yf.Ticker(h.symbol).history(period="1d")["Close"].iloc[-1]
                h.last_price = float(price)
                total += h.weight * 10000 * h.last_price
                h.updated_at = datetime.utcnow()
            except Exception:
                pass
        spy = yf.Ticker("SPY").history(period="1d")["Close"].iloc[-1]
        m = MetricsDaily(
            equity=total, pnl_day=0.0, pnl_total=0.0,
            benchmark_value=float(spy)
        )
        db.add(m)
        db.commit()
        return {"ok": True, "equity": total, "benchmark": float(spy)}
    finally:
        db.close()


@app.get("/metrics/daily/latest")
def get_latest_metrics():
    db = SessionLocal()
    try:
        m = db.query(MetricsDaily).order_by(MetricsDaily.ts.desc()).first()
        if not m:
            return {"error": "no metrics"}
        return {
            "ts": m.ts, "equity": m.equity,
            "pnl_day": m.pnl_day, "pnl_total": m.pnl_total,
            "benchmark": m.benchmark_value
        }
    finally:
        db.close()


@app.post("/forecast/price")
def forecast_price(req: ForecastRequest):
    import yfinance as yf
    from sklearn.linear_model import LinearRegression
    import numpy as np
    hist = yf.Ticker(req.symbol).history(period="6mo")
    prices = hist["Close"].values
    X = np.arange(len(prices)).reshape(-1, 1)
    y = prices
    model = LinearRegression().fit(X, y)
    future_X = np.arange(len(prices), len(prices) + req.days).reshape(-1, 1)
    preds = model.predict(future_X)
    return {"symbol": req.symbol,
            "forecast": [{"day": i + 1, "price": float(p)} for i, p in enumerate(preds)]}


@app.get("/report/json")
def report_json():
    db = SessionLocal()
    try:
        holds = db.query(PortfolioHolding).all()
        return {"portfolio": [{"symbol": h.symbol, "weight": h.weight, "last_price": h.last_price} for h in holds]}
    finally:
        db.close()


@app.get("/report/pdf")
def report_pdf():
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    c.drawString(100, 750, "Investment Portfolio Report")
    c.drawString(100, 730, "Generated by ai-portfolio-bot")
    c.showPage()
    c.save()
    buffer.seek(0)
    return StreamingResponse(buffer, media_type="application/pdf", headers={"Content-Disposition": "inline; filename=report.pdf"})


@app.get("/advice/ai")
def advice_ai():
    import os
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        # Rule-based советы
        return {"advice": [
            "Снизьте долю micro-cap до 5–7% от портфеля.",
            "Не концентрируйте >40% в одном активе.",
            "Пересматривайте портфель каждые 6 месяцев."
        ]}
    else:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        prompt = "Дай 3 совета по ребалансировке портфеля с учётом риска."
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}]
        )
        text = resp.choices[0].message.content
        return {"advice": text}
