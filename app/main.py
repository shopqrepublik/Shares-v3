# app/main.py
import os
import math
import time
import json
import httpx
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="WealthAI Simulator API")

# -------------------------
# CORS
# -------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # для prod можно сузить до домена фронта
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -------------------------
# ENV / Config
# -------------------------
API_PASSWORD = os.getenv("API_PASSWORD", "SuperSecret123")

ALPACA_API_KEY = os.getenv("ALPACA_API_KEY", "")
ALPACA_SECRET_KEY = os.getenv("ALPACA_SECRET_KEY", "")
# торговый (account) API
ALPACA_BASE_URL = os.getenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")
# data API (цены/снапшоты)
ALPACA_DATA_URL = os.getenv("ALPACA_DATA_URL", "https://data.alpaca.markets")

HEADERS_ALPACA = {
    "APCA-API-KEY-ID": ALPACA_API_KEY,
    "APCA-API-SECRET-KEY": ALPACA_SECRET_KEY,
}

# -------------------------
# In-memory store (MVP)
# -------------------------
STORE: Dict[str, Any] = {
    "profile": None,     # будет словарь профиля
    "holdings": [],      # список позиций {symbol, shares, price, timestamp}
    "last_build": None,  # мета о последней сборке
}

# -------------------------
# Helpers
# -------------------------
def check_api_key(request: Request):
    api_key = request.headers.get("x-api-key") or request.headers.get("X-API-Key")
    if api_key != API_PASSWORD:
        raise HTTPException(status_code=401, detail="Unauthorized")

def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

async def alpaca_get_json(url: str, headers: Dict[str, str]) -> Dict[str, Any]:
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(url, headers=headers)
    # пытаемся распарсить JSON, если нет — вернём текст
    try:
        data = resp.json()
    except Exception:
        data = {"raw_text": resp.text}
    return {"status_code": resp.status_code, "data": data}

async def fetch_prices_for(symbols: List[str]) -> Dict[str, float]:
    """
    Тянем цены из Alpaca Data API (snapshots).
    Возвращаем dict {symbol: price}.
    """
    if not symbols:
        return {}
    # API ограничивает длину, на MVP — одним чанком до 200 тикеров
    syms = ",".join(symbols[:200])
    url = f"{ALPACA_DATA_URL}/v2/stocks/snapshots?symbols={syms}"

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(url, headers=HEADERS_ALPACA)

    if resp.status_code != 200:
        # на всякий случай — «мягкая» ошибка
        raise HTTPException(status_code=500, detail=f"Alpaca snapshots error {resp.status_code}: {resp.text}")

    data = resp.json()
    prices: Dict[str, float] = {}

    # у Alpaca структура бывает {'snapshots': {SYMBOL: {...}}} либо просто {SYMBOL:{...}}
    payload = data.get("snapshots", data)

    for sym, snap in payload.items():
        # пытаемся взять askPrice (latestQuote.ap) или последнюю цену трейда (latestTrade.p)
        price = None
        try:
            price = snap.get("latestQuote", {}).get("ap")
        except Exception:
            pass
        if not price:
            try:
                price = snap.get("latestTrade", {}).get("p")
            except Exception:
                pass
        # запасной вариант — close из minute/prevDaily (если вернулся)
        if not price:
            try:
                price = snap.get("prevDailyBar", {}).get("c")
            except Exception:
                pass

        # фильтр
        if price and isinstance(price, (int, float)) and price > 0:
            prices[sym] = float(price)

    return prices

def portfolio_template_by_risk(risk_level: str, micro_caps: bool) -> Dict[str, float]:
    """
    Базовые веса по риску (ETF + крупные техи).
    micro_caps=True добавляет малую долю IWM (small caps ETF) вместо «настоящих microcap».
    """
    risk = (risk_level or "").lower()
    weights: Dict[str, float] = {}

    if risk in ("conservative", "консервативный"):
        weights = {
            "SPY": 0.40,
            "BND": 0.30,   # облигации (Vanguard Total Bond)
            "QQQ": 0.10,
            "AAPL": 0.07,
            "MSFT": 0.07,
            "VTI": 0.06,   # total market
        }
    elif risk in ("aggressive", "агрессивный"):
        weights = {
            "QQQ": 0.25,
            "NVDA": 0.15,
            "AAPL": 0.12,
            "MSFT": 0.12,
            "GOOGL": 0.10,
            "AMZN": 0.10,
            "META": 0.08,
            "TSLA": 0.08,
        }
    else:  # balanced / сбалансированный
        weights = {
            "SPY": 0.25,
            "QQQ": 0.15,
            "VTI": 0.10,
            "AAPL": 0.12,
            "MSFT": 0.12,
            "GOOGL": 0.10,
            "AMZN": 0.08,
            "META": 0.08,
        }

    if micro_caps:
        # вместо настоящих microcap (для надёжности котировок) — добавим small-caps ETF
        # берём 5% из SPY (или из крупнейшего веса)
        take_from = max(weights, key=weights.get)
        delta = min(0.05, weights[take_from] * 0.25)
        weights[take_from] -= delta
        weights["IWM"] = delta

    # нормализация до 1.0 (на всякий)
    total = sum(weights.values()) or 1.0
    return {k: v / total for k, v in weights.items()}

