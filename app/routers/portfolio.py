# Shares-v3/app/routers/portfolio.py

from fastapi import APIRouter, Query
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from math import floor

import yfinance as yf
import pandas as pd  # остается для /track

router = APIRouter(prefix="/portfolio", tags=["portfolio"])

# -----------------------------
# МОДЕЛИ, КОТОРЫЕ ЖДЁТ ФРОНТ
# -----------------------------
class HoldingOut(BaseModel):
    symbol: str
    shares: float
    price: float
    timestamp: str

class HoldingsResponse(BaseModel):
    data: List[HoldingOut]


# -----------------------------
# ПРОСТОЕ ХРАНИЛИЩЕ В ПАМЯТИ
# (для прототипа; на проде заменить БД)
# -----------------------------
CURRENT_HOLDINGS: List[Dict[str, Any]] = []  # всегда список dict


# -----------------------------
# ВСПОМОГАТЕЛЬНОЕ: НОРМАЛИЗАЦИЯ В ЕДИНЫЙ КОНТРАКТ
# Принимаем всё что угодно и приводим к [{"symbol","shares","price","timestamp"}]
# -----------------------------
def normalize_to_front_contract(raw: Any) -> List[Dict[str, Any]]:
    # 1) извлечь список "сырых" позиций
    if raw is None:
        items = []
    elif isinstance(raw, list):
        items = raw
    elif isinstance(raw, dict):
        if isinstance(raw.get("data"), list):
            items = raw["data"]
        elif isinstance(raw.get("holdings"), list):
            items = raw["holdings"]
        else:
            # Возможно формат {"AAPL": {...}, "MSFT": {...}}
            items = list(raw.values())
    else:
        items = []

    # 2) замапить поля под фронт
    out: List[Dict[str, Any]] = []
    for h in items:
        symbol = (h.get("symbol") or h.get("ticker") or h.get("code") or "UNKNOWN")
        shares = h.get("shares", h.get("qty", 0)) or 0
        price = h.get("price", h.get("market_price", 0.0)) or 0.0
        ts = h.get("timestamp") or h.get("ts") or datetime.utcnow().isoformat()
        out.append({
            "symbol": str(symbol),
            "shares": float(shares),
            "price": float(price),
            "timestamp": str(ts),
        })
    return out


# -----------------------------
# ВСПОМОГАТЕЛЬНОЕ: ПОЛУЧИТЬ ЦЕНУ
# -----------------------------
def get_last_price(symbol: str) -> float:
    try:
        hist = yf.Ticker(symbol).history(period="1d")
        if hist is not None and not hist.empty:
            return float(hist["Close"].iloc[-1])
    except Exception:
        pass
    # если не удалось — 0.0 (фронт покажет $0.00, но не упадёт)
    return 0.0


# -----------------------------
# ЭНДПОИНТ: ПРОЧИТАТЬ ТЕКУЩИЕ ПОЗИЦИИ (ЕДИНЫЙ КОНТРАКТ)
# Фронт ожидает именно этот формат.
# -----------------------------
@router.get("/holdings", response_model=HoldingsResponse)
def get_holdings():
    # CURRENT_HOLDINGS уже должен быть в целевом формате;
    # однако на всякий случай – нормализуем.
    data = normalize_to_front_contract({"data": CURRENT_HOLDINGS})
    return {"data": data}


# -----------------------------
# ЭНДПОИНТ: СФОРМИРОВАТЬ ПОРТФЕЛЬ (BUILD)
# Собирает портфель по риск-профилю и бюджету и сохраняет его в память.
# -----------------------------
class BuildRequest(BaseModel):
    budget: float = 1000.0
    risk_level: str = "medium"   # допустимые: low/medium/high
    micro_caps: bool = False

# Карты риск-профиля и micro-доли (можно расширять)
RISK_BUCKETS = {
    "low":    [("SPY", 0.6), ("BND", 0.4)],
    "medium": [("VOO", 0.4), ("AAPL", 0.3), ("MSFT", 0.3)],
    "high":   [("TSLA", 0.34), ("NVDA", 0.33), ("AMD", 0.33)],
}
MICRO_POOL = ["IWM", "ARKK", "SOXL", "TQQQ"]  # для примера
MICRO_SHARE_BY_RISK = {"low": 0.05, "medium": 0.10, "high": 0.20}

