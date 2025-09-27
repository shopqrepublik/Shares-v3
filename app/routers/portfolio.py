from fastapi import APIRouter, Query
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta, timezone
from math import floor
import logging, os, requests

import yfinance as yf
import pandas as pd
import numpy as np
from sklearn.linear_model import LinearRegression

log = logging.getLogger(__name__)

router = APIRouter(prefix="/portfolio", tags=["portfolio"])

# -----------------------------
# МОДЕЛИ ОТВЕТА
# -----------------------------
class HoldingOut(BaseModel):
    symbol: str
    shares: float
    price: float
    timestamp: str
    score: Optional[float] = None

class HoldingsResponse(BaseModel):
    data: List[HoldingOut]

# -----------------------------
# In-memory хранилище
# -----------------------------
CURRENT_HOLDINGS: List[Dict[str, Any]] = []

# -----------------------------
# Нормализация к фронтовому контракту
# -----------------------------
def normalize_to_front_contract(raw: Any) -> List[Dict[str, Any]]:
    if raw is None:
        items = []
    elif isinstance(raw, list):
        items = raw
    elif isinstance(raw, dict):
        items = raw.get("data", []) or raw.get("holdings", []) or list(raw.values())
    else:
        items = []

    out: List[Dict[str, Any]] = []
    for h in items:
        out.append({
            "symbol": str(h.get("symbol") or h.get("ticker") or "UNKNOWN"),
            "shares": float(h.get("shares", h.get("qty", 0)) or 0),
            "price": float(h.get("price", h.get("market_price", 0.0)) or 0.0),
            "timestamp": str(h.get("timestamp") or h.get("ts") or datetime.utcnow().isoformat()),
            "score": float(h.get("score")) if h.get("score") is not None else None
        })
    return out

# -----------------------------
# Вспомогательные функции
# -----------------------------
ALPACA_API_KEY = os.getenv("ALPACA_API_KEY")
ALPACA_API_SECRET = os.getenv("ALPACA_API_SECRET")
ALPACA_API_URL = "https://paper-api.alpaca.markets"
FMP_API_KEY = os.getenv("FMP_API_KEY")

def get_assets(limit=200):
    """Список активов с Alpaca (ограничим 200 для MVP)."""
    try:
        r = requests.get(f"{ALPACA_API_URL}/v2/assets", headers={
            "APCA-API-KEY-ID": ALPACA_API_KEY,
            "APCA-API-SECRET-KEY": ALPACA_API_SECRET
        }, timeout=20)
        r.raise_for_status()
        assets = r.json()
        syms = [a["symbol"] for a in assets if a["tradable"] and a["status"]=="active"]
        return syms[:limit]
    except Exception as e:
        log.warning("Assets fetch failed: %s", e)
        return ["AAPL","MSFT","SPY","QQQ"]  # fallback

def get_mktcap(symbol):
    try:
        url = f"https://financialmodelingprep.com/api/v3/profile/{symbol}?apikey={FMP_API_KEY}"
        r = requests.get(url, timeout=10)
        data = r.json()
        if isinstance(data, list) and len(data)>0:
            return data[0].get("mktCap",0)
    except Exception:
        return 0
    return 0

def forecast_linear(df: pd.DataFrame, days=30):
    if df.empty: return 0
    closes = df["Close"].values
    if len(closes) < 20: return 0
    X = np.arange(len(closes)).reshape(-1,1)
    y = closes
    model = LinearRegression().fit(X,y)
    future_x = np.arange(len(closes), len(closes)+days).reshape(-1,1)
    preds = model.predict(future_x)
    return (preds[-1] - closes[-1]) / closes[-1]

def detect_pattern(df: pd.DataFrame):
    if len(df)<2: return 0
    prev, last = df.iloc[-2], df.iloc[-1]
    if (last["Close"]>last["Open"] and prev["Close"]<prev["Open"] 
        and last["Close"]>prev["Open"] and last["Open"]<prev["Close"]):
        return 1
    return 0

# -----------------------------
# /holdings
# -----------------------------
@router.get("/holdings", response_model=HoldingsResponse)
def get_holdings():
    return {"data": normalize_to_front_contract({"data": CURRENT_HOLDINGS})}

# -----------------------------
# /build
# -----------------------------
class BuildRequest(BaseModel):
    budget: float = 1000.0
    risk_level: str = "medium"
    micro_caps: bool = False

@router.post("/build", response_model=HoldingsResponse)
def build_portfolio(body: Optional[BuildRequest] = None):
    global CURRENT_HOLDINGS

    budget_val = float(body.budget if body else 1000.0)

    symbols = get_assets(limit=100)
    scored = []

    for sym in symbols:
        try:
            df = yf.download(sym, period="6mo", interval="1d", progress=False)
            if df.empty: continue
            mom = (df["Close"].iloc[-1] / df["Close"].iloc[max(0,-60)]) - 1
            vol_spike = df["Volume"].iloc[-1] / df["Volume"].tail(20).mean()
            forecast = forecast_linear(df, days=30)
            pattern = detect_pattern(df)
            score = 0.4*mom + 0.2*vol_spike + 0.3*forecast + 0.1*pattern
            scored.append((sym, score, df["Close"].iloc[-1]))
        except Exception:
            continue

    top = sorted(scored, key=lambda x:x[1], reverse=True)[:5]

    holdings: List[Dict[str,Any]] = []
    now_iso = datetime.now(timezone.utc).isoformat()
    per_bucket = budget_val/max(1,len(top))

    for sym,score,px in top:
        qty = floor(per_bucket/px) if px>0 else 0
        if qty<=0: qty=1
        holdings.append({
            "symbol": sym,
            "shares": float(qty),
            "price": float(px),
            "timestamp": now_iso,
            "score": score
        })

    CURRENT_HOLDINGS = holdings
    return {"data": holdings}

# -----------------------------
# /track (оставляем как было)
# -----------------------------
@router.get("/track")
def track_portfolio(symbols: str, benchmark: str="SPY", days: int=365):
    tickers = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    end = datetime.utcnow()
    start = end - timedelta(days=days)

    data = yf.download(tickers+[benchmark], start=start.date(), end=end.date(), progress=False)["Adj Close"]
    data = data.fillna(method="ffill")
    rel = (data / data.iloc[0] - 1.0)

    return {
        "portfolio": {t: round(float(rel[t].iloc[-1]),6) for t in tickers},
        "benchmark": {benchmark: round(float(rel[benchmark].iloc[-1]),6)},
        "last_date": str(data.index[-1].date())
    }
