from __future__ import annotations
from fastapi import FastAPI
from fastapi.responses import JSONResponse, FileResponse
from pydantic import BaseModel
from datetime import datetime
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
import os
import json

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
    weights: list[float] | None = None  # если None — равные доли


# ---------------- HEALTH ----------------
@app.get("/ping")
def ping():
    return {"message": "pong"}


# ---------------- ONBOARD ----------------
@app.post("/onboard")
def onboard(req: OnboardReq):
    db = SessionLocal()
    # Сохраняем единственную запись настроек (простая модель)
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


# ---------------- POSITIONS (исторические снимки для отчётов) ----------------
@app.get("/positions")
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
@app.get("/report/daily")
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
@app.get("/report/pdf")
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
        c.drawString(100, y, f"Equity: {last.equity}")
        y -= 20
        c.drawString(100, y, f"PnL Day: {last.pnl_day}")
        y -= 20
        c.drawString(100, y, f"PnL Total: {last.pnl_total}")
        y -= 20
        c.drawString(100, y, f"SPY Benchmark: {last.benchmark_value}")
        y -= 40

    c.setFont("Helvetica-Bold", 14)
    c.drawString(100, y, "Positions:")
    y -= 20

    for p in positions:
        c.setFont("Helvetica", 10)
        c.drawString(
            100,
            y,
            f"{p.ticker} | Qty: {p.qty} | Avg: {p.avg_price} | Market: {p.market_price} | Value: {p.market_value}",
        )
        y -= 15
        if y < 100:
            c.showPage()
            y = 700

    c.save()
    return FileResponse(filename, media_type="application/pdf", filename="daily_report.pdf")


# ---------------- SEED TEST DATA (для /report/*) ----------------
@app.post("/seed")
def seed_data():
    db = SessionLocal()
    db.add(PositionSnapshot(
        ts=datetime.utcnow(), ticker="AAPL", qty=10, avg_price=150.0, market_price=155.0, market_value=1550.0
    ))
    db.add(PositionSnapshot(
        ts=datetime.utcnow(), ticker="TSLA", qty=5, avg_price=700.0, market_price=710.0, market_value=3550.0
    ))
    db.add(MetricsDaily(
        ts=datetime.utcnow(), equity=10000.0, pnl_day=200.0, pnl_total=1200.0, benchmark_value=fetch_spy_last_close() or 400.0
    ))
    db.commit()
    db.close()
    return {"status": "seeded"}


# ---------------- AI RECOMMEND ----------------
@app.post("/ai/recommend")
def ai_recommend(req: RecommendReq):
    """
    1) Просим LLM выдать строгий JSON (tickers[], explanation)
    2) Подтягиваем цены (yfinance; если не выйдет — вернём None по тикеру)
    """
    if not client:
        # сервис всё равно отвечает — просто без LLM
        return {
            "strategy": req.strategy,
            "tickers": [],
            "explanation": "OpenAI API key not configured on server",
            "prices": {}
        }

    user_prompt = f"""
    Ты финансовый аналитик. Используя стратегию: {req.strategy},
    предложи список из 3–5 тикеров акций (только тикеры без лишнего текста) и объяснение.
    Верни СТРОГО JSON-объект вида:
    {{
      "tickers": ["AAPL","MSFT","NVDA"],
      "explanation": "Краткое объяснение выбора и как стратегия применена"
    }}
    Запрос пользователя: {req.prompt}
    """

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "Ты помощник по инвестициям. Не даёшь инвестиционных советов; это учебный симулятор."},
            {"role": "user", "content": user_prompt}
        ],
        max_tokens=600,
        temperature=0.7,
        response_format={"type": "json_object"},
    )

    # API v1 с response_format даёт готовый JSON-текст в message.content
    raw = response.choices[0].message.content or "{}"
    try:
        parsed = json.loads(raw)
        tickers = [t.strip().upper() for t in parsed.get("tickers", []) if isinstance(t, str)]
        explanation = parsed.get("explanation", "")
    except Exception:
        tickers, explanation = [], raw

    prices = fetch_many_last_close(tickers) if tickers else {}
    return {
        "strategy": req.strategy,
        "tickers": tickers,
        "explanation": explanation,
        "prices": prices
    }


# ---------------- PORTFOLIO: BUILD & VIEW ----------------
@app.post("/portfolio/build")
def build_portfolio(req: BuildReq):
    """
    Создаём виртуальный портфель:
      - если weights не переданы — равные доли
      - qty считается так, чтобы сумма = budget (из UserPref), округляем qty вниз по цене
    """
    db = SessionLocal()
    pref = db.query(UserPref).first()
    budget = float(pref.budget if pref else 10000.0)

    tickers = [t.strip().upper() for t in req.tickers if t.strip()]
    if not tickers:
        db.close()
        return JSONResponse({"error": "tickers is empty"}, status_code=400)

    if req.weights and len(req.weights) == len(tickers):
        weights = req.weights
        s = sum(w for w in weights if w is not None)
        weights = [w / s for w in weights]
    else:
        w = 1.0 / len(tickers)
        weights = [w] * len(tickers)

    # очищаем старые
    db.query(PortfolioHolding).delete()

    prices = fetch_many_last_close(tickers)
    total_alloc_value = 0.0
    rows: list[PortfolioHolding] = []

    # сначала считаем целевые суммы и qty
    for t, w in zip(tickers, weights):
        target_value = budget * w
        price = prices.get(t) or 0.0
        qty = int(target_value // price) if price > 0 else 0
        line_value = qty * price
        total_alloc_value += line_value
        rows.append(PortfolioHolding(ticker=t, weight=w, qty=qty, last_price=price))

    for r in rows:
        r.updated_at = datetime.utcnow()
        db.add(r)
    db.commit()

    out = [
        {"ticker": r.ticker, "weight": r.weight, "qty": r.qty, "last_price": r.last_price}
        for r in db.query(PortfolioHolding).all()
    ]
    db.close()

    return {
        "budget": budget,
        "allocated_value": round(total_alloc_value, 2),
        "uninvested_cash": round(budget - total_alloc_value, 2),
        "holdings": out,
    }

@app.get("/portfolio/holdings")
def get_holdings():
    db = SessionLocal()
    rows = db.query(PortfolioHolding).all()
    db.close()
    return [
        {"ticker": r.ticker, "weight": r.weight, "qty": r.qty, "last_price": r.last_price, "updated_at": r.updated_at}
        for r in rows
    ]
