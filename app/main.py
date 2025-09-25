import logging
import sys
import os
from datetime import datetime
from typing import Optional, Any, List, Dict

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, declarative_base

# ---------------- LOGGING ----------------
logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)
logger = logging.getLogger(__name__)

# ---------------- FASTAPI ----------------
app = FastAPI(title="AI Portfolio Bot")

# CORS — фронт
origins = [
    "https://wealth-dashboard-ai.lovable.app",
    "http://localhost:3000",
    "http://localhost:5173",  # Vite dev-server
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],  # включает X-API-Key
)

# ---------------- DB ----------------
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./app.db")
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

try:
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    DB_READY = True
    DB_INIT_ERR = None
    logger.info("✅ DB initialized")
except Exception as e:
    DB_READY = False
    DB_INIT_ERR = str(e)
    logger.error(f"❌ DB init error: {e}")

# ---------------- AUTH ----------------
API_PASSWORD = os.getenv("API_PASSWORD", "AI_German")

def check_api_key(request: Request):
    key = request.headers.get("x-api-key")
    if key != API_PASSWORD:
        logger.warning(f"Unauthorized request: x-api-key={key}")
        raise HTTPException(status_code=401, detail="Unauthorized")

# ---------------- HELPERS ----------------
# Нормализатор любого «сырого» формата к контракту фронта
def normalize_to_front_contract(raw: Any) -> List[Dict[str, Any]]:
    # 1) достаём список
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
            items = list(raw.values())  # например {"AAPL": {...}}
    else:
        items = []

    # 2) маппим в {symbol, shares, price, timestamp}
    out: List[Dict[str, Any]] = []
    for h in items:
        symbol = (h.get("symbol") or h.get("ticker") or h.get("code") or "UNKNOWN")
        shares = h.get("shares", h.get("qty", 0)) or 0
        price  = h.get("price",  h.get("market_price", 0.0)) or 0.0
        ts     = h.get("timestamp") or h.get("ts") or datetime.utcnow().isoformat()
        out.append({
            "symbol": str(symbol),
            "shares": float(shares),
            "price": float(price),
            "timestamp": str(ts),
        })
    return out

# Простое хранилище текущего портфеля (в памяти)
CURRENT_HOLDINGS: List[Dict[str, Any]] = []

# ---------------- HEALTH ----------------
@app.get("/ping")
def ping():
    return {"message": "pong"}

@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "ai-portfolio-bot",
        "db_ready": DB_READY,
        "db_error": (DB_INIT_ERR[:500] if DB_INIT_ERR else None),
    }

# ---------------- ONBOARDING ----------------
@app.post("/onboard")
async def onboard(request: Request):
    check_api_key(request)
    data = await request.json()
    # принимаем и risk_level, и risk (обратная совместимость)
    budget = data.get("budget")
    risk = data.get("risk_level") or data.get("risk")
    goals = data.get("goals")
    logger.info(f"Onboarding received: {data}")
    return {"status": "ok", "saved": True, "data": {"budget": budget, "risk_level": risk, "goals": goals}}

# ---------------- PORTFOLIO ----------------
@app.get("/portfolio/holdings")
def portfolio_holdings(request: Request):
    """
    ВАЖНО: возвращаем строго контракт фронта:
      {"data":[{"symbol","shares","price","timestamp"}]}
    """
    check_api_key(request)

    # здесь может быть загрузка из БД, сейчас — примерные данные
    legacy_holdings = [
        {
            "ticker": "AAPL",
            "qty": 10,
            "avg_price": 150.0,
            "market_price": 155.0,
            "market_value": 1550.0,
            "ts": datetime.utcnow().isoformat()
        },
        {
            "ticker": "MSFT",
            "qty": 5,
            "avg_price": 300.0,
            "market_price": 305.0,
            "market_value": 1525.0,
            "ts": datetime.utcnow().isoformat()
        },
        {
            "ticker": "GOOG",
            "qty": 3,
            "avg_price": 140.0,
            "market_price": 142.5,
            "market_value": 427.5,
            "ts": datetime.utcnow().isoformat()
        }
    ]

    # нормализуем старый формат -> фронтовый контракт
    data = normalize_to_front_contract({"holdings": legacy_holdings})
    # сохраняем в «текущий портфель» (по желанию)
    global CURRENT_HOLDINGS
    CURRENT_HOLDINGS = data

    return {"data": data}
