import os
import json
import random
import yfinance as yf
import time
import logging
import openai
from types import SimpleNamespace

# Настройка логов
logging.basicConfig(level=logging.INFO)

# OpenAI
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
if OPENAI_API_KEY:
    openai.api_key = OPENAI_API_KEY

# Папка с тикерами
DATA_DIR = "app/data"

# -------------------------
# Нормализация тикеров
# -------------------------
def normalize_ticker(ticker: str) -> str:
    """Приводим тикер к формату Yahoo Finance"""
    if "." in ticker:
        ticker = ticker.replace(".", "-")
    return ticker.strip().upper()

# -------------------------
# Безопасная загрузка yfinance
# -------------------------
def safe_download(ticker, period="6mo", interval="1d", retries=3, delay=1):
    for attempt in range(retries):
        try:
            data = yf.download(ticker, period=period, interval=interval, progress=False)
            if not data.empty:
                logging.info(f"[YF] {ticker} ✅ {len(data)} bars")
                return data
        except Exception as e:
            logging.warning(f"[YF] {ticker} ❌ попытка {attempt+1}: {e}")
            time.sleep(delay)
    logging.error(f"[YF] {ticker} пропущен (нет данных)")
    return None

# -------------------------
# Загрузка тикеров
# -------------------------
def load_tickers():
    tickers = []
    try:
        with open(os.path.join(DATA_DIR, "sp500.json"), "r") as f:
            tickers += json.load(f)
        with open(os.path.join(DATA_DIR, "nasdaq100.json"), "r") as f:
            tickers += json.load(f)
    except Exception as e:
        logging.error(f"[TICKERS] Ошибка загрузки JSON: {e}")

    tickers = [normalize_ticker(t) for t in tickers]
    return list(set(tickers))

# -------------------------
# Метрики
# -------------------------
def compute_metrics(hist):
    if hist is None or hist.empty:
        return None
    try:
        momentum = (hist["Close"][-1] - hist["Close"][0]) / hist["Close"][0]
        score = momentum * 100
        pattern = "uptrend" if momentum > 0 else "downtrend"
        return {"score": score, "momentum": momentum, "pattern": pattern}
    except Exception as e:
        logging.warning(f"[METRICS] ошибка: {e}")
        return None

# -------------------------
# AI-аннотация
# -------------------------
def ai_annotate(ticker, metrics):
    if not OPENAI_API_KEY:
        return {"reason": "AI off (no key)", "forecast": "n/a"}
    try:
        prompt = f"""
        Analyze stock {ticker}.
        Momentum: {metrics['momentum']:.2%}
        Trend: {metrics['pattern']}
        Score: {metrics['score']:.2f}

        Give a 1-sentence reason why it might grow.
        Predict price direction in 6 months (up/down).
        """
        resp = openai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.6
        )
        text = resp.choices[0].message.content.strip()
        parts = text.split("\n")
        reason = parts[0] if len(parts) > 0 else text
        forecast = parts[1] if len(parts) > 1 else "No forecast"
        return {"reason": reason, "forecast": forecast}
    except Exception as e:
        logging.error(f"[AI] {ticker} error: {e}")
        return {"reason": "AI failed", "forecast": "n/a"}

# -------------------------
# Построение портфеля
# -------------------------
def build_portfolio(profile):
    # Поддержка dict и SimpleNamespace
    if isinstance(profile, SimpleNamespace):
        profile = vars(profile)

    if not isinstance(profile, dict):
        raise ValueError("profile должен быть dict или SimpleNamespace")

    budget = profile.get("budget", 1000)
    risk_level = profile.get("risk_level", "medium")
    goals = profile.get("goals", "grow")

    tickers = load_tickers()
    portfolio = []
    skipped = []

    for ticker in random.sample(tickers, min(30, len(tickers))):
        hist = safe_download(ticker)
        if hist is None:
            skipped.append(ticker)
            continue
        metrics = compute_metrics(hist)
        if not metrics:
            skipped.append(ticker)
            continue
        annotations = ai_annotate(ticker, metrics)
        last_price = hist["Close"][-1]
        qty = max(1, int(budget * 0.05 // last_price))
        portfolio.append({
            "ticker": ticker,
            "price": float(last_price),
            "qty": qty,
            "score": metrics["score"],
            "momentum": metrics["momentum"],
            "pattern": metrics["pattern"],
            "reason": annotations["reason"],
            "forecast": annotations["forecast"],
        })

    portfolio = sorted(portfolio, key=lambda x: x["score"], reverse=True)[:5]
    logging.info(f"[PORTFOLIO] готово: {len(portfolio)} акций, пропущено {len(skipped)}")
    return {"portfolio": portfolio, "skipped": skipped}
