from fastapi import APIRouter, Depends, Header, HTTPException
from typing import Optional
from .build_portfolio import build_portfolio

router = APIRouter()

API_KEY = "..."  # возьми из os.getenv("API_KEY")

def require_key(x_api_key: Optional[str] = Header(None)):
    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")

@router.post("/portfolio/build", dependencies=[Depends(require_key)])
def build(limit: int = 100):
    """
    Формирует портфель:
      – пробует yfinance, если нет – Finnhub
      – сохраняет в portfolio_holdings
      – возвращает статистику по провайдерам
    """
    result = build_portfolio(limit=limit)
    return result

@router.get("/portfolio/holdings", dependencies=[Depends(require_key)])
def holdings():
    from .build_portfolio import get_pg_connection
    import psycopg2.extras
    conn = get_pg_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM portfolio_holdings ORDER BY updated_at DESC LIMIT 50;")
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return {"holdings": rows}