@router.post("/build", response_model=HoldingsResponse)
def build_portfolio(
    body: Optional[BuildRequest] = None,
    # на случай, если фронт шлёт risk в query (обратная совместимость)
    risk: Optional[str] = Query(None, description="low|medium|high"),
    budget: Optional[float] = Query(None, description="budget override")
):
    global CURRENT_HOLDINGS

    risk_level = (risk or (body.risk_level if body else "medium")).lower()
    budget_val = float(budget if budget is not None else (body.budget if body else 1000.0))
    micro_caps = bool(body.micro_caps) if body and body.micro_caps is not None else False

    # 1) базовые веса по риск-профилю
    pairs = RISK_BUCKETS.get(risk_level, RISK_BUCKETS["medium"])[:]  # copy

    # 2) учесть micro_caps
    micro_share = MICRO_SHARE_BY_RISK.get(risk_level, 0.10) if micro_caps else 0.0
    if micro_share > 0:
        # уменьшить веса базового ядра пропорционально
        pairs = [(sym, w * (1.0 - micro_share)) for sym, w in pairs]
        # равномерно распределить долю micro между MICRO_POOL
        micro_w = micro_share / len(MICRO_POOL)
        pairs += [(sym, micro_w) for sym in MICRO_POOL]

    # 3) посчитать лоты и цены
    holdings: List[Dict[str, Any]] = []
    now_iso = datetime.utcnow().isoformat()
    for sym, w in pairs:
        price = get_last_price(sym)
        alloc_amount = budget_val * w
        qty = floor(alloc_amount / price) if price > 0 else 0
        if qty > 0:
            holdings.append({
                "symbol": sym,
                "shares": float(qty),
                "price": float(price),
                "timestamp": now_iso
            })

    # 4) сохранить «текущий портфель» (для /holdings)
    CURRENT_HOLDINGS = holdings

    # 5) вернуть фронту в ЕДИНОМ ФОРМАТЕ
    return {"data": holdings}


# -----------------------------
# СТАРЫЙ ЭНДПОИНТ /generate
# Оставляем для обратной совместимости: возвращает allocation (веса).
# Фронту для Portfolio он НЕ нужен, но может пригодиться тебе отдельно.
# -----------------------------
class PortfolioRequest(BaseModel):
    budget: float
    risk_profile: str
    micro_caps: bool = False

@router.post("/generate")
def generate_portfolio(req: PortfolioRequest):
    etf_core = ["SPY", "QQQ", "VXUS", "IEF"]
    micro_pool = ["IBIT", "SOXL", "TQQQ", "IWM", "ARKK"]
    weights = {"SPY": 0.35, "QQQ": 0.25, "VXUS": 0.20, "IEF": 0.20}

    micro_share = 0.0
    if req.micro_caps:
        micro_share = {"conservative": 0.05, "balanced": 0.10, "aggressive": 0.20}.get(req.risk_profile, 0.10)
        for k in weights:
            weights[k] *= (1 - micro_share)

    allocation = [{"symbol": k, "weight": round(v, 4)} for k, v in weights.items()]
    if micro_share > 0:
        w = round(micro_share / len(micro_pool), 4)
        allocation += [{"symbol": m, "weight": w} for m in micro_pool]

    return {"allocation": allocation}


# -----------------------------
# ТВОЙ /track — оставляем как был (для сравнения с бенчмарком)
# -----------------------------
@router.get("/track")
def track_portfolio(symbols: str, benchmark: str = "SPY", days: int = 365):
    tickers = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    end = datetime.utcnow()
    start = end - timedelta(days=days)

    data = yf.download(tickers + [benchmark], start=start.date(), end=end.date(), progress=False)["Adj Close"]
    data = data.fillna(method="ffill")
    rel = (data / data.iloc[0] - 1.0)

    return {
        "portfolio": {t: round(float(rel[t].iloc[-1]), 6) for t in tickers},
        "benchmark": {benchmark: round(float(rel[benchmark].iloc[-1]), 6)},
        "last_date": str(data.index[-1].date()),
    }
