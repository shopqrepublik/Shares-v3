from __future__ import annotations
from datetime import datetime
import yfinance as yf
from alpaca.trading.client import TradingClient
from .models import SessionLocal, TradeLog, PositionSnapshot, MetricsDaily
from sqlalchemy.orm import Session

def log_preview(trades: list[dict], side: str):
    db: Session = SessionLocal()
    try:
        for t in trades:
            db.add(TradeLog(ticker=t["ticker"], side=side.upper(), qty=t["qty"], price=t.get("price", 0.0), status="preview", note="guardrails preview"))
        db.commit()
    finally:
        db.close()

def log_placed(placed: list[dict], side: str):
    db: Session = SessionLocal()
    try:
        for p in placed:
            db.add(TradeLog(ticker=p["ticker"], side=side.upper(), qty=p["qty"], price=0.0, order_id=p.get("order_id"), status="placed"))
        db.commit()
    finally:
        db.close()

def snapshot_positions(trading: TradingClient):
    db: Session = SessionLocal()
    try:
        positions = trading.get_all_positions()
        for p in positions:
            db.add(PositionSnapshot(
                ticker=p.symbol,
                qty=float(p.qty),
                avg_price=float(p.avg_entry_price),
                market_price=float(p.current_price),
                market_value=float(p.market_value),
            ))
        db.commit()
    finally:
        db.close()

def log_daily_metrics(trading: TradingClient, benchmark_symbol: str = "SPY"):
    acct = trading.get_account()
    equity = float(acct.equity)
    pnl_day = float(acct.daytrading_buying_power) if hasattr(acct, "daytrading_buying_power") else 0.0
    # Benchmark close (naive last close)
    bm = yf.Ticker(benchmark_symbol).history(period="1mo")["Close"]
    bm_val = float(bm.iloc[-1]) if not bm.empty else 0.0

    db: Session = SessionLocal()
    try:
        db.add(MetricsDaily(equity=equity, pnl_day=0.0, pnl_total=0.0, benchmark_value=bm_val, note="daily snapshot"))
        db.commit()
    finally:
        db.close()
