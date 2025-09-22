# app/guardrails.py

from typing import List
from pydantic import BaseModel

class RailConfig(BaseModel):
    max_position_size: float = 0.2      # максимум 20% в одну акцию
    max_leverage: float = 1.0           # без маржинального плеча
    max_drawdown: float = 0.3           # стоп при -30%
    allow_microcap: bool = False        # запрет на микро-капитализации

def rebalance_with_guardrails(proposals: List[dict], config: RailConfig):
    """Фильтруем ордера через guardrails перед реальной торговлей"""
    filtered = []
    for p in proposals:
        if p["weight"] > config.max_position_size:
            p["weight"] = config.max_position_size
        filtered.append(p)
    return filtered
