from __future__ import annotations
from fastapi import FastAPI
from fastapi.responses import JSONResponse, FileResponse
from pydantic import BaseModel
from datetime import datetime
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
import os
import json
import yfinance as yf   # ✅ вынес наверх

from openai import OpenAI
from app.models import (
    init_db, SessionLocal,
    PositionSnapshot, MetricsDaily,
    UserPref, PortfolioHolding
)
from app.utils import fetch_many_last_close, fetch_spy_last_close

# ---------------- INIT ----------------
init_db()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

app = FastAPI(title="AI Portfolio Bot", version="1.0")

# ---------------- SCHEMAS ----------------
class OnboardReq(BaseModel):
    budget: float
    goal: str           # growth / income / balanced
    risk: str           # low / medium / high
    horizon_years: int

class RecommendReq(BaseModel):
    prompt: str
    strategy: str

class BuildReq(BaseModel):
    tickers: list[str]
    weights: list[float] | None = None

# ---------------- HEALTH ----------------
@app.get("/ping", tags=["health"])
def ping():
    return {"message": "pong"}

# ---------------- ONBOARD ----------------
@app.post("/onboard", tags=["portfolio"])
def onboard(req: OnboardReq):
    db = SessionLocal()
    pref = db.query(UserPref).first()
    if pref is None:
        pref = UserPref()
        db.add(pref)

    pref.budget = float(req.budget)
    pref.goal = req.goal
    pref.risk = req.risk
    pref.horizon_years = int(req.horizon_years)
    db.commit()
    db.refresh(pref)
    db.close()
    return {"status": "ok", "pref": {
        "budget": pref.budget, "goal": pref.goal, "risk": pref.risk, "horizon_years": pref.horizon_years
    }}

# ---------------- POSITIONS ----------------
@app.get("/positions", tags=["portfolio"])
def get_positions():
    db = SessionLocal()
    positions = db.query(PositionSnapshot).all()
    db.close()
    return [
        {
            "ticker": p.ticker,
            "qty": p.qty,
            "avg_price": p.avg_price,
            "market_price": p.market_price,
            "market_value": p.market_value,
            "ts": p.ts
        }
        for p in positions
    ]

# ---------------- REPORT (JSON) ----------------
@app.get("/report/daily", tags=["reports"])
def get_daily_report():
    db = SessionLocal()
    last = db.query(MetricsDaily).order_by(MetricsDaily.ts.desc()).first()
    positions = db.query(PositionSnapshot).all()
    db.close()

    if not last:
        return JSONResponse({"error": "No data"})

    return {
        "equity": last.equity,
        "pnl_day": last.pnl_day,
        "pnl_total": last.pnl_total,
        "benchmark_value": last.benchmark_value,
        "timestamp": last.ts,
        "positions": [
            {
                "ticker": p.ticker,
                "qty": p.qty,
                "avg_price": p.avg_price,
                "market_price": p.market_price,
                "market_value": p.market_value,
            }
            for p in positions
        ],
    }

# ---------------- REPORT (PDF) ----------------
@app.get("/report/pdf", tags=["reports"])
def get_pdf_report():
    filename = "daily_report.pdf"
    db = SessionLocal()
    last = db.query(MetricsDaily).order_by(MetricsDaily.ts.desc()).first()
    positions = db.query(PositionSnapshot).all()
    db.close()

    c = canvas.Canvas(filename, pagesize=letter)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(100, 750, "AI Portfolio Bot — Daily Report")

    y = 700
    if last:
        c.setFont("Helvetica", 12)
        c.drawString(100, y, f"Equity: {last.equity}"); y -= 20
        c.drawString(100, y, f"PnL Day: {last.pnl_day}"); y -= 20
        c.drawString(100, y, f"PnL Total: {last.pnl_total}"); y -= 20
        c.drawString(100, y, f"SPY Benchmark: {last.benchmark_value}"); y -= 40

    c.setFont("Helvetica-Bold", 14)
    c.drawString(100, y, "Positions:"); y -= 20

    for p in positions:
        c.setFont("Helvetica", 10)
        c.drawString(
            100, y,
            f"{p.ticker} | Qty: {p.qty} | Avg: {p.avg_price} | Market: {p.market_price} | Value: {p.market_value}"
        )
        y -= 15
        if y < 100:
            c.showPage()
            y = 700

    c.save()
    return FileResponse(filename, media_type="application/pdf", filename="daily_report.pdf")

