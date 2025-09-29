import yfinance as yf
import pandas as pd
from fastapi import APIRouter, Request
from datetime import datetime, timedelta
import psycopg2
import os

router = APIRouter()

def get_pg_connection():
    dsn = os.environ.get("DATABASE_URL")
    if dsn and "postgresql+psycopg2://" in dsn:
        dsn = dsn.replace("postgresql+psycopg2://", "postgresql://")
    return psycopg2.connect(dsn)

def get_tickers_from_db(limit=200):
    conn = get_pg_connection()
    cur = conn.cursor()
    cur.execute("SELECT symbol FROM tickers WHERE index_name='SP500' LIMIT %s;", (limit,))
    rows = cur.fetchall()
    conn.close()
    return [r[0] for r in rows]

def fetch_yfinance_data(tickers, months=12):
    end = datetime.today()
    start = end - timedelta(days=365*3)
    df = yf.download(tickers, start=start, end=end, group_by="ticker", auto_adjust=True, progress=False)
    return df

# ===== Фильтры =====
def filter_by_goal(df, goal):
    if goal == "Grow portfolio":
        # Фильтруем по росту цены (6м доходность)
        scores = {}
        for t in df.columns.levels[0]:
            try:
                px = df[t]["Close"]
                ret6m = px.iloc[-1] / px.iloc[-126] - 1  # ~126 торговых дней = 6 мес
                scores[t] = ret6m
            except:
                scores[t] = -999
        return pd.DataFrame(scores.items(), columns=["symbol", "score"])
    elif goal == "Preserve capital":
        # Ставим приоритет на низкую волатильность
        scores = {}
        for t in df.columns.levels[0]:
            try:
                px = df[t]["Close"]
                vol = px.pct_change().std()
                scores[t] = -vol  # чем меньше вола, тем лучше
            except:
                scores[t] = -999
        return pd.DataFrame(scores.items(), columns=["symbol", "score"])
    elif goal == "Generate income":
        # Дивиденды (через yfinance info)
        scores = {}
        for t in df.columns.levels[0]:
            try:
                yld = yf.Ticker(t).info.get("dividendYield", 0) or 0
                scores[t] = yld
            except:
                scores[t] = 0
        return pd.DataFrame(scores.items(), columns=["symbol", "score"])
    return pd.DataFrame(columns=["symbol", "score"])

def filter_by_risk(df, risk, scores):
    if risk == "Conservative":
        scores["score"] = scores["score"] * 0.8
    elif risk == "Balanced":
        scores["score"] = scores["score"] * 1.0
    elif risk == "Aggressive":
        scores["score"] = scores["score"] * 1.2
    return scores

def adjust_by_horizon(scores, horizon):
    if horizon == "3 months":
        scores["score"] = scores["score"] * 1.1
    elif horizon == "6 months":
        scores["score"] = scores["score"] * 1.0
    elif horizon == "1 year":
        scores["score"] = scores["score"] * 1.2
    return scores

def adjust_by_knowledge(scores, knowledge):
    if knowledge == "Beginner":
        # убираем экзотические тикеры (по длине >4)
        scores = scores[scores["symbol"].str.len() <= 4]
    elif knowledge == "Advanced":
        pass  # оставляем всё
    elif knowledge == "Expert":
        # можно добавить рискованных → усиливаем score
        scores["score"] = scores["score"] * 1.1
    return scores

def save_portfolio(symbols):
    conn = get_pg_connection()
    cur = conn.cursor()
    cur.execute("TRUNCATE TABLE portfolio_holdings RESTART IDENTITY;")
    for sym in symbols:
        cur.execute(
            "INSERT INTO portfolio_holdings (symbol, created_at) VALUES (%s, NOW());",
            (sym,)
        )
    conn.commit()
    conn.close()

@router.post("/build_portfolio")
async def build_portfolio(request: Request):
    params = await request.json()
    goal = params.get("goal")
    risk = params.get("risk")
    horizon = params.get("horizon")
    knowledge = params.get("knowledge")

    # 1. Тикеры
    tickers = get_tickers_from_db(limit=50)

    # 2. Данные
    df = fetch_yfinance_data(tickers)

    # 3. Фильтры
    scores = filter_by_goal(df, goal)
    scores = filter_by_risk(df, risk, scores)
    scores = adjust_by_horizon(scores, horizon)
    scores = adjust_by_knowledge(scores, knowledge)

    # 4. Выбираем топ-5
    top5 = scores.sort_values("score", ascending=False).head(5)
    save_portfolio(top5["symbol"].tolist())

    return {"status": "ok", "portfolio": top5.to_dict(orient="records")}
