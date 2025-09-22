from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from dotenv import load_dotenv
import os
import yfinance as yf
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce

load_dotenv()

app = FastAPI(title="AI Portfolio Bot")

ALPACA_KEY = os.getenv("ALPACA_API_KEY")
ALPACA_SECRET = os.getenv("ALPACA_SECRET_KEY")
ALPACA_BASE = os.getenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")

trading = None
if ALPACA_KEY and ALPACA_SECRET:
    trading = TradingClient(ALPACA_KEY, ALPACA_SECRET, paper="paper" in ALPACA_BASE)

class OnboardReq(BaseModel):
    budget_usd: float
    horizon_months: int
    risk_level: int
    allow_microcap: bool = False

class AllocationItem(BaseModel):
    ticker: str
    target_weight: float

class Proposal(BaseModel):
    allocations: list[AllocationItem]

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
def rebalance(p: Proposal, budget: float):
    orders = []
    for item in p.allocations:
        last = float(yf.Ticker(item.ticker).history(period="5d")["Close"].iloc[-1])
        target_value = budget * item.target_weight
        qty = int(target_value // last)
        if qty <= 0:
            continue
        req = MarketOrderRequest(
            symbol=item.ticker,
            qty=qty,
            side=OrderSide.BUY,
            time_in_force=TimeInForce.DAY,
        )
        # Uncomment below after adding guardrails
        # order = trading.submit_order(req)
        orders.append({"ticker": item.ticker, "qty": qty, "est_cost": qty * last})
    return {"preview": orders, "note": "Validate with guardrails before submit_order"}
