from fastapi import FastAPI
from fastapi.responses import JSONResponse, FileResponse
from app.models import init_db, SessionLocal, PositionSnapshot, MetricsDaily
from datetime import datetime
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

app = FastAPI(title="AI Portfolio Bot", version="0.4")

# инициализируем БД
init_db()


@app.get("/ping")
def ping():
    return {"message": "pong"}


@app.get("/positions")
def get_positions():
    """Возвращает список позиций"""
    db = SessionLocal()
    positions = db.query(PositionSnapshot).all()
    db.close()
    return [
        {
            "ticker": p.ticker,
            "qty": p.qty,
            "avg_price": p.avg_price,
            "market_price": p.market_price,
            "market_value": p.market_value,
            "ts": p.ts
        }
        for p in positions
    ]


@app.get("/report/daily")
def get_daily_report():
    """JSON-отчёт с equity и PnL"""
    db = SessionLocal()
    last = db.query(MetricsDaily).order_by(MetricsDaily.ts.desc()).first()
    positions = db.query(PositionSnapshot).all()
    db.close()

    if not last:
        return JSONResponse({"error": "No data"})

    return {
        "equity": last.equity,
        "pnl_day": last.pnl_day,
        "pnl_total": last.pnl_total,
        "benchmark_value": last.benchmark_value,
        "timestamp": last.ts,
        "positions": [
            {
                "ticker": p.ticker,
                "qty": p.qty,
                "avg_price": p.avg_price,
                "market_price": p.market_price,
                "market_value": p.market_value,
            }
            for p in positions
        ],
    }


@app.get("/report/pdf")
def get_pdf_report():
    """Генерирует PDF отчёт"""
    filename = "daily_report.pdf"
    db = SessionLocal()
    last = db.query(MetricsDaily).order_by(MetricsDaily.ts.desc()).first()
    positions = db.query(PositionSnapshot).all()
    db.close()

    c = canvas.Canvas(filename, pagesize=letter)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(100, 750, "AI Portfolio Bot — Daily Report")

    y = 700
    if last:
        c.setFont("Helvetica", 12)
        c.drawString(100, y, f"Equity: {last.equity}")
        y -= 20
        c.drawString(100, y, f"PnL Day: {last.pnl_day}")
        y -= 20
        c.drawString(100, y, f"PnL Total: {last.pnl_total}")
        y -= 20
        c.drawString(100, y, f"SPY Benchmark: {last.benchmark_value}")
        y -= 40

    c.setFont("Helvetica-Bold", 14)
    c.drawString(100, y, "Positions:")
    y -= 20

    for p in positions:
        c.setFont("Helvetica", 10)
        c.drawString(
            100,
            y,
            f"{p.ticker} | Qty: {p.qty} | Avg: {p.avg_price} | Market: {p.market_price} | Value: {p.market_value}",
        )
        y -= 15
        if y < 100:
            c.showPage()
            y = 700

    c.save()
    return FileResponse(filename, media_type="application/pdf", filename="daily_report.pdf")


@app.post("/seed")
def seed_data():
    """Создаёт тестовые данные в БД для отчётов"""
    db = SessionLocal()

    # Тестовые позиции
    db.add(PositionSnapshot(
        ts=datetime.utcnow(),
        ticker="AAPL",
        qty=10,
        avg_price=150.0,
        market_price=155.0,
        market_value=1550.0
    ))
    db.add(PositionSnapshot(
        ts=datetime.utcnow(),
        ticker="TSLA",
        qty=5,
        avg_price=700.0,
        market_price=710.0,
        market_value=3550.0
    ))

    # Тестовые метрики
    db.add(MetricsDaily(
        ts=datetime.utcnow(),
        equity=10000.0,
        pnl_day=200.0,
        pnl_total=1200.0,
        benchmark_value=400.0
    ))

    db.commit()
    db.close()
    return {"status": "seeded"}
