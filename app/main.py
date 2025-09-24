import logging, sys
from fastapi import FastAPI
from pydantic import BaseModel
from typing import List

# ---------------- LOGGING ----------------
logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)
logging.debug("🚀 main.py started loading")

# ---------------- APP ----------------
app = FastAPI(title="AI Portfolio Bot", version="0.2")

# ---------------- SCHEMAS ----------------
class OnboardRequest(BaseModel):
    budget: float
    risk_level: str  # "low" | "medium" | "high"
    goals: List[str]

class PortfolioResponse(BaseModel):
    portfolio: dict
    message: str

# ---------------- ROUTES ----------------
@app.get("/ping", tags=["health"])
def ping():
    return {"message": "pong"}

@app.get("/health", tags=["health"])
def health():
    return {
        "status": "ok",
        "service": "ai-portfolio-bot",
        "db_ready": False,  # базы пока нет
        "db_error": None
    }

@app.get("/", tags=["health"])
def root():
    return {"ok": True, "service": "ai-portfolio-bot"}

# ----- Demo endpoint: Onboarding -----
@app.post("/onboard", response_model=PortfolioResponse, tags=["demo"])
def onboard(req: OnboardRequest):
    # Простая заглушка: подбираем портфель на основе risk_level
    if req.risk_level == "low":
        portfolio = {"ETF": "BND", "Stocks": "AAPL"}
    elif req.risk_level == "medium":
        portfolio = {"ETF": "VOO", "Stocks": "MSFT"}
    else:  # high
        portfolio = {"ETF": "QQQ", "Stocks": "TSLA"}

    return PortfolioResponse(
        portfolio=portfolio,
        message=f"Portfolio built for risk level {req.risk_level}"
    )