def allocate_shares(budget: float, weights: Dict[str, float], prices: Dict[str, float]) -> List[Dict[str, Any]]:
    """
    Раскладываем бюджет по весам, считаем целые лоты.
    """
    now = utc_now_iso()
    result: List[Dict[str, Any]] = []
    cash_left = budget

    # сначала в порядке убывания веса, чтобы бОльшие доли получили шанс на округление
    for sym, w in sorted(weights.items(), key=lambda x: x[1], reverse=True):
        price = prices.get(sym)
        if not price:
            continue
        target_amount = budget * w
        shares = int(target_amount // price)  # целые лоты
        if shares <= 0:
            continue
        amount = shares * price
        cash_left -= amount
        result.append({
            "symbol": sym,
            "shares": shares,
            "price": round(float(price), 4),
            "timestamp": now
        })

    # если остался ощутимый кэш — докупим по крупнейшему ETF (SPY/QQQ/VTI)
    if cash_left > 0:
        for pick in ("SPY", "QQQ", "VTI"):
            p = prices.get(pick)
            if p and cash_left >= p:
                extra = int(cash_left // p)
                if extra > 0:
                    result.append({
                        "symbol": pick,
                        "shares": extra,
                        "price": round(float(p), 4),
                        "timestamp": now
                    })
                    cash_left -= extra * p
                    break

    return result

# -------------------------
# Healthcheck (без ключа)
# -------------------------
@app.get("/ping")
async def ping():
    return {"message": "pong"}

# -------------------------
# Onboarding (protected)
# -------------------------
@app.post("/onboard")
async def onboard(request: Request):
    check_api_key(request)
    body = await request.json()
    profile = {
        "budget": float(body.get("budget", 5000)),
        "risk_level": body.get("risk_level") or body.get("risk") or "balanced",
        "goals": body.get("goals", "growth"),
        "micro_caps": bool(body.get("micro_caps", False)),
        "horizon": body.get("horizon", "6m"),       # 3m / 6m / 12m
        "knowledge": body.get("knowledge", "basic") # basic / advanced
    }
    STORE["profile"] = profile
    return {"status": "ok", "profile": profile}

# -------------------------
# Build portfolio (protected)
# -------------------------
@app.post("/portfolio/build")
async def portfolio_build(request: Request):
    check_api_key(request)
    body = await request.json()

    # профиль берём из STORE, но разрешаем override полями из body
    profile = STORE.get("profile") or {}
    budget = float(body.get("budget", profile.get("budget", 5000)))
    risk_level = (body.get("risk_level") or body.get("risk") or profile.get("risk_level") or "balanced")
    micro_caps = bool(body.get("micro_caps", profile.get("micro_caps", False)))

    # подбираем базовые веса
    weights = portfolio_template_by_risk(risk_level, micro_caps)

    # получаем цены
    symbols = list(weights.keys())
    prices = await fetch_prices_for(symbols)

    # если какого-то символа нет в снапшоте — исключим из весов
    available = {s: w for s, w in weights.items() if s in prices}
    total_w = sum(available.values()) or 1.0
    norm_weights = {s: w / total_w for s, w in available.items()}

    # считаем лоты
    positions = allocate_shares(budget, norm_weights, prices)

    STORE["holdings"] = positions
    STORE["last_build"] = {
        "budget": budget,
        "risk_level": risk_level,
        "micro_caps": micro_caps,
        "built_at": utc_now_iso()
    }

    return {
        "status": "ok",
        "input": {"budget": budget, "risk_level": risk_level, "micro_caps": micro_caps},
        "data": positions  # контракт как в ТЗ для /portfolio/holdings
    }

# -------------------------
# Holdings (protected)
# -------------------------
@app.get("/portfolio/holdings")
async def portfolio_holdings(request: Request):
    check_api_key(request)
    return {"data": STORE.get("holdings", [])}

# -------------------------
# Alpaca utils (без ключа — для отладки)
# -------------------------
@app.get("/alpaca/test")
async def alpaca_test():
    url = f"{ALPACA_BASE_URL}/v2/account"
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(url, headers=HEADERS_ALPACA)
    try:
        data = resp.json()
    except Exception:
        data = {"raw_text": resp.text}
    return {
        "status_code": resp.status_code,
        "url": url,
        "headers_used": {
            "APCA-API-KEY-ID": (ALPACA_API_KEY[:4] + "****") if ALPACA_API_KEY else None,
            "APCA-API-SECRET-KEY": (ALPACA_SECRET_KEY[:4] + "****") if ALPACA_SECRET_KEY else None,
        },
        "data": data,
    }

@app.get("/alpaca/positions")
async def alpaca_positions():
    url = f"{ALPACA_BASE_URL}/v2/positions"
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(url, headers=HEADERS_ALPACA)
    try:
        data = resp.json()
    except Exception:
        data = {"raw_text": resp.text}
    return {
        "status_code": resp.status_code,
        "url": url,
        "data": data,
    }
