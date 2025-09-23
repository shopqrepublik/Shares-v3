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
