from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel
from dotenv import load_dotenv
import os
from typing import List

from alpaca.trading.client import TradingClient

from app.guardrails import rebalance_with_guardrails, RailConfig
from .models import init_db
from .reporting import snapshot_positions, log_daily_metrics

# Load env
load_dotenv()

app = FastAPI(title="AI Portfolio Bot", version="1.2.0")

# DB init
init_db()

# Alpaca client
ALPACA_KEY = os.getenv("PKVT34KMH6EOKGFR0MAN")
ALPACA_SECRET = os.getenv("9ziJkgjcvjCv07ASbccfbfOh3gcAj4V4oyd8mL3V")
ALPACA_BASE = os.getenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")
BENCHMARK = os.getenv("BENCHMARK", "SPY")

trading = None
if ALPACA_KEY and ALPACA_SECRET:
    trading = TradingClient(ALPACA_KEY, ALPACA_SECRET, paper="paper" in ALPACA_BASE)


# ===== Root & healthcheck =====
@app.get("/")
def root():
    return {"message": "✅ AI Portfolio Bot is running. Go to /docs for Swagger UI."}

@app.get("/ping")
def ping():
    return {"status": "ok"}


# ===== Models =====
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


# ===== Endpoints =====
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
    # ⚠️ пока ещё yfinance; позже заменим Alpaca Market Data
    import yfinance as yf
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
    try:
        snapshot_positions(trading)
        log_daily_metrics(trading, BENCHMARK)
    except Exception:
        pass
    return result


@app.get("/positions")
def positions():
    """Текущие позиции в Alpaca"""
    if trading is None:
        raise HTTPException(400, "Trading client not configured")
    pos = trading.get_all_positions()
    return [
        {
            "ticker": p.symbol,
            "qty": float(p.qty),
            "avg_price": float(p.avg_entry_price),
            "market_price": float(p.current_price),
            "market_value": float(p.market_value),
            "unrealized_pl": float(p.unrealized_pl),
        }
        for p in pos
    ]


@app.get("/report/daily")
def daily_report():
    """Сводка: equity, PnL, сравнение с бенчмарком"""
    if trading is None:
        raise HTTPException(400, "Trading client not configured")
    acct = trading.get_account()
    equity = float(acct.equity)
    cash = float(acct.cash)
    pnl_day = float(acct.equity) - float(acct.last_equity)

    # Benchmark (SPY) через yfinance; позже заменим Alpaca Market Data
    import yfinance as yf
    bm = yf.Ticker(BENCHMARK).history(period="ytd")["Close"].pct_change().add(1).cumprod()
    bm_return = (bm.iloc[-1] - 1) * 100 if not bm.empty else 0.0

    return {
        "equity": equity,
        "cash": cash,
        "pnl_day": pnl_day,
        "benchmark": BENCHMARK,
        "benchmark_ytd_return_pct": bm_return,
    }
