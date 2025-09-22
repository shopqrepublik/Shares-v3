from fastapi import FastAPI
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import List, Dict
import requests
import os
from datetime import datetime
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

# Alpaca credentials
ALPACA_KEY = os.getenv("ALPACA_API_KEY")
ALPACA_SECRET = os.getenv("ALPACA_SECRET_KEY")
ALPACA_BASE_URL = "https://paper-api.alpaca.markets"
ALPACA_DATA_URL = "https://data.alpaca.markets/v2"

HEADERS = {
    "APCA-API-KEY-ID": ALPACA_KEY,
    "APCA-API-SECRET-KEY": ALPACA_SECRET,
}

app = FastAPI(title="AI Portfolio Bot", version="0.3")


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
        "date": datetime.utcnow().isoformat(),
        "equity": account.get("equity"),
        "cash": account.get("cash"),
        "pnl_day": account.get("daytrading_buying_power"),
        "pnl_total": account.get("unrealized_pl"),
        "benchmark": {"ticker": "SPY", "last_price": spy.get("quote", {}).get("ap")},
    }


@app.get("/report/pdf")
def get_pdf_report():
    """Generate and return PDF report"""
    account_url = f"{ALPACA_BASE_URL}/v2/account"
    account = requests.get(account_url, headers=HEADERS).json()

    spy_url = f"{ALPACA_DATA_URL}/stocks/SPY/quotes/latest"
    spy = requests.get(spy_url, headers=HEADERS).json()

    filename = "/tmp/daily_report.pdf"
    c = canvas.Canvas(filename, pagesize=letter)
    c.setFont("Helvetica", 12)

    c.drawString(50, 750, "AI Portfolio Bot — Daily Report")
    c.drawString(50, 730, f"Date: {datetime.utcnow().isoformat()}")
    c.drawString(50, 710, f"Equity: {account.get('equity')}")
    c.drawString(50, 690, f"Cash: {account.get('cash')}")
    c.drawString(50, 670, f"PnL Today: {account.get('daytrading_buying_power')}")
    c.drawString(50, 650, f"PnL Total: {account.get('unrealized_pl')}")
    c.drawString(50, 630, f"SPY Price: {spy.get('quote', {}).get('ap')}")

    c.showPage()
    c.save()

    return FileResponse(filename, media_type="application/pdf", filename="daily_report.pdf")