# ---------------- SEED TEST DATA ----------------
@app.post("/seed", tags=["debug"])
def seed_data():
    db = SessionLocal()
    db.add(PositionSnapshot(
        ts=datetime.utcnow(), ticker="AAPL", qty=10, avg_price=150.0, market_price=155.0, market_value=1550.0
    ))
    db.add(PositionSnapshot(
        ts=datetime.utcnow(), ticker="TSLA", qty=5, avg_price=700.0, market_price=710.0, market_value=3550.0
    ))
    db.add(MetricsDaily(
        ts=datetime.utcnow(), equity=10000.0, pnl_day=200.0, pnl_total=1200.0,
        benchmark_value=fetch_spy_last_close() or 400.0
    ))
    db.commit()
    db.close()
    return {"status": "seeded"}

# ---------------- AI RECOMMEND ----------------
@app.post("/ai/recommend", tags=["ai"])
def ai_recommend(req: RecommendReq):
    if not client:
        return {
            "strategy": req.strategy,
            "tickers": [],
            "explanation": "OpenAI API key not configured",
            "prices": {}
        }

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "Ты — финансовый аналитик. Верни только JSON с полями: tickers и explanation."},
            {"role": "user", "content": f"Стратегия: {req.strategy}\nЗапрос: {req.prompt}"}
        ],
        response_format={"type": "json_object"}
    )

    parsed = {}
    try:
        parsed = response.choices[0].message.parsed
    except AttributeError:
        raw = response.choices[0].message.content or "{}"
        clean = raw.replace("```json", "").replace("```", "").strip()
        try:
            parsed = json.loads(clean)
        except Exception as e:
            print("Ошибка парсинга JSON:", e)
            parsed = {}

    tickers = [t.strip().upper() for t in parsed.get("tickers", []) if isinstance(t, str)]
    explanation = parsed.get("explanation", "")

    prices = {}
    for ticker in tickers:
        try:
            data = yf.Ticker(ticker).history(period="5d")
            if not data.empty:
                prices[ticker] = round(data["Close"].iloc[-1], 2)
            else:
                prices[ticker] = None
        except Exception:
            prices[ticker] = None

    return {
        "strategy": req.strategy,
        "tickers": tickers,
        "explanation": explanation,
        "prices": prices
    }

# ---------------- DEBUG CONNECTIONS ----------------
@app.get("/debug/connections", tags=["debug"])
def debug_connections():
    results = {}

    # OpenAI
    try:
        if not client:
            results["openai"] = {"ok": False, "msg": "API key not configured"}
        else:
            resp = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": "ping"}]
            )
            parsed = getattr(resp.choices[0].message, "parsed", None)
            content = getattr(resp.choices[0].message, "content", None)
            if parsed:
                results["openai"] = {"ok": True, "mode": "parsed", "sample": parsed}
            elif content:
                results["openai"] = {"ok": True, "mode": "content", "sample": content[:80]}
            else:
                results["openai"] = {"ok": False, "msg": "empty response"}
    except Exception as e:
        results["openai"] = {"ok": False, "error": str(e)}

    # yfinance
    try:
        data = yf.Ticker("AAPL").history(period="5d")
        if not data.empty:
            last_price = float(round(data["Close"].iloc[-1], 2))
            results["yfinance"] = {"ok": True, "AAPL_last_close": last_price}
        else:
            results["yfinance"] = {"ok": False, "msg": "empty dataframe"}
    except Exception as e:
        results["yfinance"] = {"ok": False, "error": str(e)}

    return results
