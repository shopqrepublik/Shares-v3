import logging, sys
from fastapi import FastAPI
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker
from io import BytesIO
from reportlab.pdfgen import canvas
import os

# ---------------- LOGGING ----------------
logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)
logging.debug("🚀 main.py started loading")

# ---------------- APP ----------------
app = FastAPI(title="AI Portfolio Bot", version="0.2")

# ---------------- DATABASE ----------------
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./app.db")
Base = declarative_base()

class TradeLog(Base):
    __tablename__ = "trade_logs"
    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String, index=True)
    action = Column(String)
    shares = Column(Integer)
    price = Column(Float)
    timestamp = Column(DateTime)

engine = None
SessionLocal = None
DB_READY = False
DB_INIT_ERR = None

try:
    engine = create_engine(DATABASE_URL, echo=False, future=True)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(engine)
    DB_READY = True
    logging.debug(f"✅ create_engine success, url={DATABASE_URL}")
except Exception as e:
    DB_INIT_ERR = str(e)
    logging.error(f"❌ create_engine failed: {DB_INIT_ERR}")

# ---------------- SCHEMAS ----------------
class OnboardRequest(BaseModel):
    budget: float
    risk_level: str
    goals: str

class PortfolioResponse(BaseModel):
    message: str
    portfolio: dict

# ---------------- ROUTES ----------------
@app.get("/ping", tags=["health"])
def ping():
    return {"message": "pong"}

@app.get("/health", tags=["health"])
def health():
    return {
        "status": "ok",
        "service": "ai-portfolio-bot",
        "db_ready": DB_READY,
        "db_error": DB_INIT_ERR[:200] if DB_INIT_ERR else None,
    }

@app.get("/", tags=["health"])
def root():
    return {"ok": True, "service": "ai-portfolio-bot"}

@app.post("/onboard", response_model=PortfolioResponse, tags=["portfolio"])
def onboard(req: OnboardRequest):
    sample_portfolios = {
        "low": {"AAPL": 0.3, "BND": 0.7},
        "medium": {"AAPL": 0.5, "TSLA": 0.3, "BND": 0.2},
        "high": {"TSLA": 0.6, "BTC": 0.4},
    }
    portfolio = sample_portfolios.get(req.risk_level.lower(), {})
    return PortfolioResponse(
        message=f"Portfolio created for {req.risk_level} risk",
        portfolio=portfolio
    )

# ---------------- REPORTS ----------------
@app.get("/report/json", tags=["reports"])
def get_report_json():
    sample_report = {
        "portfolio_value": 100000,
        "performance": "+12.5%",
        "holdings": [
            {"symbol": "AAPL", "shares": 10, "value": 1900},
            {"symbol": "TSLA", "shares": 5, "value": 1200},
        ]
    }
    return JSONResponse(content=sample_report)

@app.get("/report/pdf", tags=["reports"])
def get_report_pdf():
    buffer = BytesIO()
    p = canvas.Canvas(buffer)
    p.drawString(100, 800, "AI Portfolio Bot Report")
    p.drawString(100, 780, "Portfolio Value: $100,000")
    p.drawString(100, 760, "Performance: +12.5%")
    p.showPage()
    p.save()
    buffer.seek(0)

    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": "inline; filename=report.pdf"}
    )

    
