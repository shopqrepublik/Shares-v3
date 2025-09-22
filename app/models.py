from __future__ import annotations
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Boolean
from sqlalchemy.orm import declarative_base, sessionmaker
import os

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./app.db")
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
Base = declarative_base()

# Логи сделок (опционально)
class TradeLog(Base):
    __tablename__ = "trades"
    id = Column(Integer, primary_key=True, autoincrement=True)
    ts = Column(DateTime, default=datetime.utcnow)
    ticker = Column(String, index=True)
    side = Column(String)  # BUY/SELL
    qty = Column(Float)
    price = Column(Float)
    order_id = Column(String, nullable=True)
    status = Column(String, default="preview")
    note = Column(String, nullable=True)

# Снимок позиций (для отчётов)
class PositionSnapshot(Base):
    __tablename__ = "positions_snapshots"
    id = Column(Integer, primary_key=True, autoincrement=True)
    ts = Column(DateTime, default=datetime.utcnow, index=True)
    ticker = Column(String, index=True)
    qty = Column(Float)
    avg_price = Column(Float)
    market_price = Column(Float)
    market_value = Column(Float)

# Метрики дня (для отчётов)
class MetricsDaily(Base):
    __tablename__ = "metrics_daily"
    id = Column(Integer, primary_key=True, autoincrement=True)
    ts = Column(DateTime, default=datetime.utcnow, index=True)
    equity = Column(Float)
    pnl_day = Column(Float)
    pnl_total = Column(Float)
    benchmark_value = Column(Float)
    note = Column(String, nullable=True)

# Настройки пользователя / онбординг
class UserPref(Base):
    __tablename__ = "user_prefs"
    id = Column(Integer, primary_key=True, autoincrement=True)
    budget = Column(Float, default=10000.0)
    goal = Column(String, default="growth")  # growth / income / balanced
    risk = Column(String, default="medium")  # low / medium / high
    horizon_years = Column(Integer, default=5)

# Текущий «построенный» портфель (симулятор)
class PortfolioHolding(Base):
    __tablename__ = "portfolio_holdings"
    id = Column(Integer, primary_key=True, autoincrement=True)
    ticker = Column(String, index=True)
    weight = Column(Float)            # доля в портфеле (0..1)
    qty = Column(Float, default=0.0)  # виртуальные акции
    last_price = Column(Float, default=0.0)
    updated_at = Column(DateTime, default=datetime.utcnow)

def init_db():
    Base.metadata.create_all(engine)
    return engine

