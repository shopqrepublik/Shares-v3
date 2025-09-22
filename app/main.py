from fastapi import FastAPI
from fastapi.responses import JSONResponse, FileResponse
from pydantic import BaseModel
from app.models import init_db, SessionLocal, PositionSnapshot, MetricsDaily
from datetime import datetime
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
import os
import openai
import yfinance as yf
import json
import re
from openai import OpenAI

# ---------------- INIT ----------------
# DB init
init_db()

# OpenAI init
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
openai.api_key = OPENAI_API_KEY
client = OpenAI(api_key=OPENAI_API_KEY)

# FastAPI app
app = FastAPI(title="AI Portfolio Bot", version="0.7")


# ---------------- SCHEMAS ----------------
class RecommendReq(BaseModel):
    prompt: str
    strategy: str


# ---------------- HEALTH ----------------
@app.get("/ping")
def ping():
    return {"message": "pong"}


# ---------------- POSITIONS ----------------
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


# ---------------- SEED TEST DATA ----------------
@app.post("/seed")
def seed_data():
    db = SessionLocal()
    db.add(PositionSnapshot(
        ts=datetime.utcnow(),
        ticker="AAPL",
        qty=10,
        avg_price=150.0,
        market_price=155.0,
        market_value=1550.0
    ))
    db.add(PositionSnapshot(
        ts=datetime.utcnow(),
        ticker="TSLA",
        qty=5,
        avg_price=700.0,
        market_price=710.0,
        market_value=3550.0
    ))
    db.add(MetricsDaily(
        ts=datetime.utcnow(),
        equity=10000.0,
        pnl_day=200.0,
        pnl_total=1200.0,
        benchmark_value=400.0
    ))
    db.commit()
    db.close()
    return {"status": "seeded"}


# ---------------- AI RECOMMEND ----------------
# ---------------- AI RECOMMEND ----------------
@app.post("/ai/recommend")
def ai_recommend(req: RecommendReq):
    user_prompt = f"""
    Ты финансовый аналитик. Используя стратегию: {req.strategy}, 
    предложи список из 3–5 акций в формате JSON:
    {{
      "tickers": ["AAPL", "MSFT", "NVDA"],
      "explanation": "Краткое объяснение стратегии и выбора"
    }}
    Ответ должен быть строго в JSON!
    Запрос пользователя: {req.prompt}
    """

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "Ты помощник по инвестициям."},
            {"role": "user", "content": user_prompt}
        ],
        max_tokens=600,
        temperature=0.7,
    )

    raw_answer = response.choices[0].message.content or ""

    # Ищем JSON между первой { и последней }
    parsed = {"tickers": [], "explanation": raw_answer}
    try:
        start = raw_answer.find("{")
        end = raw_answer.rfind("}")
        if start != -1 and end != -1:
            json_str = raw_answer[start:end+1]
            parsed = json.loads(json_str)
    except Exception:
        return {
            "strategy": req.strategy,
            "tickers": [],
            "explanation": raw_answer,
            "prices": {}
        }

    # Загружаем цены (берём 5 дней, чтобы всегда было закрытие)
    prices = {}
    for ticker in parsed.get("tickers", []):
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
        "tickers": parsed.get("tickers", []),
        "explanation": parsed.get("explanation", ""),
        "prices": prices
    }

