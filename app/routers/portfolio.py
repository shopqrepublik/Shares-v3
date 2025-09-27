import os
import logging
import json
from datetime import datetime
from types import SimpleNamespace

import yfinance as yf
from openai import OpenAI

# -------------------------
# Настройки
# -------------------------
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
client = OpenAI(api_key=OPENAI_API_KEY)

# S&P500 + NASDAQ100 (сокращённый список, можно расширить)
SP500_TICKERS = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "META",
    "TSLA", "NVDA", "BRK-B", "JPM", "JNJ",
    "V", "PG", "UNH", "HD", "XOM"
]

NASDAQ100_TICKERS = [
    "AAPL", "MSFT", "AMZN", "META", "GOOGL",
    "TSLA", "NVDA", "PEP", "ADBE", "NFLX"
]

# -------------------------
# Метрики
# -------------------------
def analyze_stock(ticker: str, period="6mo") -> dict:
    try:
        df = yf.download(ticker, period=period, interval="1d", progress=False)
        if df.empty:
            return None

        first_price = df["Close"].iloc[0]
        last_price = df["Close"].iloc[-1]

        momentum = (last_price - first_price) / first_price
        score = round(momentum * 100, 2)

        if momentum > 0.1:
            pattern = "uptrend"
        elif momentum < -0.1:
            pattern = "downtrend"
        else:
            pattern = "sideways"

        return {
            "symbol": ticker,
            "price": float(last_price),
            "score": score,
            "momentum": round(momentum, 3),
            "pattern": pattern
        }
    except Exception as e:
        logging.error(f"Ошибка анализа {ticker}: {e}")
        return None

# -------------------------
# OpenAI аннотация
# -------------------------
def annotate_with_ai(candidates, profile):
    if not OPENAI_API_KEY:
        logging.warning("Нет OPENAI_API_KEY — вернём без аннотаций")
        return candidates

    prompt = f"""
Ты — инвестиционный аналитик. У тебя есть портфель кандидатов {json.dumps(candidates)}.
Для каждого тикера добавь:
- reason: краткое объяснение (1–2 предложения), почему акция выбрана
- forecast: JSON с target_date (через 6 месяцев) и target_price (разумный прогноз)

Профиль инвестора: {profile}.
Верни JSON вида:
{{"symbols":[{{"symbol":"AAPL","reason":"...","forecast":{{"target_date":"2025-12-01","price":200}}}}]}}
    """

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3
        )

        raw = response.choices[0].message.content.strip()
        raw = raw.replace("```json", "").replace("```", "")

        parsed = json.loads(raw)
        ai_map = {}
        for item in parsed.get("symbols", []):
            ai_map[item["symbol"]] = item

        enriched = []
        for c in candidates:
            if c["symbol"] in ai_map:
                c["reason"] = ai_map[c["symbol"]].get("reason", "")
                c["forecast"] = ai_map[c["symbol"]].get("forecast", {})
            enriched.append(c)

        return enriched
    except Exception as e:
        logging.error(f"AI аннотация сломалась: {e}")
        return candidates

# -------------------------
# Построение портфеля
# -------------------------
def build_portfolio(profile: SimpleNamespace):
    tickers = list(set(SP500_TICKERS + NASDAQ100_TICKERS))
    results = []

    logging.info(f"Анализируем {len(tickers)} тикеров...")

    for t in tickers:
        data = analyze_stock(t)
        if data:
            results.append(data)

    if not results:
        logging.warning("Нет данных для анализа!")
        return []

    # сортируем по score
    results.sort(key=lambda x: x["score"], reverse=True)

    # топ-5
    top5 = results[:5]

    # добавляем AI-аннотацию
    enriched = annotate_with_ai(top5, profile)

    # timestamp
    for c in enriched:
        c["timestamp"] = datetime.utcnow().isoformat()

    return enriched
