from fastapi import APIRouter
from pydantic import BaseModel
import pandas as pd

router = APIRouter()

class PortfolioRequest(BaseModel):
    budget: float
    risk_profile: str
    micro_caps: bool = False

@router.post("/generate")
def generate_portfolio(req: PortfolioRequest):
    # Простая эвристика: ядро ETF + 0..20% micro-cap в зависимости от риска
    etf_core = ["SPY","QQQ","VXUS","IEF"]
    micro_pool = ["IBIT","SOXL","TQQQ","IWM","ARKK"]  # можно заменить на реальный список micro/small-cap
    weights = {"SPY":0.35,"QQQ":0.25,"VXUS":0.20,"IEF":0.20}

    micro_share = 0.0
    if req.micro_caps:
        micro_share = {"conservative":0.05,"balanced":0.10,"aggressive":0.20}.get(req.risk_profile,0.10)
        # скорректировать ядро пропорционально
        for k in weights:
            weights[k] *= (1 - micro_share)

    allocation = [{"symbol":k,"weight":round(v,4)} for k,v in weights.items()]
    if micro_share>0:
        # равные доли внутри micro_pool
        w = round(micro_share/len(micro_pool),4)
        allocation += [{"symbol":m,"weight":w} for m in micro_pool]

    # Расчёт лотов условный (без брокера): budget * weight / last_price
    return {"allocation": allocation}
import yfinance as yf
from datetime import datetime, timedelta

@router.get("/track")
def track_portfolio(symbols: str, benchmark: str = "SPY", days: int = 365):
    # symbols = "SPY,QQQ,..." (фактический портфель)
    tickers = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    end = datetime.utcnow()
    start = end - timedelta(days=days)

    data = yf.download(tickers + [benchmark], start=start.date(), end=end.date(), progress=False)["Adj Close"]
    data = data.fillna(method="ffill")
    rel = (data / data.iloc[0] - 1.0)  # доходность от старта

    return {
        "portfolio": {t: round(float(rel[t].iloc[-1]), 6) for t in tickers},
        "benchmark": {benchmark: round(float(rel[benchmark].iloc[-1]), 6)},
        "last_date": str(data.index[-1].date())
    }
