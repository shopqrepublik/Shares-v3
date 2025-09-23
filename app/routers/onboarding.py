from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter()

class Preferences(BaseModel):
    budget: float = Field(gt=0)
    goal: str
    risk_profile: str  # "conservative" | "balanced" | "aggressive"
    micro_caps: bool = False
    horizon_months: int = 12

@router.post("/collect", summary="Собрать предпочтения пользователя")
def collect_preferences(prefs: Preferences):
    # здесь можно сохранить в БД/сессию; пока вернём как есть
    return {"received": prefs}
