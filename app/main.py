from fastapi import FastAPI
from pydantic import BaseModel
from typing import List, Dict
import requests
import os

# Alpaca credentials
ALPACA_KEY = os.getenv("ALPACA_API_KEY")
ALPACA_SECRET = os.getenv("ALPACA_SECRET_KEY")
ALPACA_BASE_URL = "https://paper-api.alpaca.markets"
ALPACA_DATA_URL = "https://data.alpaca.markets/v2"

HEADERS = {
    "APCA-API-KEY-ID": ALPACA_KEY,
    "APCA-API-SECRET-KEY": ALPACA_SECRET,
}

app = FastAPI(title="AI Portfolio Bot", version="0.2")


# -----------------------
# Schemas
# -----------------------
class AllocationItem(BaseModel):
    ticker: str
    weight: float


class Proposal(BaseModel):
    allocations: List[Dict]
    comment: str


class OnboardReq(BaseModel):
    budget_usd: float
    horizon_months: int
    risk_level: int
    allow_microcap: bool


# -----------------------
# Endpoints
# -----------------------
@app.get("/ping")
def ping():
    return {"status": "ok"}


@app.get("/positions")
def get_positions():
    """Fetch current positions from Alpaca"""
    url = f"{ALPACA_BASE_URL}/v2/positions"
    r = requests.get(url, headers=HEADERS)
    if r.status_code != 200:
        return {"error": r.json()}
    return r.json()


@app.get("/report/daily")
def get_daily_report():
    """Return JSON summary: equity, PnL day/total, SPY comparison"""
    account_url = f"{ALPACA_BASE_URL}/v2/account"
    account = requests.get(account_url, headers=HEADERS).json()

    spy_url = f"{ALPACA_DATA_URL}/stocks/SPY/quotes/latest"
    spy = requests.get(spy_url, headers=HEADERS).json()

    return {
        "equity": account.get("equity"),
        "pnl_day": account.get("daytrading_buying_power"),  # можно заменить на pnl_today
        "pnl_total": account.get("unrealized_pl"),
        "benchmark": {"ticker": "SPY", "last_price": spy.get("quote", {}).get("ap")},
    }
