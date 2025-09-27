import os
import json
import logging
import random
import yfinance as yf
import requests
import pandas as pd
from io import StringIO
from datetime import datetime, timedelta

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

# -------------------------
# Загрузка тикеров
# -------------------------
def load_wikipedia_tickers():
    tickers = []
    try:
        with open("app/data/sp500.json", "r") as f:
            tickers += json.load(f)
        with open("app/data/nasdaq100.json", "r") as f:
            tickers += json.load(f)
        logging.info(f"[Wikipedia] Загружено {len(tickers)} тикеров")
    except Exception as e:
        logging.error(f"[Wikipedia] Ошибка загрузки: {e}")
    return tickers

def fetch_finviz_tickers(filter_query: str):
    """
    Берём тикеры с Finviz screener
    Пример filter_query:
      - ETF: "ind_etf"
      - MicroCap: "cap_micro"
      - Growth: "fa_eps5years_pos,ta_perf_26wup"
    """
    url = f"https://finviz.com/screener.ashx?v=111&f={filter_query}"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        html = requests.get(url, headers=headers).text
        tables = pd.read_html(StringIO(html))
        if tables:
            df = tables[0]
            if "Ticker" in df.columns:
                tickers = df["Ticker"].tolist()
                logging.info(f"[Finviz] {filter_query} → {len(tickers)} тикеров")
                return tickers
    except Exception as e:
        logging.error(f"[Finviz] Ошибка {filter_query}: {e}")
    return []

# -------------------------
# Аналитика через yfinance
# -------------------------
def analyze_ticker(ticker):
    try:
        hist = yf.download(ticker, period="6mo", interval="1d", progress=False)
        if hist.empty:
            return None
        close_prices = hist["Close"]

        momentum = (close_prices.iloc[-1] / close_prices.iloc[0]) - 1
        score = round(momentum * 100, 2)

        if momentum > 0.1:
            pattern = "uptrend"
        elif momentum < -0.1:
            pattern = "downtrend"
        else:
            pattern = "sideways"

        return {
            "symbol": ticker,
            "price": float(close_prices.iloc[-1]),
            "score": score,
            "momentum": round(momentum, 3),
            "pattern": pattern,
        }
    except Exception as e:
        logging.warning(f"[yfinance] Ошибка для {ticker}: {e}")
        return None

# -------------------------
# AI-аннотация
# -------------------------
def annotate_with_ai(candidates, profile):
    if not OPENAI_API_KEY:
        logging.warning("OPENAI_API_KEY отсутствует, пропускаем аннотации")
        return candidates

    import httpx
    import json

    prompt = f"""
    У тебя есть список акций: {candidates}.
    Для каждой бумаги добавь:
    - reason: объяснение выбора
    - forecast: JSON с target_date (через 6 месяцев) и target_price
    Профиль инвестора: {profile}.
    Верни JSON {{"symbols":[...]}}
    """

    try:
        with httpx.Client(timeout=30) as client:
            resp = client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENAI_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "gpt-4o-mini",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.4,
                },
            )
            data = resp.json()
            raw = data["choices"][0]["message"]["content"]
            raw = raw.strip().replace("```json", "").replace("```", "")
            parsed = json.loads(raw)

            ai_map = {}
            if isinstance(parsed, dict) and "symbols" in parsed:
                for item in parsed["symbols"]:
                    ai_map[item.get("symbol")] = item

            enriched = []
            for c in candidates:
                sym = c.get("symbol")
                if sym in ai_map:
                    c["reason"] = ai_map[sym].get("reason", "")
                    c["forecast"] = ai_map[sym].get("forecast", {})
                enriched.append(c)

            return enriched
    except Exception as e:
        logging.error(f"[AI] Ошибка: {e}")
        return candidates

# -------------------------
# Построение портфеля
# -------------------------
def build_portfolio(profile):
    tickers = []

    # Wikipedia базовые тикеры
    tickers += load_wikipedia_tickers()

    # Finviz сегменты
    tickers += fetch_finviz_tickers("ind_etf")[:10]       # ETFs
    tickers += fetch_finviz_tickers("cap_micro")[:10]     # Micro-caps
    tickers += fetch_finviz_tickers("fa_eps5years_pos,ta_perf_26wup")[:10]  # Growth

    tickers = list(set(tickers))  # убираем дубли

    # Анализируем
    candidates = []
    for t in tickers[:50]:  # ограничим первыми 50 для скорости
        info = analyze_ticker(t)
        if info:
            candidates.append(info)

    # Сортировка по score
    candidates = sorted(candidates, key=lambda x: x["score"], reverse=True)

    # Берём топ-5
    top_candidates = candidates[:5]

    # Аннотации
    enriched = annotate_with_ai(top_candidates, profile)

    # Добавляем количество акций по бюджету
    budget = profile.get("budget", 1000)
    allocation = budget / len(enriched) if enriched else 0
    for c in enriched:
        price = c.get("price", 1)
        c["quantity"] = int(allocation // price)
        c["timestamp"] = datetime.utcnow().isoformat()

    logging.info(f"[Portfolio] Сформировано {len(enriched)} бумаг")
    return enriched
