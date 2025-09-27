from fastapi import APIRouter
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta, timezone
from math import floor
import logging, os, requests
import numpy as np
import pandas as pd
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
# Alpaca API конфиг
# -----------------------------
ALPACA_API_KEY = os.getenv("ALPACA_API_KEY")
ALPACA_API_SECRET = os.getenv("ALPACA_API_SECRET")
ALPACA_API_URL = "https://paper-api.alpaca.markets"
ALPACA_DATA_URL = "https://data.alpaca.markets/v2"

# -----------------------------
# Вспомогательные функции
# -----------------------------
def get_assets(limit=200):
    """Берем список активов с Alpaca (ограничим для MVP)."""
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

def get_bars(symbol: str, days: int = 180):
    """Загрузка дневных баров через Alpaca Market Data API v2"""
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)
    url = f"{ALPACA_DATA_URL}/stocks/{symbol}/bars"
    params = {
        "timeframe": "1Day",
        "start": start.isoformat(),
        "end": end.isoformat(),
        "limit": days
    }
    r = requests.get(url, headers={
        "APCA-API-KEY-ID": ALPACA_API_KEY,
        "APCA-API-SECRET-KEY": ALPACA_API_SECRET
    }, params=params, timeout=20)
    if r.status_code != 200:
        return []
    return r.json().get("bars", [])

def compute_metrics(bars: list):
    if not bars or len(bars) < 20:
        return None
    
    df = pd.DataFrame(bars)
    df["t"] = pd.to_datetime(df["t"])
    df.set_index("t", inplace=True)

    # Momentum (3 месяца ~ 60 дней)
    mom = (df["c"].iloc[-1] / df["c"].iloc[-60]) - 1 if len(df) > 60 else 0

    # Volume spike
    vol_spike = df["v"].iloc[-1] / df["v"].tail(20).mean()

    # Forecast (линейная регрессия на последних N дней)
    closes = df["c"].values
    X = np.arange(len(closes)).reshape(-1, 1)
    y = closes
    model = LinearRegression().fit(X, y)
    future_x = np.arange(len(closes), len(closes)+30).reshape(-1, 1)
    preds = model.predict(future_x)
    forecast = (preds[-1] - closes[-1]) / closes[-1]

    # Простейший паттерн (Bullish Engulfing)
    pattern = 0
    if len(df) >= 2:
        prev, last = df.iloc[-2], df.iloc[-1]
        if (last["c"] > last["o"] and prev["c"] < prev["o"] 
            and last["c"] > prev["o"] and last["o"] < prev["c"]):
            pattern = 1

    return {
        "momentum": mom,
        "vol_spike": vol_spike,
        "forecast": forecast,
        "pattern": pattern,
        "last_price": df["c"].iloc[-1]
    }

# -----------------------------
# /holdings
# -----------------------------
@router.get("/holdings", response_model=HoldingsResponse)
def get_holdings():
    return {"data": CURRENT_HOLDINGS}

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

    symbols = get_assets(limit=50)  # ограничим 50 для скорости
    scored = []

    for sym in symbols:
        try:
            bars = get_bars(sym, days=180)
            metrics = compute_metrics(bars)
            if not metrics:
                continue
            score = (0.4*metrics["momentum"] 
                     + 0.2*metrics["vol_spike"] 
                     + 0.3*metrics["forecast"] 
                     + 0.1*metrics["pattern"])
            scored.append((sym, score, metrics["last_price"]))
        except Exception as e:
            log.warning("Metrics failed for %s: %s", sym, e)
            continue

    # Берем top-5
    top = sorted(scored, key=lambda x:x[1], reverse=True)[:5]

    holdings: List[Dict[str,Any]] = []
    now_iso = datetime.now(timezone.utc).isoformat()
    per_bucket = budget_val / max(1, len(top))

    for sym,score,px in top:
        qty = floor(per_bucket/px) if px>0 else 0
        if qty <= 0: qty = 1
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
# /track (пока через Alpaca bars для SPY и тикеров)
# -----------------------------
@router.get("/track")
def track_portfolio(symbols: str, benchmark: str="SPY", days: int=365):
    tickers = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    tickers.append(benchmark)

    rel = {}
    last_date = None

    for sym in tickers:
        bars = get_bars(sym, days=days)
        df = pd.DataFrame(bars)
        if df.empty: 
            continue
        df["t"] = pd.to_datetime(df["t"])
        df.set_index("t", inplace=True)
        df = df[["c"]]
        df = df.rename(columns={"c": sym})
        if last_date is None and not df.empty:
            last_date = str(df.index[-1].date())
        if sym not in rel:
            rel[sym] = (df[sym].iloc[-1] / df[sym].iloc[0]) - 1

    return {
        "portfolio": {t: float(rel[t]) for t in tickers if t!=benchmark and t in rel},
        "benchmark": {benchmark: float(rel[benchmark]) if benchmark in rel else 0.0},
        "last_date": last_date
    }
