from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel
from dotenv import load_dotenv
import os
import yfinance as yf
from typing import List

from alpaca.trading.client import TradingClient

from .guardrails import rebalance_with_guardrails, RailConfig
from .models import init_db
from .reporting import snapshot_positions, log_daily_metrics

# Load env
load_dotenv()

app = FastAPI(title="AI Portfolio Bot", version="1.1.0")

# DB init
init_db()

# Alpaca client
ALPACA_KEY = os.getenv("ALPACA_API_KEY")
ALPACA_SECRET = os.getenv("ALPACA_SECRET_KEY")
ALPACA_BASE = os.getenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")
BENCHMARK = os.getenv("BENCHMARK", "SPY")

trading = None
if ALPACA_KEY and ALPACA_SECRET:
    trading = TradingClient(ALPACA_KEY, ALPACA_SECRET, paper="paper" in ALPACA_BASE)

@app.get("/")
def root():
    return {"message": "✅ AI Portfolio Bot is running. Go to /docs for Swagger UI."}

@app.get("/ping")
def ping():
    return {"status": "ok"}

class OnboardReq(BaseModel):
    budget_usd: float
    horizon_months: int
    risk_level: int
    allow_microcap: bool = False

class AllocationItem(BaseModel):
    ticker: str
    target_weight: float

class Proposal(BaseModel):
    allocations: List[AllocationItem]

@app.post("/onboard")
def onboard(req: OnboardReq):
    core = [("SPY", 0.60), ("IXUS", 0.20), ("AGG", 0.10)]
    growth = [("QQQ", 0.10)]
    micro = [("ABEO", 0.0), ("CALA", 0.0)] if req.allow_microcap else []

    if req.risk_level >= 4:
        core = [("SPY", 0.50), ("IXUS", 0.20), ("AGG", 0.00)]
        growth = [("QQQ", 0.20), ("VGT", 0.10)]

    alloc = core + growth + micro
    s = sum(w for _, w in alloc)
    alloc = [(t, w / s) for t, w in alloc]

    return Proposal(allocations=[AllocationItem(ticker=t, target_weight=w) for t, w in alloc])

@app.get("/price/{ticker}")
def price(ticker: str):
    info = yf.Ticker(ticker)
    hist = info.history(period="1mo")
    if hist.empty:
        raise HTTPException(404, "No data")
    last = float(hist["Close"].iloc[-1])
    return {"ticker": ticker, "last": last}

@app.post("/rebalance")
def rebalance(p: Proposal, budget: float = Query(..., gt=0), submit: bool = Query(False)):
    if trading is None:
        return {"ok": False, "errors": ["Trading client is not configured (missing API keys)."], "preview": {}}
    allocations = [dict(ticker=a.ticker, target_weight=a.target_weight) for a in p.allocations]
    result = rebalance_with_guardrails(trading, allocations, budget, submit, RailConfig())
    # Take snapshot & metrics after successful place or always preview
    try:
        snapshot_positions(trading)
        log_daily_metrics(trading, BENCHMARK)
    except Exception:
        pass
    return result
