from fastapi import APIRouter
from pydantic import BaseModel
import os

router = APIRouter()

class ReportInput(BaseModel):
    allocation: list  # [{"symbol":"SPY","weight":0.35}, ...]
    perf_vs_benchmark: dict  # ответ из /portfolio/track
    forecast: dict  # ответ из /forecast/{symbol}
    goals: str
    risk_profile: str

@router.post("/generate")
def generate_report(data: ReportInput):
    # Заглушка: здесь можно позвать OpenAI API (или локальную LLM) и сгенерировать понятный отчёт + советы
    # Сейчас — простая структурированная рекомендация:
    tips = []
    if data.risk_profile == "aggressive":
        tips.append("У вас высокий риск-профиль: контролируйте долю микрокапов, ограничьте её 10–20% бюджета.")
    else:
        tips.append("Сбалансируйте портфель: ядро ETF + ограниченный риск в тематических позициях.")

    return {
        "summary": "Черновой отчёт по портфелю и прогнозу (демо).",
        "tips": tips,
        "next_steps": [
            "Настроить авт ребаланс раз в квартал",
            "Подключить paper-trading API (Alpaca) и симуляцию сделок",
        ]
    }
