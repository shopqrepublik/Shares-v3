from __future__ import annotations
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker
from datetime import datetime
import os

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./app.db")
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {})
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
Base = declarative_base()

class TradeLog(Base):
    __tablename__ = "trades"
    id = Column(Integer, primary_key=True, autoincrement=True)
    ts = Column(DateTime, default=datetime.utcnow)
    ticker = Column(String, index=True)
    side = Column(String)  # BUY/SELL
    qty = Column(Float)
    price = Column(Float)
    order_id = Column(String, nullable=True)
    status = Column(String, default="preview")  # preview/placed
    note = Column(String, nullable=True)

class PositionSnapshot(Base):
    __tablename__ = "positions_snapshots"
    id = Column(Integer, primary_key=True, autoincrement=True)
    ts = Column(DateTime, default=datetime.utcnow, index=True)
    ticker = Column(String, index=True)
    qty = Column(Float)
    avg_price = Column(Float)
    market_price = Column(Float)
    market_value = Column(Float)

class MetricsDaily(Base):
    __tablename__ = "metrics_daily"
    id = Column(Integer, primary_key=True, autoincrement=True)
    ts = Column(DateTime, default=datetime.utcnow, index=True)
    equity = Column(Float)
    pnl_day = Column(Float)
    pnl_total = Column(Float)
    benchmark_value = Column(Float)
    note = Column(String, nullable=True)

def init_db():
    Base.metadata.create_all(engine)
    return engine
